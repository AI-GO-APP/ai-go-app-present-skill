# -*- coding: utf-8 -*-
"""交付通知：把這次交付組成一則可以直接貼給需求方的訊息，並在產出前檢查用語與安全（只用標準函式庫）。

兩種訊息（輸入檔範本：templates/handoff.example.json、templates/handoff.weekly.example.json）：
  notice  做完一件事就交。固定五段：做好了什麼／在哪裡看／驗什麼怎麼驗（≤ 5 步）／何時回覆／不行回給誰附什麼。
          對方有「會用 AI 的人」且在測試站 → 上下兩段：上段給人看，下段整段貼給對方的 AI 照步驟測、照格式回報。
  weekly  本週薄版：只放本週變動和要對方決定的事。

用法：
  python scripts/handoff.py handoff.json                       # 印出訊息；檢查不過 exit 1、不印訊息
  python scripts/handoff.py handoff.json --ui disc/ui.json     # 畫面上的字（按鈕、分頁…）加進白名單
  python scripts/handoff.py handoff.json --out 交付通知.txt     # 另存檔案
  python scripts/handoff.py handoff.json --allow Shopee,momo   # 額外允許的英文詞

檢查（不過就 exit 1，逐條列出哪一句、哪個詞）：
  - 用語：開發用語、英文與縮寫、錯誤代碼、內部叫法。「」裡的字與網址不檢查（「」＝畫面上照抄的字）
  - 安全：步驟不能有刪資料、對外發訊息、付款的動作；訊息不能有帳號密碼、金鑰、帶金鑰的網址
  - 格式：五段齊全、步驟 1～5 步、連結是網址、回覆期限不在過去
提醒（印在 stderr，不擋）：FDE 沒在週會前 2 天交、步驟一句太長、「」裡的字在畫面上找不到（有給 --ui 時）。
"""
import argparse
import datetime as _dt
import json
import re
import sys
from pathlib import Path

TW = _dt.timezone(_dt.timedelta(hours=8))
WEEKDAY = "一二三四五六日"
MAX_STEPS = 5
TEST_SITE, PROD_SITE = "測試站", "正式站"
SEP = "———— 以下請整段複製，貼給您的 AI ————"

# 不能出現的詞（「」裡與網址除外）。英文詞另有通則：不在白名單的英文一律擋
BANNED = {
    "開發時才會碰到的詞": ["環境變數", "分支", "合併", "部署", "程式碼", "資料表", "欄位權限", "金鑰", "後端", "前端",
                    "資料庫", "伺服器", "快取", "原始碼", "資料結構"],
    "錯誤代碼": ["逾時", "錯誤代碼", "錯誤碼", "狀態碼"],
    "我們內部的叫法": ["Hosted App", "Custom App", "資料代理", "VFS", "Server-Side Action", "資料中心"],
}
# 客戶平常也會講的英文
ALLOW = {"ai", "app", "line", "email", "e-mail", "excel", "pdf", "csv", "google", "iphone", "android", "word", "ok"}
ERROR_CODES = re.compile(r"(?<![\d/.:])(?:400|401|403|404|405|408|409|413|422|429|500|502|503|504)(?![\d/.%])"
                         r"(?!\s*(?:筆|張|元|個|人|天|次|件|份|頁|行|字|分|秒|塊))")
LATIN = re.compile(r"[A-Za-z][A-Za-z0-9+\-]*")
QUOTE = re.compile(r"「([^」]*)」")
URL = re.compile(r"https?://[\x21-\x7e]+")
# 步驟裡不能有的動作（「」裡也算：按「刪除」就是刪除）
DANGER = re.compile(r"刪除|刪掉|移除|清空|作廢|封存|發送|寄出|寄信|推播|群發|發訊息|傳訊息|回覆客人|通知客人|付款|刷卡|退款|轉帳")
SECRET = [
    (re.compile(r"(密碼|帳密|password|passwd)\s*[:：=]\s*\S", re.I), "密碼"),
    (re.compile(r"(帳號|account|email)\s*[:：=]\s*\S+@\S+", re.I), "登入帳號"),
    (re.compile(r"dev_sk_|sk-[A-Za-z0-9]{8,}|eyJ[A-Za-z0-9_-]{10,}\."), "金鑰"),
    (re.compile(r"(?<![A-Za-z0-9])[A-Za-z0-9_\-]{32,}(?![A-Za-z0-9])"), "像金鑰的長字串"),
]
URL_SECRET = re.compile(r"[?&#](?:token|access_token|key|api_key|pat|password|secret|sig)=", re.I)


