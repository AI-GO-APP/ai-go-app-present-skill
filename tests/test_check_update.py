"""
scripts/check_update.py 的單元測試（標準函式庫 unittest，零相依）。

執行：python -m unittest discover -s tests -v

全部在暫存目錄裡跑：狀態檔、安裝目錄都是假的，網路一律 mock 掉——
不會碰到真正的 skill 安裝、~/.aigo/ 或 GitHub。
"""

from __future__ import annotations
import contextlib
import importlib.util
import io
import json
import shutil
import subprocess
import tempfile
import time
import unittest
import zipfile
from pathlib import Path
from unittest import mock

SCRIPT = Path(__file__).resolve().parent.parent / "scripts" / "check_update.py"
_spec = importlib.util.spec_from_file_location("check_update", SCRIPT)
cu = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(cu)

TOP = "ai-go-app-present-skill-main"


def make_zip(files: dict[str, str], top: str | None = TOP) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        if top:
            zf.writestr(f"{top}/", "")
        for rel, content in files.items():
            zf.writestr(f"{top}/{rel}" if top else rel, content)
    return buf.getvalue()


def pkg_json(version: str, deps: dict | None = None) -> str:
    return json.dumps({"name": "x", "version": version, "dependencies": deps or {"puppeteer-core": "^25.6.0"}})


def lock_json(version: str, pkgs: dict | None = None) -> str:
    packages = {"": {"name": "x", "version": version, "dependencies": {"puppeteer-core": "^25.6.0"}}}
    packages.update(pkgs or {"node_modules/puppeteer-core": {"version": "25.6.0"}})
    return json.dumps({"name": "x", "version": version, "lockfileVersion": 3, "packages": packages})


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="cu-test-"))
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        patches = [
            mock.patch.object(cu, "STATE_FILE", self.tmp / "state.json"),
            mock.patch.object(cu, "THROTTLE_SECONDS", 3 * 60 * 60),
            # 預設斷網：個別測試再覆寫
            mock.patch.object(cu, "_fetch_bytes", return_value=None),
        ]
        for p in patches:
            p.start()
            self.addCleanup(p.stop)

    def install(self, name: str, version: str, files: dict[str, str] | None = None) -> Path:
        d = self.tmp / name
        d.mkdir(parents=True)
        (d / "VERSION").write_text(version + "\n", encoding="utf-8")
        for rel, content in (files or {}).items():
            (d / rel).parent.mkdir(parents=True, exist_ok=True)
            (d / rel).write_text(content, encoding="utf-8")
        return d

    def remote(self, version: str, archive: bytes | None = None, changelog: str | None = None):
        """模擬遠端：VERSION、CHANGELOG、main.zip。"""

        def fake(url, timeout):
            if url == cu.REMOTE_VERSION_URL:
                return (version + "\n").encode()
            if url == cu.REMOTE_CHANGELOG_URL and changelog is not None:
                return changelog.encode()
            if url == cu.REMOTE_ARCHIVE_URL and archive is not None:
                return archive
            return None

        cu._fetch_bytes.side_effect = fake


class VersionTests(Base):
    def test_semver_ordering(self):
        self.assertTrue(cu._is_newer("0.3.0", "0.2.0"))
        self.assertTrue(cu._is_newer("0.10.0", "0.9.0"))  # 不是字串比較
        self.assertTrue(cu._is_newer("1.2.0", "1.2.0-rc1"))  # pre-release 排前
        self.assertFalse(cu._is_newer("0.2.0", "0.2.0"))
        self.assertFalse(cu._is_newer("0.2.0", "0.3.0"))

    def test_read_version_tolerates_bom_and_blank(self):
        d = self.tmp / "bom"
        d.mkdir()
        (d / "VERSION").write_bytes("﻿0.3.0\r\n".encode("utf-8"))
        self.assertEqual(cu._read_version_at(d), "0.3.0")
        (d / "VERSION").write_text("  \n", encoding="utf-8")
        self.assertIsNone(cu._read_version_at(d))
        self.assertIsNone(cu._read_version_at(self.tmp / "missing"))


