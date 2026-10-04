"""
deck_kit 用途（Phase 0）與功能展示頁的單元測試（標準函式庫 unittest）。

執行：python -m unittest discover -s tests -v
"""

from __future__ import annotations
import contextlib
import importlib.util
import io
import json
import re
import tempfile
import unittest
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent.parent / "scripts"
spec = importlib.util.spec_from_file_location("deck_kit", SCRIPTS / "deck_kit.py")
dk = importlib.util.module_from_spec(spec)
spec.loader.exec_module(dk)

SECTION = re.compile(r'<section id="p(\d+)" class="slide ([^"]*)"')
KICKER = re.compile(r'<header><div class="kicker">([^<]*)</div><h2>([^<]*)</h2>')
CARD = ("98.2%", "金額辨識準確率", "發票總金額與人工核對完全相同的比例")
SRC = ["app/docs/eval/ocr.md"]


class PurposeTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        (self.tmp / "shots").mkdir()
        shot = {"w": 1600, "h": 900, "full": True, "marks": []}
        (self.tmp / "shots" / "shots.json").write_text(json.dumps({"a": shot, "b": shot}), encoding="utf-8")

    def deck(self, *purposes, **kw):
        return dk.Deck(tenant="展示公司", app="發票辨識", purposes=list(purposes), shots=self.tmp / "shots",
                       made="2026-10-04", **kw)

    def write(self, d):
        with contextlib.redirect_stdout(io.StringIO()):
            return d.write(self.tmp / "deck.html").read_text(encoding="utf-8")

    def test_purposes_required(self):
        for bad in (None, [], ()):
            with self.subTest(bad=bad), self.assertRaisesRegex(ValueError, "Phase 0"):
                dk.Deck(tenant="t", app="a", purposes=bad)
        with self.assertRaisesRegex(ValueError, "progress.py"):
            self.deck("操作說明", "進度報告")
        with self.assertRaisesRegex(ValueError, "不認得"):
            self.deck("週報")

    def test_order_and_title(self):
        d = self.deck("操作說明", "功能展示", "測試報告")
        self.assertEqual(d.purposes, ("功能展示", "測試報告", "操作說明"))
        self.assertEqual(d.title, "功能展示・測試報告・操作手冊")
        self.assertEqual(self.deck("操作說明").title, "後台操作手冊")
        self.assertEqual(self.deck("測試報告").title, "測試報告")
        self.assertEqual(self.deck("操作說明", title="自訂").title, "自訂")

    def test_combined_order(self):
        d = self.deck("操作說明", "功能展示", "測試報告")
        d.cover("一句話")
        d.slide("開始之前", "前置", "", "")                     # 操作說明（預設）
        d.acceptance([CARD], sources=SRC)                      # 測試報告
        d.showcase("訂單匯出", "選個月份，訂單一鍵變成檔案", "a")  # 功能展示
        d.divider("核心", "PART A", "核心", "一句話")
        d.slide("核心", "流程", "", "")
        d.showcase("電話遮蔽", "列表只露後三碼", "b")
        d.back_cover()
        html = self.write(d)
        cls = [c for _, c in SECTION.findall(html)]
        self.assertIn("cover-slide", cls[0])
        self.assertIn("toc-slide", cls[1])
        self.assertIn("back-slide", cls[-1])
        heads = KICKER.findall(html)
        self.assertEqual([t for _, t in heads], ["目錄", "訂單匯出", "電話遮蔽", "指標與結果", "前置", "流程"])
        self.assertIn("功能展示・測試報告・操作手冊", html)          # 封面眉標跟著用途

    def test_section_switch(self):
        d = self.deck("功能展示", "操作說明")
        d.slide("開始之前", "前置", "", "")
        d.section("功能展示")
        d.slide("功能展示", "總覽", "", "")                     # 自訂的展示頁
        d.showcase("訂單匯出", "一句話", "a")
        html = self.write(d)
        self.assertEqual([t for _, t in KICKER.findall(html)], ["目錄", "總覽", "訂單匯出", "前置"])
        with self.assertRaisesRegex(ValueError, "沒選"):
            d.section("測試報告")

    def test_default_section_without_manual(self):
        d = self.deck("功能展示")
        d.slide("功能展示", "總覽", "", "")                     # 沒選操作說明 → 屬於功能展示
        d.showcase("訂單匯出", "一句話", "a")
        self.write(d)

    def test_every_selected_purpose_needs_pages(self):
        d = self.deck("功能展示", "操作說明")
        d.slide("開始之前", "前置", "", "")
        with self.assertRaisesRegex(ValueError, "選了「功能展示」但沒有內容頁"):
            self.write(d)

    def test_showcase_only_when_selected_and_limits(self):
        with self.assertRaisesRegex(ValueError, "沒選「功能展示」"):
            self.deck("操作說明").showcase("x", "y", "a")
        d = self.deck("功能展示")
        with self.assertRaisesRegex(ValueError, "一句話"):
            d.showcase("x", "一" * 41, "a")
        with self.assertRaisesRegex(ValueError, "notes"):
            d.showcase("x", "y", "a", notes=[(i, "n", "d") for i in range(6)])
        for i in range(dk.SHOW_MAX_PAGES):
            d.showcase(f"功能 {i}", "一句話", "a")
        with self.assertRaisesRegex(ValueError, "最多"):
            d.showcase("再一頁", "一句話", "a")

    def test_showcase_page(self):
        d = self.deck("功能展示")
        d.showcase("訂單匯出", "選個月份，訂單一鍵變成檔案", "a", notes=[(1, "月份", "選要匯出的月份")])
        html = self.write(d)
        self.assertIn('class="slide soft show-slide"', html)
        self.assertIn("選個月份，訂單一鍵變成檔案", html)
        self.assertIn("選要匯出的月份", html)
        self.assertNotIn('class="howto"', html)                # 沒選操作說明：目錄不放讀法列

    def test_filename_has_purposes(self):
        self.assertEqual(self.deck("操作說明").filename(), "AI GO 展示公司 發票辨識 操作說明 20261004.pdf")
        self.assertEqual(self.deck("操作說明", "功能展示").filename(".html"),
                         "AI GO 展示公司 發票辨識 功能展示・操作說明 20261004.html")
        self.assertEqual(self.deck("操作說明", "測試報告", "功能展示").filename(""),
                         "AI GO 展示公司 發票辨識 功能展示・測試報告・操作說明 20261004")
        self.assertNotEqual(self.deck("功能展示").filename(), self.deck("操作說明").filename())   # 同一天不撞名
        d = self.deck("測試報告")
        d.acceptance([CARD], sources=SRC)
        with contextlib.redirect_stdout(io.StringIO()):
            out = d.write()                                    # 不給路徑＝照檔名規則
        self.addCleanup(out.unlink)
        self.assertEqual(out.name, "AI GO 展示公司 發票辨識 測試報告 20261004.html")
        self.assertIn("<title>AI GO 展示公司 發票辨識 測試報告 20261004</title>", out.read_text(encoding="utf-8"))
        self.assertEqual(dk.deck_filename("租戶", "App", dk._dt.date(2026, 10, 4)), "AI GO 租戶 App 20261004.pdf")

    def test_howto_only_with_manual(self):
        d = self.deck("操作說明")
        d.slide("開始之前", "前置", "", "")
        self.assertIn('class="howto"', self.write(d))


if __name__ == "__main__":
    unittest.main()
