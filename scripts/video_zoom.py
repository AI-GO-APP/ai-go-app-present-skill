"""功能展示影片的鏡頭：每一步推近（zoom in）到要操作的地方、做完拉回（zoom out），連續幾步在同一區就留在近景橫移。
推近、拉回、橫移都用 cubic-bezier 緩動（慢 → 快 → 慢），不是等速。video_post.py 用；tests/test_video_zoom.py 測。

鏡頭狀態 = (x0, y0, s)：畫面上看得到的範圍，左上角 (x0, y0)、邊長比例 s，都是 0～1（全景 = (0, 0, 1)；推近 1.5 倍 s = 1/1.5）。
用比例不用像素，母片解析度換了不用改。
"""
from __future__ import annotations

import subprocess
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

FULL = (0.0, 0.0, 1.0)


def bezier_ease(x1: float, y1: float, x2: float, y2: float):
    """CSS 的 cubic-bezier(x1, y1, x2, y2)：時間進度 0～1 → 動畫進度 0～1。"""
    def bx(t: float) -> float:
        return 3 * (1 - t) ** 2 * t * x1 + 3 * (1 - t) * t * t * x2 + t ** 3

    def by(t: float) -> float:
        return 3 * (1 - t) ** 2 * t * y1 + 3 * (1 - t) * t * t * y2 + t ** 3

    def ease(p: float) -> float:
        if p <= 0:
            return 0.0
        if p >= 1:
            return 1.0
        lo, hi = 0.0, 1.0
        for _ in range(40):            # x(t) 單調遞增：二分法解 t
            mid = (lo + hi) / 2
            if bx(mid) < p:
                lo = mid
            else:
                hi = mid
        return by((lo + hi) / 2)
    return ease


EASE = bezier_ease(0.65, 0.0, 0.35, 1.0)


def focus_box(x: float, y: float, zoom: float) -> tuple[float, float, float]:
    """以 (x, y)（0～1）為中心推近 zoom 倍的鏡頭範圍；靠邊時整個範圍推回畫面內（不露出畫面外）。"""
    s = 1.0 / max(1.0, zoom)
    x0 = min(max(x - s / 2, 0.0), 1.0 - s)
    y0 = min(max(y - s / 2, 0.0), 1.0 - s)
    return (x0, y0, s)


def reveal_time(boxes: list, af: int, t0: float, t1: float, view: tuple[float, float, float, float], size: tuple[int, int],
                min_frac: float = 0.06, margin: float = 0.02) -> float | None:
    """t0～t1（原始影片秒）之間，畫面有沒有「一大塊變化跑到鏡頭範圍外」——彈出視窗、換頁、列表更新。
    有：回傳那一刻（鏡頭要拉回全景才看得到結果）；沒有（變化都在近景裡，例如在欄位裡打字）：None。
    boxes 是 video_post.activity() 的每格變化範圍（分析解析度 size 的像素）；view 是鏡頭範圍 (x0, y0, x1, y1)，
    原始畫面的 0～1 比例。小於畫面 min_frac 的變化（游標、提示訊息）不算。"""
    w, h = size
    vx0, vy0, vx1, vy1 = view
    for i in range(max(0, int(t0 * af)), min(len(boxes), int(t1 * af) + 1)):
        b = boxes[i]
        if not b:
            continue
        if (b[2] - b[0] + 1) * (b[3] - b[1] + 1) < min_frac * w * h:
            continue
        if (b[0] / w < vx0 - margin or b[1] / h < vy0 - margin or (b[2] + 1) / w > vx1 + margin or (b[3] + 1) / h > vy1 + margin):
            return i / af
    return None


