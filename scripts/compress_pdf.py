# -*- coding: utf-8 -*-
"""整份 PDF 壓縮：超過上限（預設 20 MB）時縮小檔案，並驗證成品是可以單獨寄出的獨立檔案。

用法：
    python scripts/compress_pdf.py "AI GO 租戶名 App名 用途 YYYYMMDD.pdf"            # 超過 20 MB 才壓
    python scripts/compress_pdf.py 手冊.pdf --max-mb 15 --keep-original disc     # 自訂上限、原檔存哪
    python scripts/compress_pdf.py 手冊.pdf --check                              # 只做獨立性檢查，不壓
    python scripts/compress_pdf.py 手冊.pdf --json                               # 機器可讀結果

render.mjs 輸出 PDF 後若超過上限會自動呼叫本腳本，一般不用手動跑。

壓縮方式（依序嘗試，第一個壓到上限以內、且通過驗證的就採用）：
  1. 有 Ghostscript（gs／gswin64c）→ pdfwrite /printer、/ebook
  2. pypdf（需要 pypdf＋Pillow）→ 無損整理（內容串流壓縮、重複物件合併），
     再依序把內嵌圖片重編成 JPEG 品質 85 → 75 → 65 → 60（後兩階同時把長邊縮到 2560／1920）
每一個候選都要通過驗證：頁數、頁面尺寸、每頁圖片數、內部連結數、書籤都和原檔一致，且沒有外部參照。

結果：
  exit 0：已在上限以內（或本來就沒超過）。正式檔名＝壓縮後的檔案；原檔搬到 --keep-original。
  exit 2：壓到底線仍超過上限。正式檔名＝最小的那一版（仍可交付），但要先問使用者（見 references/workflow.md P7）。
  exit 1：錯誤，或檔案不是獨立檔案（有外部參照、字型未內嵌）。
"""
from __future__ import annotations

import argparse
import io
import json
import logging
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

MB = 1024 * 1024
DEFAULT_MAX_MB = 20
# (標籤, JPEG 品質, 長邊上限 px)；None＝不縮尺寸。最後一階是畫質底線，不再往下降。
PYPDF_LADDER = [("jpeg85", 85, None), ("jpeg75", 75, None), ("jpeg65-2560", 65, 2560), ("jpeg60-1920", 60, 1920)]
GS_LADDER = [("gs-printer", "/printer"), ("gs-ebook", "/ebook")]
MIN_IMAGE_BYTES = 30 * 1024      # 小圖（圖標、logo）不動
logging.getLogger("pypdf").setLevel(logging.ERROR)   # Chrome 產的 PDF 常有無害的 trailer 警告，不要洗版


def fmt_mb(n: int) -> str:
    return f"{n / MB:.1f} MB"


# ───────────── 檢查 ─────────────
def _pdf():
    try:
        import pypdf  # noqa: F401
        return pypdf
    except ImportError:
        return None


def _walk(obj, seen, visit):
    """走訪整份 PDF 的物件圖（避開循環）。"""
    from pypdf.generic import ArrayObject, DictionaryObject, IndirectObject
    stack = [obj]
    while stack:
        o = stack.pop()
        if isinstance(o, IndirectObject):
            key = (o.idnum, o.generation)
            if key in seen:
                continue
            seen.add(key)
            try:
                o = o.get_object()
            except Exception:  # noqa: BLE001 壞掉的參照不影響其他檢查
                continue
        if isinstance(o, DictionaryObject):
            visit(o)
            stack.extend(o.values())
        elif isinstance(o, ArrayObject):
            stack.extend(o)


