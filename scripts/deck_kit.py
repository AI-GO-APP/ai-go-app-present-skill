# -*- coding: utf-8 -*-
"""ai-go-app-present：AI GO 品牌 16:9 閱讀式簡報元件（每頁 1600×900 px＝母版 1280×720 的 1.25 倍）。

內容檔（見 templates/deck_content.example.py）這樣用：

    from deck_kit import Deck
    d = Deck.from_meta("disc/meta.json", purposes=["操作說明"], shots="shots", version="VFS v12")
    d.cover(...); d.slide(part, title, lede, body); ...; d.back_cover(...)
    html = d.write()          # →「AI GO 租戶名 App名 用途 YYYYMMDD.html」，PDF 同名

purposes＝Phase 0 使用者選的用途（PDF 類：功能展示／測試報告／整合測試／操作說明，至少一種；進度報告是文字訊息，
用 scripts/progress.py）。多選合成一份 PDF，內容頁依「功能展示 → 測試報告 → 整合測試 → 操作說明」排：
  功能展示 d.showcase(...)、測試報告 d.acceptance(...)、整合測試 d.itest(...)（讀 itest.mjs 的結果）、
  操作說明 d.slide()/d.divider()/d.raw()。
  slide()/divider()/raw() 預設屬於操作說明（沒選操作說明時屬於第一個選的用途）；d.section(用途) 可切換。
目錄頁一定會有：沒呼叫 d.toc() 時 write() 自動插在封面後面。頁碼、分隔頁頁目都在 write() 時才算。

版面預算（見 references/layout-guide.md）：內容區約 1392×650；兩張並排圖每張 ≤ 680 寬。
品牌規則：品牌藍不換色、每頁左緣藍條、封面／分隔頁／封底深底（見 references/brand.md）。
"""
import datetime as _dt
import json
import os
import re
from html import escape, unescape
from pathlib import Path

HERE = Path(__file__).resolve().parent
TW = _dt.timezone(_dt.timedelta(hours=8))
LOGO = ('<div class="logo"><svg viewBox="0 0 24 24" fill="none" stroke="#1F80FF" stroke-width="1.6" stroke-linecap="round">'
        '<path d="M12 3 L4.5 20 M12 3 L19.5 20 M8 13 h8"/><circle cx="12" cy="3" r="1.6" fill="#1F80FF"/></svg></div>')
_BAD = set('<>:"/\\|?*')
_TAG = re.compile(r"<[^>]+>")
_TOC_ROWS = 15          # 目錄每欄最多列數（一般字級）
_TOC_ROWS_DENSE = 18    # dense 字級
_TOC_HOWTO_ROWS = 3     # 目錄底部「讀法」列佔掉的列數
_TOC_HEAD_ROWS = 3      # 同一欄疊第二組時，組標題（含上方間距）佔掉的列數（實測約 2.6 列）
MANUAL, TEST, SHOWCASE, PROGRESS, ITEST = "操作說明", "測試報告", "功能展示", "進度報告", "整合測試"
PURPOSES = (MANUAL, PROGRESS, TEST, SHOWCASE, ITEST)   # Phase 0 的選項（可多選、至少一種）
DECK_ORDER = (SHOWCASE, TEST, ITEST, MANUAL)           # 出 PDF 的用途；多選合成一份時的順序
_TITLE = {SHOWCASE: "功能展示", TEST: "測試報告", ITEST: "整合測試報告", MANUAL: "操作手冊"}
ACC_PART = TEST
SHOW_MAX_PAGES, SHOW_MAX_NOTES, SHOW_MAX_VALUE = 12, 5, 40
ACC_MAX_PAGES, ACC_MAX_CARDS, ACC_MAX_ROWS = 2, 4, 8
ACC_HEAD = ("指標", "定義", "結果", "樣本", "測試日期")
IT_STATUS = {"pass": ("通過", "ok"), "fail": ("未通過", "danger"), "doubt": ("疑慮", "warn"), "skip": ("略過", "")}
IT_SEVERITY = {"高": "danger", "中": "warn", "低": "info"}
IT_GROUPS = {"smoke": "冒煙測試（每頁載入）", "sweep": "UI 巡檢（逐一點擊）", "e2e": "端到端流程", "form": "表單驗證",
             "role": "權限與角色"}
IT_MAX_JUDGE, IT_MAX_STEPS, IT_MAX_FINDINGS = 90, 6, 5


def deck_filename(tenant, app, made, ext=".pdf", purposes=()):
    """檔名規則：「AI GO 租戶名 App名 用途 YYYYMMDD」。用途照 Phase 0 選的、依固定順序用「・」串
    （例：功能展示・操作說明），同一天分開產不同用途也不會撞名。檔名不能用的字元換成底線。"""
    clean = lambda t: "".join("_" if ch in _BAD else ch for ch in str(t)).strip()
    use = "・".join(p for p in DECK_ORDER if p in purposes)
    return f"AI GO {clean(tenant)} {clean(app)} {use + ' ' if use else ''}{made:%Y%m%d}{ext}"


