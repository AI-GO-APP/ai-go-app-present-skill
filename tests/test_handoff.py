"""
交付通知（scripts/handoff.py）的單元測試（標準函式庫 unittest）。

執行：python -m unittest discover -s tests -v
"""

from __future__ import annotations
import contextlib
import copy
import datetime as dt
import importlib.util
import io
import json
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
spec = importlib.util.spec_from_file_location("handoff", ROOT / "scripts" / "handoff.py")
ho = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ho)

TODAY = dt.date(2026, 10, 4)      # 週日
BASE = {
    "mode": "notice", "audience": "fde", "to": "王經理", "feature": "訂單匯出",
    "site": "測試站", "url": "https://example.ai-go.app/runtime/order-center#/orders",
    "steps": [
        {"do": "打開連結，進「訂單」頁", "expect": "右上角有「匯出」按鈕"},
        {"do": "月份選 9 月，按「匯出」", "expect": "下載一個檔案"},
    ],
    "reply_by": "2026-10-06",
}


def cfg(**kw):
    c = copy.deepcopy(BASE)
    c.update(kw)
    return c


def build(c, **kw):
    return ho.build(c, today=TODAY, **kw)


class NoticeTests(unittest.TestCase):
    def test_human_only_has_five_parts(self):
        msg, errors, _ = build(cfg())
        self.assertEqual(errors, [])
        self.assertNotIn(ho.SEP, msg)
        self.assertIn("「訂單匯出」做好了，放在測試站", msg)          # 1 做好了什麼
        self.assertIn("連結：https://example.ai-go.app/", msg)       # 2 在哪裡看
        self.assertIn("1. 打開連結，進「訂單」頁，看到右上角有「匯出」按鈕就對了", msg)   # 3 怎麼驗
        self.assertIn("請在 10/6（二）前回我「可以」或「不行」", msg)   # 4 何時回覆
        self.assertIn("不行的話，截圖傳給我", msg)                    # 5 回給誰、附什麼

    def test_say_overrides_human_step(self):
        c = cfg()
        c["steps"][1]["say"] = "按「匯出」，看有沒有下載一個檔案"
        msg, _, _ = build(c)
        self.assertIn("2. 按「匯出」，看有沒有下載一個檔案", msg)

    def test_ai_helper_on_test_site_gives_two_parts(self):
        msg, errors, warns = build(cfg(ai_helper="王經理"))
        self.assertEqual(errors, [])
        upper, lower = msg.split(ho.SEP)
        self.assertIn("下面那段請直接貼給您的 AI", upper)
        self.assertIn("把 AI 的回報直接轉給我", upper)
        self.assertNotIn("預期：", upper)
        self.assertIn("只在測試站操作", lower)
        self.assertIn("不要自己輸入帳號密碼", lower)
        self.assertIn("1. 打開連結，進「訂單」頁。預期：右上角有「匯出」按鈕", lower)
        self.assertIn("「通過」或「不通過」", lower)

    def test_ai_helper_on_prod_falls_back_to_human(self):
        msg, errors, warns = build(cfg(ai_helper="王經理", site="正式站"))
        self.assertEqual(errors, [])
        self.assertNotIn(ho.SEP, msg)
        self.assertTrue(any("只讓 AI 在測試站" in w for w in warns))

    def test_ai_version_needs_expect(self):
        c = cfg(ai_helper="王經理")
        del c["steps"][0]["expect"]
        with self.assertRaises(ho.HandoffError):
            build(c)

    def test_step_count(self):
        with self.assertRaises(ho.HandoffError):
            build(cfg(steps=[]))
        with self.assertRaises(ho.HandoffError):
            build(cfg(steps=[{"do": f"第 {i} 件事"} for i in range(6)]))

    def test_required_fields_and_url(self):
        c = cfg()
        del c["feature"]
        with self.assertRaises(ho.HandoffError):
            build(c)
        with self.assertRaises(ho.HandoffError):
            build(cfg(url="測試站首頁"))
        with self.assertRaises(ho.HandoffError):
            build(cfg(site="預覽"))


class DeadlineTests(unittest.TestCase):
    def test_format(self):
        self.assertEqual(ho.fmt_date(dt.date(2026, 10, 5)), "10/5（一）")
        self.assertEqual(ho.fmt_date(dt.date(2026, 10, 11)), "10/11（日）")

    def test_defaults(self):
        c = cfg()
        del c["reply_by"]
        self.assertEqual(ho.reply_deadline(c, TODAY), dt.date(2026, 10, 6))     # 週日起第 2 個工作日＝週二
        c["meeting"] = "2026-10-08"
        self.assertEqual(ho.reply_deadline(c, TODAY), dt.date(2026, 10, 7))     # 週會前一天

    def test_past_deadline_is_error(self):
        _, errors, _ = build(cfg(reply_by="2026-10-01"))
        self.assertTrue(any("已經過了" in e for e in errors))

    def test_fde_two_days_before_meeting(self):
        _, _, warns = build(cfg(meeting="2026-10-05"))
        self.assertTrue(any("週會前 2 天" in w for w in warns))
        _, _, warns = build(cfg(meeting="2026-10-07"))
        self.assertFalse(any("週會前 2 天" in w for w in warns))
        _, _, warns = build(cfg(audience="rd", meeting="2026-10-05"))
        self.assertFalse(any("週會前 2 天" in w for w in warns))


