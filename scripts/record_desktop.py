"""桌面錄影（ffmpeg gdigrab）＋字幕紀錄：瀏覽器以外的畫面，或由 agent 的桌面操作工具（computer use）操作時用。
網頁一律優先用 record.mjs（可重跑、不受桌面干擾、節奏可控）；這支是退路（references/video.md「桌面錄影」）。

  python record_desktop.py start --dir video/desk [--window "視窗標題" | --screen 1 | --region x,y,w,h] [--fps 15] [--max 900]
      （放背景跑：一直錄到 stop；--max 秒數到了自動停）
  python record_desktop.py say     --dir video/desk "點「新增」開一張新單" [--xy 812,440]   # 動作「之前」記（建議）
  python record_desktop.py did     --dir video/desk "已送出" [--xy 812,440]                # 動作「之後」才記：後製往回對
  python record_desktop.py chapter --dir video/desk "查詢訂單" [--sub "一句話"]            # 章節字卡
  python record_desktop.py stop    --dir video/desk
  然後：python video_post.py --dir video/desk --purpose 操作說明 --tenant … --app …

--xy 是螢幕座標（實體像素）；截圖有縮放時加 --scale（xy×scale）。錄影範圍內出現的所有東西都會錄進去
（通知、其他視窗）：開錄前關掉不相干的視窗與通知。目前只支援 Windows。
"""
from __future__ import annotations

import argparse
import json
import platform
import re
import subprocess
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))


def ffmpeg_bin() -> str:
    from video_post import ffmpeg_bin as fb
    return fb()


def screen_rects() -> list[tuple[int, int, int, int]]:
    import ctypes
    from ctypes import wintypes
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(2)
    except Exception:
        pass
    rects: list[tuple[int, int, int, int]] = []
    primary: list[int] = []
    MONITORINFOF_PRIMARY = 1

    class MI(ctypes.Structure):
        _fields_ = [("cbSize", wintypes.DWORD), ("rcMonitor", wintypes.RECT), ("rcWork", wintypes.RECT), ("dwFlags", wintypes.DWORD)]

    proc = ctypes.WINFUNCTYPE(ctypes.c_int, wintypes.HMONITOR, wintypes.HDC, ctypes.POINTER(wintypes.RECT), wintypes.LPARAM)

    def cb(hmon, hdc, lprc, lp):
        mi = MI(); mi.cbSize = ctypes.sizeof(MI)
        ctypes.windll.user32.GetMonitorInfoW(hmon, ctypes.byref(mi))
        r = mi.rcMonitor
        if mi.dwFlags & MONITORINFOF_PRIMARY:
            primary.append(len(rects))
        rects.append((r.left, r.top, r.right - r.left, r.bottom - r.top))
        return 1

    ctypes.windll.user32.EnumDisplayMonitors(None, None, proc(cb), 0)
    if primary:  # 主螢幕排第一，--screen 1 就是主螢幕
        rects.insert(0, rects.pop(primary[0]))
    return rects


def resolve_region(a) -> tuple[tuple[int, int, int, int], str]:
    if a.region:
        x, y, w, h = (int(v) for v in a.region.split(","))
        return (x, y, w, h), f"region {a.region}"
    if a.window:
        import desktop_shot as ds  # 沿用 skill 的視窗查找（DPI aware、去掉陰影外框）
        ds._win_dpi_aware()
        hwnd, title, rect = ds.win_find_window(a.window)
        ds.win_focus(hwnd)
        time.sleep(0.4)
        return rect, f"window {title}"
    rs = screen_rects()
    i = max(1, a.screen) - 1
    if i >= len(rs):
        raise SystemExit(f"只有 {len(rs)} 個螢幕")
    return rs[i], f"screen {i + 1}"