class HandoffError(Exception):
    """輸入檔缺欄位或格式不對（不是用語問題）。"""


def today_tw():
    return _dt.datetime.now(TW).date()


def fmt_date(d):
    """2026-10-06 →「10/6（一）」。"""
    return f"{d.month}/{d.day}（{WEEKDAY[d.weekday()]}）"


def _date(v, field):
    try:
        return _dt.date.fromisoformat(str(v))
    except ValueError:
        raise HandoffError(f"{field} 要寫成 YYYY-MM-DD：{v!r}")


def add_workdays(d, n):
    while n > 0:
        d += _dt.timedelta(days=1)
        if d.weekday() < 5:
            n -= 1
    return d


def reply_deadline(cfg, today):
    """回覆期限：有寫 reply_by 就用；FDE 有週會日 → 週會前一天；其他 → 今天起第 2 個工作日。"""
    if cfg.get("reply_by"):
        return _date(cfg["reply_by"], "reply_by")
    if cfg.get("meeting"):
        return _date(cfg["meeting"], "meeting") - _dt.timedelta(days=1)
    return add_workdays(today, 2)


def _need(cfg, *keys):
    miss = [k for k in keys if not str(cfg.get(k) or "").strip()]
    if miss:
        raise HandoffError("缺欄位：" + "、".join(miss))


def _check_url(url, field="url"):
    if not URL.fullmatch(str(url or "")):
        raise HandoffError(f"{field} 要是完整網址（https://…）：{url!r}")


def _human_step(s):
    if s.get("say"):
        return s["say"]
    return f"{s['do']}，看到{s['expect']}就對了" if s.get("expect") else s["do"]


def compose_notice(cfg, today):
    """回傳 (parts, notes)。parts＝[(標籤, 文字)]；notes＝給 RD 的提醒（不進訊息）。"""
    _need(cfg, "to", "feature", "site", "url")
    site = cfg["site"]
    if site not in (TEST_SITE, PROD_SITE):
        raise HandoffError(f"site 只能是「{TEST_SITE}」或「{PROD_SITE}」：{site!r}")
    _check_url(cfg["url"])
    steps = cfg.get("steps") or []
    if not 1 <= len(steps) <= MAX_STEPS:
        raise HandoffError(f"步驟要 1～{MAX_STEPS} 步，現在 {len(steps)} 步；太多就拆成兩次交付，或只留對方最在意的")
    for i, s in enumerate(steps, 1):
        if not str(s.get("do") or "").strip():
            raise HandoffError(f"第 {i} 步缺 do（要做什麼）")
    notes = []
    to, feature, url = cfg["to"], cfg["feature"], cfg["url"]
    due = fmt_date(reply_deadline(cfg, today))
    reply_to = cfg.get("reply_to") or "我"
    done = cfg.get("done") or f"「{feature}」做好了"
    helper = str(cfg.get("ai_helper") or "").strip()
    use_ai = bool(helper) and site == TEST_SITE
    if helper and not use_ai:
        notes.append(f"對方有會用 AI 的人（{helper}），但這次在{PROD_SITE}：依安全規則只讓 AI 在{TEST_SITE}操作，所以只產出給人看的版本")
    if use_ai and any(not s.get("expect") for s in steps):
        raise HandoffError("給 AI 的版本每一步都要寫 expect（預期看到什麼），AI 才能判斷通過或不通過")

    head = [f"{to}您好，{done}，放在{site}。", f"連結：{url}"]
    if use_ai:
        upper = head + [
            "下面那段請直接貼給您的 AI，它會幫您測完並回報結果。",
            f"看完結果，請在 {due}前回我「可以」或「不行」。",
            f"不行的話，把 AI 的回報直接轉給{reply_to}就好，不用另外說明。",
        ]
        lower = [
            f"請幫我檢查{TEST_SITE}上的「{feature}」功能。網址：{url}",
            f"規則：只在{TEST_SITE}操作；不要刪除任何資料，不要送出訊息給任何人。"
            "請用我已經登入的瀏覽器操作；需要登入時停下來叫我，不要自己輸入帳號密碼。",
        ]
        lower += [f"{i}. {s['do']}。預期：{s['expect']}" for i, s in enumerate(steps, 1)]
        lower.append("請照這個格式回報：每一步寫「通過」或「不通過」；不通過的附截圖，寫你看到什麼。")
        parts = [(f"上半段：給{to}看", "\n".join(upper)), (f"下半段：貼給{to}的 AI", "\n".join(lower))]
    else:
        attach = cfg.get("attach") or "截圖"
        body = head + [f"麻煩您試 {len(steps)} 件事："]
        body += [f"{i}. {_human_step(s)}" for i, s in enumerate(steps, 1)]
        body += [f"請在 {due}前回我「可以」或「不行」。",
                 f"不行的話，{attach}傳給{reply_to}，說是第幾步就好。"]
        parts = [(f"給{to}", "\n".join(body))]
    return parts, notes