def inspect_pdf(path: Path) -> dict:
    """結構摘要：頁數、頁面尺寸、每頁圖片數、內部／外部連結、書籤數、外部參照、未內嵌字型、每頁圖片位元組。"""
    from pypdf import PdfReader
    r = PdfReader(str(path))
    info = dict(pages=len(r.pages), sizes=[], images=[], image_bytes=[], internal_links=0, uri_links=0,
                outline=0, external=[], unembedded_fonts=set())
    for page in r.pages:
        info["sizes"].append((round(float(page.mediabox.width)), round(float(page.mediabox.height))))
        n, nbytes = 0, 0
        for img in _page_images(page):
            n += 1
            nbytes += len(img.get_object()._data or b"")
        info["images"].append(n)
        info["image_bytes"].append(nbytes)
        for a in page.get("/Annots") or []:
            a = a.get_object()
            if a.get("/Subtype") != "/Link":
                continue
            act = a.get("/A")
            act = act.get_object() if act is not None else None
            if a.get("/Dest") is not None or (act is not None and act.get("/S") == "/GoTo"):
                info["internal_links"] += 1
            elif act is not None and act.get("/S") == "/URI":
                info["uri_links"] += 1

    def count_outline(items):
        c = 0
        for it in items:
            c += count_outline(it) if isinstance(it, list) else 1
        return c
    try:
        info["outline"] = count_outline(r.outline)
    except Exception:  # noqa: BLE001
        info["outline"] = 0

    def visit(d):
        t, s = d.get("/Type"), d.get("/S")
        if t == "/Filespec" or "/FS" in d and d.get("/FS") == "/URL":
            info["external"].append("外部檔案參照（Filespec）")
        if s in ("/GoToR", "/Launch", "/ImportData", "/GoToE"):
            info["external"].append(f"外部動作 {s}")
        if t == "/Font" and d.get("/Subtype") in ("/TrueType", "/Type1", "/CIDFontType0", "/CIDFontType2"):
            fd = d.get("/FontDescriptor")
            fd = fd.get_object() if fd is not None else None
            if fd is not None and not any(k in fd for k in ("/FontFile", "/FontFile2", "/FontFile3")):
                info["unembedded_fonts"].add(str(d.get("/BaseFont")))
    _walk(r.trailer["/Root"], set(), visit)
    info["unembedded_fonts"] = sorted(info["unembedded_fonts"])
    info["external"] = sorted(set(info["external"]))
    return info


def _page_images(page):
    """一頁用到的所有圖片 XObject（含 Form XObject 裡面的），回傳 IndirectObject 清單（去重）。"""
    from pypdf.generic import IndirectObject
    out, seen = [], set()

    def scan(res):
        res = res.get_object() if res is not None else None
        if not res:
            return
        xo = res.get("/XObject")
        xo = xo.get_object() if xo is not None else None
        for ref in (xo or {}).values():
            if not isinstance(ref, IndirectObject):
                continue
            key = ref.idnum
            if key in seen:
                continue
            seen.add(key)
            o = ref.get_object()
            if o.get("/Subtype") == "/Image":
                out.append(ref)
            elif o.get("/Subtype") == "/Form":
                scan(o.get("/Resources"))
    scan(page.get("/Resources"))
    return out


def self_contained_issues(info: dict) -> list[str]:
    issues = list(info["external"])
    if info["unembedded_fonts"]:
        issues.append("字型未內嵌：" + "、".join(info["unembedded_fonts"][:5]))
    return issues


def verify(orig: dict, new: dict) -> list[str]:
    """壓縮後的檔案必須和原檔同樣完整：頁數、尺寸、圖片、連結、書籤一個都不能少。"""
    bad = []
    if new["pages"] != orig["pages"]:
        bad.append(f"頁數 {orig['pages']} → {new['pages']}")
    if new["sizes"] != orig["sizes"]:
        bad.append("頁面尺寸改變")
    if new["images"] != orig["images"]:
        diff = [i + 1 for i, (a, b) in enumerate(zip(orig["images"], new["images"])) if a != b]
        bad.append("圖片數不一致（第 " + "、".join(map(str, diff[:8])) + " 頁）")
    if new["internal_links"] < orig["internal_links"]:
        bad.append(f"內部連結 {orig['internal_links']} → {new['internal_links']}")
    if new["outline"] < orig["outline"]:
        bad.append(f"書籤 {orig['outline']} → {new['outline']}")
    bad += self_contained_issues(new)
    return bad


# ───────────── 壓縮器 ─────────────
def find_gs() -> str | None:
    for name in ("gs", "gswin64c", "gswin32c"):
        p = shutil.which(name)
        if p:
            return p
    if os.name == "nt":
        for root in (Path(os.environ.get("ProgramFiles", r"C:\Program Files")) / "gs",):
            for exe in sorted(root.glob("gs*/bin/gswin64c.exe"), reverse=True):
                return str(exe)
    return None


def compress_gs(gs: str, src: Path, dst: Path, setting: str) -> None:
    subprocess.run([gs, "-sDEVICE=pdfwrite", "-dCompatibilityLevel=1.6", f"-dPDFSETTINGS={setting}",
                    "-dNOPAUSE", "-dBATCH", "-dQUIET", "-dDetectDuplicateImages=true",
                    f"-sOutputFile={dst}", str(src)], check=True, timeout=600)


