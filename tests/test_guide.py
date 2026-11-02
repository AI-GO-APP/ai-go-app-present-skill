"""
guide_kit 測試指引（第六種用途）的單元測試（標準函式庫 unittest）。

執行：python -m unittest discover -s tests -v
"""

from __future__ import annotations
import contextlib
import importlib.util
import io
import json
import re
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent.parent / "scripts"
sys.path.insert(0, str(SCRIPTS))
spec = importlib.util.spec_from_file_location("guide_kit", SCRIPTS / "guide_kit.py")
gk = importlib.util.module_from_spec(spec)
spec.loader.exec_module(gk)
import deck_kit as dk  # noqa: E402

SECTION = re.compile(r'<section id="p(\d+)" class="slide a4 ([^"]*)"')
TITLE = re.compile(r"<h2>([^<]*)</h2>")
ROLES = [("店長", "店長-1", "看全店訂單", "建立訂單"), ("客服", "客服-1", "回覆客人", "查詢訂單")]
STEPS = [("點「訂單」", "訂單列表出現"), ("點「新增訂單」", "右側滑出表單")]


class GuideTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        (self.tmp / "shots").mkdir()
        shot = {"w": 1600, "h": 900, "full": True, "marks": []}
        (self.tmp / "shots" / "shots.json").write_text(json.dumps({"a": shot, "b": shot, "c": shot}), encoding="utf-8")

    def guide(self, **kw):
        return gk.Guide(tenant="展示公司", app="訂單中心", shots=self.tmp / "shots", made="2026-11-02", **kw)

    def full(self, **kw):
        g = self.guide(**kw)
        g.roles(ROLES)
        g.flow("建立一筆訂單", role="店長", goal="列表看得到新訂單。", steps=STEPS, shot="a")
        g.report(channel="LINE 群組「測試回報」", to="王小明", deadline="11/7")
        return g

    def write(self, g):
        with contextlib.redirect_stdout(io.StringIO()):
            return g.write(self.tmp / "guide.html").read_text(encoding="utf-8")

    def pages(self, html):
        return [(m.group(2).split()[0], m.group(2)) for m in SECTION.finditer(html)]

    def test_filename_and_title(self):
        g = self.guide()
        self.assertEqual(g.title, "測試指引")
        self.assertEqual(g.filename(), "AI GO 展示公司 訂單中心 測試指引 20261102.pdf")
        self.assertEqual(dk.deck_filename("t", "a", g.made, ".txt", ["進度報告"]), "AI GO t a 進度報告 20261102.txt")

    def test_deck_rejects_guide(self):
        with self.assertRaisesRegex(ValueError, "guide_kit"):
            dk.Deck(tenant="t", app="a", purposes=["操作說明", "測試指引"])
        self.assertIn("測試指引", dk.PURPOSES)

    def test_required_parts(self):
        g = self.guide()
        with self.assertRaisesRegex(ValueError, "身分與帳號"):
            self.write(g)
        g.roles(ROLES)
        with self.assertRaisesRegex(ValueError, "測試流程"):
            self.write(g)
        g.flow("查訂單", role="客服", goal="查得到。", steps=STEPS)
        with self.assertRaisesRegex(ValueError, "回報方式"):
            self.write(g)
        g.report(channel="Email")
        self.write(g)

    def test_fixed_order_and_auto_pages(self):
        g = self.guide()
        g.report(channel="LINE")                                        # 故意倒著寫
        g.permissions([("退款", "可以", "看不到")])
        g.flow("建立一筆訂單", role="店長", goal="列表看得到。", steps=STEPS)
        g.flow("查詢訂單", role="客服", goal="查得到。", steps=STEPS)
        g.roles(ROLES)
        g.prepare(env=[("期間", "11/3～11/7")])
        html = self.write(g)
        kinds = [c.replace("g-", "") for c, _ in self.pages(html)]
        kinds = [{"cover-slide": "cover", "back-slide": "back"}.get(k, k) for k in kinds]
        self.assertEqual(kinds, ["cover", "toc", "prepare", "roles", "howto", "flow", "flow", "perms", "judge", "report",
                                 "checklist", "issue", "back"])
        titles = TITLE.findall(html)
        self.assertIn("T01　建立一筆訂單", titles)
        self.assertIn("T02　查詢訂單", titles)

    def test_toc_links_match_pages(self):
        html = self.write(self.full())
        ids = {int(m.group(1)) for m in SECTION.finditer(html)}
        links = re.findall(r'<a class="toc-i" href="#p(\d+)"><span class="t">([^<]*)</span><span class="pg">(\d+)</span>', html)
        self.assertTrue(links)
        for href, _, pg in links:
            self.assertEqual(int(href), int(pg))
            self.assertIn(int(href), ids)
        self.assertIn('class="g-toc-h"', html)

    def test_flow_validation(self):
        g = self.guide()
        with self.assertRaisesRegex(ValueError, "預期畫面"):
            g.flow("x", role="店長", goal="g", steps=[("點 A", "")])
        with self.assertRaisesRegex(ValueError, "超過"):
            g.flow("x", role="店長", goal="g", steps=STEPS * 7)
        with self.assertRaisesRegex(ValueError, "字"):
            g.flow("這是一個非常非常非常非常長的流程名稱超過二十字", role="店長", goal="g", steps=STEPS)
        with self.assertRaisesRegex(ValueError, "goal"):
            g.flow("x", role="店長", goal="", steps=STEPS)
        with self.assertRaises(KeyError):
            g.flow("x", role="店長", goal="g", steps=STEPS, shot="沒有這張")
        with self.assertRaisesRegex(ValueError, "最多"):
            g.flow("x", role="店長", goal="g", steps=STEPS, shot=["a", "b", "c"])
        g.flow("x", role="店長", goal="g", steps=STEPS, code="A1")
        with self.assertRaisesRegex(ValueError, "重複"):
            g.flow("y", role="店長", goal="g", steps=STEPS, code="A1")

    def test_unknown_role(self):
        g = self.full()
        g.flow("倉管出貨", role="倉管", goal="g", steps=STEPS)
        with self.assertRaisesRegex(ValueError, "倉管"):
            self.write(g)

    def test_roles_validation(self):
        g = self.guide()
        with self.assertRaisesRegex(ValueError, "4 欄"):
            g.roles([("店長", "店長-1")])
        with self.assertRaisesRegex(ValueError, "重複"):
            g.roles([ROLES[0], ROLES[0]])

    def test_permissions_columns(self):
        g = self.full()
        g.permissions([("退款", "可以")])                                  # 少一欄
        with self.assertRaisesRegex(ValueError, "3 欄"):
            self.write(g)
        g = self.full()
        g.permissions([("退款", "可以", "看不到")])
        html = self.write(g)
        self.assertIn('chip ok">可以', html)
        self.assertIn('chip danger">看不到', html)
        self.assertIn("權限檢查（客服）", html)                          # 總檢查清單每個身分一列

    def test_report_content(self):
        g = self.guide()
        g.roles(ROLES)
        g.flow("建立一筆訂單", role="店長", goal="g", steps=STEPS)
        with self.assertRaisesRegex(ValueError, "channel"):
            g.report(channel="")
        with self.assertRaisesRegex(ValueError, "sla"):
            g.report(channel="LINE", sla={"緊急": "馬上"})
        g.report(channel="LINE 群組「測試回報」", to="王小明", sla={"高": "當天回覆"})
        html = self.write(g)
        self.assertIn("當天回覆", html)
        self.assertIn("【測試回報】T01 第 2 步", html)                    # 自動範例用第一條流程
        self.assertIn("右側滑出表單", html)
        self.assertNotIn("2 個工作天", html)                              # 沒寫的時效不放

    def test_secret_blocked(self):
        g = self.guide()
        g.roles([("店長", "store@demo.tw 密碼：abc123", "看訂單", "建立")])
        g.flow("x", role="店長", goal="g", steps=STEPS)
        g.report(channel="LINE")
        with self.assertRaisesRegex(ValueError, "密碼"):
            self.write(g)

    def test_checklist_paginates(self):
        g = self.guide()
        g.roles(ROLES)
        for i in range(30):
            g.flow(f"流程 {i}", role="店長", goal="g", steps=STEPS)
        g.report(channel="LINE")
        html = self.write(g)
        self.assertIn("總檢查清單（1／2）", html)
        self.assertIn("總檢查清單（2／2）", html)
        self.assertEqual(html.count('class="g-tally"'), 1)               # 合計只在最後一頁
        self.assertIn("目錄（續）", html)                                  # 30 條流程，目錄自動續頁

    def test_cover_counts_and_deck_only_pages(self):
        g = self.full(site="https://demo.ai-go.app", audience="店長")
        html = self.write(g)
        self.assertIn("2 種身分・1 條流程", html)
        self.assertIn("https://demo.ai-go.app", html)
        for call in (lambda: g.divider("A", "PART A", "t", "d"), lambda: g.raw("<p>x</p>"),
                     lambda: g.showcase("f", "v", "a"), lambda: g.itest()):
            with self.assertRaises(ValueError):
                call()


if __name__ == "__main__":
    unittest.main()
