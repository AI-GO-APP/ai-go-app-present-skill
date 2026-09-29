"""
scripts/compress_pdf.py 的單元測試（unittest）。需要 pypdf＋Pillow，沒裝就整組跳過。

執行：python -m unittest discover -s tests -v

用 Pillow 產一份雜訊圖多的小 PDF（每頁一張 JPEG 品質 100），測：
壓縮後變小且結構不變、超過上限時 exit 2 且正式檔換成最小版、原檔保留、驗證會抓到缺頁與外部參照。
"""

from __future__ import annotations
import contextlib
import importlib.util
import io
import shutil
import tempfile
import unittest
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent.parent / "scripts"
spec = importlib.util.spec_from_file_location("compress_pdf", SCRIPTS / "compress_pdf.py")
cp = importlib.util.module_from_spec(spec)
spec.loader.exec_module(cp)

try:
    import pypdf  # noqa: F401
    from PIL import Image
    HAVE = True
except ImportError:
    HAVE = False


def make_pdf(path: Path, pages=3, size=(1600, 900)):
    imgs = [Image.effect_noise(size, 60).convert("RGB") for _ in range(pages)]
    imgs[0].save(path, "PDF", save_all=True, append_images=imgs[1:], quality=100, resolution=96)


def quiet(fn, *a, **kw):
    with contextlib.redirect_stdout(io.StringIO()):
        return fn(*a, **kw)


@unittest.skipUnless(HAVE, "需要 pypdf 與 Pillow")
class CompressTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.pdf = self.tmp / "AI GO 展示 客服 20260929.pdf"
        make_pdf(self.pdf)
        self.size0 = self.pdf.stat().st_size
        self.info0 = cp.inspect_pdf(self.pdf)

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_under_limit_untouched(self):
        rc = quiet(cp.main, [str(self.pdf), "--max-mb", "100"])
        self.assertEqual(rc, 0)
        self.assertEqual(self.pdf.stat().st_size, self.size0)
        self.assertFalse((self.tmp / "disc").exists())

    def test_compress_under_limit(self):
        limit = self.size0 * 0.6 / cp.MB
        rc = quiet(cp.main, [str(self.pdf), "--max-mb", f"{limit:.4f}"])
        self.assertEqual(rc, 0)
        new = self.pdf.stat().st_size
        self.assertLessEqual(new, limit * cp.MB)
        info = cp.inspect_pdf(self.pdf)
        self.assertEqual(cp.verify(self.info0, info), [])          # 頁數、尺寸、圖片數都沒變
        kept = self.tmp / "disc" / (self.pdf.stem + ".original.pdf")
        self.assertEqual(kept.stat().st_size, self.size0)          # 原檔保留在 disc/

    def test_over_limit_exit2_keeps_smallest(self):
        res = quiet(cp.run, self.pdf, 0.001, self.tmp / "disc")
        self.assertTrue(res["over"])
        self.assertEqual(res["step"], "jpeg60-1920")               # 走到畫質底線
        self.assertLess(self.pdf.stat().st_size, self.size0)       # 正式檔名＝最小版，可交付
        self.assertEqual(cp.verify(self.info0, cp.inspect_pdf(self.pdf)), [])
        rc = quiet(cp.main, [str(self.pdf), "--max-mb", "0.001", "--keep-original", "-"])
        self.assertEqual(rc, 2)

    def test_check_mode(self):
        self.assertEqual(quiet(cp.main, [str(self.pdf), "--check"]), 0)
        self.assertEqual(self.pdf.stat().st_size, self.size0)

    def test_verify_catches_missing_page_and_external(self):
        info = dict(self.info0, pages=2, sizes=self.info0["sizes"][:2], images=self.info0["images"][:2])
        bad = cp.verify(self.info0, info)
        self.assertTrue(any("頁數" in b for b in bad))
        info = dict(self.info0, external=["外部動作 /GoToR"], unembedded_fonts=["Arial"])
        bad = cp.verify(self.info0, info)
        self.assertTrue(any("GoToR" in b for b in bad))
        self.assertTrue(any("字型未內嵌" in b for b in bad))

    def test_internal_links_and_outline_survive(self):
        from pypdf import PdfWriter
        from pypdf.annotations import Link
        w = PdfWriter(clone_from=str(self.pdf))
        w.add_annotation(0, Link(rect=(0, 0, 100, 100), target_page_index=2))
        w.add_outline_item("第三頁", 2)
        w.write(str(self.pdf))
        orig = cp.inspect_pdf(self.pdf)
        self.assertEqual((orig["internal_links"], orig["outline"]), (1, 1))
        quiet(cp.run, self.pdf, 0.001, None)
        new = cp.inspect_pdf(self.pdf)
        self.assertEqual((new["internal_links"], new["outline"]), (1, 1))


if __name__ == "__main__":
    unittest.main()
