"""scripts/doctor.py：npm 套件是否裝好／過期、ffmpeg 尋找順序、必要項目決定結束碼。"""
from __future__ import annotations

import importlib.util
import json
import os
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock

SCRIPTS = Path(__file__).resolve().parent.parent / "scripts"
spec = importlib.util.spec_from_file_location("doctor", SCRIPTS / "doctor.py")
doc = importlib.util.module_from_spec(spec)
spec.loader.exec_module(doc)


def _lock(pkgs: dict) -> str:
    return json.dumps({"packages": {"": {"name": "x"}, **{f"node_modules/{k}": v for k, v in pkgs.items()}}})


WANT = {"puppeteer-core": {"version": "25.0.0"}, "ffmpeg-static": {"version": "5.2.0"},
        "@img/sharp-darwin-arm64": {"version": "1.0.0", "optional": True}}


def _skill(tmp: Path, installed: bool) -> Path:
    (tmp / "package.json").write_text(json.dumps({"dependencies": {"puppeteer-core": "^25"}}), encoding="utf-8")
    (tmp / "package-lock.json").write_text(_lock(WANT), encoding="utf-8")
    if installed:
        d = tmp / "node_modules" / "puppeteer-core"
        d.mkdir(parents=True)
        (d / "package.json").write_text("{}", encoding="utf-8")
        have = {k: v for k, v in WANT.items() if not v.get("optional")}
        (tmp / "node_modules" / ".package-lock.json").write_text(_lock(have), encoding="utf-8")
    return tmp


class NpmDeps(unittest.TestCase):
    def test_missing_lists_package_and_command(self):
        with tempfile.TemporaryDirectory() as t:
            r = doc.check_npm_deps(_skill(Path(t), installed=False))
            self.assertFalse(r["ok"])
            self.assertIn("puppeteer-core", r["detail"])
            self.assertIn("npm install", r["fix"])

    def test_installed_ok(self):
        with tempfile.TemporaryDirectory() as t:
            self.assertTrue(doc.check_npm_deps(_skill(Path(t), installed=True))["ok"])

    def test_touched_lock_same_content_is_ok(self):
        # git reset 會更新 lock 的修改時間；內容沒變不該叫人重裝（0.15.1 誤報過）
        with tempfile.TemporaryDirectory() as t:
            s = _skill(Path(t), installed=True)
            old = time.time() - 3600
            os.utime(s / "node_modules" / ".package-lock.json", (old, old))
            self.assertTrue(doc.check_npm_deps(s)["ok"])

    def test_lock_version_changed_is_stale(self):
        # skill 自動更新換了 package-lock.json 但沒重裝
        with tempfile.TemporaryDirectory() as t:
            s = _skill(Path(t), installed=True)
            (s / "package-lock.json").write_text(
                _lock({**WANT, "puppeteer-core": {"version": "26.0.0"}}), encoding="utf-8")
            r = doc.check_npm_deps(s)
            self.assertFalse(r["ok"])
            self.assertIn("puppeteer-core", r["detail"])
            self.assertIn("npm install", r["fix"])

    def test_lock_new_package_is_stale(self):
        with tempfile.TemporaryDirectory() as t:
            s = _skill(Path(t), installed=True)
            (s / "package-lock.json").write_text(
                _lock({**WANT, "new-dep": {"version": "1.0.0"}}), encoding="utf-8")
            r = doc.check_npm_deps(s)
            self.assertFalse(r["ok"])
            self.assertIn("new-dep", r["detail"])


class Ffmpeg(unittest.TestCase):
    def test_env_first_then_skill_copy(self):
        with tempfile.TemporaryDirectory() as t:
            s = Path(t)
            exe = s / "node_modules" / "ffmpeg-static" / ("ffmpeg.exe" if doc.OS == "Windows" else "ffmpeg")
            exe.parent.mkdir(parents=True)
            exe.write_bytes(b"")
            other = s / "my-ffmpeg"
            other.write_bytes(b"")
            with mock.patch.dict(os.environ, {"FFMPEG": str(other)}):
                self.assertEqual(doc.find_ffmpeg(s), str(other))
            with mock.patch.dict(os.environ, {"FFMPEG": ""}):
                self.assertEqual(doc.find_ffmpeg(s), str(exe))

    def test_missing_gives_install_hint(self):
        with tempfile.TemporaryDirectory() as t, mock.patch.dict(os.environ, {"FFMPEG": ""}), \
                mock.patch.object(doc.shutil, "which", return_value=None):
            r = doc.check_ffmpeg(Path(t))
            self.assertFalse(r["ok"])
            self.assertIn("npm install", r["fix"])


class Required(unittest.TestCase):
    def test_ffmpeg_required_only_for_video(self):
        bad = {"ok": False, "detail": "x", "fix": "y"}
        good = {"ok": True, "detail": "x"}
        with mock.patch.multiple(doc, check_node=lambda: good, check_npm_deps=lambda: good, check_chrome=lambda: good,
                                 check_py=lambda m: good, check_ffmpeg=lambda: bad, check_gs=lambda: bad):
            pdf = {r["name"]: r for r in doc.run(video=False)}
            vid = {r["name"]: r for r in doc.run(video=True)}
        self.assertFalse(pdf["ffmpeg"]["required"])
        self.assertTrue(vid["ffmpeg"]["required"])
        self.assertFalse(vid["Ghostscript"]["required"])


if __name__ == "__main__":
    unittest.main()
