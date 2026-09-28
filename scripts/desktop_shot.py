# -*- coding: utf-8 -*-
"""
desktop_shot.py — 瀏覽器以外的畫面：桌面應用程式視窗／整個螢幕／指定區域截圖，寫進 shots/ 與 shots.json。

跟 shoot.mjs 拍的截圖走同一條管線：產出 shots/<name>.png ＋ shots.json 一筆（多 "kind": "desktop"），
deck_kit.Deck.shot()／fig() 直接可用，預設包「視窗框」而不是瀏覽器框。

用法（在工作資料夾）：
    python <skill>/scripts/desktop_shot.py --name line-app --title "LINE"            # 依視窗標題（子字串）抓該視窗
    python <skill>/scripts/desktop_shot.py --name desk --screen                       # 整個主螢幕
    python <skill>/scripts/desktop_shot.py --name part --region 100,80,900,600        # 螢幕上的一塊（x,y,w,h，實體像素）
    python <skill>/scripts/desktop_shot.py --name menu --from capture.png --region …  # 裁切既有圖（桌面操作工具存下來的截圖）
選項：
    --out shots            輸出資料夾（預設 shots；shots.json 在同一層）
    --delay 1.5            截圖前等幾秒（把視窗帶到前面後給它時間重繪；預設 1.0）
    --mark 1:x,y,w,h       圖解標號（相對截圖左上角的像素座標；可多個）
    --note "…"             備註，寫進 shots.json
    --no-focus             不把視窗帶到前面（視窗已在前面、或不想改變焦點時）
    --list                 列出目前可見的視窗標題（找 --title 用）

支援：
    Windows  完整支援（ctypes 直接呼叫 Win32／GDI，零相依；DPI 已處理，座標一律實體像素）
    macOS    osascript 取視窗位置 → screencapture；Retina 輸出為實體像素
    Linux    xdotool 取視窗位置 → gnome-screenshot／import；盡力支援
    --from   任何平台，需要 Pillow（pip install pillow）

規則（references/screenshot-guide.md「瀏覽器以外的畫面」）：
    - 終端指令不用這支：改用 deck_kit.Deck.term() 把指令與輸出渲染成終端框
    - 拍之前關掉通知、收起無關視窗；拍完照 G2 檢查工作列、系統匣、標題列有沒有個資
"""

from __future__ import annotations
import argparse
import ctypes
import json
import os
import platform
import struct
import subprocess
import sys
import time
import zlib
from pathlib import Path

SYSTEM = platform.system()


# ---------------------------------------------------------------------------
# 共用：PNG 編碼、manifest
# ---------------------------------------------------------------------------


def encode_png(width: int, height: int, bgra: bytes) -> bytes:
    """32bpp BGRA（由上到下）→ PNG（RGB）。標準函式庫實作，避免依賴 Pillow。"""
    rows = bytearray()
    stride = width * 4
    for y in range(height):
        rows.append(0)  # filter: none
        row = bgra[y * stride:(y + 1) * stride]
        rows += _bgra_row_to_rgb(row)

    def chunk(tag: bytes, data: bytes) -> bytes:
        body = tag + data
        return struct.pack(">I", len(data)) + body + struct.pack(">I", zlib.crc32(body) & 0xFFFFFFFF)

    ihdr = struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)
    return b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", ihdr) + chunk(b"IDAT", zlib.compress(bytes(rows), 6)) + chunk(b"IEND", b"")


def _bgra_row_to_rgb(row: bytes) -> bytes:
    # 用 slice 做通道重排，比逐 byte 迴圈快一個數量級（2560 寬一列 < 0.1 ms）
    b, g, r = row[0::4], row[1::4], row[2::4]
    out = bytearray(len(r) * 3)
    out[0::3], out[1::3], out[2::3] = r, g, b
    return bytes(out)


def parse_region(text: str) -> tuple[int, int, int, int]:
    parts = [int(p) for p in text.replace(" ", "").split(",")]
    if len(parts) != 4 or parts[2] <= 0 or parts[3] <= 0:
        raise ValueError("--region 要是 x,y,w,h 四個整數，w、h 大於 0")
    return tuple(parts)  # type: ignore[return-value]


def parse_mark(text: str) -> dict:
    """'1:x,y,w,h' → {"n": 1, "x":…, "y":…, "w":…, "h":…}"""
    n, _, rect = text.partition(":")
    if not n or not rect:
        raise ValueError("--mark 要是 編號:x,y,w,h")
    x, y, w, h = parse_region(rect)
    return {"n": int(n) if n.isdigit() else n, "x": x, "y": y, "w": w, "h": h}