class RemoteCacheTests(Base):
    def test_fresh_cache_skips_network(self):
        state = {"remote_cache": {"version": "0.3.0", "fetched_at": time.time()}}
        self.remote("0.9.0")
        self.assertEqual(cu._resolve_remote(state, force=False), "0.3.0")
        cu._fetch_bytes.assert_not_called()

    def test_stale_cache_refetches(self):
        state = {"remote_cache": {"version": "0.3.0", "fetched_at": time.time() - 4 * 3600}}
        self.remote("0.4.0")
        self.assertEqual(cu._resolve_remote(state, force=False), "0.4.0")
        self.assertEqual(state["remote_cache"]["version"], "0.4.0")

    def test_force_bypasses_fresh_cache(self):
        state = {"remote_cache": {"version": "0.3.0", "fetched_at": time.time()}}
        self.remote("0.4.0")
        self.assertEqual(cu._resolve_remote(state, force=True), "0.4.0")

    def test_offline_falls_back_to_stale_cache(self):
        state = {"remote_cache": {"version": "0.3.0", "fetched_at": 0}}
        self.assertEqual(cu._resolve_remote(state, force=False), "0.3.0")
        self.assertIsNone(cu._resolve_remote({}, force=False))

    def test_recently_failed_only_for_same_remote_within_window(self):
        state = {"installs": {"/a": {"last_sync": {"remote": "0.3.0", "ok": False, "at": time.time()}}}}
        self.assertTrue(cu._recently_failed(state, "/a", "0.3.0"))
        self.assertFalse(cu._recently_failed(state, "/a", "0.4.0"))
        state["installs"]["/a"]["last_sync"]["at"] = time.time() - 4 * 3600
        self.assertFalse(cu._recently_failed(state, "/a", "0.3.0"))
        state["installs"]["/a"]["last_sync"] = {"remote": "0.3.0", "ok": True, "at": time.time()}
        self.assertFalse(cu._recently_failed(state, "/a", "0.3.0"))


class RegistryTests(Base):
    def test_register_self_and_prune_missing(self):
        me = self.install("me", "0.2.0")
        state = {"installs": {str(self.tmp / "gone"): {"local": "0.1.0"}}}
        with mock.patch.object(cu, "SKILL_DIR", me):
            cu._register_install(state, "0.2.0")
        self.assertEqual(list(state["installs"]), [str(me)])
        self.assertEqual(state["installs"][str(me)]["local"], "0.2.0")


class DevCheckoutTests(Base):
    def test_local_newer_is_dev(self):
        d = self.install("a", "0.4.0")
        self.assertIn("高於遠端", cu._dev_checkout_reason(d, "0.4.0", "0.3.0"))

    def test_copy_install_same_or_older_is_not_dev(self):
        d = self.install("a", "0.2.0")
        self.assertIsNone(cu._dev_checkout_reason(d, "0.2.0", "0.3.0"))

    @unittest.skipUnless(shutil.which("git"), "需要 git")
    def test_git_branch_decides(self):
        d = self.install("g", "0.2.0")
        subprocess.run(["git", "-C", str(d), "init", "-q"], check=True)
        subprocess.run(["git", "-C", str(d), "symbolic-ref", "HEAD", "refs/heads/feat/x"], check=True)
        self.assertIn("feat/x", cu._dev_checkout_reason(d, "0.2.0", "0.3.0"))
        subprocess.run(["git", "-C", str(d), "symbolic-ref", "HEAD", "refs/heads/main"], check=True)
        self.assertIsNone(cu._dev_checkout_reason(d, "0.2.0", "0.3.0"))


