# -*- coding: utf-8 -*-
"""進度報告（FDE 給客戶，一週一則）：組成一則可以直接貼給客戶的文字訊息，產出前檢查用語與安全（只用標準函式庫）。

Phase 0 使用者選了「進度報告」才用（references/progress-report.md）。輸入檔範本：templates/progress.example.json。
一則涵蓋這週所有做好的事，週會前 48 小時交；會上只討論結果。內容固定：做好了什麼／連結（交付站，問使用者）／
每件事怎麼驗（各 1～5 步）／要對方決定的事（選填）／何時回覆「可以」或「不行」／不行回給誰、附什麼。
有助於說明時可以補畫面（items[].images）：訊息裡寫「附圖 N」，圖片照順序另外附上。
with_ai＝true（每次問使用者：對方有沒有會用 AI 的人）→ 上下兩段：上段給人看，下段整段貼給對方的 AI
照步驟測、照格式回報。

用法：
  python scripts/progress.py progress.json                     # 印出訊息；檢查不過 exit 1、不印訊息
  python scripts/progress.py progress.json --ui disc/ui.json   # 畫面上的字（按鈕、分頁…）加進白名單
  python scripts/progress.py progress.json --out "AI GO 租戶 App 進度報告 20261004.txt"   # 另存；附圖複製成同名加「_附圖1.png」…
  python scripts/progress.py progress.json --allow Shopee,momo # 額外允許的英文詞

檢查（不過就 exit 1，逐條列出哪一句、哪個詞）：
  - 用語：開發用語、英文與縮寫、錯誤代碼、內部叫法。「」裡的字與網址不檢查（「」＝畫面上照抄的字）
  - 安全：步驟（做什麼與預期結果）不能有刪資料、對外發訊息、付款的動作；訊息不能有帳號密碼、金鑰、帶金鑰的網址
  - 格式：欄位齊全、每件事 1～5 步、連結是網址、附圖檔案存在、回覆期限不在過去
提醒（印在 stderr，不擋）：離週會不到 48 小時、整則超過 10 步、步驟一句太長、附圖要先過密鑰檢查、
「」裡的字在畫面上找不到（有給 --ui 時）。
"""
import argparse
import datetime as _dt
import json
import re
import shutil
import sys
from pathlib import Path

TW = _dt.timezone(_dt.timedelta(hours=8))
WEEKDAY = "一二三四五六日"
NUM = "一二三四五六七八九十"
MAX_STEPS = 5
TOTAL_STEPS_WARN = 10
FDE_LEAD_HOURS = 48
SEP = "———— 以下請整段複製，貼給您的 AI ————"

# 不能出現的詞（「」裡與網址除外）。英文詞另有通則：不在白名單的英文一律擋
# 清單照 issue #8；其他英文內部叫法（VFS、Server-Side Action…）由英文通則擋
BANNED = {
    "開發時才會碰到的詞": ["環境變數", "分支", "合併", "部署", "程式碼", "資料表", "欄位權限", "金鑰"],
    "錯誤代碼": ["逾時"],
    "我們內部的叫法": ["Hosted App", "Custom App", "資料代理"],
}
# 含禁用詞的一般用語：先拿掉再檢查
BANNED_OK = ["分支機構"]
# 客戶平常也會講的英文
ALLOW = {"ai", "app", "line", "email", "e-mail", "excel", "pdf", "csv", "google", "iphone", "android", "word", "ok"}
ERROR_CODES = re.compile(r"(?<![\d/.:])(?:400|401|403|404|405|408|409|413|422|429|500|502|503|504)(?![\d/.%])"
                         r"(?!\s*(?:筆|張|元|個|人|天|次|件|份|字|分|秒|塊))")
