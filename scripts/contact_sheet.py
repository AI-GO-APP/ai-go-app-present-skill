# -*- coding: utf-8 -*-
"""把多張圖拼成總表，一次檢查（截圖驗收、簡報預覽都用它）。

用法：
  python scripts/contact_sheet.py shots/*.png --cols 3 --out disc/sheet    # 截圖總表（每 9 張一張，左上角標檔名）
  python scripts/contact_sheet.py preview/p*.png --cols 3 --rows 2 --out disc/pv   # 簡報預覽（每 6 頁一張）
需要 Pillow（pip install pillow）。
"""
import argparse
import glob
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont


def font(size):
    for f in ("C:/Windows/Fonts/msjh.ttc", "/System/Library/Fonts/PingFang.ttc", "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc"):
        if Path(f).exists():
            return ImageFont.truetype(f, size)
    return ImageFont.load_default()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("files", nargs="+")
    ap.add_argument("--cols", type=int, default=3)
    ap.add_argument("--rows", type=int, default=3)
    ap.add_argument("--cell", default="800x450", help="每格大小，例 800x450")
    ap.add_argument("--out", default="sheet")
    ap.add_argument("--no-label", action="store_true")
    a = ap.parse_args()
    files = sorted({f for g in a.files for f in glob.glob(g)})
    files = [f for f in files if not Path(f).name.startswith("_fail")]
    W, H = (int(x) for x in a.cell.split("x"))
    per = a.cols * a.rows
    fnt = font(26)
    Path(a.out).parent.mkdir(parents=True, exist_ok=True)
    for i in range(0, len(files), per):
        sheet = Image.new("RGB", (W * a.cols + 6 * (a.cols - 1), H * a.rows + 6 * (a.rows - 1)), "#888")
        d = ImageDraw.Draw(sheet)
        for k, f in enumerate(files[i:i + per]):
            im = Image.open(f).convert("RGB")
            im.thumbnail((W, H))
            x, y = (k % a.cols) * (W + 6), (k // a.cols) * (H + 6)
            sheet.paste(Image.new("RGB", (W, H), "white"), (x, y))
            sheet.paste(im, (x, y))
            if not a.no_label:
                label = Path(f).stem
                d.rectangle([x, y, x + 12 + 15 * len(label), y + 34], fill="yellow")
                d.text((x + 5, y + 2), label, fill="black", font=fnt)
        out = f"{a.out}{i // per + 1}.png"
        sheet.save(out)
        print(out)


if __name__ == "__main__":
    main()
