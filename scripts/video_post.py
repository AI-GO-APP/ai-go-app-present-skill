"""操作影片後製：快轉沒在操作的畫面、每一步前凍結讓字幕讀得完、片頭／章節／片尾字卡、燒字幕、點擊圈、MP4 章節。

  python video_post.py --dir video/manual --purpose 操作說明 [--tenant 展示公司 --app 訂單中心] [--out 檔名.mp4]

讀 --dir 裡 record.mjs（網頁）或 record_desktop.py（桌面）留下的 session.json、events.jsonl、raw.*。
檔名預設照交付規則「AI GO 租戶名 App名 用途 YYYYMMDD.mp4」（租戶名、App 名沒給就讀 session.json 的 meta），
另存同名 .srt（外掛字幕）與 --dir/edit.json（剪輯表，除錯用）。

節奏規則（都可調）：
  - 畫面靜止超過 --idle 秒（預設 1.2）：壓成 0.6 秒；靜止超過 4 秒的壓成 1.2 秒並標「快轉 ▶▶ 略過 N 秒」
  - 每一步動作前：凍結畫面 1～3 秒，字幕＋點擊位置先出現，讀完才動（依字數，--cps 每秒字數，預設 5）
  - 一步的字幕總時長 ≥ 0.8 + 字數 / cps；動作後畫面太快換下一步時，凍結時間自動拉長
用途差別：操作說明的字幕帶步驟編號；功能展示不編號、章節字卡多一行「這能幫你做什麼」（chapter 的 sub），
  而且鏡頭會動（--zoom，video_zoom.py）：每一步在讀字幕的停格裡推近到要操作的地方，做完拉回全景；
  接下來的變化都還在近景裡（同一張表單連續填欄位）就留在近景橫移。推近、拉回、橫移都用貝茲緩動（慢 → 快 → 慢）。
需要：ffmpeg（skill 目錄 npm install 會裝 ffmpeg-static；或 PATH 上的 ffmpeg、環境變數 FFMPEG）、Pillow。
"""
from __future__ import annotations

import argparse
import datetime as _dt
import json
import os
import platform
import re
import shutil
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from deck_kit import MANUAL, SHOWCASE, TW, deck_filename  # noqa: E402
import video_zoom as vz  # noqa: E402

VIDEO_PURPOSES = (SHOWCASE, MANUAL)   # 可以選影片輸出的用途（Phase 0）
_VIDEO_TITLE = {MANUAL: "操作說明", SHOWCASE: "功能展示"}
BG = "0x050E1F"
MAX_MINUTES = 10.5                    # 超過就提醒拆成多支（一支一組流程）
# (字型檔, libass 用的字型名)：照順序找第一個有的
FONTS = [
    ([r"C:\Windows\Fonts\msjh.ttc", r"C:\Windows\Fonts\msjhbd.ttc"], "Microsoft JhengHei"),
    (["/System/Library/Fonts/PingFang.ttc"], "PingFang TC"),
    (["/System/Library/Fonts/STHeiti Medium.ttc"], "Heiti TC"),
    (["/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc", "/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc"],
     "Noto Sans CJK TC"),
    (["/usr/share/fonts/noto-cjk/NotoSansCJK-Regular.ttc", "/usr/share/fonts/noto-cjk/NotoSansCJK-Bold.ttc"], "Noto Sans CJK TC"),
]


def video_filename(tenant: str, app: str, made: _dt.date, purpose: str, part: str | None = None) -> str:
    """「AI GO 租戶名 App名 用途 YYYYMMDD.mp4」；拆成多支時日期後面接分集名。影片一個用途一支，不合併。"""
    if purpose not in VIDEO_PURPOSES:
        raise ValueError(f"影片只做 {'／'.join(VIDEO_PURPOSES)}，不認得「{purpose}」")
    name = deck_filename(tenant, app, made, "", [purpose])
    if part:
        name += " " + "".join("_" if ch in '<>:"/\\|?*' else ch for ch in part).strip()
    return name + ".mp4"