def merge_manifest(path: Path, name: str, entry: dict) -> None:
    """讀 → 併入一筆 → 寫回。shoot.mjs 也會寫這個檔，所以每次都重讀，不在記憶體裡累積。"""
    man = {}
    if path.exists():
        try:
            man = json.loads(path.read_text(encoding="utf-8-sig"))
        except ValueError:
            man = {}
    man[name] = entry
    path.write_text(json.dumps(man, ensure_ascii=False, indent=1), encoding="utf-8")


# ---------------------------------------------------------------------------
# Windows：Win32 ＋ GDI
# ---------------------------------------------------------------------------


def _win_dpi_aware() -> None:
    """讓 GetWindowRect 等 API 回實體像素；沒宣告的話 150% 縮放下座標會差 1.5 倍。"""
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(2)  # PER_MONITOR_AWARE
    except (AttributeError, OSError):
        try:
            ctypes.windll.user32.SetProcessDPIAware()
        except (AttributeError, OSError):
            pass


def win_list_windows() -> list[tuple[int, str, tuple[int, int, int, int]]]:
    """可見、有標題的頂層視窗：[(hwnd, title, (x, y, w, h))]，面積大的在前。"""
    user32 = ctypes.windll.user32
    out = []

    @ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_void_p, ctypes.c_void_p)
    def cb(hwnd, _):
        if not user32.IsWindowVisible(hwnd):
            return True
        n = user32.GetWindowTextLengthW(hwnd)
        if n == 0:
            return True
        buf = ctypes.create_unicode_buffer(n + 1)
        user32.GetWindowTextW(hwnd, buf, n + 1)
        rect = win_window_rect(hwnd)
        if rect[2] > 0 and rect[3] > 0:
            out.append((hwnd, buf.value, rect))
        return True

    user32.EnumWindows(cb, 0)
    out.sort(key=lambda t: -(t[2][2] * t[2][3]))
    return out


def win_window_rect(hwnd: int) -> tuple[int, int, int, int]:
    """視窗可見範圍（去掉 Win10+ 的隱形邊框）。DWM 取不到就退回 GetWindowRect。"""
    class RECT(ctypes.Structure):
        _fields_ = [("l", ctypes.c_long), ("t", ctypes.c_long), ("r", ctypes.c_long), ("b", ctypes.c_long)]

    r = RECT()
    ok = False
    try:
        DWMWA_EXTENDED_FRAME_BOUNDS = 9
        ok = ctypes.windll.dwmapi.DwmGetWindowAttribute(ctypes.c_void_p(hwnd), DWMWA_EXTENDED_FRAME_BOUNDS,
                                                        ctypes.byref(r), ctypes.sizeof(r)) == 0
    except (AttributeError, OSError):
        ok = False
    if not ok:
        ctypes.windll.user32.GetWindowRect(ctypes.c_void_p(hwnd), ctypes.byref(r))
    return (r.l, r.t, r.r - r.l, r.b - r.t)


def win_find_window(title: str) -> tuple[int, str, tuple[int, int, int, int]]:
    needle = title.lower()
    hits = [w for w in win_list_windows() if needle in w[1].lower()]
    if not hits:
        raise SystemExit(f"找不到標題含「{title}」的視窗。用 --list 看目前有哪些。")
    return hits[0]


def win_focus(hwnd: int) -> None:
    user32 = ctypes.windll.user32
    SW_RESTORE = 9
    if user32.IsIconic(hwnd):
        user32.ShowWindow(ctypes.c_void_p(hwnd), SW_RESTORE)
    user32.SetForegroundWindow(ctypes.c_void_p(hwnd))


def win_capture(region: tuple[int, int, int, int]) -> bytes:
    """GDI BitBlt 抓螢幕上的一塊（實體像素）→ PNG bytes。"""
    x, y, w, h = region
    user32, gdi32 = ctypes.windll.user32, ctypes.windll.gdi32
    SRCCOPY, CAPTUREBLT = 0x00CC0020, 0x40000000
    hdc = user32.GetDC(None)
    mem = gdi32.CreateCompatibleDC(hdc)
    bmp = gdi32.CreateCompatibleBitmap(hdc, w, h)
    old = gdi32.SelectObject(mem, bmp)
    try:
        if not gdi32.BitBlt(mem, 0, 0, w, h, hdc, x, y, SRCCOPY | CAPTUREBLT):
            raise SystemExit("BitBlt 失敗（區域超出螢幕？）")

        class BITMAPINFOHEADER(ctypes.Structure):
            _fields_ = [("biSize", ctypes.c_uint32), ("biWidth", ctypes.c_int32), ("biHeight", ctypes.c_int32),
                        ("biPlanes", ctypes.c_uint16), ("biBitCount", ctypes.c_uint16), ("biCompression", ctypes.c_uint32),
                        ("biSizeImage", ctypes.c_uint32), ("biXPelsPerMeter", ctypes.c_int32), ("biYPelsPerMeter", ctypes.c_int32),
                        ("biClrUsed", ctypes.c_uint32), ("biClrImportant", ctypes.c_uint32)]

        bi = BITMAPINFOHEADER(ctypes.sizeof(BITMAPINFOHEADER), w, -h, 1, 32, 0, 0, 0, 0, 0, 0)  # 負高度＝由上到下
        buf = ctypes.create_string_buffer(w * h * 4)
        DIB_RGB_COLORS = 0
        if gdi32.GetDIBits(mem, bmp, 0, h, buf, ctypes.byref(bi), DIB_RGB_COLORS) == 0:
            raise SystemExit("GetDIBits 失敗")
        return encode_png(w, h, buf.raw)
    finally:
        gdi32.SelectObject(mem, old)
        gdi32.DeleteObject(bmp)
        gdi32.DeleteDC(mem)
        user32.ReleaseDC(None, hdc)