def plan_camera(focuses: list[dict], *, zoom: float = 1.5, t_in: float = 0.7, t_out: float = 0.7, t_pan: float = 0.8,
                lead: float = 0.15) -> list[tuple[float, tuple[float, float, float]]]:
    """鏡頭關鍵格 [(成片秒, 狀態)]，時間遞增；兩格之間用 EASE 內插（camera_at）。

    focuses：依時間排好的每一步，成片秒：
      frm   字幕出現（畫面停在動作前）    act  動作那一刻
      rel   可以開始拉回的時刻            limit  拉回最晚要在這之前結束（下一步、字卡、片尾）
      x, y  要操作的位置（0～1）          chain  True＝做完不拉回，直接橫移到下一步
    推近在 frm 之後 lead 秒開始、動作前結束（讀字幕的那段停格裡推近）；太短（< 0.5 秒）的停格不推。"""
    keys: list[tuple[float, tuple[float, float, float]]] = [(0.0, FULL)]

    def add(t: float, st: tuple[float, float, float]) -> float:
        t = max(t, keys[-1][0])
        if st != keys[-1][1] or t > keys[-1][0]:
            keys.append((t, st))
        return t

    zoomed = False
    for i, f in enumerate(focuses):
        box = focus_box(f["x"], f["y"], zoom)
        if not zoomed:
            if f["act"] - f["frm"] < 0.5:
                continue
            t0 = add(f["frm"] + lead, FULL)
            add(max(t0 + 0.3, min(t0 + t_in, f["act"] - 0.05)), box)
            zoomed = True
        nxt = focuses[i + 1] if i + 1 < len(focuses) else None
        if f.get("chain") and nxt is not None:
            # 橫移跟著游標走：在下一步字幕出現前開始，游標到位後一點點結束
            t0 = add(max(f["act"] + 0.3, nxt["frm"] - t_pan + 0.1), box)
            add(max(t0 + 0.3, nxt["frm"] + 0.1), focus_box(nxt["x"], nxt["y"], zoom))
            continue
        rel = max(f["act"] + 0.2, min(f["rel"], f["limit"] - t_out))
        t0 = add(rel, box)
        add(t0 + max(0.25, min(t_out, f["limit"] - t0)), FULL)
        zoomed = False
    return keys


def camera_at(keys: list[tuple[float, tuple[float, float, float]]], t: float) -> tuple[float, float, float]:
    """t（成片秒）那一刻的鏡頭狀態。"""
    if t <= keys[0][0]:
        return keys[0][1]
    for (ta, a), (tb, b) in zip(keys, keys[1:]):
        if t < tb:
            if a == b or tb <= ta:
                return a
            p = EASE((t - ta) / (tb - ta))
            return tuple(a[k] + (b[k] - a[k]) * p for k in range(3))  # type: ignore[return-value]
    return keys[-1][1]


def zoom_pass(ffmpeg: str, work: Path, keys: list, *, src: str, master: tuple[int, int], out_size: tuple[int, int], fps: int,
              pre_vf: str, enc_args: list[str], out_name: str, jobs: int = 4) -> None:
    """逐格套鏡頭：ffmpeg 解碼（pre_vf 先燒上點擊圈，圈會跟著畫面一起放大）→ Pillow 裁切縮放 → ffmpeg 編碼（enc_args 燒字幕）。
    用 Pillow 是因為裁切範圍可以帶小數（推近時不會一格一格抖），緩動也算得準；ffmpeg 的 zoompan 只能整數像素。"""
    from PIL import Image
    mw, mh = master
    ow, oh = out_size
    size = mw * mh * 3
    with open(work / "zoom_dec.log", "wb") as dlog, open(work / "zoom_enc.log", "wb") as elog:
        dec = subprocess.Popen([ffmpeg, "-hide_banner", "-nostdin", "-i", src, "-vf", pre_vf, "-f", "rawvideo", "-pix_fmt", "rgb24", "-"],
                               cwd=work, stdout=subprocess.PIPE, stderr=dlog)
        enc = subprocess.Popen([ffmpeg, "-hide_banner", "-y", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{ow}x{oh}", "-r", str(fps),
                                "-i", "-", *enc_args, out_name], cwd=work, stdin=subprocess.PIPE, stderr=elog)

        def one(job: tuple[int, bytes]) -> bytes:
            i, buf = job
            x0, y0, s = camera_at(keys, (i + 0.5) / fps)
            if s >= 1.0 and (mw, mh) == (ow, oh):
                return buf
            im = Image.frombuffer("RGB", (mw, mh), buf)
            return im.resize((ow, oh), Image.BICUBIC, box=(x0 * mw, y0 * mh, (x0 + s) * mw, (y0 + s) * mh)).tobytes()

        n = 0
        try:
            with ThreadPoolExecutor(max_workers=jobs) as ex:
                while True:
                    batch = []
                    for _ in range(jobs * 2):
                        buf = dec.stdout.read(size)
                        if len(buf) < size:
                            break
                        batch.append((n, buf)); n += 1
                    if not batch:
                        break
                    for res in ex.map(one, batch):
                        enc.stdin.write(res)
            enc.stdin.close()
        except (BrokenPipeError, OSError):
            pass
        dec.stdout.close()
        rc_d, rc_e = dec.wait(), enc.wait()
    if rc_e != 0 or n == 0:
        log = (work / ("zoom_enc.log" if rc_e != 0 else "zoom_dec.log")).read_text(encoding="utf-8", errors="replace")
        raise RuntimeError(f"鏡頭後製失敗（解碼 {rc_d}／編碼 {rc_e}，{n} 格）：\n{log[-2500:]}")