LATIN = re.compile(r"[A-Za-z][A-Za-z0-9+\-]*")
QUOTE = re.compile(r"「([^」]*)」")
URL = re.compile(r"https?://[\x21-\x7e]+")
# 步驟裡不能有的動作（「」裡也算：按「刪除」就是刪除）
DANGER = re.compile(r"刪除|刪掉|清空|作廢|發送|寄出|寄信|推播|群發|發訊息|傳訊息|回覆客人|通知客人|付款|刷卡|退款|轉帳")
SECRET = [
    (re.compile(r"(密碼|帳密|password|passwd)\s*[:：=]\s*\S", re.I), "密碼"),
    (re.compile(r"(帳號|account|email)\s*[:：=]\s*\S+@\S+", re.I), "登入帳號"),
    (re.compile(r"dev_sk_|sk-[A-Za-z0-9]{8,}|eyJ[A-Za-z0-9_-]{10,}\."), "金鑰"),
    (re.compile(r"(?<![A-Za-z0-9])[A-Za-z0-9_\-]{32,}(?![A-Za-z0-9])"), "像金鑰的長字串"),
]
URL_SECRET = re.compile(r"[?&#](?:token|access_token|key|api_key|pat|password|secret|sig)=", re.I)
FIXED_QUOTES = {"可以", "不行", "通過", "不通過"}
IMAGE_EXT = {".png", ".jpg", ".jpeg", ".gif", ".webp"}


class ProgressError(Exception):
    """輸入檔缺欄位或格式不對（不是用語問題）。"""


def now_tw():
    return _dt.datetime.now(TW).replace(tzinfo=None, second=0, microsecond=0)


def fmt_date(d):
    """2026-10-06 →「10/6（二）」。"""
    return f"{d.month}/{d.day}（{WEEKDAY[d.weekday()]}）"


def parse_when(v, field):
    """「YYYY-MM-DD」或「YYYY-MM-DD HH:MM」→ (datetime, 有沒有寫時間)。"""
    s = str(v).strip()
    try:
        if len(s) <= 10:
            return _dt.datetime.combine(_dt.date.fromisoformat(s), _dt.time()), False
        t = _dt.datetime.fromisoformat(s.replace("T", " "))
        if t.tzinfo:                                  # 帶時區 → 換成台灣時間再去掉時區
            t = t.astimezone(TW).replace(tzinfo=None)
        return t, True
    except ValueError:
        raise ProgressError(f"{field} 要寫成 YYYY-MM-DD 或 YYYY-MM-DD HH:MM：{v!r}")


def _end_of(d):
    return _dt.datetime.combine(d + _dt.timedelta(days=1), _dt.time())


def reply_deadline(cfg, now):
    """回覆期限 (截止時間點, 顯示文字)：有寫 reply_by 就用，否則＝週會開始前。只寫日期＝那天結束前。"""
    if cfg.get("reply_by"):
        t, timed = parse_when(cfg["reply_by"], "reply_by")
        return (t, f"{fmt_date(t.date())}{t:%H:%M} 前") if timed else (_end_of(t.date()), f"{fmt_date(t.date())}前")
    m, timed = parse_when(cfg["meeting"], "meeting")
    return (m if timed else _end_of(m.date())), f"{fmt_date(m.date())}{f'{m:%H:%M} ' if timed else ''}週會前"


def _need(obj, where, *keys):
    miss = [k for k in keys if not str(obj.get(k) or "").strip()]
    if miss:
        raise ProgressError(f"{where}缺欄位：" + "、".join(miss))


def _check_url(url, field="url"):
    if not URL.fullmatch(str(url or "")):
        raise ProgressError(f"{field} 要是完整網址（https://…）：{url!r}")


def _num(n):
    return NUM[n - 1] if n <= len(NUM) else str(n)


def _human_step(s):
    if s.get("say"):
        return s["say"]
    return f"{s['do']}，看到{s['expect']}就對了" if s.get("expect") else s["do"]