def compress_pypdf(src: Path, dst: Path, quality: int | None, max_px: int | None) -> None:
    """quality=None：只做無損整理。否則把每張夠大的圖重編成 JPEG（有變小才換）。"""
    from pypdf import PdfWriter
    w = PdfWriter(clone_from=str(src))
    if quality is not None:
        from PIL import Image
        done = set()
        for page in w.pages:
            for ref in _page_images(page):
                if ref.idnum in done:
                    continue
                done.add(ref.idnum)
                obj = ref.get_object()
                old = len(obj._data or b"")
                if old < MIN_IMAGE_BYTES or obj.get("/ImageMask"):
                    continue
                img = _to_rgb(_decode(obj), Image)
                if img is None:
                    continue
                if max_px and max(img.size) > max_px:
                    k = max_px / max(img.size)
                    img = img.resize((max(1, round(img.width * k)), max(1, round(img.height * k))), Image.LANCZOS)
                buf = io.BytesIO()
                img.save(buf, "JPEG", quality=quality, optimize=True)
                if buf.tell() >= old * 0.95:
                    continue
                _replace_image(ref, img, quality)
    for page in w.pages:
        page.compress_content_streams(level=9)
    try:        # pypdf 6.x 新參數名；舊版退回舊名
        w.compress_identical_objects(remove_duplicates=True, remove_unreferenced=True)
    except TypeError:
        w.compress_identical_objects(remove_identicals=True, remove_orphans=True)
    with open(dst, "wb") as f:
        w.write(f)


def _decode(obj):
    from pypdf.generic._image_xobject import _xobj_to_image
    try:
        return _xobj_to_image(obj)[2]
    except Exception:  # noqa: BLE001 解不開的色彩空間就不動
        return None


def _to_rgb(img, Image):
    if img is None:
        return None
    if img.mode in ("RGBA", "LA", "PA") or (img.mode == "P" and "transparency" in img.info):
        rgba = img.convert("RGBA")
        bg = Image.new("RGB", rgba.size, (255, 255, 255))     # 透明處墊白，避免 JPEG 變黑底
        bg.paste(rgba, mask=rgba.split()[-1])
        return bg
    if img.mode in ("RGB", "L"):
        return img
    return img.convert("RGB")


def _replace_image(ref, img, quality):
    """用 JPEG 版取代圖片物件（同一個物件編號，所有引用它的頁一起換）。"""
    from pypdf import PdfReader
    from pypdf.generic import NameObject
    buf = io.BytesIO()
    img.save(buf, "PDF", quality=quality)
    new = PdfReader(buf).pages[0].images[0].indirect_reference.get_object()
    obj = ref.get_object()
    for k in list(obj.keys()):
        if k not in ("/Type", "/Subtype"):
            del obj[k]
    for k, v in new.items():
        if k in ("/Length",):
            continue
        obj[NameObject(k)] = v if not hasattr(v, "get_object") else v.get_object()
    obj._data = new._data
    obj[NameObject("/Filter")] = NameObject("/DCTDecode")


# ───────────── 主流程 ─────────────
def heaviest_pages(info: dict, n=5) -> list[tuple[int, int]]:
    ranked = sorted(enumerate(info["image_bytes"], 1), key=lambda x: -x[1])
    return [(p, b) for p, b in ranked[:n] if b]