def contact_sheet(video: Path, total: float, out: Path, cells: int = 48) -> None:
    """成片總表（GV 檢查用）：平均取 cells 格排成 6 欄。"""
    rows = max(1, -(-cells // 6))
    run(["-i", str(video), "-vf", f"fps={cells / max(total, 1):.5f},scale=480:-2,tile=6x{rows}",
         "-frames:v", "1", "-update", "1", str(out)])


def ffmpeg_bin() -> str:
    """環境變數 FFMPEG → skill 的 node_modules/ffmpeg-static → PATH 上的 ffmpeg。"""
    env = os.environ.get("FFMPEG")
    if env:
        return env
    exe = "ffmpeg.exe" if platform.system() == "Windows" else "ffmpeg"
    here = HERE.parent / "node_modules" / "ffmpeg-static" / exe
    if here.exists():
        return str(here)
    found = shutil.which("ffmpeg")
    if found:
        return found
    raise SystemExit("找不到 ffmpeg：在 skill 目錄執行 npm install（會裝 ffmpeg-static），或安裝 ffmpeg、設環境變數 FFMPEG")


def pick_font() -> tuple[list[Path], str]:
    for files, name in FONTS:
        fs = [Path(f) for f in files if Path(f).exists()]
        if fs:
            return fs, name
    return [], "Noto Sans CJK TC"


def run(args: list[str], cwd: Path | None = None) -> str:
    p = subprocess.run([ffmpeg_bin(), "-hide_banner", "-nostdin", "-y", *args], cwd=cwd, capture_output=True, text=True,
                       encoding="utf-8", errors="replace")
    if p.returncode != 0:
        raise RuntimeError("ffmpeg 失敗：\n" + p.stderr[-2500:])
    return p.stderr


def probe(path: Path) -> tuple[float, int, int]:
    """(秒數, 寬, 高)。ffmpeg-static 沒附 ffprobe，直接把整支解碼一次讀最後的 time=。"""
    err = run(["-i", str(path), "-map", "0:v:0", "-c", "copy", "-f", "null", "-"])
    m = re.search(r"Stream #0:0.*?Video:.*?(\d{2,5})x(\d{2,5})", err)
    ts = re.findall(r"time=(\d+):(\d+):(\d+\.\d+)", err)
    h, mi, s = ts[-1]
    return int(h) * 3600 + int(mi) * 60 + float(s), int(m.group(1)), int(m.group(2))


def normalize(raw: Path, work: Path, fps: int) -> Path:
    """幀率不固定、沒有索引的素材（webm 等）：先轉成每秒一個關鍵幀的 mkv，後面切段才快。"""
    out = work / "norm.mkv"
    run(["-i", str(raw), "-vf", f"fps={fps}", "-c:v", "libx264", "-preset", "ultrafast", "-crf", "16", "-g", str(fps),
         "-pix_fmt", "yuv420p", str(out)])
    return out


def activity(frames, minpx: int = 12, thresh: int = 30) -> tuple[list[bool], list[tuple[int, int, int, int] | None]]:
    """逐格比對灰階畫面（PIL.Image 序列），回傳每格「有沒有在變」與變化範圍。
    變化像素 < minpx 或只是一條細直線（閃爍的輸入游標）都當沒變；打一個中文字就超過 minpx，所以打字不會被快轉。"""
    from PIL import ImageChops
    act: list[bool] = []
    boxes: list[tuple[int, int, int, int] | None] = []
    prev = None
    for f in frames:
        if prev is None:
            act.append(False); boxes.append(None)
        else:
            m = ImageChops.difference(f, prev).point(lambda v: 255 if v > thresh else 0)
            bb = m.getbbox()
            n = m.histogram()[255] if bb else 0
            caret = bb is not None and bb[2] - bb[0] <= 4 and bb[3] - bb[1] <= 61
            if n >= minpx and not caret:
                act.append(True); boxes.append((bb[0], bb[1], bb[2] - 1, bb[3] - 1))
            else:
                act.append(False); boxes.append(None)
        prev = f
    return act, boxes


def idle_spans(act: list[bool], boxes: list, af: int, dur: float, idle: float, area: int,
               busy_secs: float = 4.0, busy_area: float = 0.025) -> list[tuple[float, float]]:
    """「沒有在操作」的區間（可以快轉）。連續變化超過 busy_secs 秒、但都擠在畫面一小塊（< busy_area）：
    當成載入中的轉圈圖示，也算等待。"""
    act = list(act)
    i = 0
    while i < len(act):
        if not act[i]:
            i += 1; continue
        j, gap = i, 0
        while j + 1 < len(act) and gap <= 3:   # 容許中間斷 0.3 秒
            j += 1
            gap = 0 if act[j] else gap + 1
        j -= gap
        if (j - i + 1) / af >= busy_secs:
            bs = [b for b in boxes[i:j + 1] if b]
            ux0, uy0 = min(b[0] for b in bs), min(b[1] for b in bs)
            ux1, uy1 = max(b[2] for b in bs), max(b[3] for b in bs)
            if (ux1 - ux0 + 1) * (uy1 - uy0 + 1) < busy_area * area:
                for k in range(i + af // 2, j + 1):
                    act[k] = False
        i = j + 1
    out: list[tuple[float, float]] = []
    k = 0
    while k < len(act):
        if act[k]:
            k += 1; continue
        s = k
        while k < len(act) and not act[k]:
            k += 1
        a0, b0 = s / af, min(dur, k / af)
        if b0 - a0 >= idle:
            out.append((a0, b0))
    return out


def freezes(src: Path, idle: float, dur: float, w: int, h: int) -> list[tuple[float, float]]:
    """整支影片「沒有在操作」的區間。"""
    act, boxes, af, (aw, ah) = analyze(src, w, h)
    return idle_spans(act, boxes, af, dur, idle, aw * ah)


def analyze(src: Path, w: int, h: int) -> tuple[list[bool], list, int, tuple[int, int]]:
    """解碼成 10 fps、寬 ≤ 1280 的灰階逐格比對，回傳 (每格有沒有變, 變化範圍, 分析幀率, 分析解析度)。
    ffmpeg 的 freezedetect 看整格平均差異，一次貼上一串字的變化太小抓不到，所以不用它。"""
    from PIL import Image
    AF = 10
    aw = min(1280, w) // 2 * 2
    ah = round(h * aw / w) // 2 * 2
    p = subprocess.Popen([ffmpeg_bin(), "-hide_banner", "-nostdin", "-i", str(src), "-vf",
                          f"fps={AF},scale={aw}:{ah}:flags=area,format=gray", "-f", "rawvideo", "-"],
                         stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
    size = aw * ah

    def frames():
        while True:
            buf = p.stdout.read(size)
            if len(buf) < size:
                return
            yield Image.frombytes("L", (aw, ah), buf)
    act, boxes = activity(frames())
    p.stdout.close()
    p.wait()
    return act, boxes, AF, (aw, ah)


def find_magenta(src: Path, fps: int, secs: float = 6.0) -> float | None:
    p = subprocess.run([ffmpeg_bin(), "-hide_banner", "-nostdin", "-t", str(secs), "-i", str(src), "-vf", f"fps={fps},scale=16:9",
                        "-f", "rawvideo", "-pix_fmt", "rgb24", "-"], capture_output=True)
    fr = 16 * 9 * 3
    for i in range(len(p.stdout) // fr):
        px = p.stdout[i * fr:(i + 1) * fr]
        r, g, b = (sum(px[k::3]) / (16 * 9) for k in range(3))
        if r > 200 and b > 200 and g < 60:
            return i / fps
    return None


def text_len(t: str) -> float:
    return sum(1.0 if ord(c) > 0x2E80 else 0.45 for c in t if not c.isspace())


def anchor(ev: dict, fz: list[tuple[float, float]], dur: float, window: float = 20.0, think_gap: float = 2.5) -> float:
    """把事件時間對到「畫面真的開始變」的前一刻（凍結那一格要是動作前的畫面）。
    before：記在操作前（say）→ 若當下畫面靜止，取這段靜止的結尾（下一次變化）。
    after ：記在操作後（did）→ 往回找動作前那段思考停頓（≥ think_gap 秒的靜止）的結尾；
            中間較短的靜止多半是動作引起的連鎖變化（toast 出現又消失），跳過。
    at    ：腳本記的精確時間（record.mjs），不調整。"""
    t = min(max(ev["t"], 0.0), dur)
    when = ev.get("when", "at")
    if when == "at":
        return t
    pre = 0.15   # 靜止段的結尾＝偵測到變化的第一格（分析 10 fps），往前退一點
    cur = next(((a, b) for a, b in fz if a <= t < b), None)
    if when == "before":
        if cur and cur[1] - t <= window:
            return max(0.0, cur[1] - pre)
        return t
    limit = cur[0] if cur else t
    prev = [(a, b) for a, b in fz if b <= limit + 1e-6 and t - b <= window]
    if not prev:
        return t
    pick = next((b for a, b in reversed(prev) if b - a >= think_gap), prev[-1][1])
    return max(0.0, pick - pre)


def ass_time(s: float) -> str:
    cs = int(round(max(0.0, s) * 100))
    return f"{cs // 360000}:{cs // 6000 % 60:02d}:{cs // 100 % 60:02d}.{cs % 100:02d}"


def srt_time(s: float) -> str:
    ms = int(round(max(0.0, s) * 1000))
    return f"{ms // 3600000:02d}:{ms // 60000 % 60:02d}:{ms // 1000 % 60:02d},{ms % 1000:03d}"


def esc(t: str) -> str:
    return t.replace("\\", "＼").replace("{", "｛").replace("}", "｝").replace("\n", "\\N")


def circle(r: float) -> str:
    k = 0.5523 * r
    return (f"m {r} 0 b {r + k} 0 {2 * r} {r - k} {2 * r} {r} b {2 * r} {r + k} {r + k} {2 * r} {r} {2 * r} "
            f"b {r - k} {2 * r} 0 {r + k} 0 {r} b 0 {r - k} {r - k} 0 {r} 0")


def load_events(d: Path, sess: dict) -> list[dict]:
    """events.jsonl → 每個事件補上原始影片秒數 t（桌面錄影用系統時鐘對時）與錄影區域內座標 x/y。"""
    rx, ry = sess["region"][0], sess["region"][1]
    evs = []
    for line in (d / "events.jsonl").read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        e = json.loads(line)
        t0 = sess.get("video_start") or sess.get("launched") or 0
        if "t" not in e:
            e["t"] = e["ts"] - t0
        if "end" in e:                   # 這一步操作做完的時刻（record.mjs 的打字、選值）
            e["t_end"] = e["end"] - t0
        if "sx" in e:
            e["x"], e["y"] = e["sx"] - rx, e["sy"] - ry
        evs.append(e)
    return evs


def plan_clips(evs: list[dict], fz: list[tuple[float, float]], dur: float, *, idle: float, cps: float, fps: int,
               intro: bool = True, outro: bool = True, keep_head: bool = False) -> tuple[list[dict], float]:
    """剪輯表：切點＝每個事件的錨點。片段開頭若是步驟，就在前一段尾巴凍結（＝動作前的畫面）。
    第一個事件之前是準備動作（開視窗、登入、終端機）：預設剪掉。回傳 (依序的 clips, 總秒數)。"""
    head = 0.0 if keep_head or not evs else max(0.0, evs[0]["A"])
    cuts = sorted({head, dur, *[min(e["A"], dur) for e in evs]})
    clips: list[dict] = []
    if intro:
        clips.append({"type": "card", "dur": 3.2, "card": "intro"})
    ev_at: dict[float, list[dict]] = {}
    for e in evs:
        ev_at.setdefault(min(e["A"], dur), []).append(e)
    for ci in range(len(cuts) - 1):
        s, e_ = cuts[ci], cuts[ci + 1]
        for ev in ev_at.get(s, []):
            if ev["kind"] == "chapter":
                clips.append({"type": "card", "dur": 3.0 if ev.get("sub") else 2.4, "card": "chapter",
                              "text": ev["text"], "sub": ev.get("sub", "")})
        if e_ - s < 1 / fps:
            continue
        pieces = []  # (a, b, speed, skipped_seconds)
        t = s
        for fa, fb in fz:
            a0, b0 = max(fa, s), min(fb, e_)
            if b0 - a0 < idle:
                continue
            L = b0 - a0
            keep = 1.2 if L >= 4 else 0.6
            if a0 > t:
                pieces.append((t, a0, 1.0, 0))
            pieces.append((a0, b0, L / keep, L if L >= 4 else 0))
            t = b0
        if e_ > t:
            pieces.append((t, e_, 1.0, 0))
        pieces = [p for p in pieces if p[1] - p[0] >= 1 / fps]
        clips.append({"type": "video", "s": s, "e": e_, "pieces": pieces, "hold": 0.0,
                      "steps": [x for x in ev_at.get(s, []) if x["kind"] == "step"]})

    def out_len(c):
        return sum((p[1] - p[0]) / p[2] for p in c["pieces"])
    for ci, c in enumerate(clips):
        if c["type"] != "video" or not c["steps"]:
            continue
        text = " ".join(x["text"] for x in c["steps"] if x.get("text"))
        need = 0.8 + text_len(text) / cps
        hold = min(3.0, max(1.0, need * 0.55))
        play = out_len(c)
        if hold + play < need:
            hold = need - play
        prev = clips[ci - 1] if ci > 0 else None
        if prev is not None and prev["type"] == "video":
            prev["hold"] += hold          # 凍結前一段的最後一格＝動作前的畫面
            c["from_prev"] = prev
        else:
            c["pre_hold"] = hold          # 前面是字卡：凍結這段的第一格
    vids = [c for c in clips if c["type"] == "video"]
    if vids:
        vids[-1]["hold"] += 1.5           # 結尾停在最後畫面
    if outro:
        clips.append({"type": "card", "dur": 3.0, "card": "outro"})
    T = 0.0
    for c in clips:
        c["start"] = T
        if c["type"] == "card":
            T += c["dur"]
        else:
            c["pre"] = c.get("pre_hold", 0.0)
            c["play_start"] = T + c["pre"]
            T = c["play_start"] + out_len(c)
            c["hold_start"] = T
            T += c["hold"]
        c["end"] = T
    return clips, T


CAP_BAND = 0.8   # 操作點落在畫面最下面 20%（字幕列）時，這一步的字幕改放上方，免得蓋住要點的按鈕


def caption_on_top(x: float, y: float, zoom: float | None = None) -> bool:
    """操作點（0～1 的全畫面座標）會不會被底部字幕蓋住。推近時用近景裡的位置判斷（字幕在推近後才燒）。"""
    if zoom:
        bx, by, bs = vz.focus_box(x, y, zoom)
        y = (y - by) / bs
    return y > CAP_BAND


def src_to_out(clips: list[dict], t: float) -> float | None:
    """原始影片的 t 秒在成片的第幾秒（照剪輯表的快轉換算）；被剪掉的開頭回傳 None。"""
    vids = [c for c in clips if c["type"] == "video"]
    for i, c in enumerate(vids):
        if c["s"] <= t < c["e"] or (i == len(vids) - 1 and abs(t - c["e"]) < 1e-6):
            o = c["play_start"]
            for pa, pb, sp, _ in c["pieces"]:
                if t >= pb:
                    o += (pb - pa) / sp
                elif t > pa:
                    o += (t - pa) / sp
            return o
    return None


def main() -> int:
    for s in (sys.stdout, sys.stderr):
        try:
            s.reconfigure(encoding="utf-8")
        except Exception:
            pass
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--dir", required=True, help="record.mjs／record_desktop.py 的輸出資料夾")
    ap.add_argument("--purpose", default=MANUAL, choices=VIDEO_PURPOSES)
    ap.add_argument("--tenant", help="租戶名（預設讀 session.json 的 meta）")
    ap.add_argument("--app", help="App 名（預設讀 session.json 的 meta）")
    ap.add_argument("--made", help="製作日 YYYY-MM-DD（預設今天，台灣時間）")
    ap.add_argument("--title", help="片頭標題（預設「App名 用途」）")
    ap.add_argument("--subtitle", default="", help="片頭副標（例：示範帳號：店長）")
    ap.add_argument("--out", help="輸出檔（預設照檔名規則存在目前資料夾）")
    ap.add_argument("--part", help="超過 10 分鐘拆成多支時的分集名，接在檔名日期後（例：「1 新增與查詢」）")
    ap.add_argument("--size", default="1920x1080")
    ap.add_argument("--fps", type=int, default=30)
    ap.add_argument("--idle", type=float, default=1.2)
    ap.add_argument("--cps", type=float, default=5.0)
    ap.add_argument("--no-intro", action="store_true")
    ap.add_argument("--no-outro", action="store_true")
    ap.add_argument("--keep-head", action="store_true", help="保留第一個事件之前的畫面")
    ap.add_argument("--zoom", default="auto", choices=("auto", "on", "off"),
                    help="每一步推近鏡頭到要操作的地方、做完拉回（auto：功能展示開、操作說明關）")
    ap.add_argument("--zoom-scale", type=float, default=1.5, help="推近幾倍（預設 1.5；錄影用 --dsf 1.8 才不會糊）")
    ap.add_argument("--jobs", type=int, default=4)
    a = ap.parse_args()
    t_start = time.time()

    d = Path(a.dir).resolve()
    sess = json.loads((d / "session.json").read_text(encoding="utf-8"))
    meta = sess.get("meta") or {}
    tenant = a.tenant or meta.get("tenant") or "租戶"
    app = a.app or meta.get("app") or "App"
    made = _dt.date.fromisoformat(a.made) if a.made else _dt.datetime.now(TW).date()
    title = a.title or f"{app} {_VIDEO_TITLE[a.purpose]}"
    numbered = a.purpose == MANUAL
    out = Path(a.out).resolve() if a.out else Path.cwd() / video_filename(tenant, app, made, a.purpose, a.part)

    raw = d / sess["raw"]
    work = d / "_post"
    shutil.rmtree(work, ignore_errors=True); work.mkdir()
    OW, OH = (int(v) for v in a.size.split("x"))
    FPS = a.fps
    font_files, FONT = pick_font()

    src = raw if raw.suffix == ".mkv" else normalize(raw, work, FPS)
    dur, RW, RH = probe(src)
    act_flags, act_boxes, AF, asize = analyze(src, RW, RH)
    fz = idle_spans(act_flags, act_boxes, AF, dur, a.idle, asize[0] * asize[1])
    zoom = a.zoom == "on" or (a.zoom == "auto" and a.purpose == SHOWCASE)
    print(f"原始 {dur:.1f}s {RW}x{RH}，靜止 {len(fz)} 段共 {sum(b - a for a, b in fz):.1f}s")

    evs = load_events(d, sess)
    sync = next((e for e in evs if e["kind"] == "sync"), None)
    if sync:  # 舊式腳本錄影：找洋紅色那一格，把事件時間平移到影片時間
        hit = find_magenta(src, FPS)
        if hit is not None:
            for e in evs:
                e["t"] += hit - sync["t"]
        evs = [e for e in evs if e["kind"] != "sync"]
    if not any(e["kind"] == "step" for e in evs):
        raise SystemExit("events.jsonl 沒有任何步驟：錄影時要記字幕（record.mjs 的 v.click／v.say；record_desktop.py say／did）")
    for e in evs:
        e["A"] = anchor(e, fz, dur)
    evs.sort(key=lambda e: (e["A"], e["t"]))
    for i in range(1, len(evs)):  # 同一刻的多個事件保持先後
        evs[i]["A"] = max(evs[i]["A"], evs[i - 1]["A"])

    timeline, total = plan_clips(evs, fz, dur, idle=a.idle, cps=a.cps, fps=FPS, intro=not a.no_intro,
                                 outro=not a.no_outro, keep_head=a.keep_head)
    vids = [c for c in timeline if c["type"] == "video"]

    # 縮放到輸出畫面（等比、置中、補底色）
    sc = min(OW / RW, OH / RH)
    SW, SH = int(RW * sc) // 2 * 2, int(RH * sc) // 2 * 2
    PX, PY = (OW - SW) // 2, (OH - SH) // 2
    # 母片：要推近鏡頭時，各片段先用原始解析度（最多輸出的 2 倍）渲染，推近後才不會糊；不推近就等於輸出尺寸
    mk = min(2.0, max(1.0, 1 / sc)) if zoom else 1.0
    MW, MH = int(OW * mk) // 2 * 2, int(OH * mk) // 2 * 2
    msc = min(MW / RW, MH / RH)
    MSW, MSH = int(RW * msc) // 2 * 2, int(RH * msc) // 2 * 2
    MPX, MPY = (MW - MSW) // 2, (MH - MSH) // 2
    vf_fit = f"scale={MSW}:{MSH}:flags=lanczos,pad={MW}:{MH}:{MPX}:{MPY}:color={BG},fps={FPS},format=yuv420p"

    step_marks = []  # (字幕出現, 動作那一刻, 事件)：字幕從前一段尾巴的凍結開始
    for c in vids:
        for ev in c["steps"]:
            frm = c["from_prev"]["hold_start"] if "from_prev" in c else c["start"]
            step_marks.append((frm, c["play_start"], ev))
    chapters = [(c["start"], c["text"]) for c in timeline if c.get("card") == "chapter"]

    # ── 渲染各片段（平行），再無損接起來 ──
    enc = ["-c:v", "libx264", "-preset", "veryfast", "-crf", "18", "-pix_fmt", "yuv420p", "-r", str(FPS), "-an"]

    def frames(c):  # 每段的格數由時間軸的起訖取整決定，累計不漂移
        return round(c["end"] * FPS) - round(c["start"] * FPS)

    def render(i_c):
        i, c = i_c
        o = work / f"c{i:04d}.mp4"
        if c["type"] == "card":
            run(["-f", "lavfi", "-i", f"color=c={BG}:s={MW}x{MH}:r={FPS}:d={c['dur'] + 0.3:.3f}", "-frames:v", str(frames(c)), *enc, str(o)])
            return o
        ps = c["pieces"]
        n = len(ps)
        fc = f"[0:v]split={n}" + "".join(f"[s{k}]" for k in range(n)) + ";" if n > 1 else ""
        for k, (pa, pb, sp, _) in enumerate(ps):
            inp = f"[s{k}]" if n > 1 else "[0:v]"
            fc += f"{inp}trim=start={pa - c['s']:.4f}:end={pb - c['s']:.4f},setpts=(PTS-STARTPTS)/{sp:.5f}[p{k}];"
        fc += "".join(f"[p{k}]" for k in range(n)) + f"concat=n={n}:v=1:a=0,{vf_fit}"
        # 前後凍結寫在同一個 tpad（串兩個 tpad 前面那段凍結會不見）；尾巴多墊 0.3 秒，再用格數截齊
        fc += f",tpad=start_mode=clone:start_duration={c.get('pre', 0):.3f}:stop_mode=clone:stop_duration={c['hold'] + 0.3:.3f}[v]"
        run(["-ss", f"{c['s']:.4f}", "-t", f"{c['e'] - c['s'] + 0.2:.4f}", "-i", str(src), "-filter_complex", fc,
             "-map", "[v]", "-frames:v", str(frames(c)), *enc, str(o)])
        return o

    with ThreadPoolExecutor(max_workers=a.jobs) as ex:
        files = list(ex.map(render, enumerate(timeline)))
    (work / "list.txt").write_text("".join(f"file '{f.name}'\n" for f in files), encoding="utf-8")
    run(["-f", "concat", "-safe", "0", "-i", "list.txt", "-c", "copy", "joined.mp4"], cwd=work)

    # ── 字幕與字卡（ASS，品牌色：藍 #1F80FF、深底 #050E1F、青 #4DC9EC）──
    u = OH / 1080
    B = lambda v: int(round(v * u))  # noqa: E731
    lines = []
    fx_lines = []   # 點擊圈：推近鏡頭時要先燒在畫面上，跟著畫面一起放大（字幕、字卡在推近之後才燒，不跟著動）

    def dlg(st, en, style, text, layer=0):
        if en - st > 0.02:
            (fx_lines if zoom and style == "Fx" else lines).append(
                f"Dialogue: {layer},{ass_time(st)},{ass_time(en)},{style},,0,0,0,,{text}")

    bar = f"{{\\an7\\pos(0,0)\\p1\\bord0\\shad0\\1c&HFF801F&}}m 0 0 l {B(12)} 0 l {B(12)} {OH} l 0 {OH}{{\\p0}}"
    fad = "\\fad(300,300)"
    for c in timeline:
        st, en = c["start"], c["end"]
        if c.get("card") == "intro":
            dlg(st, en, "Bar", bar)
            dlg(st, en, "Label", f"{{\\an7\\pos({B(150)},{B(330)}){fad}}}AI GO · {_VIDEO_TITLE[a.purpose]}")
            dlg(st, en, "Title", f"{{\\an7\\pos({B(150)},{B(390)}){fad}}}{esc(title)}")
            if a.subtitle:
                dlg(st, en, "Sub", f"{{\\an7\\pos({B(150)},{B(500)}){fad}}}{esc(a.subtitle)}")
            dlg(st, en, "Label", f"{{\\an1\\pos({B(150)},{OH - B(110)}){fad}}}{esc(tenant)} · 製作日 {made:%Y-%m-%d}")
        elif c.get("card") == "chapter":
            n = chapters.index((c["start"], c["text"])) + 1
            dlg(st, en, "Bar", bar)
            dlg(st, en, "Label", f"{{\\an7\\pos({B(150)},{B(400)})\\fad(250,250)}}PART {n:02d}")
            dlg(st, en, "Title", f"{{\\an7\\pos({B(150)},{B(450)})\\fad(250,250)}}{esc(c['text'])}")
            if c.get("sub"):
                dlg(st, en, "Sub", f"{{\\an7\\pos({B(150)},{B(570)})\\fad(250,250)}}{esc(c['sub'])}")
        elif c.get("card") == "outro":
            dlg(st, en, "Bar", bar)
            dlg(st, en, "Label", f"{{\\an7\\pos({B(150)},{B(400)}){fad}}}AI GO")
            dlg(st, en, "Title", f"{{\\an7\\pos({B(150)},{B(450)}){fad}}}{esc(title)}")
            dlg(st, en, "Label", f"{{\\an1\\pos({B(150)},{OH - B(110)}){fad}}}Urfit Technology Co., Ltd. · ai-go.app")

    cap_on_top = lambda x, y: caption_on_top(x, y, a.zoom_scale if zoom else None)  # noqa: E731
    srt = []
    untils = []
    for k, (frm, act, ev) in enumerate(step_marks):
        nxt = step_marks[k + 1][0] if k + 1 < len(step_marks) else None
        until = nxt if nxt is not None else total
        for cs, _ in chapters:          # 下一步之前若有章節字卡，字幕在字卡前收掉
            if frm < cs < until:
                until = cs
        for c in timeline:              # 片尾字卡前也收掉
            if c.get("card") == "outro" and frm < c["start"] < until:
                until = c["start"]
        untils.append(until)
        if ev.get("text"):
            num = f"{{\\c&HECC94D&\\b1}}{k + 1}{{\\c&HFFFFFF&\\b0}} " if numbered else ""
            top = "{\\an8}" if "x" in ev and cap_on_top((PX + ev["x"] * sc) / OW, (PY + ev["y"] * sc) / OH) else ""
            dlg(frm, until, "Cap", top + num + esc(ev["text"]))
            srt.append((frm, until, ev["text"]))
        if "x" in ev:
            x, y = PX + ev["x"] * sc, PY + ev["y"] * sc
            r = B(30)
            dlg(frm, act + 0.6, "Fx", f"{{\\an7\\pos({x - r:.0f},{y - r:.0f})\\p1\\1a&HFF&\\3c&HFF801F&\\bord{B(5)}\\shad0"
                f"\\fad(150,200)}}{circle(r)}{{\\p0}}", 2)
            if ev.get("act", True):     # 只是指出位置（v.say 帶元素）不畫點擊點與擴散圈
                dot = B(7)
                dlg(frm, act + 0.6, "Fx", f"{{\\an7\\pos({x - dot:.0f},{y - dot:.0f})\\p1\\bord0\\shad0\\1c&HFF801F&"
                    f"\\fad(150,200)}}{circle(dot)}{{\\p0}}", 2)
                dlg(act, act + 0.55, "Fx", f"{{\\an5\\pos({x:.0f},{y:.0f})\\p1\\1a&HFF&\\3c&HFF801F&\\bord{B(4)}\\shad0"
                    f"\\fscx60\\fscy60\\t(0,550,\\fscx200\\fscy200\\3a&HFF&)}}{circle(r)}{{\\p0}}", 2)
    for c in vids:
        t = c["play_start"]
        for pa, pb, sp, skipped in c["pieces"]:
            ln = (pb - pa) / sp
            if skipped:
                dlg(t, t + ln, "Fast", f"{{\\an9\\pos({OW - B(40)},{B(36)})}}快轉 ▶▶ 略過 {skipped:.0f} 秒")
            t += ln

    # ── 鏡頭（功能展示）：每一步推近到要操作的地方，做完拉回；接下來的變化都還在近景裡就留著、橫移到下一步 ──
    keys = None
    if zoom:
        cand: list[dict | None] = []
        for k, (frm, act, ev) in enumerate(step_marks):
            if "x" not in ev:
                cand.append(None); continue
            rel = act + 0.6
            done = src_to_out(timeline, ev["t_end"]) if "t_end" in ev else None
            if done is not None:        # 打字、選值：做完才拉回
                rel = max(rel, done + 0.4)
            cand.append({"frm": frm, "act": act, "rel": rel, "limit": min(untils[k], total - 0.2), "A": ev["A"],
                         "x": (PX + ev["x"] * sc) / OW, "y": (PY + ev["y"] * sc) / OH})
        for k, f in enumerate(cand):
            nxt = cand[k + 1] if k + 1 < len(cand) else None
            if not f or not nxt or untils[k] < nxt["frm"] - 1e-6 or nxt["frm"] - f["rel"] > 2.5:
                continue
            bx, by, bs = vz.focus_box(f["x"], f["y"], a.zoom_scale)
            view = ((bx * OW - PX) / SW, (by * OH - PY) / SH, ((bx + bs) * OW - PX) / SW, ((by + bs) * OH - PY) / SH)
            f["chain"] = vz.reveal_time(act_boxes, AF, f["A"], nxt["A"], view, asize) is None
        keys = vz.plan_camera([f for f in cand if f], zoom=a.zoom_scale)

    def style(name, size, bold, color, align, outline_col="&H00000000", border=0, outline=0, margin_v=0):
        return (f"Style: {name},{FONT},{B(size)},{color},&H000000FF,{outline_col},&H80000000,{-1 if bold else 0},0,0,0,"
                f"100,100,0,0,{border},{outline},0,{align},{B(80)},{B(80)},{B(margin_v)},1")
    ass = lambda body: "\n".join([  # noqa: E731
        "[Script Info]", "ScriptType: v4.00+", f"PlayResX: {OW}", f"PlayResY: {OH}", "WrapStyle: 0",
        "ScaledBorderAndShadow: yes", "", "[V4+ Styles]",
        "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, "
        "StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding",
        style("Cap", 46, True, "&H00FFFFFF", 2, "&H001F0E05", 3, B(16), 56),
        style("Title", 84, True, "&H00FFFFFF", 7),
        style("Sub", 40, False, "&H00E0C4AF", 7),
        style("Label", 30, True, "&H00ECC94D", 7),
        style("Bar", 10, False, "&H00FF801F", 7),
        style("Fx", 10, False, "&H00FF801F", 7),
        style("Fast", 30, True, "&H00FFFFFF", 9, "&H40FF801F", 3, B(10)),
        "", "[Events]", "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text", *body, ""])
    (work / "captions.ass").write_text(ass(lines), encoding="utf-8-sig")
    (work / "fx.ass").write_text(ass(fx_lines), encoding="utf-8-sig")
    (work / "fonts").mkdir(exist_ok=True)  # libass 在 Windows 讀不到含磁碟代號的 fontsdir：複製到工作夾用相對路徑
    for f in font_files:
        shutil.copy(f, work / "fonts" / f.name)

    meta_lines = [";FFMETADATA1", f"title={title}"]
    marks = ([(0.0, "片頭")] if not a.no_intro else []) + chapters
    for i, (st, name) in enumerate(marks):
        en = marks[i + 1][0] if i + 1 < len(marks) else total
        meta_lines += ["[CHAPTER]", "TIMEBASE=1/1000", f"START={int(st * 1000)}", f"END={int(en * 1000)}", f"title={name}"]
    (work / "chapters.txt").write_text("\n".join(meta_lines) + "\n", encoding="utf-8")

    out.parent.mkdir(parents=True, exist_ok=True)
    tmp = work / "final.mp4"
    final = ["-i", "chapters.txt", "-map_metadata", "1", "-map_chapters", "1", "-map", "0:v",
             "-vf", "subtitles=captions.ass:fontsdir=fonts", "-c:v", "libx264", "-preset", "medium", "-crf", "22"]
    tail = ["-pix_fmt", "yuv420p", "-movflags", "+faststart"]
    if zoom:
        vz.zoom_pass(ffmpeg_bin(), work, keys, src="joined.mp4", master=(MW, MH), out_size=(OW, OH), fps=FPS,
                     pre_vf="subtitles=fx.ass:fontsdir=fonts", enc_args=[*final, *tail], out_name=tmp.name, jobs=a.jobs)
    else:
        run(["-i", "joined.mp4", *final, "-tune", "stillimage", *tail, tmp.name], cwd=work)
    shutil.move(str(tmp), out)
    out.with_suffix(".srt").write_text("".join(f"{i + 1}\n{srt_time(s)} --> {srt_time(e)}\n{t}\n\n"
                                               for i, (s, e, t) in enumerate(srt)), encoding="utf-8")
    (d / "edit.json").write_text(json.dumps({"raw_seconds": dur, "out_seconds": total, "freezes": fz, "events": evs, "camera": keys,
                                             "clips": [{k: v for k, v in c.items() if k != "from_prev"} for c in timeline]},
                                            ensure_ascii=False, indent=1, default=str), encoding="utf-8")
    contact_sheet(out, total, d / "sheet.png")
    print(f"完成 {out}（{total:.1f}s，原始 {dur:.1f}s，{out.stat().st_size / 1e6:.1f} MB，耗時 {time.time() - t_start:.0f}s）")
    print(f"成片總表 {d / 'sheet.png'}（GV：逐格看字幕與畫面對不對）")
    if total > MAX_MINUTES * 60:
        print(f"注意：影片 {total / 60:.1f} 分鐘，超過 10 分鐘——照 references/video.md 拆成多支（一支一組流程）")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