def win_screen_region() -> tuple[int, int, int, int]:
    user32 = ctypes.windll.user32
    return (0, 0, user32.GetSystemMetrics(0), user32.GetSystemMetrics(1))


# ---------------------------------------------------------------------------
# macOS／Linux：外部指令，盡力支援
# ---------------------------------------------------------------------------


def _run(cmd: list[str]) -> str:
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        raise SystemExit(f"執行失敗：{' '.join(cmd)}\n{r.stderr.strip()}")
    return r.stdout.strip()


def mac_find_window(title: str) -> tuple[str, tuple[int, int, int, int]]:
    """用 System Events 找標題含 title 的視窗（需要輔助使用權限）；回 (標題, (x,y,w,h))，單位是點（point）。"""
    script = f'''
    tell application "System Events"
      repeat with p in (every process whose background only is false)
        repeat with w in (every window of p)
          if (name of w as string) contains "{title}" then
            set pos to position of w
            set sz to size of w
            return (name of w as string) & "|" & (item 1 of pos) & "," & (item 2 of pos) & "," & (item 1 of sz) & "," & (item 2 of sz)
          end if
        end repeat
      end repeat
    end tell
    return ""'''
    out = _run(["osascript", "-e", script])
    if not out:
        raise SystemExit(f"找不到標題含「{title}」的視窗（System Events 需要「輔助使用」權限）")
    name, _, rect = out.partition("|")
    return name, parse_region(rect)


def mac_capture(region: tuple[int, int, int, int], out: Path) -> None:
    x, y, w, h = region
    _run(["screencapture", "-x", "-R", f"{x},{y},{w},{h}", str(out)])


def linux_find_window(title: str) -> tuple[str, tuple[int, int, int, int]]:
    ids = _run(["xdotool", "search", "--onlyvisible", "--name", title]).split()
    if not ids:
        raise SystemExit(f"找不到標題含「{title}」的視窗（需要 xdotool）")
    wid = ids[0]
    name = _run(["xdotool", "getwindowname", wid])
    geo = dict(line.split("=", 1) for line in _run(["xdotool", "getwindowgeometry", "--shell", wid]).splitlines())
    return name, (int(geo["X"]), int(geo["Y"]), int(geo["WIDTH"]), int(geo["HEIGHT"]))


def linux_capture(region: tuple[int, int, int, int] | None, out: Path) -> None:
    if region:
        x, y, w, h = region
        _run(["import", "-window", "root", "-crop", f"{w}x{h}+{x}+{y}", str(out)])  # ImageMagick
    else:
        _run(["gnome-screenshot", "-f", str(out)])


# ---------------------------------------------------------------------------
# 既有圖片裁切（--from）
# ---------------------------------------------------------------------------


def crop_file(src: Path, region: tuple[int, int, int, int] | None, out: Path) -> tuple[int, int]:
    try:
        from PIL import Image  # type: ignore
    except ImportError:
        raise SystemExit("--from 需要 Pillow：pip install pillow")
    img = Image.open(src)
    if region:
        x, y, w, h = region
        img = img.crop((x, y, x + w, y + h))
    img.save(out)
    return img.size


def png_size(path: Path) -> tuple[int, int]:
    with path.open("rb") as f:
        head = f.read(24)
    if head[:8] != b"\x89PNG\r\n\x1a\n":
        raise SystemExit(f"不是 PNG：{path}")
    return struct.unpack(">II", head[16:24])


# ---------------------------------------------------------------------------
# 主流程
# ---------------------------------------------------------------------------