class ArchiveMirrorTests(Base):
    def test_archive_strips_top_dir_and_preserved_names(self):
        data = make_zip({"VERSION": "0.3.0", "scripts/a.py": "x", "node_modules/p/i.js": "y", ".git/HEAD": "z"})
        self.assertEqual(sorted(cu._archive_entries(data)), ["VERSION", "scripts/a.py"])

    def test_archive_rejects_bad_input(self):
        self.assertIsNone(cu._archive_entries(b"not a zip"))
        self.assertIsNone(cu._archive_entries(make_zip({"VERSION": "0.3.0"}, top=None)))

    def test_mirror_writes_deletes_extras_and_keeps_preserved(self):
        d = self.install(
            "m",
            "0.2.0",
            {
                "scripts/old.py": "stale",
                "scripts/keep.py": "old",
                "gone/deep/file.txt": "x",
                "node_modules/p/index.js": "dep",
                ".env": "SECRET=1",
                ".aigo/token.json": "{}",
            },
        )
        n = cu._mirror_into(d, {"VERSION": b"0.3.0\n", "scripts/keep.py": b"new", "scripts/new.py": b"n"})
        self.assertEqual(n, 3)
        self.assertEqual((d / "VERSION").read_text(), "0.3.0\n")
        self.assertEqual((d / "scripts/keep.py").read_text(), "new")
        self.assertTrue((d / "scripts/new.py").exists())
        self.assertFalse((d / "scripts/old.py").exists())
        self.assertFalse((d / "gone").exists())  # 刪空的目錄一併清掉
        self.assertTrue((d / "node_modules/p/index.js").exists())
        self.assertTrue((d / ".env").exists())
        self.assertTrue((d / ".aigo/token.json").exists())


class DepsFingerprintTests(Base):
    def test_version_bump_alone_does_not_change_fingerprint(self):
        a = self.install("a", "0.2.0", {"package.json": pkg_json("0.2.0"), "package-lock.json": lock_json("0.2.0")})
        b = self.install("b", "0.3.0", {"package.json": pkg_json("0.3.0"), "package-lock.json": lock_json("0.3.0")})
        self.assertEqual(cu._deps_fingerprint(a), cu._deps_fingerprint(b))

    def test_dependency_change_changes_fingerprint(self):
        a = self.install("a", "0.2.0", {"package.json": pkg_json("0.2.0"), "package-lock.json": lock_json("0.2.0")})
        b = self.install(
            "b",
            "0.3.0",
            {
                "package.json": pkg_json("0.3.0"),
                "package-lock.json": lock_json("0.3.0", {"node_modules/puppeteer-core": {"version": "26.0.0"}}),
            },
        )
        c = self.install("c", "0.3.0", {"package.json": pkg_json("0.3.0", {"sharp": "^0.33.0"})})
        self.assertNotEqual(cu._deps_fingerprint(a), cu._deps_fingerprint(b))
        self.assertNotEqual(cu._deps_fingerprint(a), cu._deps_fingerprint(c))


class SyncAllTests(Base):
    def remote_tree(self, version: str, lock_pkgs: dict | None = None) -> bytes:
        return make_zip(
            {
                "VERSION": version + "\n",
                "SKILL.md": "new",
                "package.json": pkg_json(version),
                "package-lock.json": lock_json(version, lock_pkgs),
            }
        )

    def local_files(self, version: str) -> dict[str, str]:
        return {
            "SKILL.md": "old",
            "stray.txt": "x",
            "package.json": pkg_json(version),
            "package-lock.json": lock_json(version),
        }

    def test_copy_install_synced_without_deps_change(self):
        d = self.install("copy", "0.2.0", self.local_files("0.2.0"))
        self.remote("0.3.0", archive=self.remote_tree("0.3.0"))
        state = {"installs": {str(d): {}}}
        [r] = cu._sync_all(state, "0.3.0", force=False)
        self.assertEqual(r["action"], "synced")
        self.assertFalse(r["deps_changed"])
        self.assertEqual(cu._read_version_at(d), "0.3.0")
        self.assertEqual((d / "SKILL.md").read_text(), "new")
        self.assertFalse((d / "stray.txt").exists())
        self.assertTrue(state["installs"][str(d)]["last_sync"]["ok"])

    def test_deps_change_is_reported(self):
        d = self.install("copy", "0.2.0", self.local_files("0.2.0"))
        tree = self.remote_tree("0.3.0", {"node_modules/puppeteer-core": {"version": "26.0.0"}})
        self.remote("0.3.0", archive=tree)
        [r] = cu._sync_all({"installs": {str(d): {}}}, "0.3.0", force=False)
        self.assertTrue(r["deps_changed"])

    def test_failure_recorded_then_throttled(self):
        d = self.install("copy", "0.2.0")
        self.remote("0.3.0", archive=None)  # 下載失敗
        state = {"installs": {str(d): {}}}
        [r] = cu._sync_all(state, "0.3.0", force=False)
        self.assertEqual(r["action"], "failed")
        [r] = cu._sync_all(state, "0.3.0", force=False)
        self.assertEqual(r["action"], "throttled")
        [r] = cu._sync_all(state, "0.3.0", force=True)  # --force 無視抑制
        self.assertEqual(r["action"], "failed")

    def test_up_to_date_dev_and_missing_installs(self):
        cur = self.install("cur", "0.3.0")
        dev = self.install("dev", "0.4.0")
        state = {"installs": {str(cur): {}, str(dev): {}, str(self.tmp / "none"): {}}}
        actions = {Path(r["path"]).name: r["action"] for r in cu._sync_all(state, "0.3.0", False)}
        self.assertEqual(actions, {"cur": "up-to-date", "dev": "dev-skip"})


