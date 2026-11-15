#!/usr/bin/env python3
"""
環境檢查：列出這台電腦缺什麼、為什麼需要、怎麼裝。零相依（只用標準函式庫），裝好任何東西之前就能跑。

    python <skill>/scripts/doctor.py             # 簡報 PDF／測試指引／整合測試要的東西
    python <skill>/scripts/doctor.py --video     # 再加操作影片要的 ffmpeg
    python <skill>/scripts/doctor.py --json      # 機器可讀

結束碼：0＝必要項目都齊；1＝有必要項目缺（輸出會列出要執行的指令）。
「選配」缺了不影響結束碼。
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import os
import platform
import re
import shutil
import subprocess
import sys
from pathlib import Path

SKILL = Path(__file__).resolve().parent.parent
OS = platform.system()          # Windows / Darwin / Linux
PY = "python" if OS == "Windows" else "python3"

CHROME_PATHS = [
    "C:/Program Files/Google/Chrome/Application/chrome.exe",
    "C:/Program Files (x86)/Google/Chrome/Application/chrome.exe",
    "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
    "/usr/bin/google-chrome", "/usr/bin/chromium",
]


def _by_os(win: str, mac: str, linux: str) -> str:
    return {"Windows": win, "Darwin": mac}.get(OS, linux)


def check_node() -> dict:
    node = shutil.which("node")
    fix = _by_os("winget install OpenJS.NodeJS.LTS", "brew install node", "到 https://nodejs.org 安裝 LTS 版")
    if not node:
        return {"ok": False, "detail": "找不到 node", "fix": fix}
    try:
        v = subprocess.run([node, "--version"], capture_output=True, text=True, timeout=20).stdout.strip()
    except (OSError, subprocess.SubprocessError):
        return {"ok": False, "detail": "node 無法執行", "fix": fix}
    m = re.match(r"v(\d+)", v)
    if not m or int(m.group(1)) < 18:
        return {"ok": False, "detail": f"版本 {v or '?'}，需要 18 以上", "fix": fix}
    return {"ok": True, "detail": v}


def check_npm_deps(skill: Path = SKILL) -> dict:
    fix = f'cd "{skill}" && npm install'
    pkg = json.loads((skill / "package.json").read_text(encoding="utf-8"))
    missing = [d for d in pkg.get("dependencies", {}) if not (skill / "node_modules" / d / "package.json").exists()]
    if missing:
        return {"ok": False, "detail": "還沒裝：" + "、".join(missing), "fix": fix}
    # skill 自動更新只換檔案、不重裝：lock 要的套件版本跟 node_modules 裝的不一樣＝該重裝。
    # 比內容不比修改時間——git reset 會更新 lock 的時間，內容沒變也不該叫人重裝。
    stale = _lock_drift(skill)
    if stale:
        return {"ok": False, "detail": "skill 更新過，這些套件要重裝：" + "、".join(stale[:5])
                + ("…" if len(stale) > 5 else ""), "fix": fix}
    return {"ok": True, "detail": "puppeteer-core 已裝"}


def _lock_drift(skill: Path) -> list[str]:
    """package-lock.json 要的 vs node_modules/.package-lock.json 已裝的，回傳版本不符或沒裝的套件名。"""
    def packages(p: Path) -> dict | None:
        try:
            return json.loads(p.read_text(encoding="utf-8")).get("packages") or {}
        except (OSError, ValueError, AttributeError):
            return None
    want = packages(skill / "package-lock.json")
    have = packages(skill / "node_modules" / ".package-lock.json")
    if want is None or have is None:
        return []  # 沒有 lock 可比：上面已確認直接依賴都在，就算過
    drift = []
    for key, meta in want.items():
        if not key.startswith("node_modules/") or not isinstance(meta, dict):
            continue
        if meta.get("optional") or meta.get("dev"):
            continue  # 其他平台的選配套件、開發用套件，沒裝是正常的
        got = have.get(key)
        if not isinstance(got, dict) or got.get("version") != meta.get("version"):
            drift.append(key.rsplit("node_modules/", 1)[-1])
    return drift


def check_chrome() -> dict:
    hit = next((p for p in [os.environ.get("CHROME_PATH"), *CHROME_PATHS] if p and Path(p).exists()), None)
    if hit:
        return {"ok": True, "detail": hit}
    return {"ok": False, "detail": "找不到 Google Chrome",
            "fix": "安裝 Google Chrome，或設環境變數 CHROME_PATH／present.config.json 的 chrome 指到 Chrome 執行檔"}


def check_py(mods: list[str]) -> dict:
    missing = [m for m in mods if importlib.util.find_spec(m) is None]
    names = {"PIL": "pillow"}
    if missing:
        return {"ok": False, "detail": "還沒裝：" + "、".join(names.get(m, m) for m in missing),
                "fix": f"{PY} -m pip install " + " ".join(names.get(m, m) for m in missing)}
    return {"ok": True, "detail": "pillow、pypdf 已裝"}


def find_ffmpeg(skill: Path = SKILL) -> str | None:
    """與 video_post.ffmpeg_bin 同順序：FFMPEG → skill 的 ffmpeg-static → PATH。"""
    env = os.environ.get("FFMPEG")
    if env and Path(env).exists():
        return env
    local = skill / "node_modules" / "ffmpeg-static" / ("ffmpeg.exe" if OS == "Windows" else "ffmpeg")
    if local.exists():
        return str(local)
    return shutil.which("ffmpeg")


def check_ffmpeg(skill: Path = SKILL) -> dict:
    hit = find_ffmpeg(skill)
    if hit:
        return {"ok": True, "detail": hit}
    return {"ok": False, "detail": "找不到 ffmpeg",
            "fix": f'cd "{skill}" && npm install（會一起裝 ffmpeg-static）；或 '
                   + _by_os("winget install Gyan.FFmpeg", "brew install ffmpeg", "sudo apt install ffmpeg")
                   + "；或設環境變數 FFMPEG 指到 ffmpeg 執行檔"}


def check_gs() -> dict:
    hit = shutil.which("gswin64c") or shutil.which("gs")
    return {"ok": bool(hit), "detail": hit or "沒有（PDF 壓縮改用 pypdf，可以不裝）",
            "fix": _by_os("winget install ArtifexSoftware.GhostScript", "brew install ghostscript", "sudo apt install ghostscript")}


def run(video: bool) -> list[dict]:
    items = [
        ("Node.js 18+", "截圖、錄影、渲染 PDF 的腳本", True, check_node),
        ("npm 套件", "puppeteer-core：開 Chrome 截圖、錄影、轉 PDF", True, check_npm_deps),
        ("Google Chrome", "puppeteer 用它開頁面", True, check_chrome),
        ("Python 套件", "排版總表、PDF 壓縮", True, lambda: check_py(["PIL", "pypdf"])),
        ("ffmpeg", "操作影片的組片與後製", video, check_ffmpeg),
        ("Ghostscript", "PDF 壓縮得更小", False, check_gs),
    ]
    out = []
    for name, why, required, fn in items:
        r = fn()
        out.append({"name": name, "why": why, "required": required, **r})
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description="檢查這台電腦有沒有 skill 需要的東西")
    ap.add_argument("--video", action="store_true", help="要做操作影片（ffmpeg 改成必要）")
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args()
    res = run(a.video)
    bad = [r for r in res if r["required"] and not r["ok"]]
    if a.json:
        print(json.dumps({"ok": not bad, "skill_dir": str(SKILL), "items": res}, ensure_ascii=False, indent=1))
        return 1 if bad else 0
    for r in res:
        mark = "✓" if r["ok"] else ("✗" if r["required"] else "－")
        tag = "" if r["required"] else "（選配）"
        print(f"{mark} {r['name']}{tag}：{r['detail']}")
        if not r["ok"] and r["required"]:
            print(f"    用途：{r['why']}")
            print(f"    安裝：{r['fix']}")
    if bad:
        print(f"\n缺 {len(bad)} 項必要的東西。照上面「安裝」那行執行後再跑一次本檢查。")
    else:
        print("\n必要項目都齊了。")
    return 1 if bad else 0


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except (AttributeError, ValueError):
        pass
    sys.exit(main())
