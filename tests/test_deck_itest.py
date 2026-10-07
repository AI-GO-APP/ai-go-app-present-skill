"""
deck_kit 整合測試報告頁（Deck.itest）的單元測試（標準函式庫 unittest）。

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

KICKER = re.compile(r'<header><div class="kicker">([^<]*)</div><h2>([^<]*)</h2>')


def case(cid, status, group="e2e", **kw):
    return dict(id=cid, group=group, area="訂單", title=f"{cid} 標題", steps=["打開 /orders", "點「建立」"],
                expect="列表多一筆", status=status, findings=kw.pop("findings", []), notes=kw.pop("notes", []),
                shot=f"it-{cid}", at=f"t-{cid}", **kw)


class ItestTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        (self.tmp / "shots").mkdir()
        shot = {"w": 1600, "h": 900, "full": True, "marks": [{"n": 1, "x": 10, "y": 10, "w": 50, "h": 20}]}
        self.cases = [
            case("SMK-home", "pass", "smoke", notes=["頁面正常顯示"]),
            case("E2E-01", "fail", findings=[{"level": "fail", "kind": "assert", "text": "列表沒有新的一筆", "mark": 1},
                                             {"level": "info", "kind": "repro", "text": "重跑一次仍未通過"}]),
            case("E2E-02", "doubt", findings=[{"level": "doubt", "kind": "text", "text": "畫面出現 NaN"}]),
            case("E2E-03", "pass"),
            case("E2E-04", "skip", reason="會真的扣款"),
        ]
        man = {c["shot"]: shot for c in self.cases}
        (self.tmp / "shots" / "shots.json").write_text(json.dumps(man), encoding="utf-8")
        self.res = self.tmp / "results.json"
        self.rev = self.tmp / "review.json"
        self.save(self.cases, {
            "E2E-01": {"run": "t-E2E-01", "status": "fail", "severity": "高", "judgement": "建立後列表沒有更新，使用者會重複建立。",
                       "suggest": "建立成功後重新讀取列表"},
            "E2E-02": {"run": "t-E2E-02", "status": "doubt", "severity": "", "judgement": "金額顯示 NaN，看不懂。"},
        })

    def save(self, cases, review):
        self.res.write_text(json.dumps({"meta": {"base": "https://demo.ai-go.app", "mode": "runtime", "account": "測試帳號",
                                                 "browser": "HeadlessChrome/131.0.0.0", "viewport": "1600×900",
                                                 "started": "2026-10-07T02:00:00Z", "finished": "2026-10-07T02:40:00Z",
                                                 "labels": {"e2e": "端到端流程"}},
                                        "cases": cases}, ensure_ascii=False), encoding="utf-8")
        self.rev.write_text(json.dumps(review, ensure_ascii=False), encoding="utf-8")

    def deck(self, *purposes):
        return dk.Deck(tenant="展示公司", app="訂單中心", purposes=list(purposes or ["整合測試"]), shots=self.tmp / "shots",
                       made="2026-10-07")

    def build(self, d=None, **kw):
        d = d or self.deck()
        d.itest(self.res, self.rev, **kw)
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            html = d.write(self.tmp / "deck.html").read_text(encoding="utf-8")
        return html, out.getvalue()

    def test_purpose_and_title(self):
        self.assertIn("整合測試", dk.PURPOSES)
        self.assertEqual(dk.DECK_ORDER, ("功能展示", "測試報告", "整合測試", "操作說明"))
        self.assertEqual(self.deck().title, "整合測試報告")
        self.assertEqual(self.deck("操作說明", "整合測試").filename(), "AI GO 展示公司 訂單中心 整合測試・操作說明 20261007.pdf")
        with self.assertRaisesRegex(ValueError, "沒選「整合測試」"):
            self.deck("操作說明").itest(self.res, self.rev)

    def test_pages_and_order(self):
        html, out = self.build(scope="範圍：後台 3 頁")
        titles = [t for _, t in KICKER.findall(html)]
        self.assertEqual(titles, ["目錄", "測試範圍與結果", "問題一覽", "E2E-01　E2E-01 標題", "E2E-02　E2E-02 標題",
                                  "通過項目", "未測項目與原因"])                       # 未通過在疑慮前面
        self.assertIn("整合測試 · 未通過", html)
        self.assertIn("範圍：後台 3 頁", html)
        self.assertIn("Chrome 131", html)
        self.assertIn("2026-10-07 10:00～10:40", html)                       # 台灣時間
        self.assertIn("端到端流程", html)
        self.assertIn("冒煙測試（每頁載入）", html)
        self.assertIn("建立成功後重新讀取列表", html)
        self.assertIn('src="shots/it-E2E-01.png"', html)                     # 問題頁有截圖
        self.assertNotIn("it-E2E-03.png", html)                              # 通過的免截圖
        self.assertIn("頁面正常顯示", html)                                   # 通過：寫觀察
        self.assertIn("符合預期：列表多一筆", html)                            # 沒觀察：寫預期
        self.assertIn("會真的扣款", html)
        self.assertIn("列表沒有新的一筆", html)
        self.assertNotIn("重跑一次仍未通過", html)                              # info 沒標號不列
        self.assertIn("E2E-01｜未通過｜高｜建立後列表沒有更新", out)             # 交付回報
        self.assertNotIn('class="howto"', html)

    def test_gt2_required(self):
        self.save(self.cases, {"E2E-01": {"run": "t-E2E-01", "status": "fail", "severity": "高", "judgement": "x"}})
        with self.assertRaisesRegex(ValueError, r"GT2 還沒判讀完（1 個）：E2E-02"):
            self.deck().itest(self.res, self.rev)
        self.save(self.cases, {"E2E-01": {"run": "舊的", "status": "fail", "severity": "高", "judgement": "x"},
                               "E2E-02": {"run": "t-E2E-02", "judgement": "y"}})
        with self.assertRaisesRegex(ValueError, "E2E-01"):                  # 重跑過＝過期
            self.deck().itest(self.res, self.rev)

    def test_severity_and_length(self):
        self.save(self.cases, {"E2E-01": {"run": "t-E2E-01", "judgement": "x"}, "E2E-02": {"run": "t-E2E-02", "judgement": "y"}})
        with self.assertRaisesRegex(ValueError, "severity"):
            self.deck().itest(self.res, self.rev)
        self.save(self.cases, {"E2E-01": {"run": "t-E2E-01", "severity": "高", "judgement": "長" * 91},
                               "E2E-02": {"run": "t-E2E-02", "judgement": "y"}})
        with self.assertRaisesRegex(ValueError, "一句話"):
            self.deck().itest(self.res, self.rev)

    def test_override_and_fixed(self):
        self.save(self.cases, {
            "E2E-01": {"run": "t-E2E-01", "severity": "中", "judgement": "x"},
            "E2E-02": {"run": "t-E2E-02", "status": "pass", "judgement": "NaN 是測試資料本身的值，畫面照實顯示。"},
            "E2E-03": {"run": "t-E2E-03", "status": "pass", "fixed": "原本建立後不會跳回列表"},
            "SMK-home": {"run": "t-SMK-home", "status": "doubt", "judgement": "首頁標題寫錯字。"},
        })
        html, _ = self.build()
        titles = [t for _, t in KICKER.findall(html)]
        self.assertIn("SMK-home　SMK-home 標題", titles)                      # 通過改判疑慮 → 有問題頁
        self.assertNotIn("E2E-02　E2E-02 標題", titles)                       # 疑慮改判通過 → 進通過清單
        self.assertIn("NaN 是測試資料本身的值", html)
        self.assertIn("修正後重測通過", html)
        self.assertIn("原本建立後不會跳回列表", html)

    def test_stray_review_and_missing_shot(self):
        self.save(self.cases, {"E2E-01": {"run": "t-E2E-01", "severity": "高", "judgement": "x"},
                               "E2E-02": {"run": "t-E2E-02", "judgement": "y"}, "XX-9": {}})
        with self.assertRaisesRegex(ValueError, "XX-9"):
            self.deck().itest(self.res, self.rev)
        (self.tmp / "shots" / "shots.json").write_text("{}", encoding="utf-8")
        self.save(self.cases, {"E2E-01": {"run": "t-E2E-01", "severity": "高", "judgement": "x"},
                               "E2E-02": {"run": "t-E2E-02", "judgement": "y"}})
        with self.assertRaisesRegex(ValueError, "沒有截圖"):
            self.deck().itest(self.res, self.rev)

    def test_pagination_and_once(self):
        many = [case(f"SWP-{i:02d}", "pass", "sweep") for i in range(25)]
        self.save(many, {})
        html, _ = self.build(per_page=12)
        titles = [t for _, t in KICKER.findall(html)]
        self.assertEqual([t for t in titles if t.startswith("通過項目")], ["通過項目（1／3）", "通過項目（2／3）", "通過項目（3／3）"])
        self.assertNotIn("問題一覽", titles)                                   # 沒問題就沒有一覽頁
        d = self.deck()
        d.itest(self.res, self.rev)
        with self.assertRaisesRegex(ValueError, "一次"):
            d.itest(self.res, self.rev)

    def test_combined_with_manual(self):
        d = self.deck("操作說明", "整合測試")
        d.slide("開始之前", "前置", "", "")
        html, _ = self.build(d)
        titles = [t for _, t in KICKER.findall(html)]
        self.assertLess(titles.index("測試範圍與結果"), titles.index("前置"))      # 整合測試排在操作說明前面


if __name__ == "__main__":
    unittest.main()