def _configure_stdout() -> None:
    """Windows 主控台預設 cp950：視窗標題裡的字印不出來會直接炸；導向管線時改 UTF-8，編不出的換 ?。"""
    try:
        if sys.stdout.isatty():
            sys.stdout.reconfigure(errors="replace")
        else:
            sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError, OSError):
        pass


def main(argv: list[str] | None = None) -> int:
    _configure_stdout()
    ap = argparse.ArgumentParser(description="桌面視窗／螢幕／區域截圖 → shots/ ＋ shots.json")
    ap.add_argument("--name", help="截圖名（不含 .png）")
    src = ap.add_mutually_exclusive_group()
    src.add_argument("--title", help="視窗標題（子字串，不分大小寫）")
    src.add_argument("--screen", action="store_true", help="整個主螢幕")
    src.add_argument("--from", dest="from_file", help="裁切既有的 PNG／JPG")
    ap.add_argument("--region", help="x,y,w,h（實體像素）；單獨用＝抓螢幕上這一塊，配 --title／--from＝再裁一次")
    ap.add_argument("--out", default="shots")
    ap.add_argument("--delay", type=float, default=1.0)
    ap.add_argument("--mark", action="append", default=[], help="編號:x,y,w,h，可多個")
    ap.add_argument("--note", default="")
    ap.add_argument("--no-focus", action="store_true")
    ap.add_argument("--list", action="store_true", help="列出可見視窗")
    a = ap.parse_args(argv)

    if a.list:
        if SYSTEM == "Windows":
            _win_dpi_aware()
            for _, title, (x, y, w, h) in win_list_windows():
                print(f"{w}x{h} @ {x},{y}  {title}")
        else:
            print("--list 目前只支援 Windows；macOS 請用 --title 直接試，Linux 用 xdotool search --name")
        return 0

    if not a.name:
        ap.error("--name 必填")
    if not (a.title or a.screen or a.from_file or a.region):
        ap.error("要指定 --title、--screen、--region 或 --from 其中之一")

    out_dir = Path(a.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    out = out_dir / f"{a.name}.png"
    region = parse_region(a.region) if a.region else None
    marks = [parse_mark(m) for m in a.mark]
    title = ""

    if a.from_file:
        w, h = crop_file(Path(a.from_file), region, out)
        kind = "desktop"
    elif SYSTEM == "Windows":
        _win_dpi_aware()
        if a.title:
            hwnd, title, rect = win_find_window(a.title)
            if not a.no_focus:
                win_focus(hwnd)
            time.sleep(a.delay)
            rect = win_window_rect(hwnd)  # 帶到前面後可能還原／移動，重取
            if region:  # 相對視窗左上角再裁
                rect = (rect[0] + region[0], rect[1] + region[1], region[2], region[3])
        else:
            time.sleep(a.delay)
            rect = region or win_screen_region()
        out.write_bytes(win_capture(rect))
        w, h = rect[2], rect[3]
        kind = "desktop"
    elif SYSTEM == "Darwin":
        if a.title:
            title, rect = mac_find_window(a.title)
            if not a.no_focus:
                _run(["osascript", "-e", f'tell application "System Events" to set frontmost of (first process whose windows contains (first window whose name contains "{a.title}")) to true'])
            time.sleep(a.delay)
            if region:
                rect = (rect[0] + region[0], rect[1] + region[1], region[2], region[3])
            mac_capture(rect, out)
        elif region:
            time.sleep(a.delay)
            mac_capture(region, out)
        else:
            time.sleep(a.delay)
            _run(["screencapture", "-x", str(out)])
        w, h = png_size(out)
        kind = "desktop"
    else:
        if a.title:
            title, rect = linux_find_window(a.title)
            if not a.no_focus:
                _run(["xdotool", "search", "--onlyvisible", "--name", a.title, "windowactivate"])
            time.sleep(a.delay)
            if region:
                rect = (rect[0] + region[0], rect[1] + region[1], region[2], region[3])
            linux_capture(rect, out)
        else:
            time.sleep(a.delay)
            linux_capture(region, out)
        w, h = png_size(out)
        kind = "desktop"

    # full＝整個視窗或整個螢幕（簡報會包視窗框）；--region／--from 裁的局部＝False（白底細框，同瀏覽器局部截圖）
    full = not region and not a.from_file
    entry = {"w": int(w), "h": int(h), "full": full, "kind": kind, "marks": marks, "note": a.note}
    if title:
        entry["title"] = title
    merge_manifest(out_dir / "shots.json", a.name, entry)
    print("OK", a.name, f"{w}x{h}", (f"「{title}」" if title else ""), f"{len(marks)} marks" if marks else "")
    return 0


if __name__ == "__main__":
    sys.exit(main())