class Deck:
    def __init__(self, tenant, app, purposes=None, shots="shots", made=None, version="", title=None, extra_css=""):
        """tenant＝租戶名（例：展示股份有限公司）；app＝平台上的 App 名；made＝製作日（預設今天，台灣時間）。
        purposes＝Phase 0 使用者選的 PDF 用途（必填，至少一種）：功能展示／測試報告／操作說明。
        title 省略＝依用途：只有操作說明「後台操作手冊」，其他「功能展示・測試報告・操作手冊」這樣串。"""
        self.purposes = self._check_purposes(purposes)
        self._cur = MANUAL if MANUAL in self.purposes else self.purposes[0]
        if title is None:
            title = "後台操作手冊" if self.purposes == (MANUAL,) else "・".join(_TITLE[p] for p in self.purposes)
        self.shots = Path(shots).resolve()
        mf = self.shots / "shots.json"
        self.man = json.loads(mf.read_text(encoding="utf-8")) if mf.exists() else {}
        self.tenant, self.app, self.title, self.version, self.extra_css = tenant, app, title, version, extra_css
        if isinstance(made, str):
            made = _dt.date.fromisoformat(made)
        self.made = made or _dt.datetime.now(TW).date()
        self.slides = []
        self._src = "shots"

    @staticmethod
    def _check_purposes(purposes):
        if isinstance(purposes, str):
            purposes = [purposes]
        chosen = list(dict.fromkeys(purposes or []))
        if PROGRESS in chosen:
            raise ValueError("進度報告是文字訊息、不出 PDF：用 scripts/progress.py（references/progress-report.md）。"
                             "purposes 只放 PDF 類：" + "／".join(DECK_ORDER))
        bad = [p for p in chosen if p not in DECK_ORDER]
        if bad:
            raise ValueError(f"不認得的用途 {bad}：PDF 類只有 " + "／".join(DECK_ORDER))
        if not chosen:
            raise ValueError("先完成 Phase 0 選用途：purposes=[…] 至少一種（" + "／".join(DECK_ORDER) + "）")
        return tuple(p for p in DECK_ORDER if p in chosen)

    def section(self, purpose):
        """切換之後 slide()／divider()／raw() 頁面屬於哪個用途（要在 purposes 裡）。"""
        if purpose not in self.purposes:
            raise ValueError(f"這次沒選「{purpose}」：purposes＝{'／'.join(self.purposes)}")
        self._cur = purpose

    @classmethod
    def from_meta(cls, meta="disc/meta.json", **kw):
        """讀 discover.mjs 寫的 meta.json（tenant、app）；kw 可覆寫。"""
        m = json.loads(Path(meta).read_text(encoding="utf-8"))
        kw.setdefault("tenant", m.get("tenant") or "租戶")
        kw.setdefault("app", m.get("app") or "App")
        return cls(**kw)

    @property
    def name(self):
        """手冊正式名稱（頁尾用）。"""
        return f"{self.app} {self.title}"

    def filename(self, ext=".pdf"):
        return deck_filename(self.tenant, self.app, self.made, ext, self.purposes)

    # ───────────── 元件 ─────────────
    def shot(self, name, maxw, maxh=None, marks=True, cls="", frame=None):
        """截圖，依 maxw／maxh 等比縮放；marks=True 疊上 shots.json 記的編號框。
        全頁截圖自動包深色瀏覽器框（品牌規則：產品截圖不裸貼）；desktop_shot.py 拍的整個桌面視窗／螢幕
        （shots.json 的 kind="desktop" 且 full）自動包視窗框（同樣的深色列＋視窗標題）；
        --region／--from 裁的局部跟瀏覽器局部一樣不包框。
        frame：None 自動｜True／"browser" 瀏覽器框｜"window" 視窗框｜False 不包。"""
        if name not in self.man:
            raise KeyError("shots.json 沒有這張截圖：" + name)
        m = self.man[name]
        if frame is None:
            full = m.get("full", m["w"] >= 1600 and m["h"] >= 900)
            frame = ("window" if m.get("kind") == "desktop" else "browser") if full else False
        if frame is True:
            frame = "browser"
        framed = bool(frame)
        bar = 26 if framed else 0
        s = maxw / m["w"]
        if maxh:
            s = min(s, (maxh - bar) / m["h"])
        W, H = round(m["w"] * s), round(m["h"] * s)
        mk = ""
        if marks:
            for k in m.get("marks", []):
                x, y = max(0, k["x"] * s) + 2, max(0, k["y"] * s) + 2
                w, h = min(W - x - 2, k["w"] * s - 4), min(H - y - 2, k["h"] * s - 4)
                mk += (f'<div class="mk" style="left:{x:.0f}px;top:{y:.0f}px;width:{max(w, 8):.0f}px;'
                       f'height:{max(h, 8):.0f}px"><b>{k["n"]}</b></div>')
        img = f'<div class="img" style="height:{H}px"><img src="{self._src}/{name}.png" alt="">{mk}</div>'
        if framed:
            title = f'<span>{escape(m.get("title", ""))}</span>' if frame == "window" and m.get("title") else ""
            return (f'<div class="shot framed {frame} {cls}" style="width:{W}px;height:{H + bar}px">'
                    f'<div class="bar"><i></i><i></i><i></i>{title}</div>{img}</div>')
        return f'<div class="shot {cls}" style="width:{W}px;height:{H}px">{img}</div>'

    @staticmethod
    def term(commands, title="", width=None, maxh=None, redact=()):
        """終端框：把指令與實際輸出渲染成深色終端（不要截真實終端畫面——會帶進路徑、token、無關視窗）。
        commands：[(指令, 輸出)]，輸出可為空字串；或單一字串＝只有指令。
        redact：要遮掉的字串（token、密碼、Email），一律換成 ••••。"""
        if isinstance(commands, str):
            commands = [(commands, "")]
        blocks = []
        for cmd, out in commands:
            cmd, out = str(cmd), str(out or "")
            for secret in redact:
                if secret:
                    cmd, out = cmd.replace(secret, "••••"), out.replace(secret, "••••")
            blocks.append(f'<div class="cmd"><span class="ps">$</span>{escape(cmd)}</div>'
                          + (f'<pre>{escape(out)}</pre>' if out else ""))
        style = (f"width:{width}px;" if width else "") + (f"max-height:{maxh}px;" if maxh else "")
        head = f'<span>{escape(title)}</span>' if title else ""
        return (f'<div class="term" style="{style}"><div class="bar"><i></i><i></i><i></i>{head}</div>'
                f'<div class="body">{"".join(blocks)}</div></div>')

    @staticmethod
    def cap(text):
        return f'<div class="cap">{text}</div>'

    def fig(self, name, maxw, maxh=None, caption="", marks=True, frame=None):
        return f'<figure>{self.shot(name, maxw, maxh, marks, frame=frame)}{self.cap(caption) if caption else ""}</figure>'

    @staticmethod
    def legend(items, cls="side"):
        """items: [(編號, 標題, 說明)]；編號用 "·" 會顯示成圓點。"""
        li = "".join(f'<li><span class="n">{n}</span><div><b>{t}</b>{"<br>" + d if d else ""}</div></li>' for n, t, d in items)
        dot = " dot" if items and all(str(n) == "·" for n, _, _ in items) else ""
        return f'<ol class="legend {cls}{dot}">{li}</ol>'

    @staticmethod
    def steps(items, cls="tight"):
        """items: [(標題, 說明)]，自動編號。"""
        li = "".join(f'<li><span class="sn">{i + 1}</span><div><b>{t}</b>{"<br>" + d if d else ""}</div></li>'
                     for i, (t, d) in enumerate(items))
        return f'<ol class="steps {cls}">{li}</ol>'

    @staticmethod
    def table(head, rows, widths=None, cls="compact"):
        cols = "".join(f'<col style="width:{w}">' for w in widths) if widths else ""
        th = "".join(f"<th>{h}</th>" for h in head)
        tr = "".join("<tr>" + "".join(f"<td>{c}</td>" for c in r) + "</tr>" for r in rows)
        return f'<table class="t {cls}"><colgroup>{cols}</colgroup><thead><tr>{th}</tr></thead><tbody>{tr}</tbody></table>'

    @staticmethod
    def note(text, kind=""):
        """kind="warn" ＝ 橘色注意框。"""
        return f'<div class="note {kind}">{text}</div>'

    @staticmethod
    def chip(t, kind=""):
        """kind: ok｜warn｜info｜danger｜（空）灰。"""
        return f'<span class="chip {kind}">{t}</span>'

    @staticmethod
    def bullets(items, cls=""):
        return f'<ul class="bl {cls}">' + "".join(f"<li>{x}</li>" for x in items) + "</ul>"

    @staticmethod
    def row(*cols, gap=28):
        return f'<div class="row" style="gap:{gap}px">' + "".join(cols) + "</div>"

    @staticmethod
    def col(html, width=None):
        return f'<div style="width:{width}px">{html}</div>' if width else f'<div class="grow">{html}</div>'

    # ───────────── 頁面 ─────────────
    def slide(self, part, title, lede, body, kicker=None, cls="", bg="light"):
        """bg：light 白（預設）｜soft 淺灰（截圖多的頁）｜dark 深底。"""
        self.slides.append(dict(part=part, title=title, lede=lede, body=body, kicker=kicker or part, cls=f"{cls} {bg}".strip(),
                                purpose=self._cur))

    def raw(self, html, part="", cls="", title=None):
        """自訂整頁 HTML。title 有給才會列進目錄。"""
        frame = cls in ("cover-slide", "back-slide")
        self.slides.append(dict(raw=html, part=part, cls=cls, title=title, purpose=None if frame else self._cur))

    def cover(self, sub, meta=(), hero=None, hero_w=720, kicker=None):
        """封面（深底）：logo、眉標、App 名＋手冊名、一句話、製作日章、底部資訊列。
        meta：額外的 [(欄名, 內容)]，接在「租戶／App／版本」之後；hero：右側截圖名（包瀏覽器框）。"""
        rows = [("租戶", self.tenant), ("App", self.app)] + ([("版本", self.version)] if self.version else []) + list(meta)
        m = "".join(f"<div><span>{k}</span>{v}</div>" for k, v in rows)
        h = self.shot(hero, hero_w, 620, marks=False, frame=True) if hero else ""
        k = kicker or f"AI GO · {escape(self.tenant)} · {escape(self.title)}"
        self.raw(f"""<div class="cover"><div class="cv-l">{LOGO}<div class="cv-k">{k}</div>
<h1><span class="app">{escape(self.app)}</span>{escape(self.title)}</h1><p class="cv-sub">{sub}</p>
<div class="cv-date"><span>製作日</span><b>{self.made:%Y.%m.%d}</b></div>
<div class="cv-meta">{m}</div></div><div class="cv-r">{h}</div></div>""", cls="cover-slide")

    def divider(self, part, label, title, desc, items=None):
        """分隔頁（深底）：PART 標籤、標題、一句話、本部分頁目。
        items 省略＝write() 時自動列出本部分每一頁的標題與頁碼（建議）；給字串清單則照給的列。
        分隔頁同時是目錄的分組：label（PART A）＋title（核心工作）。"""
        self.slides.append(dict(kind="divider", part=part, label=label, title=title, desc=desc, items=items,
                                cls="divider-slide", purpose=self._cur))

    def acceptance(self, cards=(), rows=(), note="", sources=(), title="指標與結果",
                   lede="交付前的驗收測試結果，每個數字都附定義與樣本數。", head=ACC_HEAD):
        """測試報告頁（使用者在 Phase 0 選了「測試報告」才用）：開發歷程中已有的重要測試數據
        （例：OCR 辨識準確度、AI 判斷正確率）。排在功能展示之後、操作說明之前。

        cards：[(數值, 指標名, 一句話定義)]，≤ 4 張，放最重要的指標，例 ("98.2%", "金額辨識準確率", "…")
        rows：[(指標, 定義, 結果, 樣本, 測試日期)]，≤ 8 列；欄位可用 head 改
        note：一句話講測試範圍與限制（例：樣本來源、未涵蓋的情況）
        sources：每個數字的來源（評估紀錄、測試報告的路徑或名稱）。**必填**，不印進手冊，
                 write() 時印出來供 G3 查證與 P7 交付回報。
        最多 2 頁；數字照來源抄，不重算、不美化（references/writing-guide.md「測試報告」）。"""
        if TEST not in self.purposes:
            raise ValueError("這次沒選「測試報告」：測試數據只在使用者 Phase 0 選了測試報告時才放")
        if sum(x.get("kind") == "acceptance" for x in self.slides) >= ACC_MAX_PAGES:
            raise ValueError(f"測試報告最多 {ACC_MAX_PAGES} 頁：挑最重要的指標，其餘請使用者決定要不要放")
        if not sources:
            raise ValueError("測試報告要附來源 sources=[…]（評估紀錄、測試報告）：不印進 PDF，查證與交付回報用")
        if not cards and not rows:
            raise ValueError("測試報告至少要有 cards 或 rows")
        if len(cards) > ACC_MAX_CARDS:
            raise ValueError(f"指標卡最多 {ACC_MAX_CARDS} 張：只放最重要的，其餘放 rows")
        if len(rows) > ACC_MAX_ROWS:
            raise ValueError(f"表格最多 {ACC_MAX_ROWS} 列：挑重點，或拆成第二頁")
        if any(len(r) != len(head) for r in rows):
            raise ValueError(f"每一列要有 {len(head)} 欄：{'｜'.join(head)}")
        body = ""
        if cards:
            body += (f'<div class="acc-cards" style="grid-template-columns:repeat({len(cards)},minmax(0,1fr))">'
                     + "".join(f'<div class="acc-card"><div class="v">{v}</div><b>{n}</b><span>{d}</span></div>'
                               for v, n, d in cards) + "</div>")
        if rows:
            widths = ["220px", "auto", "220px", "110px", "130px"] if len(head) == 5 else None
            body += self.table(list(head), [list(r) for r in rows], widths)
        if note:
            body += f'<div class="acc-note">{note}</div>'
        self.slides.append(dict(kind="acceptance", part=ACC_PART, title=title, lede=lede, body=body,
                                kicker=ACC_PART, cls="light acc-slide", sources=list(sources), purpose=TEST))

    def showcase(self, feature, value, shot, notes=(), maxw=1000, maxh=None):
        """功能展示頁（使用者在 Phase 0 選了「功能展示」才用）：一個重點功能一頁，不教操作。
        feature＝功能名（頁標題，列進目錄）；value＝一句「這能幫你做什麼」（導言，≤ 40 字）；
        shot＝全頁截圖名（shots.json 有圖解座標就自動畫編號）；notes＝同編號說明 [(編號, 名稱, 做什麼)] ≤ 5，
        省略＝截圖佔滿整頁、不畫編號。整段最多 12 頁（建議 5～10）。寫法見 references/writing-guide.md「功能展示」。"""
        if SHOWCASE not in self.purposes:
            raise ValueError("這次沒選「功能展示」")
        if sum(x.get("kind") == "showcase" for x in self.slides) >= SHOW_MAX_PAGES:
            raise ValueError(f"功能展示最多 {SHOW_MAX_PAGES} 頁：只挑重點功能，細節留給操作說明")
        if len(self._plain(value)) > SHOW_MAX_VALUE:
            raise ValueError(f"value 是一句話（≤ {SHOW_MAX_VALUE} 字）：「這能幫你做什麼」，其餘放進 notes")
        if len(notes) > SHOW_MAX_NOTES:
            raise ValueError(f"notes 最多 {SHOW_MAX_NOTES} 個：展示只講重點，超過就拆頁或刪")
        body = (self.row(self.fig(shot, maxw, maxh), self.legend(list(notes))) if notes
                else self.fig(shot, 1392, maxh or 600, marks=False))     # 沒有說明就不畫編號（對不上）
        self.slides.append(dict(kind="showcase", part=SHOWCASE, title=feature, lede=value, body=body,
                                kicker=SHOWCASE, cls="soft show-slide", purpose=SHOWCASE))

    def itest(self, results="itest/results.json", review="itest/review.json", per_page=12, scope=""):
        """整合測試報告（使用者在 Phase 0 選了「整合測試」才用）：讀 scripts/itest.mjs 的 results.json 與 GT2 判讀檔
        review.json，一次產生全部頁面（references/integration-test.md）：
          測試範圍與結果（指標卡＋各測試層統計＋環境）→ 問題一覽 → 每個未通過／疑慮一頁（全頁截圖＋問題標框＋
          步驟／預期／實際／判讀）→ 通過項目（文字逐條，免截圖）→ 未測項目與原因。
        review.json：{編號: {run, status, severity, judgement, actual, suggest, observed, fixed}}，run 要等於該案例的 at
          （重跑過就過期，要重新判讀）。未通過／疑慮都要有 judgement（一句白話判讀，≤ 90 字）；未通過要有 severity（高／中／低）。
          status 可改判（例：自動判疑慮、看過截圖確認沒問題 → pass，judgement 寫理由）；通過的看過截圖覺得不合理也可改成 doubt。
        scope：一句話講測試範圍（例：「後台全部 6 頁＋3 條核心流程；不含 LINE 端」），印在第一頁。"""
        if ITEST not in self.purposes:
            raise ValueError("這次沒選「整合測試」")
        if any(str(x.get("kind", "")).startswith("itest") for x in self.slides):
            raise ValueError("itest() 只能呼叫一次")
        data = json.loads(Path(results).read_text(encoding="utf-8"))
        rp = Path(review)
        rev = json.loads(rp.read_text(encoding="utf-8")) if rp.exists() else {}
        cases = data.get("cases") or []
        if not cases:
            raise ValueError(f"{results} 沒有任何案例：先跑 node <skill>/scripts/itest.mjs")
        ids = {c["id"] for c in cases}
        stray = [k for k in rev if k not in ids]
        if stray:
            raise ValueError(f"review.json 有結果裡沒有的編號：{'、'.join(stray)}")
        rows, todo = [], []
        for c in cases:
            r = rev.get(c["id"]) or {}
            fresh = bool(r) and r.get("run") == c.get("at")
            st = (r.get("status") or c["status"]) if fresh else c["status"]
            if st not in IT_STATUS:
                raise ValueError(f"{c['id']}：status 只能是 {'／'.join(IT_STATUS)}")
            judge = self._plain(r.get("judgement")) if fresh else ""
            if st in ("fail", "doubt") or (fresh and st != c["status"]):
                if not judge:
                    todo.append(c["id"])
                    continue
                if len(judge) > IT_MAX_JUDGE:
                    raise ValueError(f"{c['id']}：judgement 是一句話（≤ {IT_MAX_JUDGE} 字），細節寫進 actual／suggest")
            sev = (r.get("severity") or "") if fresh else ""
            if st == "fail" and sev not in IT_SEVERITY:
                raise ValueError(f"{c['id']}：未通過要寫 severity（高／中／低）")
            if sev and sev not in IT_SEVERITY:
                raise ValueError(f"{c['id']}：severity 只能是 高／中／低")
            if st in ("fail", "doubt") and c.get("shot") not in self.man:
                raise ValueError(f"{c['id']}：shots.json 沒有截圖 {c.get('shot')!r}（itest.mjs 與 Deck 要用同一個 shots 資料夾）")
            rows.append(dict(c, status=st, judgement=judge, severity=sev, review=r if fresh else {}))
        if todo:
            raise ValueError(f"GT2 還沒判讀完（{len(todo)} 個）：{'、'.join(todo)}。看過截圖後在 {review} 寫 judgement"
                             "（未通過另寫 severity）；重跑過的案例要重新判讀")
        meta = data.get("meta") or {}
        labels = {**IT_GROUPS, **(meta.get("labels") or {})}
        n = {k: sum(r["status"] == k for r in rows) for k in IT_STATUS}
        issues = [r for r in rows if r["status"] == "fail"] + [r for r in rows if r["status"] == "doubt"]
        passed = [r for r in rows if r["status"] == "pass"]
        skipped = [r for r in rows if r["status"] == "skip"]

        def add(kind, title, lede, body, cls="light it-slide", kicker=ITEST):
            self.slides.append(dict(kind=kind, part=ITEST, title=title, lede=lede, body=body, kicker=kicker, cls=cls,
                                    purpose=ITEST))

        # 1. 測試範圍與結果
        cards = "".join(f'<div class="acc-card it-card {k}"><div class="v">{n[k]}</div><b>{IT_STATUS[k][0]}</b>'
                        f'<span>{d}</span></div>' for k, d in (
                            ("pass", "照預期完成，沒有錯誤"), ("fail", "流程走不下去或結果錯誤"),
                            ("doubt", "能用，但畫面或訊息不合理、或偶發"), ("skip", "這次沒測，原因列在最後")))
        order = list(dict.fromkeys(c.get("group", "") for c in cases))
        grows = [[escape(labels.get(g, g) or "其他"), str(sum(r.get("group", "") == g for r in rows))]
                 + [str(sum(r.get("group", "") == g and r["status"] == k for r in rows)) for k in IT_STATUS]
                 for g in order]
        env = [x for x in (
            f"環境：{escape(meta.get('base', ''))}" + (f"（{escape(meta['mode'])}）" if meta.get("mode") else ""),
            f"帳號：{escape(meta['account'])}" if meta.get("account") else "",
            f"瀏覽器：{escape(self._browser(meta.get('browser', '')))}，視窗 {escape(meta.get('viewport', ''))}",
            f"時間：{self._when(meta.get('started'), meta.get('finished'))}") if x]
        body = (f'<div class="acc-cards it-cards" style="grid-template-columns:repeat(4,minmax(0,1fr))">{cards}</div>'
                + self.table(["測試層", "案例", "通過", "未通過", "疑慮", "略過"], grows,
                             ["auto", "110px", "110px", "110px", "110px", "110px"], "compact it-groups")
                + f'<div class="acc-note">{(escape(scope) + "<br>") if scope else ""}{"　｜　".join(env)}</div>')
        day = self._when(meta.get("started"), None).split(" ")[0]
        add("itest-summary", "測試範圍與結果",
            f"{day + ' ' if day else ''}實際操作 {len(rows)} 個案例：通過 {n['pass']}、未通過 {n['fail']}、疑慮 {n['doubt']}"
            + (f"、略過 {n['skip']}" if n["skip"] else "") + "。", body)

        # 2. 問題一覽
        def st_chip(r):
            return self.chip(*IT_STATUS[r["status"]])

        def sev_chip(r):
            return self.chip(r["severity"], IT_SEVERITY[r["severity"]]) if r["severity"] else "—"

        for k, chunk in self._chunks(issues, 10):
            add("itest-issues", "問題一覽" + self._part_no(k, len(issues), 10),
                "未通過與疑慮的項目；每一項後面都有一頁截圖與說明。", self.table(
                    ["編號", "區域", "問題", "判定", "嚴重度"],
                    [[f"<b>{escape(r['id'])}</b>", escape(r.get("area", "")), escape(r["judgement"]), st_chip(r), sev_chip(r)]
                     for r in chunk], ["170px", "150px", "auto", "100px", "90px"], "compact"))

        # 3. 每個問題一頁
        for r in issues:
            add("itest-issue", f"{r['id']}　{self._plain(r['title'])}", escape(r["judgement"]), self._issue_body(r),
                cls="soft it-slide it-issue", kicker=f"{ITEST} · {IT_STATUS[r['status']][0]}")

        # 4. 通過項目（文字逐條，免截圖）
        for k, chunk in self._chunks(passed, per_page):
            add("itest-pass", "通過項目" + self._part_no(k, len(passed), per_page),
                "照預期完成、沒有錯誤的項目，逐條列出測了什麼、看到什麼。", self.table(
                    ["編號", "區域", "測了什麼", "結果"],
                    [[f"<b>{escape(r['id'])}</b>", escape(r.get("area", "")), escape(self._plain(r["title"])),
                      self._pass_text(r)] for r in chunk], ["170px", "140px", "340px", "auto"], "dense it-pass"))

        # 5. 未測項目
        for k, chunk in self._chunks(skipped, per_page):
            add("itest-skip", "未測項目與原因" + self._part_no(k, len(skipped), per_page),
                "這次沒有測、需要另外驗證的項目。", self.table(
                    ["編號", "區域", "項目", "沒測的原因"],
                    [[f"<b>{escape(r['id'])}</b>", escape(r.get("area", "")), escape(self._plain(r["title"])),
                      escape(r.get("reason") or r["review"].get("judgement", ""))] for r in chunk],
                    ["170px", "140px", "340px", "auto"], "compact"))
        self._itest_issues = [(r["id"], r["status"], r["severity"], r["judgement"]) for r in issues]

    @staticmethod
    def _chunks(items, size):
        return [(k, items[i:i + size]) for k, i in enumerate(range(0, len(items), size))]

    @staticmethod
    def _part_no(k, total, size):
        pages = -(-total // size)
        return f"（{k + 1}／{pages}）" if pages > 1 else ""

    @staticmethod
    def _browser(ua):
        m = re.search(r"(?:Headless)?Chrome/(\d+)", ua or "")
        return f"Chrome {m.group(1)}" if m else (ua or "Chrome")

    @staticmethod
    def _when(start, end):
        def tw(x):
            return _dt.datetime.fromisoformat(str(x).replace("Z", "+00:00")).astimezone(TW) if x else None
        a, b = tw(start), tw(end)
        if not a:
            return ""
        s = f"{a:%Y-%m-%d %H:%M}"
        if b:
            s += f"～{b:%H:%M}" if b.date() == a.date() else f"～{b:%Y-%m-%d %H:%M}"
        return s

    def _pass_text(self, r):
        rv = r["review"]
        if rv.get("observed"):
            txt = escape(self._plain(rv["observed"]))
        elif r.get("judgement"):                 # 自動判疑慮、看過截圖改判通過：寫理由
            txt = escape(r["judgement"])
        elif r.get("notes"):
            txt = escape("；".join(self._plain(x) for x in r["notes"]))
        else:
            txt = "符合預期：" + escape(self._plain(r.get("expect", "")))
        if rv.get("fixed"):
            txt = self.chip("修正後重測通過", "info") + " " + escape(self._plain(rv["fixed"])) + "<br>" + txt
        return txt

    def _issue_body(self, r):
        rv = r["review"]
        chips = self.chip(*IT_STATUS[r["status"]]) + (
            " " + self.chip("嚴重度 " + r["severity"], IT_SEVERITY[r["severity"]]) if r["severity"] else "")
        steps = list(r.get("steps") or [])
        if len(steps) > IT_MAX_STEPS:
            steps = steps[:IT_MAX_STEPS - 1] + [f"……（共 {len(r['steps'])} 步）"]
        st = "".join(f'<li><span class="sn">{i + 1}</span><div>{escape(self._plain(x))}</div></li>'
                     for i, x in enumerate(steps))
        finds = [f for f in r.get("findings") or [] if f.get("level") != "info" or f.get("mark")]
        finds.sort(key=lambda f: (f.get("mark") is None, f.get("mark") or 0))
        extra = len(finds) - IT_MAX_FINDINGS
        li = "".join(f'<li><span class="n">{f["mark"] if f.get("mark") else "·"}</span><div>{escape(f["text"])}</div></li>'
                     for f in finds[:IT_MAX_FINDINGS])
        if extra > 0:
            li += f'<li><span class="n">·</span><div>另有 {extra} 項偵測紀錄</div></li>'
        side = (f'<div class="chips-row">{chips}</div>'
                + (f'<h4>步驟</h4><ol class="steps mini">{st}</ol>' if st else "")
                + f'<h4>預期</h4><p>{escape(self._plain(rv.get("expect") or r.get("expect", "")))}</p>'
                + '<h4>實際</h4>' + (f'<p>{escape(self._plain(rv["actual"]))}</p>' if rv.get("actual") else "")
                + (f'<ol class="legend it-find">{li}</ol>' if li else "")
                + (f'<h4>建議</h4><p>{escape(self._plain(rv["suggest"]))}</p>' if rv.get("suggest") else ""))
        return self.row(self.fig(r["shot"], 860, 600), f'<div class="it-side">{side}</div>')

    def toc(self, title="目錄", lede="點標題可直接跳到該頁。", howto=None):
        """目錄頁：write() 時依實際頁序產生（分隔頁＝分組、內容頁＝列、頁碼可點）。
        放在呼叫的位置；沒呼叫的話 write() 自動插在封面後面——每份手冊一定有目錄。
        howto：底部放「讀法」列（編號、情境 → 結果、注意）；省略＝有選操作說明才放。列太多放不下時省略。
        列多時自動縮字級（dense），再多就拆成「（續）」欄與多頁。"""
        if any(x.get("kind") == "toc" for x in self.slides):
            raise ValueError("目錄只能有一個（d.toc() 呼叫了兩次）")
        self.slides.append(dict(kind="toc", title=title, lede=lede,
                                howto=(MANUAL in self.purposes) if howto is None else howto))

    def back_cover(self, title="有問題時", lead="", contact=()):
        """封底（深底）：logo、一句話、摘要、聯絡列（固定帶 Urfit Technology Co., Ltd. · ai-go.app）。"""
        items = "".join(f"<span>{x}</span>" for x in list(contact) + ["Urfit Technology Co., Ltd. · Taipei", "ai-go.app"])
        self.raw(f"""<div class="back">{LOGO}<div class="cv-k" style="margin:0 0 26px">AI GO · {escape(self.tenant)}</div>
<h1>{title}</h1><p>{lead}</p><div class="contact">{items}</div></div>""", cls="back-slide")

    # ───────────── 目錄 ─────────────
    @staticmethod
    def _plain(html):
        return unescape(_TAG.sub("", str(html or ""))).strip()

    def _toc_groups(self, slides):
        """依頁序把可列入目錄的頁分組：[{label, title, page, rows:[(標題, 頁碼)], divided}]。
        分隔頁開新組（divided）；第一個分隔頁之前的頁依 part 分組（例：功能展示、測試報告、開始之前）。"""
        groups, seen_divider = [], False
        for i, s in enumerate(slides, 1):
            kind = s.get("kind")
            if kind == "divider":
                seen_divider = True
                groups.append(dict(label=self._plain(s["label"]), title=self._plain(s["title"]), page=i, rows=[],
                                   divided=True))
                continue
            if kind == "toc" or s.get("cls") in ("cover-slide", "back-slide"):
                continue
            title = self._plain(s.get("title"))
            if not title:
                continue
            part = self._plain(s.get("part")) or "開始之前"
            if not groups or (not seen_divider and groups[-1]["title"] != part):
                groups.append(dict(label="", title=part, page=i, rows=[], divided=False))
            groups[-1]["rows"].append((title, i))
        return groups

    @staticmethod
    def _toc_pack(groups, cap):
        """排欄：欄＝[(group, rows, 是否續)]。分隔頁之前的小組（功能展示、測試報告、開始之前）疊在同一欄；
        每個 PART 自成一欄，超過 cap 列拆成「（續）」欄。"""
        cols, col, load = [], [], 0
        for g in (g for g in groups if not g["divided"]):
            rows, cont = list(g["rows"]), False
            while True:
                extra = _TOC_HEAD_ROWS if col else 0
                room = cap - load - extra
                if col and (room <= 0 or (room < len(rows) and room < 2)):
                    cols.append(col)
                    col, load = [], 0
                    continue
                take, rows = rows[:room], rows[room:]
                col.append((g, take, cont))
                load += extra + len(take)
                if not rows:
                    break
                cols.append(col)
                col, load, cont = [], 0, True
        if col:
            cols.append(col)
        for g in (g for g in groups if g["divided"]):
            rows = g["rows"] or [None]
            for k in range(0, len(rows), cap):
                cols.append([(g, [r for r in rows[k:k + cap] if r], k > 0)])
        return cols

    @staticmethod
    def _toc_load(col):
        return sum(len(rows) for _, rows, _ in col) + _TOC_HEAD_ROWS * (len(col) - 1)

    @classmethod
    def _toc_pages(cls, groups, howto):
        """把分組排成目錄頁，每頁最多 4 欄。回傳 (pages, dense, howto_at)。
        先試一般字級、再試 dense，能一頁放完且不拆「（續）」就用；否則 dense 拆成多頁。
        讀法列放在最後一頁（每欄都留得出 _TOC_HOWTO_ROWS 列時）；放不下就省略（howto_at=None），不為它多開一頁。"""
        reserve = _TOC_HOWTO_ROWS if howto else 0
        for dense, cap in ((False, _TOC_ROWS - reserve), (True, _TOC_ROWS_DENSE - reserve)):
            cols = cls._toc_pack(groups, cap)
            if len(cols) <= 4 and not any(cont for col in cols for _, _, cont in col):
                return [cols or []], dense, (0 if howto else None)
        cols = cls._toc_pack(groups, _TOC_ROWS_DENSE)
        pages = [cols[k:k + 4] for k in range(0, len(cols), 4)] or [[]]
        fits = all(cls._toc_load(col) <= _TOC_ROWS_DENSE - _TOC_HOWTO_ROWS for col in pages[-1])
        return pages, True, (len(pages) - 1 if howto and fits else None)

    def _toc_body(self, cols, dense, howto):
        html = []
        if cols:
            n = max(len(cols), 3)
            html.append(f'<div class="toc{" dense" if dense else ""}" style="grid-template-columns:repeat({n},minmax(0,1fr))">')
            for col in cols:
                html.append('<div class="toc-col">')
                for j, (g, rows, cont) in enumerate(col):
                    letter = g["label"].split()[-1] if g["label"] else ""
                    head = escape(g["title"]) + ("（續）" if cont else "")
                    html.append(f'<a class="toc-h{" sub" if j else ""}" href="#p{g["page"]:02d}">'
                                + (f'<span class="pk">{escape(letter)}</span>' if letter else "")
                                + f'<span class="toc-l">{escape(g["label"]) or "&nbsp;"}</span><b>{head}</b></a>')
                    for t, pg in rows:
                        html.append(f'<a class="toc-i" href="#p{pg:02d}"><span class="t">{escape(t)}</span>'
                                    f'<span class="pg">{pg:02d}</span></a>')
                html.append("</div>")
            html.append("</div>")
        if howto:
            html.append(f"""<div class="howto">
  <div><span class="mk-demo">1</span>截圖上的藍色編號，對應同頁的編號說明</div>
  <div>{self.chip("情境 → 結果")} 把設定改成這樣，使用者遇到時會發生什麼</div>
  <div>{self.chip("注意", "warn")} 容易踩錯或會影響客人的地方</div>
</div>""")
        return "".join(html)

    def _layout(self):
        """展開目錄、算頁碼。回傳最終頁序（每頁一個 dict；目錄頁帶 body、分隔頁帶 items）。
        內容頁依用途排成「功能展示 → 測試報告 → 操作說明」（同用途內照呼叫順序）；封面、目錄、封底位置不動。"""
        slides = list(self.slides)
        slots = [i for i, s in enumerate(slides) if s.get("purpose")]
        for i in slots:
            if slides[i]["purpose"] not in self.purposes:
                raise ValueError(f"「{self._plain(slides[i].get('title')) or '自訂頁'}」屬於「{slides[i]['purpose']}」，"
                                 f"但這次沒選：purposes＝{'／'.join(self.purposes)}")
        missing = [p for p in self.purposes if not any(slides[i]["purpose"] == p for i in slots)]
        if missing:
            raise ValueError(f"選了「{'／'.join(missing)}」但沒有內容頁：補上，或回 Phase 0 跟使用者確認拿掉")
        ordered = sorted((slides[i] for i in slots), key=lambda s: DECK_ORDER.index(s["purpose"]))
        for i, s in zip(slots, ordered):
            slides[i] = s
        at = next((i for i, s in enumerate(slides) if s.get("kind") == "toc"), None)
        if at is None:   # 目錄必須有：自動插在封面後面（沒有封面就放第一頁）
            at = next((i + 1 for i, s in enumerate(slides) if s.get("cls") == "cover-slide"), 0)
            slides.insert(at, dict(kind="toc", title="目錄", lede="點標題可直接跳到該頁。",
                                   howto=MANUAL in self.purposes))
        spec = slides[at]
        # 目錄頁數只跟列數有關、跟頁碼無關：先算頁數，展開後再算真正的頁碼
        pages, _, _ = self._toc_pages(self._toc_groups(slides), spec["howto"])
        tocs = [dict(kind="toc", part="目錄", title=spec["title"] + ("（續）" if k else ""), lede=spec["lede"])
                for k in range(len(pages))]
        slides = slides[:at] + tocs + slides[at + 1:]
        groups = self._toc_groups(slides)
        pages, dense, howto_at = self._toc_pages(groups, spec["howto"])
        for k, (t, cols) in enumerate(zip(tocs, pages)):
            t["body"] = self._toc_body(cols, dense, k == howto_at)
        # 分隔頁：items 省略 → 自動列本部分頁目＋頁碼
        for g in groups:
            s = slides[g["page"] - 1]
            if s.get("kind") == "divider" and s.get("items") is None:
                slides[g["page"] - 1] = dict(s, items=[f'{escape(t)}<span class="dv-pg">{pg:02d}</span>'
                                                       for t, pg in g["rows"]])
        return slides

    # ───────────── 輸出 ─────────────
    def write(self, out=None):
        """輸出 HTML；out 省略＝依檔名規則「AI GO 租戶名 App名 用途 YYYYMMDD.html」。PDF 用同名 .pdf。
        目錄頁一定會產生（沒呼叫 toc() 就自動插在封面後面）。每頁帶 id="pNN"，目錄可點跳頁。"""
        out = Path(out or self.filename(".html")).resolve()
        self._src = os.path.relpath(self.shots, out.parent).replace("\\", "/")
        # 截圖路徑在 shot() 時已經寫進 HTML，這裡統一換成相對 out 的路徑
        css = (HERE / "deck.css").read_text(encoding="utf-8") + self.extra_css
        slides = self._layout()
        pages, n = [], len(slides)
        for i, s in enumerate(slides, 1):
            part = ("　·　" + s["part"]) if s.get("part") else ""
            foot = (f'<div class="foot"><span>AI GO · {escape(self.tenant)}　{escape(self.name)}{part}</span>'
                    f'<span class="pg">{i:02d} / {n:02d}</span></div>')
            sid = f'id="p{i:02d}"'
            if s.get("kind") == "divider":
                pages.append(f"""<section {sid} class="slide divider-slide"><div class="divider"><div class="dv-k">{s['label']}</div>
<h1>{s['title']}</h1><p>{s['desc']}</p><div class="dv-list">{self.bullets(s['items'] or [])}</div></div>{foot}</section>""")
            elif s.get("kind") == "toc":
                pages.append(f"""<section {sid} class="slide toc-slide">
  <header><div class="kicker">CONTENTS</div><h2>{s['title']}</h2><p class="lede">{s['lede']}</p></header>
  <div class="content">{s['body']}</div>{foot}</section>""")
            elif "raw" in s:
                bare = s.get("cls") in ("cover-slide", "back-slide")
                pages.append(f'<section {sid} class="slide {s.get("cls", "")}">{s["raw"]}{"" if bare else foot}</section>')
            else:
                pages.append(f"""<section {sid} class="slide {s['cls']}">
  <header><div class="kicker">{s['kicker']}</div><h2>{s['title']}</h2><p class="lede">{s['lede']}</p></header>
  <div class="content">{s['body']}</div>{foot}</section>""")
        html = "".join(pages).replace('src="shots/', f'src="{self._src}/')
        doc = f"""<!doctype html><html lang="zh-Hant"><head><meta charset="utf-8"><title>{escape(self.filename(""))}</title>
<link rel="preconnect" href="https://fonts.googleapis.com"><link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;700&family=Noto+Sans+TC:wght@400;500;700;900&display=block" rel="stylesheet">
<style>{css}</style></head><body>{html}</body></html>"""
        out.write_text(doc, encoding="utf-8")
        print("slides", n, "→", out)
        for i, s in enumerate(slides, 1):
            if s.get("kind") == "acceptance":
                print(f"測試報告（第 {i} 頁）來源——G3 查證、P7 交付回報用，不印進 PDF：")
                for src in s["sources"]:
                    print("  -", src)
            if s.get("kind") == "itest-summary":
                issues = getattr(self, "_itest_issues", [])
                print(f"整合測試（第 {i} 頁起）：{len(issues)} 個未通過／疑慮——P7 交付時在對話裡列出：")
                for cid, st, sev, judge in issues:
                    print(f"  - {cid}｜{IT_STATUS[st][0]}{('｜' + sev) if sev else ''}｜{judge}")
        print("PDF：node <skill>/scripts/render.mjs --html", f'"{out.name}"',
              "--png preview（PDF 與 HTML 同名；超過 20 MB 自動壓縮）")
        return out