def validate(cfg, base=None):
    """base＝附圖路徑的起點（輸入檔所在資料夾）；None＝不檢查附圖檔案在不在。"""
    _need(cfg, "", "to", "url")
    _check_url(cfg["url"])
    if cfg.get("audience") not in (None, "fde"):
        raise ProgressError(f"進度報告只給 FDE 用（FDE 給客戶，一週一則）：audience={cfg.get('audience')!r}")
    if not cfg.get("meeting"):
        raise ProgressError("要填 meeting（這週週會的日期時間）：回覆期限和 48 小時提醒都靠它")
    if not isinstance(cfg.get("with_ai"), bool):
        raise ProgressError("with_ai 沒填：每次都要問使用者「對方有沒有會用 AI 的人」，再填 true 或 false（prompts.md §9）")
    items = cfg.get("items") or []
    if not items:
        raise ProgressError("items 是空的：至少要有一件做好的事")
    for n, it in enumerate(items, 1):
        where = f"items 第 {n} 項"
        _need(it, where, "feature")
        if it.get("url"):
            _check_url(it["url"], f"{where} url")
        steps = it.get("steps") or []
        if not 1 <= len(steps) <= MAX_STEPS:
            raise ProgressError(f"{where}（「{it['feature']}」）步驟要 1～{MAX_STEPS} 步，現在 {len(steps)} 步；"
                               "太多就只留對方最在意的")
        for img in it.get("images") or []:
            if Path(str(img)).suffix.lower() not in IMAGE_EXT:
                raise ProgressError(f"{where}附圖要是圖片（{'、'.join(sorted(IMAGE_EXT))}）：{img}")
            if base is not None and not (Path(base) / img).is_file():
                raise ProgressError(f"{where}附圖找不到：{img}（路徑從輸入檔所在資料夾算）")
        for i, s in enumerate(steps, 1):
            _need(s, f"{where}第 {i} 步", "do")
            if cfg["with_ai"] and not str(s.get("expect") or "").strip():
                raise ProgressError(f"{where}第 {i} 步缺 expect：給 AI 的版本每一步都要寫預期看到什麼，AI 才能判斷通過或不通過")
    for n, d in enumerate(cfg.get("decisions") or [], 1):
        _need(d, f"decisions 第 {n} 項", "ask")
    return items


def images(cfg):
    """附圖照訊息裡的編號排好：[(編號, 路徑)]。"""
    out = []
    for it in cfg.get("items") or []:
        for img in it.get("images") or []:
            out.append((len(out) + 1, img))
    return out