def compose_weekly(cfg, today):
    """本週薄版：本週變動＋要對方決定的事。"""
    _need(cfg, "to")
    changes = cfg.get("changes") or []
    decisions = cfg.get("decisions") or []
    if not changes and not decisions:
        raise HandoffError("changes 和 decisions 都是空的：這週沒東西就不用發")
    lines = [f"{cfg['to']}您好，這週的進度如下。"]
    if changes:
        lines.append("本週變動：")
        for i, c in enumerate(changes, 1):
            _need(c, "feature", "site")
            if c["site"] not in (TEST_SITE, PROD_SITE):
                raise HandoffError(f"changes 第 {i} 項 site 只能是「{TEST_SITE}」或「{PROD_SITE}」")
            line = f"{i}. 「{c['feature']}」{c.get('status') or '做好了'}，放在{c['site']}"
            if c.get("url"):
                _check_url(c["url"], f"changes 第 {i} 項 url")
                line += f"：{c['url']}"
            if c.get("note"):
                line += f"\n   {c['note']}"
            lines.append(line)
    due = fmt_date(reply_deadline(cfg, today))
    reply_to = cfg.get("reply_to") or "我"
    if decisions:
        lines.append("要請您決定的事：")
        for i, d in enumerate(decisions, 1):
            _need(d, "ask")
            opts = d.get("options") or []
            lines.append(f"{i}. {d['ask']}" + (f"（{'／'.join(opts)}）" if opts else ""))
        lines.append(f"請在 {due}前回覆{reply_to}，每一項回一個選擇就好。")
    else:
        lines.append(f"這週沒有要您決定的事。測試站上的東西有問題，截圖傳給{reply_to}就好。")
    return [(f"本週薄版：給{cfg['to']}", "\n".join(lines))], []


def ui_vocab(path):
    """從 discover.mjs 的 ui.json（或任何 JSON）收集畫面上的字：整串（核對「」用）與其中的英文詞（加進白名單）。"""
    strings = set()

    def walk(v):
        if isinstance(v, str):
            strings.add(v.strip())
        elif isinstance(v, dict):
            for x in v.values():
                walk(x)
        elif isinstance(v, list):
            for x in v:
                walk(x)

    walk(json.loads(Path(path).read_text(encoding="utf-8")))
    words = {w.lower() for s in strings for w in LATIN.findall(s)}
    return strings, words