class ChangelogTests(Base):
    CHANGELOG = "# Changelog\n\n## 0.10.3 — x\n- 不該選到\n\n## 0.3.0 — 2026-09-28\n- **破壞性**：A\n- B\n\n## 0.2.0\n- C\n"

    def test_excerpt_matches_exact_heading(self):
        self.remote("0.3.0", changelog=self.CHANGELOG)
        text = cu._changelog_excerpt("0.3.0")
        self.assertTrue(text.startswith("## 0.3.0"))
        self.assertIn("B", text)
        self.assertNotIn("C", text)
        self.assertNotIn("不該選到", text)

    def test_excerpt_missing_section(self):
        self.remote("0.9.0", changelog=self.CHANGELOG)
        self.assertIsNone(cu._changelog_excerpt("0.9.0"))


class MainOutputTests(Base):
    def run_main(self, skill_dir: Path, *argv: str) -> str:
        out = io.StringIO()
        with mock.patch.object(cu, "SKILL_DIR", skill_dir), contextlib.redirect_stdout(out):
            self.assertEqual(cu.main(list(argv)), 0)
        return out.getvalue()

    def test_silent_when_current(self):
        d = self.install("me", "0.3.0")
        self.remote("0.3.0")
        self.assertEqual(self.run_main(d), "")

    def test_silent_when_offline(self):
        d = self.install("me", "0.2.0")
        self.assertEqual(self.run_main(d), "")

    def test_silent_for_dev_copy_alone(self):
        d = self.install("me", "0.4.0")
        self.remote("0.3.0")
        self.assertEqual(self.run_main(d), "")

    def test_check_only_reports_without_syncing(self):
        d = self.install("me", "0.2.0")
        self.remote("0.3.0")
        out = self.run_main(d, "--check-only")
        self.assertIn("--check-only，未同步", out)
        self.assertEqual(cu._read_version_at(d), "0.2.0")

    def test_sync_output_with_changelog_and_deps(self):
        d = self.install(
            "me", "0.2.0", {"package.json": pkg_json("0.2.0"), "package-lock.json": lock_json("0.2.0")}
        )
        tree = make_zip(
            {
                "VERSION": "0.3.0\n",
                "package.json": pkg_json("0.3.0", {"puppeteer-core": "^26.0.0"}),
                "package-lock.json": lock_json("0.3.0"),
            }
        )
        self.remote("0.3.0", archive=tree, changelog=ChangelogTests.CHANGELOG)
        out = self.run_main(d)
        self.assertIn("[已同步]", out)
        self.assertIn("npm install", out)
        self.assertIn("變更摘要", out)
        self.assertIn("重新讀取 SKILL.md", out)
        self.assertEqual(cu._read_version_at(d), "0.3.0")

    def test_failed_sync_prints_manual_command_and_breaking_warning(self):
        d = self.install("me", "0.2.0")
        self.remote("0.3.0", archive=None, changelog=ChangelogTests.CHANGELOG)
        out = self.run_main(d)
        self.assertIn("[失敗]", out)
        self.assertIn("check_update.py", out)
        self.assertIn("破壞性變更", out)

    def test_json_output(self):
        d = self.install("me", "0.3.0")
        self.remote("0.3.0")
        data = json.loads(self.run_main(d, "--json"))
        self.assertEqual(data["status"], "current")
        self.assertEqual(data["sync_results"][0]["action"], "up-to-date")


if __name__ == "__main__":
    unittest.main()