class WordingTests(unittest.TestCase):
    def errs(self, done):
        return build(cfg(done=done))[1]

    def test_banned_terms(self):
        for word in ("環境變數", "部署", "資料表", "金鑰", "逾時", "資料代理"):
            with self.subTest(word=word):
                self.assertTrue(self.errs(f"已經{word}好了"), word)
        self.assertTrue(any("我們內部的叫法" in e for e in self.errs("Custom App 改好了")))

    def test_english_and_codes(self):
        for text in ("API 改好了", "hotfix 上了", "UAT 準備好了", "token 換好了", "不會再 404 了", "修好 503"):
            with self.subTest(text=text):
                self.assertTrue(self.errs(text), text)

    def test_allowed_words(self):
        for text in ("「訂單匯出」做好了，可以匯出 Excel", "LINE 通知改好了", "可以下載 500 筆", "9 月的報表做好了"):
            with self.subTest(text=text):
                self.assertEqual(self.errs(text), [], text)

    def test_quotes_and_urls_are_exempt(self):
        self.assertEqual(self.errs("「Export CSV」按鈕做好了"), [])
        self.assertEqual(build(cfg(url="https://example.ai-go.app/runtime/api-tool#/deploy"))[1], [])

    def test_allow_list(self):
        self.assertTrue(self.errs("Shopee 訂單可以匯入了"))
        self.assertEqual(build(cfg(done="Shopee 訂單可以匯入了"), allow=["shopee"])[1], [])

    def test_ui_vocab(self):
        tmp = Path(tempfile.mkdtemp()) / "ui.json"
        tmp.write_text(json.dumps({"orders": {"buttons": ["匯出", "Sync now"], "tabs": ["訂單"]}}), encoding="utf-8")
        strings, words = ho.ui_vocab(tmp)
        self.assertIn("匯出", strings)
        self.assertEqual(words, {"sync", "now"})
        _, errors, warns = build(cfg(done="按 Sync now 就會更新"), allow=words, ui_strings=strings)
        self.assertEqual(errors, [])
        self.assertFalse(any("找不到" in w for w in warns))
        c = cfg()
        c["steps"][0]["do"] = "按「匯入」"
        _, _, warns = build(c, ui_strings=strings)
        self.assertTrue(any("「匯入」在畫面上找不到" in w for w in warns))


class SafetyTests(unittest.TestCase):
    def test_danger_steps(self):
        for do in ("按「刪除」", "按「發送」把通知寄給客人", "選一筆訂單按「退款」", "清空購物車"):
            with self.subTest(do=do):
                c = cfg()
                c["steps"][0]["do"] = do
                self.assertTrue(any(e.startswith("安全") for e in build(c)[1]), do)

    def test_secrets(self):
        for done in ("做好了，密碼：abc123", "做好了，帳號：wang@example.com",
                     "金鑰 dev_sk_abcdef", "權杖 eyJhbGciOiJIUzI1NiJ9.eyJzdWIi"):
            with self.subTest(done=done):
                self.assertTrue(any(e.startswith("安全") for e in self.errs_any(done)), done)

    def errs_any(self, done):
        return build(cfg(done=done))[1]

    def test_url_with_token(self):
        _, errors, _ = build(cfg(url="https://example.ai-go.app/runtime/x?token=abc#/"))
        self.assertTrue(any("網址帶了金鑰" in e for e in errors))

    def test_fixed_ai_text_passes_own_lint(self):
        _, errors, _ = build(cfg(ai_helper="王經理"))
        self.assertEqual(errors, [])


class WeeklyTests(unittest.TestCase):
    def test_changes_and_decisions(self):
        c = {"mode": "weekly", "to": "王經理", "reply_by": "2026-10-06",
             "changes": [{"feature": "訂單匯出", "site": "測試站", "url": "https://example.ai-go.app/x", "note": "可以選月份"}],
             "decisions": [{"ask": "要不要加電話？", "options": ["要", "不要"]}]}
        msg, errors, _ = build(c)
        self.assertEqual(errors, [])
        self.assertIn("本週變動：\n1. 「訂單匯出」做好了，放在測試站：https://example.ai-go.app/x", msg)
        self.assertIn("1. 要不要加電話？（要／不要）", msg)
        self.assertIn("請在 10/6（二）前回覆我", msg)

    def test_no_decisions(self):
        c = {"mode": "weekly", "to": "王經理", "changes": [{"feature": "訂單匯出", "site": "正式站"}]}
        msg, errors, _ = build(c)
        self.assertEqual(errors, [])
        self.assertIn("這週沒有要您決定的事", msg)

    def test_empty_week(self):
        with self.assertRaises(ho.HandoffError):
            build({"mode": "weekly", "to": "王經理"})


class CliTests(unittest.TestCase):
    def run_cli(self, path, *args):
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = ho.main([str(path), "--today", "2026-10-04", *args])
        return code, out.getvalue(), err.getvalue()

    def test_templates_pass(self):
        for name in ("handoff.example.json", "handoff.weekly.example.json"):
            with self.subTest(name=name):
                code, out, err = self.run_cli(ROOT / "templates" / name)
                self.assertEqual(code, 0, err)
                self.assertIn("王經理您好", out)

    def test_failure_prints_no_message(self):
        tmp = Path(tempfile.mkdtemp())
        p = tmp / "h.json"
        p.write_text(json.dumps(cfg(done="API 部署好了"), ensure_ascii=False), encoding="utf-8")
        code, out, err = self.run_cli(p, "--out", str(tmp / "o.txt"))
        self.assertEqual(code, 1)
        self.assertEqual(out, "")
        self.assertIn("「部署」", err)
        self.assertIn("「API」", err)
        self.assertFalse((tmp / "o.txt").exists())


if __name__ == "__main__":
    unittest.main()