def cmd_start(a) -> int:
    if platform.system() != "Windows":
        raise SystemExit("桌面錄影目前只支援 Windows；網頁請用 record.mjs")
    d = Path(a.dir); d.mkdir(parents=True, exist_ok=True)
    (d / "stop.flag").unlink(missing_ok=True)
    (x, y, w, h), what = resolve_region(a)
    w -= w % 2; h -= h % 2  # libx264 要偶數
    raw = d / "raw.mkv"
    args = [ffmpeg_bin(), "-hide_banner", "-y", "-f", "gdigrab", "-framerate", str(a.fps), "-draw_mouse", "1",
            "-offset_x", str(x), "-offset_y", str(y), "-video_size", f"{w}x{h}", "-i", "desktop",
            "-t", str(a.max), "-c:v", "libx264", "-preset", "ultrafast", "-crf", "20", "-g", str(a.fps * 2),
            "-pix_fmt", "yuv420p", str(raw)]
    log = open(d / "ffmpeg.log", "w", encoding="utf-8", errors="replace")
    p = subprocess.Popen(args, stdin=subprocess.PIPE, stdout=log, stderr=subprocess.STDOUT)
    sess = {"kind": "desktop", "raw": raw.name, "region": [x, y, w, h], "what": what, "fps": a.fps,
            "pid": p.pid, "launched": time.time(), "video_start": None, "state": "recording"}
    js = d / "session.json"
    js.write_text(json.dumps(sess, ensure_ascii=False, indent=1), encoding="utf-8")
    (d / "events.jsonl").touch()
    print(f"錄影中：{what} {w}x{h} → {raw}（停止：python record_desktop.py stop --dir {d}）", flush=True)
    while p.poll() is None:
        if sess["video_start"] is None:  # gdigrab 的 start 是系統時鐘秒數，事件用它對時
            m = re.search(r"start: (\d+\.\d+)", (d / "ffmpeg.log").read_text(encoding="utf-8", errors="replace"))
            if m:
                sess["video_start"] = float(m.group(1))
                js.write_text(json.dumps(sess, ensure_ascii=False, indent=1), encoding="utf-8")
        if (d / "stop.flag").exists():
            try:
                p.stdin.write(b"q"); p.stdin.flush()
            except OSError:
                pass
            try:
                p.wait(30)
            except subprocess.TimeoutExpired:
                p.kill()
            break
        time.sleep(0.2)
    sess["state"] = "done"; sess["stopped"] = time.time()
    js.write_text(json.dumps(sess, ensure_ascii=False, indent=1), encoding="utf-8")
    ok = raw.exists() and raw.stat().st_size > 0
    print("錄影結束", raw, f"{raw.stat().st_size / 1e6:.1f} MB" if ok else "（沒有檔案，看 ffmpeg.log）")
    return 0 if ok else 1


def add_event(a, kind: str, when: str) -> int:
    d = Path(a.dir)
    ev = {"ts": time.time(), "kind": kind, "when": when, "text": a.text}
    if getattr(a, "sub", None):
        ev["sub"] = a.sub
    if getattr(a, "xy", None):
        x, y = (float(v) for v in a.xy.split(","))
        s = getattr(a, "scale", 1.0) or 1.0
        ev["sx"], ev["sy"] = x * s, y * s  # 螢幕座標；後製時減掉錄影區域的左上角
    with open(d / "events.jsonl", "a", encoding="utf-8") as f:
        f.write(json.dumps(ev, ensure_ascii=False) + "\n")
    print("記下", kind, a.text)
    return 0


def cmd_stop(a) -> int:
    d = Path(a.dir)
    (d / "stop.flag").write_text("stop")
    for _ in range(150):
        s = json.loads((d / "session.json").read_text(encoding="utf-8"))
        if s.get("state") == "done":
            print("已停止", d / s["raw"])
            return 0
        time.sleep(0.2)
    print("等不到錄影結束，看", d / "ffmpeg.log")
    return 1


def main() -> int:
    for s in (sys.stdout, sys.stderr):
        try:
            s.reconfigure(encoding="utf-8")
        except Exception:
            pass
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    st = sub.add_parser("start"); st.add_argument("--dir", required=True)
    st.add_argument("--screen", type=int, default=1); st.add_argument("--window"); st.add_argument("--region")
    st.add_argument("--fps", type=int, default=15); st.add_argument("--max", type=int, default=900)
    for name in ("say", "did", "chapter"):
        p = sub.add_parser(name); p.add_argument("--dir", required=True); p.add_argument("text")
        p.add_argument("--xy"); p.add_argument("--scale", type=float, default=1.0)
        if name == "chapter":
            p.add_argument("--sub", help="章節字卡第二行（功能展示：這能幫你做什麼）")
    sp = sub.add_parser("stop"); sp.add_argument("--dir", required=True)
    a = ap.parse_args()
    if a.cmd == "start":
        return cmd_start(a)
    if a.cmd == "stop":
        return cmd_stop(a)
    return add_event(a, {"say": "step", "did": "step", "chapter": "chapter"}[a.cmd],
                     {"say": "before", "did": "after", "chapter": "before"}[a.cmd])


if __name__ == "__main__":
    raise SystemExit(main())
