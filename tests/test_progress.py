"""
進度報告（scripts/progress.py）的單元測試（標準函式庫 unittest）。

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
spec = importlib.util.spec_from_file_location("progress", ROOT / "scripts" / "progress.py")
ho = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ho)

NOW = dt.datetime(2026, 10, 4, 10, 0)      # 週日 10:00
URL = "https://example.ai-go.app/runtime/order-center"
EXPORT = {"feature": "訂單匯出", "steps": [
    {"do": "打開連結，進「訂單」頁", "expect": "右上角有「匯出」按鈕"},
    {"do": "月份選 9 月，按「匯出」", "expect": "下載一個檔案"},
]}
MASK = {"feature": "客人電話遮蔽", "done": "電話只顯示後三碼", "steps": [
    {"do": "進「訂單」頁", "expect": "電話只看得到後三碼"},
]}
ONE = {"to": "王經理", "url": URL, "with_ai": False, "items": [EXPORT], "meeting": "2026-10-07 14:00",
       "reply_by": "2026-10-06"}
FDE = {"to": "王經理", "url": URL, "with_ai": False, "items": [EXPORT, MASK], "meeting": "2026-10-07 14:00"}


def one(**kw):
    """這週只有一件事。"""
    c = copy.deepcopy(ONE)
    c.update(kw)
    return c


def fde(**kw):
    c = copy.deepcopy(FDE)
    c.update(kw)
    return c


def build(c, now=NOW, **kw):
    return ho.build(c, now=now, **kw)


class SingleTests(unittest.TestCase):
    def test_human_only_has_five_parts(self):
        msg, errors, _ = build(one())
        self.assertEqual(errors, [])
        self.assertNotIn(ho.SEP, msg)
        self.assertIn("王經理您好，「訂單匯出」做好了。", msg)                       # 做好了什麼
        self.assertIn(f"連結：{URL}", msg)                                           # 在哪裡看
        self.assertIn("1. 打開連結，進「訂單」頁，看到右上角有「匯出」按鈕就對了", msg)  # 怎麼驗
        self.assertIn("請在 10/6（二）前回我「可以」或「不行」", msg)                 # 何時回覆
        self.assertIn("不行的話，截圖傳給我，說是第幾步就好", msg)                    # 回給誰、附什麼

    def test_no_site_split(self):
        msg, _, _ = build(one(with_ai=True))
        for word in ("測試站", "正式站"):
            self.assertNotIn(word, msg)
        self.assertIn("只在這個網址上操作", msg)

    def test_done_and_say(self):
        c = one()
        c["items"][0]["done"] = "您上週提的「訂單匯出」做好了"
        c["items"][0]["steps"][1]["say"] = "按「匯出」，看有沒有下載一個檔案"
        msg, _, _ = build(c)
        self.assertIn("王經理您好，您上週提的「訂單匯出」做好了。", msg)
        self.assertIn("2. 按「匯出」，看有沒有下載一個檔案", msg)

    def test_with_ai_two_parts(self):
        msg, errors, _ = build(one(with_ai=True))
        self.assertEqual(errors, [])
        upper, lower = msg.split(ho.SEP)
        self.assertIn("下面那段請直接貼給您的 AI", upper)
        self.assertIn("把 AI 的回報直接轉給我", upper)
        self.assertNotIn("預期：", upper)
        self.assertIn("請幫我檢查「訂單匯出」功能。網址：" + URL, lower)
        self.assertIn("不要自己輸入帳號密碼", lower)
        self.assertIn("1. 打開連結，進「訂單」頁。預期：右上角有「匯出」按鈕", lower)
        self.assertIn("每一步寫「通過」或「不通過」", lower)

    def test_with_ai_must_be_asked(self):
        c = one()
        del c["with_ai"]
        with self.assertRaisesRegex(ho.ProgressError, "with_ai"):
            build(c)
        with self.assertRaisesRegex(ho.ProgressError, "with_ai"):
            build(one(with_ai="王經理"))

    def test_ai_version_needs_expect(self):
        c = one(with_ai=True)
        del c["items"][0]["steps"][0]["expect"]
        with self.assertRaisesRegex(ho.ProgressError, "expect"):
            build(c)

    def test_step_count(self):
        c = one()
        c["items"][0]["steps"] = []
        with self.assertRaises(ho.ProgressError):
            build(c)
        c["items"][0]["steps"] = [{"do": f"第 {i} 件事"} for i in range(6)]
        with self.assertRaises(ho.ProgressError):
            build(c)

    def test_required_fields(self):
        for key in ("url", "to", "items"):
            with self.subTest(key=key):
                c = one()
                del c[key]
                with self.assertRaises(ho.ProgressError):
                    build(c)
        with self.assertRaises(ho.ProgressError):
            build(one(url="交付站首頁"))
        with self.assertRaisesRegex(ho.ProgressError, "只給 FDE"):
            build(one(audience="rd"))
        self.assertEqual(build(one(audience="fde"))[1], [])


class WeeklyTests(unittest.TestCase):
    def test_one_message_covers_week(self):
        msg, errors, warns = build(fde(decisions=[{"ask": "要不要加電話？", "options": ["要", "不要"]}]))
        self.assertEqual(errors, [])
        self.assertEqual(warns, [])
        self.assertIn("王經理您好，這週做好了 2 件事：「訂單匯出」、「客人電話遮蔽」。", msg)
        self.assertIn("一、「訂單匯出」\n1. 打開連結", msg)
        self.assertIn("二、「客人電話遮蔽」：電話只顯示後三碼\n1. 進「訂單」頁", msg)
        self.assertIn("要請您決定的事：\n1. 要不要加電話？（要／不要）", msg)
        self.assertIn("請在 10/7（三）14:00 週會前回我每件事「可以」或「不行」，決定的事各回一個選擇。", msg)
        self.assertIn("說是哪件事第幾步", msg)

    def test_item_url(self):
        c = fde()
        c["items"][0]["url"] = URL + "#/orders"
        msg, _, _ = build(c)
        self.assertIn(f"一、「訂單匯出」\n連結：{URL}#/orders", msg)

    def test_with_ai_weekly(self):
        msg, errors, _ = build(fde(with_ai=True, decisions=[{"ask": "要不要加電話？"}]))
        self.assertEqual(errors, [])
        upper, lower = msg.split(ho.SEP)
        self.assertIn("這週做好了 2 件事：\n一、「訂單匯出」\n二、「客人電話遮蔽」：電話只顯示後三碼\n連結：", upper)
        self.assertNotIn("預期：", upper)
        self.assertIn("要請您決定的事", upper)              # 決定的事給人，不給 AI
        self.assertNotIn("要請您決定的事", lower)
        self.assertIn("請幫我檢查下面 2 個功能", lower)
        self.assertIn("二、「客人電話遮蔽」\n1. 進「訂單」頁。預期：電話只看得到後三碼", lower)
        self.assertIn("每個功能的每一步", lower)

    def test_needs_meeting(self):
        c = fde()
        del c["meeting"]
        with self.assertRaisesRegex(ho.ProgressError, "meeting"):
            build(c)


class ImageTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        (self.tmp / "shots").mkdir()
        for n in ("a.png", "b.png", "c.jpg"):
            (self.tmp / "shots" / n).write_bytes(b"x")

    def with_images(self, c):
        c["items"][0]["images"] = ["shots/a.png", "shots/b.png"]
        if len(c["items"]) > 1:
            c["items"][1]["images"] = ["shots/c.jpg"]
        return c

    def test_numbering_human(self):
        msg, errors, warns = build(self.with_images(fde()), base=self.tmp)
        self.assertEqual(errors, [])
        self.assertIn("一、「訂單匯出」\n畫面：附圖 1、附圖 2\n1. ", msg)
        self.assertIn("二、「客人電話遮蔽」：電話只顯示後三碼\n畫面：附圖 3\n1. ", msg)
        self.assertTrue(any("逐張確認" in w for w in warns))
        self.assertEqual(ho.images(self.with_images(fde())),
                         [(1, "shots/a.png"), (2, "shots/b.png"), (3, "shots/c.jpg")])

    def test_numbering_single_and_ai(self):
        msg, _, _ = build(self.with_images(one()), base=self.tmp)
        self.assertIn(f"連結：{URL}\n畫面：附圖 1、附圖 2", msg)
        msg, errors, _ = build(self.with_images(fde(with_ai=True)), base=self.tmp)
        self.assertEqual(errors, [])
        upper, lower = msg.split(ho.SEP)
        self.assertIn("一、「訂單匯出」（附圖 1、附圖 2）", upper)
        self.assertIn("二、「客人電話遮蔽」：電話只顯示後三碼（附圖 3）", upper)
        self.assertNotIn("附圖", lower)                    # AI 看不到圖，下段不提

    def test_missing_or_not_image(self):
        c = one()
        c["items"][0]["images"] = ["shots/none.png"]
        with self.assertRaisesRegex(ho.ProgressError, "找不到"):
            build(c, base=self.tmp)
        c["items"][0]["images"] = ["notes.txt"]
        with self.assertRaisesRegex(ho.ProgressError, "圖片"):
            build(c)

    def test_no_images_no_warning(self):
        self.assertFalse(any("逐張確認" in w for w in build(fde())[2]))


class DeadlineTests(unittest.TestCase):
    def test_format(self):
        self.assertEqual(ho.fmt_date(dt.date(2026, 10, 5)), "10/5（一）")
        self.assertEqual(ho.fmt_date(dt.date(2026, 10, 11)), "10/11（日）")

    def test_defaults(self):
        c = one()
        del c["reply_by"]
        self.assertEqual(ho.reply_deadline(c, NOW), (dt.datetime(2026, 10, 7, 14), "10/7（三）14:00 週會前"))
        self.assertEqual(ho.reply_deadline(fde(), NOW), (dt.datetime(2026, 10, 7, 14), "10/7（三）14:00 週會前"))
        self.assertEqual(ho.reply_deadline(fde(meeting="2026-10-07"), NOW)[1], "10/7（三）週會前")
        self.assertEqual(ho.reply_deadline(fde(reply_by="2026-10-06"), NOW)[1], "10/6（二）前")
        self.assertEqual(ho.reply_deadline(one(reply_by="2026-10-06 18:00"), NOW), (dt.datetime(2026, 10, 6, 18), "10/6（二）18:00 前"))

    def test_timezone(self):
        m, timed = ho.parse_when("2026-10-07T06:00:00+00:00", "meeting")
        self.assertEqual((m, timed), (dt.datetime(2026, 10, 7, 14, 0), True))
        _, errors, _ = build(fde(meeting="2026-10-07T14:00:00+08:00"))
        self.assertEqual(errors, [])

    def test_past_deadline_is_error(self):
        _, errors, _ = build(one(reply_by="2026-10-01"))
        self.assertTrue(any("已經過了" in e for e in errors))
        self.assertEqual(build(one(reply_by="2026-10-04"))[1], [])                     # 只寫日期＝當天結束前
        _, errors, warns = build(fde(), now=dt.datetime(2026, 10, 7, 16, 0))         # 週會當天已開過
        self.assertTrue(any("已經過了" in e for e in errors))
        _, errors, warns = build(fde(reply_by="2026-10-09"), now=dt.datetime(2026, 10, 7, 16, 0))
        self.assertTrue(any("確認 meeting" in w for w in warns))

    def test_fde_48_hours(self):
        warn = lambda now: any("48 小時" in w for w in build(fde(), now=now)[2])
        self.assertFalse(warn(dt.datetime(2026, 10, 5, 14, 0)))      # 剛好 48 小時
        self.assertTrue(warn(dt.datetime(2026, 10, 5, 14, 1)))
        self.assertTrue(any("48 小時" in w for w in build(fde(meeting="2026-10-06"))[2]))  # 只寫日期當 00:00


class WordingTests(unittest.TestCase):
    def errs(self, done):
        c = one()
        c["items"][0]["done"] = done
        return build(c)[1]

    def test_banned_terms(self):
        for word in ("環境變數", "部署", "資料表", "金鑰", "逾時", "資料代理"):
            with self.subTest(word=word):
                self.assertTrue(self.errs(f"已經{word}好了"), word)
        self.assertTrue(any("我們內部的叫法" in e for e in self.errs("Custom App 改好了")))

    def test_english_and_codes(self):
        for text in ("API 改好了", "hotfix 上了", "UAT 準備好了", "token 換好了", "不會再 404 了", "修好 503",
                     "不會再跳 404 頁面", "VFS 更新了", "分支合併了"):
            with self.subTest(text=text):
                self.assertTrue(self.errs(text), text)

    def test_allowed_words(self):
        for text in ("「訂單匯出」做好了，可以匯出 Excel", "LINE 通知改好了", "可以下載 500 筆", "9 月的報表做好了",
                     "可以選分支機構", "資料中心的表可以匯出"):
            with self.subTest(text=text):
                self.assertEqual(self.errs(text), [], text)

    def test_quotes_and_urls_are_exempt(self):
        self.assertEqual(self.errs("「Export CSV」按鈕做好了"), [])
        self.assertEqual(build(one(url="https://example.ai-go.app/runtime/api-tool#/deploy"))[1], [])

    def test_allow_list(self):
        self.assertTrue(self.errs("Shopee 訂單可以匯入了"))
        c = one()
        c["items"][0]["done"] = "Shopee 訂單可以匯入了"
        self.assertEqual(build(c, allow=["shopee"])[1], [])

    def test_ui_vocab(self):
        tmp = Path(tempfile.mkdtemp()) / "ui.json"
        tmp.write_text(json.dumps({"orders": {"buttons": ["匯出", "Sync now"], "tabs": ["訂單"]}}), encoding="utf-8")
        strings, words = ho.ui_vocab(tmp)
        self.assertIn("匯出", strings)
        self.assertEqual(words, {"sync", "now"})
        c = one()
        c["items"][0]["done"] = "按 Sync now 就會更新"
        _, errors, warns = build(c, allow=words, ui_strings=strings)
        self.assertEqual(errors, [])
        self.assertFalse(any("找不到" in w for w in warns))
        c["items"][0]["steps"][0]["do"] = "按「匯入」"
        _, _, warns = build(c, ui_strings=strings)
        self.assertTrue(any("「匯入」在畫面上找不到" in w for w in warns))


class SafetyTests(unittest.TestCase):
    def test_danger_steps(self):
        for do in ("按「刪除」", "按「發送」把通知寄給客人", "選一筆訂單按「退款」", "清空購物車"):
            with self.subTest(do=do):
                c = fde()
                c["items"][1]["steps"][0]["do"] = do
                self.assertTrue(any(e.startswith("安全") for e in build(c)[1]), do)

    def test_danger_in_expect(self):
        c = fde()
        c["items"][1]["steps"][0] = {"do": "按「儲存」", "expect": "客人手機收到 LINE 推播"}
        self.assertTrue(any("「推播」" in e for e in build(c)[1]))

    def test_harmless_actions_pass(self):
        c = fde()
        c["items"][1]["steps"][0]["do"] = "按「移除」把篩選條件拿掉"
        self.assertEqual(build(c)[1], [])

    def test_total_steps_warning(self):
        many = {"feature": "很多步", "steps": [{"do": f"第 {i} 步", "expect": "沒問題"} for i in range(5)]}
        c = fde()
        c["items"] += [copy.deepcopy(many), copy.deepcopy(many)]       # 2 + 1 + 5 + 5 = 13 步
        self.assertTrue(any("總共 13 步" in w for w in build(c)[2]))
        self.assertFalse(any("總共" in w for w in build(fde())[2]))

    def test_secrets(self):
        for done in ("做好了，密碼：abc123", "做好了，帳號：wang@example.com",
                     "金鑰 dev_sk_abcdef", "權杖 eyJhbGciOiJIUzI1NiJ9.eyJzdWIi"):
            with self.subTest(done=done):
                c = one()
                c["items"][0]["done"] = done
                self.assertTrue(any(e.startswith("安全") for e in build(c)[1]), done)

    def test_url_with_token(self):
        _, errors, _ = build(one(url=URL + "?token=abc#/"))
        self.assertTrue(any("網址帶了金鑰" in e for e in errors))

    def test_fixed_ai_text_passes_own_lint(self):
        for c in (one(with_ai=True), fde(with_ai=True)):
            self.assertEqual(build(c)[1], [])


class CliTests(unittest.TestCase):
    def test_out_copies_images(self):
        tmp = Path(tempfile.mkdtemp())
        (tmp / "shots").mkdir()
        (tmp / "shots" / "a.png").write_bytes(b"png")
        c = one()
        c["items"][0]["images"] = ["shots/a.png"]
        p = tmp / "p.json"
        p.write_text(json.dumps(c, ensure_ascii=False), encoding="utf-8")
        code, out, err = self.run_cli(p, "--out", str(tmp / "進度報告.txt"))
        self.assertEqual(code, 0, err)
        self.assertIn("畫面：附圖 1", out)
        self.assertEqual((tmp / "進度報告_附圖1.png").read_bytes(), b"png")
        self.assertTrue((tmp / "進度報告.txt").exists())

    def run_cli(self, path, *args):
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = ho.main([str(path), "--now", "2026-10-04 10:00", *args])
        return code, out.getvalue(), err.getvalue()

    def test_templates_pass(self):
        for name in ("progress.example.json",):
            with self.subTest(name=name):
                code, out, err = self.run_cli(ROOT / "templates" / name)
                self.assertEqual(code, 0, err)
                self.assertEqual(err, "")
                self.assertIn("王經理您好", out)

    def test_failure_prints_no_message(self):
        tmp = Path(tempfile.mkdtemp())
        c = one()
        c["items"][0]["done"] = "API 部署好了"
        p = tmp / "h.json"
        p.write_text(json.dumps(c, ensure_ascii=False), encoding="utf-8")
        code, out, err = self.run_cli(p, "--out", str(tmp / "o.txt"))
        self.assertEqual(code, 1)
        self.assertEqual(out, "")
        self.assertIn("「部署」", err)
        self.assertIn("「API」", err)
        self.assertFalse((tmp / "o.txt").exists())


if __name__ == "__main__":
    unittest.main()