def lint(parts, cfg, allow=(), ui_strings=None):
    """回傳 (errors, warnings)，每條都指出哪一段哪一行。"""
    errors, warns = [], []
    ok = ALLOW | {a.lower() for a in allow}
    for label, text in parts:
        for line in text.splitlines():
            where = f"［{label}］{line.strip()}"
            bare = QUOTE.sub("「」", URL.sub("", line))
            hit = set()
            for cat, terms in BANNED.items():
                for t in terms:
                    if t.lower() in bare.lower():
                        errors.append(f"用語（{cat}）「{t}」：{where}")
                        hit.update(w.lower() for w in LATIN.findall(t))
            if ERROR_CODES.search(bare):
                errors.append(f"用語（錯誤代碼）「{ERROR_CODES.search(bare).group()}」：{where}")
            for w in LATIN.findall(bare):
                if w.lower() not in ok and w.lower() not in hit:
                    errors.append(f"用語（英文與縮寫）「{w}」：{where}")
            for rx, name in SECRET:
                if rx.search(URL.sub("", line)):
                    errors.append(f"安全（訊息裡不能有{name}）：{where}")
            for u in URL.findall(line):
                if URL_SECRET.search(u):
                    errors.append(f"安全（網址帶了金鑰或登入參數）：{u}")
            if ui_strings is not None:
                for q in QUOTE.findall(line):
                    if q and q not in ui_strings and q != cfg.get("feature") and q not in ("可以", "不行", "通過", "不通過"):
                        warns.append(f"「{q}」在畫面上找不到，確認是畫面上的字（一字不差）：{where}")
    steps = cfg.get("steps") or []
    for i, s in enumerate(steps, 1):
        text = f"{s.get('do', '')} {s.get('say', '')}"
        m = DANGER.search(text)
        if m:
            errors.append(f"安全（步驟不能有刪資料、對外發訊息、付款的動作）「{m.group()}」：第 {i} 步 {text.strip()}")
        if len(str(s.get("do") or "")) > 40:
            warns.append(f"第 {i} 步太長，一句只講一個動作：{s['do']}")
    return list(dict.fromkeys(errors)), list(dict.fromkeys(warns))


def timing_warnings(cfg, today):
    """FDE 給客戶：週會前 2 天要交。"""
    if cfg.get("audience") == "fde" and cfg.get("meeting"):
        meeting = _date(cfg["meeting"], "meeting")
        if (meeting - today).days < 2:
            return [f"FDE 交付通知要在週會前 2 天交（週會 {fmt_date(meeting)}，今天 {fmt_date(today)}），會上才能只討論結果"]
    return []


def build(cfg, today=None, allow=(), ui_strings=None):
    """組訊息＋檢查。回傳 (message, errors, warnings)。"""
    today = today or today_tw()
    mode = cfg.get("mode") or "notice"
    if mode == "notice":
        parts, notes = compose_notice(cfg, today)
    elif mode == "weekly":
        parts, notes = compose_weekly(cfg, today)
    else:
        raise HandoffError(f"mode 只能是 notice 或 weekly：{mode!r}")
    due = reply_deadline(cfg, today)
    errors, warns = lint(parts, cfg, allow, ui_strings)
    if due < today:
        errors.append(f"回覆期限 {fmt_date(due)} 已經過了")
    warns = notes + timing_warnings(cfg, today) + warns
    message = f"\n\n{SEP}\n\n".join(text for _, text in parts)
    return message, errors, warns


def main(argv=None):
    for s in (sys.stdout, sys.stderr):
        try:
            s.reconfigure(encoding="utf-8")
        except AttributeError:
            pass
    ap = argparse.ArgumentParser(description="交付通知：組訊息＋用語與安全檢查")
    ap.add_argument("input", help="輸入 JSON（templates/handoff.example.json）")
    ap.add_argument("--ui", help="discover.mjs 的 ui.json：畫面上的字加進白名單")
    ap.add_argument("--allow", default="", help="額外允許的英文詞，逗號分隔")
    ap.add_argument("--out", help="訊息另存成這個檔案")
    ap.add_argument("--today", help="今天的日期（測試用，YYYY-MM-DD）")
    a = ap.parse_args(argv)
    try:
        cfg = json.loads(Path(a.input).read_text(encoding="utf-8"))
        allow = [w.strip() for w in a.allow.split(",") if w.strip()] + list(cfg.get("allow") or [])
        ui_strings = None
        if a.ui:
            ui_strings, ui_words = ui_vocab(a.ui)
            allow += list(ui_words)
        today = _date(a.today, "--today") if a.today else None
        message, errors, warns = build(cfg, today, allow, ui_strings)
    except (HandoffError, json.JSONDecodeError, OSError) as e:
        print(f"✗ {e}", file=sys.stderr)
        return 1
    for w in warns:
        print(f"! {w}", file=sys.stderr)
    if errors:
        print(f"✗ 檢查沒過（{len(errors)} 項），改寫後重跑：", file=sys.stderr)
        for e in errors:
            print(f"  - {e}", file=sys.stderr)
        return 1
    print(message)
    if a.out:
        Path(a.out).write_text(message + "\n", encoding="utf-8")
        print(f"→ {a.out}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
