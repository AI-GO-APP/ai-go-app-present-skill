"""
deck_kit 驗收數據頁（Deck.acceptance，選配）的單元測試（標準函式庫 unittest）。

執行：python -m unittest discover -s tests -v
"""

from __future__ import annotations
import contextlib
import importlib.util
import io
import re
import tempfile
import unittest
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent.parent / "scripts"
spec = importlib.util.spec_from_file_location("deck_kit", SCRIPTS / "deck_kit.py")
dk = importlib.util.module_from_spec(spec)
spec.loader.exec_module(dk)

SECTION = re.compile(r'<section id="p(\d+)" class="slide ([^"]*)"')
CARD = ("98.2%", "金額辨識準確率", "發票總金額與人工核對完全相同的比例")
ROW = ("金額辨識準確率", "總金額與人工核對完全相同", "98.2%（491／500）", "500 張", "2026-09-20")
SRC = ["app/docs/eval/ocr-2026-09-20.md"]


class AcceptanceTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())

    def deck(self):
        return dk.Deck(tenant="展示公司", app="發票辨識", shots=self.tmp / "shots", made="2026-09-29")

    def write(self, d):
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            html = d.write(self.tmp / "deck.html").read_text(encoding="utf-8")
        return html, buf.getvalue()

    @staticmethod
    def classes(html):
        return [c for _, c in SECTION.findall(html)]

    def body(self, d, acc_first=False):
        d.cover("一句話")
        if acc_first:
            d.acceptance([CARD], [ROW], sources=SRC)
        d.slide("開始之前", "前置", "", "")
        for label, title in (("PART A", "核心工作"), ("PART B", "控制 AI"), ("PART C", "其他與維護")):
            d.divider(title, label, title, "一句話")
            d.slide(title, f"{title} 1", "", "")
        if not acc_first:
            d.acceptance([CARD], [ROW], sources=SRC)     # 寫在最後也會被移到目錄後
        d.back_cover()

    def test_moved_right_after_toc(self):
        for acc_first in (False, True):
            d = self.deck()
            self.body(d, acc_first)
            c = self.classes(self.write(d)[0])
            self.assertIn("cover-slide", c[0])
            self.assertIn("toc-slide", c[1])
            self.assertIn("acc-slide", c[2])
            self.assertEqual(sum("acc-slide" in x for x in c), 1)

    def test_after_toc_false_keeps_order(self):
        d = self.deck()
        d.cover("x")
        d.slide("開始之前", "前置", "", "")
        d.acceptance([CARD], sources=SRC, after_toc=False)
        c = self.classes(self.write(d)[0])
        self.assertIn("acc-slide", c[3])

    def test_two_pages_keep_order_third_raises(self):
        d = self.deck()
        d.cover("x")
        d.slide("開始之前", "前置", "", "")
        d.acceptance([CARD], sources=SRC, title="辨識準確度")
        d.acceptance(rows=[ROW], sources=SRC, title="判斷正確率")
        with self.assertRaises(ValueError):
            d.acceptance([CARD], sources=SRC)
        html, _ = self.write(d)
        titles = re.findall(r'class="slide light acc-slide">\s*<header><div class="kicker">[^<]*</div><h2>([^<]*)</h2>', html)
        self.assertEqual(titles, ["辨識準確度", "判斷正確率"])
        self.assertIn("acc-slide", self.classes(html)[2])
        self.assertIn("acc-slide", self.classes(html)[3])

    def test_validation(self):
        d = self.deck()
        with self.assertRaises(ValueError):
            d.acceptance([CARD], [ROW])                      # 沒有來源
        with self.assertRaises(ValueError):
            d.acceptance(sources=SRC)                        # 沒有數據
        with self.assertRaises(ValueError):
            d.acceptance([CARD] * 5, sources=SRC)            # 卡片 > 4
        with self.assertRaises(ValueError):
            d.acceptance(rows=[ROW] * 9, sources=SRC)        # 列 > 8
        with self.assertRaises(ValueError):
            d.acceptance(rows=[ROW[:4]], sources=SRC)        # 欄數不對
        d.acceptance([CARD] * 4, [ROW] * 8, sources=SRC)     # 上限剛好可以

    def test_sources_printed_not_rendered(self):
        d = self.deck()
        self.body(d)
        html, out = self.write(d)
        self.assertNotIn(SRC[0], html)
        self.assertIn(SRC[0], out)
        self.assertIn("驗收數據", out)

    def test_content_rendered(self):
        d = self.deck()
        d.acceptance([CARD], [ROW], note="範圍：500 張發票", sources=SRC)
        html, _ = self.write(d)
        self.assertIn('<div class="v">98.2%</div>', html)
        self.assertIn("<td>98.2%（491／500）</td>", html)
        self.assertIn('<div class="acc-note">範圍：500 張發票</div>', html)
        for h in dk.ACC_HEAD:
            self.assertIn(f"<th>{h}</th>", html)

    def test_toc_group_first_and_stacked(self):
        d = self.deck()
        self.body(d)
        html, _ = self.write(d)
        toc = re.search(r'class="slide toc-slide">(.*?)</section>', html, re.S).group(1)
        cols = re.findall(r'<div class="toc-col">(.*?)</div>', toc, re.S)
        self.assertEqual(len(cols), 4)                        # 驗收數據＋開始之前疊一欄，A／B／C 各一欄
        heads = re.findall(r'<a class="toc-h( sub)?"[^>]*>.*?<b>([^<]*)</b>', cols[0])
        self.assertEqual([h for _, h in heads], ["驗收數據", "開始之前"])
        self.assertEqual(heads[1][0], " sub")
        self.assertIn('href="#p03"', cols[0])

    def test_no_acceptance_no_section(self):
        d = self.deck()
        d.cover("x")
        d.slide("開始之前", "前置", "", "")
        html, out = self.write(d)
        self.assertFalse(any("acc-slide" in c for c in self.classes(html)))
        self.assertNotIn("驗收數據", out)


if __name__ == "__main__":
    unittest.main()