def compose(cfg, now, base=None):
    """回傳 parts＝[(標籤, 文字)]。"""
    items = validate(cfg, base)
    refs, k = [], 0
    for it in items:
        n = len(it.get("images") or [])
        refs.append("、".join(f"附圖 {k + j + 1}" for j in range(n)))
        k += n
    to, url, with_ai = cfg["to"], cfg["url"], cfg["with_ai"]
    decisions = cfg.get("decisions") or []
    reply_to = cfg.get("reply_to") or "我"
    attach = cfg.get("attach") or "截圖"
    due = reply_deadline(cfg, now)[1]
    single = len(items) == 1
    names = "、".join(f"「{it['feature']}」" for it in items)

    if single:
        head = [f"{to}您好，{items[0].get('done') or names + '做好了'}。"]
    elif with_ai:                                     # 上段不列步驟，每件做了什麼要寫出來，人才能判斷是不是要的
        head = [f"{to}您好，這週做好了 {len(items)} 件事："]
        head += [f"{_num(n)}、「{it['feature']}」" + (f"：{it['done']}" if it.get("done") else "")
                 + (f"（{refs[n - 1]}）" if refs[n - 1] else "") for n, it in enumerate(items, 1)]
    else:
        head = [f"{to}您好，這週做好了 {len(items)} 件事：{names}。"]
    head.append(f"連結：{url}")
    if single and refs[0]:
        head.append(f"畫面：{refs[0]}")

    def heading(n, it, for_ai=False):
        line = f"{_num(n)}、「{it['feature']}」"
        if it.get("done") and not for_ai:
            line += f"：{it['done']}"
        out = [line] + ([f"連結：{it['url']}"] if it.get("url") else [])
        return out + ([f"畫面：{refs[n - 1]}"] if refs[n - 1] and not for_ai else [])

    dec = []
    if decisions:
        dec.append("要請您決定的事：")
        for n, d in enumerate(decisions, 1):
            opts = d.get("options") or []
            dec.append(f"{n}. {d['ask']}" + (f"（{'／'.join(opts)}）" if opts else ""))
    ask = "「可以」或「不行」" if single else "每件事「可以」或「不行」"
    if decisions:
        ask += "，決定的事各回一個選擇"
    which = "第幾步" if single else "哪件事第幾步"

    if with_ai:
        upper = head + ["下面那段請直接貼給您的 AI，它會幫您測完並回報結果。"] + dec + [
            f"看完結果，請在 {due}回我{ask}。",
            f"不行的話，把 AI 的回報直接轉給{reply_to}就好，不用另外說明。",
        ]
        target = f"「{items[0]['feature']}」功能" if single else f"下面 {len(items)} 個功能"
        lower = [
            f"請幫我檢查{target}。網址：{url}",
            "規則：只在這個網址上操作；不要刪除任何資料，不要送出訊息給任何人。"
            "請用我已經登入的瀏覽器操作；需要登入時停下來叫我，不要自己輸入帳號密碼。",
        ]
        for n, it in enumerate(items, 1):
            if not single:
                lower += heading(n, it, for_ai=True)
            elif it.get("url"):
                lower.append(f"從這個網址開始：{it['url']}")
            lower += [f"{i}. {s['do']}。預期：{s['expect']}" for i, s in enumerate(it["steps"], 1)]
        each = "每一步" if single else "每個功能的每一步"
        lower.append(f"請照這個格式回報：{each}寫「通過」或「不通過」；不通過的附截圖，寫你看到什麼。")
        return [(f"上半段：給{to}看", "\n".join(upper)), (f"下半段：貼給{to}的 AI", "\n".join(lower))]

    body = list(head)
    if single:
        steps = items[0]["steps"]
        if items[0].get("url"):
            body.append(f"從這裡開始：{items[0]['url']}")
        body.append(f"麻煩您試 {len(steps)} 件事：")
        body += [f"{i}. {_human_step(s)}" for i, s in enumerate(steps, 1)]
    else:
        body.append("每件事請照下面試一次：")
        for n, it in enumerate(items, 1):
            body += heading(n, it)
            body += [f"{i}. {_human_step(s)}" for i, s in enumerate(it["steps"], 1)]
    body += dec + [f"請在 {due}回我{ask}。", f"不行的話，{attach}傳給{reply_to}，說是{which}就好。"]
    return [(f"給{to}", "\n".join(body))]


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
    items = cfg.get("items") or []
    features = {it.get("feature") for it in items}
    for label, text in parts:
        for line in text.splitlines():
            where = f"［{label}］{line.strip()}"
            bare = QUOTE.sub("「」", URL.sub("", line))
            for phrase in BANNED_OK:
                bare = bare.replace(phrase, "")
            hit = set()
            for cat, terms in BANNED.items():
                for t in terms:
                    if t.lower() in bare.lower():
                        errors.append(f"用語（{cat}）「{t}」：{where}")
                        hit.update(w.lower() for w in LATIN.findall(t))
            m = ERROR_CODES.search(bare)
            if m:
                errors.append(f"用語（錯誤代碼）「{m.group()}」：{where}")
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
                    if q and q not in ui_strings and q not in features and q not in FIXED_QUOTES:
                        warns.append(f"「{q}」在畫面上找不到，確認是畫面上的字（一字不差）：{where}")
    for it in items:
        for i, s in enumerate(it.get("steps") or [], 1):
            text = " ".join(str(s.get(k) or "") for k in ("do", "say", "expect")).strip()
            m = DANGER.search(text)
            if m:
                errors.append(f"安全（步驟不能有刪資料、對外發訊息、付款的動作）「{m.group()}」："
                              f"「{it.get('feature')}」第 {i} 步 {text.strip()}")
            if len(str(s.get("do") or "")) > 40:
                warns.append(f"「{it.get('feature')}」第 {i} 步太長，一句只講一個動作：{s['do']}")
    total = sum(len(it.get("steps") or []) for it in items)
    if total > TOTAL_STEPS_WARN:
        warns.append(f"總共 {total} 步，超過 {TOTAL_STEPS_WARN} 步對方不容易做完：每件只留最關鍵的步驟，或把次要的事移到下週")
    return list(dict.fromkeys(errors)), list(dict.fromkeys(warns))