def run(pdf: Path, max_mb: float, keep: Path | None, force=False, log=print) -> dict:
    limit = int(max_mb * MB)
    size0 = pdf.stat().st_size
    orig = inspect_pdf(pdf)
    res = dict(file=str(pdf), limit_mb=max_mb, original=size0, final=size0, step=None, over=False,
               heaviest=heaviest_pages(orig), issues=self_contained_issues(orig), tried=[])
    if res["issues"]:
        log("✗ 不是獨立檔案：" + "；".join(res["issues"]))
    if size0 <= limit and not force:
        log(f"PDF {fmt_mb(size0)}，未超過 {max_mb:g} MB，不壓縮")
        return res

    log(f"PDF {fmt_mb(size0)} 超過 {max_mb:g} MB → 整份壓縮")
    steps = []
    gs = find_gs()
    if gs:
        steps += [(lbl, lambda s, d, st=st: compress_gs(gs, s, d, st)) for lbl, st in GS_LADDER]
    if _pdf():
        steps.append(("lossless", lambda s, d: compress_pypdf(s, d, None, None)))
        steps += [(lbl, lambda s, d, q=q, m=m: compress_pypdf(s, d, q, m)) for lbl, q, m in PYPDF_LADDER]
    if not steps:
        raise SystemExit("沒有可用的壓縮工具：pip install pypdf pillow（或安裝 Ghostscript）")

    tmp = Path(tempfile.mkdtemp(prefix="present-pdf-"))
    best = None
    try:
        for lbl, fn in steps:
            out = tmp / f"{lbl}.pdf"
            try:
                fn(pdf, out)
            except Exception as e:  # noqa: BLE001 這一階失敗就試下一階
                log(f"  {lbl}：失敗（{str(e)[:120]}）")
                res["tried"].append(dict(step=lbl, error=str(e)[:200]))
                continue
            sz = out.stat().st_size
            bad = verify(orig, inspect_pdf(out))
            res["tried"].append(dict(step=lbl, size=sz, problems=bad))
            log(f"  {lbl}：{fmt_mb(sz)}" + (f"（不採用：{'；'.join(bad)}）" if bad else ""))
            if bad:
                continue
            if best is None or sz < best[1]:
                best = (out, sz, lbl)
            if sz <= limit:
                break
        if best is None or best[1] >= size0:
            log("✗ 壓不下來：每一階都沒有變小或沒通過驗證，保留原檔")
            res["over"] = size0 > limit
            return res
        out, sz, lbl = best
        if keep is not None:
            keep.mkdir(parents=True, exist_ok=True)
            backup = keep / (pdf.stem + ".original.pdf")
            shutil.copy2(pdf, backup)
            res["original_kept"] = str(backup)
        shutil.copyfile(out, pdf)
        res.update(final=sz, step=lbl, over=sz > limit)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    if res["over"]:
        log(f"⚠ 壓到畫質底線（{res['step']}）仍有 {fmt_mb(res['final'])}，超過 {max_mb:g} MB。")
        log("  正式檔名已換成最小的這一版，可以交付，但要先問使用者：直接交付／依 PART 分冊／減少全頁截圖。")
        log("  原檔最重的頁：" + "、".join(f"第 {p} 頁 {fmt_mb(b)}" for p, b in res["heaviest"]))
    else:
        log(f"✓ {fmt_mb(size0)} → {fmt_mb(res['final'])}（{res['step']}）→ {pdf.name}")
    if res.get("original_kept"):
        log(f"  原檔：{res['original_kept']}（不交付）")
    return res


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="整份 PDF 壓縮到上限以內，並檢查是獨立檔案")
    ap.add_argument("pdf")
    ap.add_argument("--max-mb", type=float, default=DEFAULT_MAX_MB)
    ap.add_argument("--keep-original", default=None,
                    help="原檔搬到哪個資料夾（預設：PDF 旁邊的 disc/）；給 '-' 不保留")
    ap.add_argument("--force", action="store_true", help="沒超過上限也壓")
    ap.add_argument("--check", action="store_true", help="只做獨立性檢查與大小報告，不壓")
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args(argv)

    pdf = Path(a.pdf).resolve()
    if not pdf.exists():
        print("找不到檔案：", pdf, file=sys.stderr)
        return 1
    if not _pdf():
        print("需要 pypdf：pip install pypdf pillow", file=sys.stderr)
        return 1
    keep = None if a.keep_original == "-" else Path(a.keep_original or pdf.parent / "disc").resolve()
    log = (lambda *x: None) if a.json else print
    if a.check:
        info = inspect_pdf(pdf)
        res = dict(file=str(pdf), size=pdf.stat().st_size, pages=info["pages"],
                   issues=self_contained_issues(info), over=pdf.stat().st_size > a.max_mb * MB)
        log(f"PDF {fmt_mb(res['size'])}，{info['pages']} 頁，內部連結 {info['internal_links']}，書籤 {info['outline']}")
        log("✓ 獨立檔案：圖片與字型都已內嵌、沒有外部參照" if not res["issues"] else "✗ " + "；".join(res["issues"]))
    else:
        res = run(pdf, a.max_mb, keep, a.force, log)
    if a.json:
        print(json.dumps(res, ensure_ascii=False, indent=1))
    if res["issues"]:
        return 1
    return 2 if res["over"] else 0


if __name__ == "__main__":
    sys.exit(main())
