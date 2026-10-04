"""
deck_kit 目錄頁（Deck.toc／write() 自動插入）與分隔頁自動頁目的單元測試（標準函式庫 unittest）。

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
TOC_ROW = re.compile(r'<a class="toc-i" href="#p(\d+)"><span class="t">([^<]*)</span><span class="pg">(\d+)</span></a>')


class TocTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())

    def deck(self):
        return dk.Deck(tenant="展示公司", app="客服後台", purposes=["操作說明"], shots=self.tmp / "shots", made="2026-09-29")

    def write(self, d) -> str:
        with contextlib.redirect_stdout(io.StringIO()):
            out = d.write(self.tmp / "deck.html")
        return out.read_text(encoding="utf-8")

    @staticmethod
    def slides(html):
        return [(int(n), cls) for n, cls in SECTION.findall(html)]

    def sample(self, d, per_part=(2, 3, 2)):
        d.cover("一句話")
        for j in range(per_part[0]):
            d.slide("開始之前", f"前置 {j + 1}", "", "")
        for label, title, cnt in (("PART A", "核心工作", per_part[1]), ("PART B", "控制 AI", per_part[2])):
            d.divider(title, label, title, "一句話")
            for j in range(cnt):
                d.slide(title, f"{title} {j + 1}", "", "")
        d.back_cover()

    def test_auto_inserted_after_cover(self):
        d = self.deck()
        self.sample(d)
        html = self.write(d)
        s = self.slides(html)
        self.assertEqual([n for n, _ in s], list(range(1, len(s) + 1)))
        self.assertIn("cover-slide", s[0][1])
        self.assertIn("toc-slide", s[1][1])
        self.assertEqual(sum("toc-slide" in c for _, c in s), 1)

    def test_page_numbers_match_targets(self):
        d = self.deck()
        self.sample(d)
        html = self.write(d)
        rows = TOC_ROW.findall(html)
        self.assertEqual(len(rows), 2 + 3 + 2)          # 封面、目錄、分隔頁、封底不列
        titles = {n: t for n, t in re.findall(r'<section id="p(\d+)"[^>]*>\s*<header><div class="kicker">[^<]*</div><h2>([^<]*)</h2>', html)}
        for href, title, shown in rows:
            self.assertEqual(href, shown)
            self.assertEqual(titles[href], title)

    def test_explicit_position_and_no_cover(self):
        d = self.deck()
        d.slide("開始之前", "第一頁", "", "")
        d.toc()
        d.slide("開始之前", "第三頁", "", "")
        s = self.slides(self.write(d))
        self.assertIn("toc-slide", s[1][1])

        d = self.deck()
        d.slide("開始之前", "唯一一頁", "", "")
        s = self.slides(self.write(d))
        self.assertIn("toc-slide", s[0][1])            # 沒有封面 → 目錄放第一頁

    def test_toc_twice_raises(self):
        d = self.deck()
        d.toc()
        with self.assertRaises(ValueError):
            d.toc()

    def test_divider_auto_items_have_page_numbers(self):
        d = self.deck()
        self.sample(d)
        html = self.write(d)
        m = re.search(r'PART A</div>.*?<ul class="bl ">(.*?)</ul>', html, re.S)
        self.assertIsNotNone(m)
        items = re.findall(r'<li>([^<]*)<span class="dv-pg">(\d+)</span></li>', m.group(1))
        self.assertEqual([t for t, _ in items], ["核心工作 1", "核心工作 2", "核心工作 3"])
        s = dict(self.slides(html))
        self.assertTrue(all(int(p) in s for _, p in items))

    def test_divider_manual_items_kept(self):
        d = self.deck()
        d.divider("A", "PART A", "核心工作", "一句話", ["手寫一", "手寫二"])
        d.slide("A", "內容", "", "")
        html = self.write(d)
        self.assertIn("<li>手寫一</li>", html)
        self.assertNotIn('class="dv-pg"', html)

    def test_raw_listed_only_with_title(self):
        d = self.deck()
        d.raw("<div>x</div>", part="A", title="自訂頁")
        d.raw("<div>y</div>", part="A")
        rows = TOC_ROW.findall(self.write(d))
        self.assertEqual([t for _, t, _ in rows], ["自訂頁"])

    def test_title_html_stripped_and_escaped(self):
        d = self.deck()
        d.slide("A", "症狀 <b>→</b> 改哪裡 & 速查", "", "")
        rows = TOC_ROW.findall(self.write(d))
        self.assertEqual(rows[0][1], "症狀 → 改哪裡 &amp; 速查")

        d = self.deck()
        d.slide("A", "A &amp; B", "", "")          # 已跳脫的實體不能再跳脫一次
        self.assertEqual(TOC_ROW.findall(self.write(d))[0][1], "A &amp; B")

    def test_howto_on_single_page(self):
        d = self.deck()
        self.sample(d)
        self.assertEqual(self.write(d).count('class="howto"'), 1)
        d = self.deck()
        d.toc(howto=False)
        self.sample(d)
        self.assertEqual(self.write(d).count('class="howto"'), 0)

    def test_dense_then_multi_page(self):
        # 一組 14 列：超過一般字級（15－讀法 3）→ dense，仍一頁
        d = self.deck()
        self.sample(d, (1, 14, 2))
        html = self.write(d)
        self.assertIn('class="toc dense"', html)
        self.assertEqual(sum("toc-slide" in c for _, c in self.slides(html)), 1)

        # 一組 60 列 → 拆成多欄、多頁；頁碼仍全部正確
        d = self.deck()
        self.sample(d, (3, 60, 40))
        html = self.write(d)
        s = self.slides(html)
        tocs = [n for n, c in s if "toc-slide" in c]
        self.assertGreater(len(tocs), 1)
        self.assertEqual(tocs, list(range(2, 2 + len(tocs))))
        self.assertIn("目錄（續）", html)
        self.assertIn("核心工作（續）", html)
        rows = TOC_ROW.findall(html)
        self.assertEqual(len(rows), 3 + 60 + 40)
        self.assertTrue(all(h == p for h, _, p in rows))
        self.assertLessEqual(html.count('class="howto"'), 1)
        # 不能出現只有讀法列、沒有任何目錄欄的空目錄頁
        for body in re.findall(r'class="slide toc-slide">(.*?)</section>', html, re.S):
            self.assertIn('class="toc-col"', body)

    def test_every_row_fits_column_capacity(self):
        d = self.deck()
        self.sample(d, (3, 60, 40))
        html = self.write(d)
        for col in re.findall(r'<div class="toc-col">(.*?)</div>', html, re.S):
            self.assertLessEqual(col.count('class="toc-i"'), dk._TOC_ROWS_DENSE)


if __name__ == "__main__":
    unittest.main()