def timing_warnings(cfg, now):
    """週會前 48 小時要交。只寫日期時當作當天 00:00（從嚴）。"""
    meeting, _ = parse_when(cfg["meeting"], "meeting")
    hours = (meeting - now).total_seconds() / 3600
    if hours <= 0:
        return [f"週會時間 {meeting:%m/%d %H:%M} 已經過了：確認 meeting 填的是這週的週會"]
    if hours < FDE_LEAD_HOURS:
        return [f"FDE 交付說明要在週會前 {FDE_LEAD_HOURS} 小時交（週會 {meeting:%m/%d %H:%M}，現在只剩約 {max(hours, 0):.0f} 小時），"
                "對方來不及驗，會上就只能現場看"]
    return []


def build(cfg, now=None, allow=(), ui_strings=None, base=None):
    """組訊息＋檢查。回傳 (message, errors, warnings)。附圖清單用 images(cfg)。"""
    now = now or now_tw()
    parts = compose(cfg, now, base)
    errors, warns = lint(parts, cfg, allow, ui_strings)
    deadline, due = reply_deadline(cfg, now)
    if deadline <= now:
        errors.append(f"回覆期限 {due} 已經過了")
    warns = timing_warnings(cfg, now) + warns
    if images(cfg):
        warns.append("有附圖：送出前逐張確認沒有密碼、金鑰、客人個資（workflow.md G2）")
    message = f"\n\n{SEP}\n\n".join(text for _, text in parts)
    return message, errors, warns


def main(argv=None):
    for s in (sys.stdout, sys.stderr):
        try:
            s.reconfigure(encoding="utf-8")
        except AttributeError:
            pass
    ap = argparse.ArgumentParser(description="進度報告：組訊息＋用語與安全檢查")
    ap.add_argument("input", help="輸入 JSON（templates/progress.example.json）")
    ap.add_argument("--ui", help="discover.mjs 的 ui.json：畫面上的字加進白名單")
    ap.add_argument("--allow", default="", help="額外允許的英文詞，逗號分隔")
    ap.add_argument("--out", help="訊息另存成這個檔案")
    ap.add_argument("--now", help="現在時間（測試用，YYYY-MM-DD 或 YYYY-MM-DD HH:MM）")
    a = ap.parse_args(argv)
    try:
        cfg = json.loads(Path(a.input).read_text(encoding="utf-8"))
        allow = [w.strip() for w in a.allow.split(",") if w.strip()] + list(cfg.get("allow") or [])
        ui_strings = None
        if a.ui:
            ui_strings, ui_words = ui_vocab(a.ui)
            allow += list(ui_words)
        now = parse_when(a.now, "--now")[0] if a.now else None
        base = Path(a.input).resolve().parent
        message, errors, warns = build(cfg, now, allow, ui_strings, base)
    except (ProgressError, json.JSONDecodeError, OSError) as e:
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
    imgs = images(cfg)
    if imgs:
        print("附圖（照編號附上）：", file=sys.stderr)
    out = Path(a.out) if a.out else None
    if out:
        out.write_text(message + "\n", encoding="utf-8")
        print(f"→ {out}", file=sys.stderr)
    for n, img in imgs:
        src = base / img
        if out:
            dst = out.with_name(f"{out.stem}_附圖{n}{src.suffix.lower()}")
            shutil.copyfile(src, dst)
            print(f"  附圖 {n}：{img} → {dst}", file=sys.stderr)
        else:
            print(f"  附圖 {n}：{src}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
