# -*- coding: utf-8 -*-
"""ai-go-app-present：測試指引（第六種用途）——A4 直式、給測試人員照著操作的文件。

讀者是要動手測系統的人（客戶端的測試人員、店長、內部 QA）：拿到就知道用哪個身分登入、照什麼步驟做、
每一步應該看到什麼畫面、怎麼打勾、不對時怎麼回報。和整合測試（我們自己跑完的結果）不同：這份是交給別人去跑的。

內容檔（見 templates/guide_content.example.py）這樣用：

    from guide_kit import Guide
    g = Guide.from_meta("disc/meta.json", shots="shots", site="https://…", audience="門市店長與客服")
    g.cover(...)                                 # 可省略（自動）
    g.prepare(env=[…], todo=[…], dont=[…])       # 測試準備
    g.roles([(身分, 帳號代碼, 做什麼, 測試重點)])   # 必填：不同身分
    g.flow("建立訂單", role="店長", goal=…, steps=[(操作, 預期畫面), …], shot="order-done")   # 必填：一條流程一頁
    g.permissions([(功能, 身分1 預期, 身分2 預期, …)])   # 選配：每個身分看得到／做得到什麼
    g.report(channel="LINE 群組「XX 測試回報」", to="王小明（FDE）", deadline="11/7（五）18:00")   # 必填：回報方式
    g.write()                                    # →「AI GO 租戶名 App名 測試指引 YYYYMMDD.html」，PDF 同名

頁序固定（寫的順序不影響，流程之間照呼叫順序）：
  封面 → 目錄 → 測試準備 → 身分與帳號 → 怎麼執行 → 自訂頁 → 測試流程（每條一頁）→ 權限檢查 → 判定標準 → 回報方式
  → 總檢查清單 → 問題回報單 → 送出前確認（封底）
目錄、怎麼執行、判定標準、總檢查清單、問題回報單、封底沒呼叫就自動產生。
樣式沿用 AI GO 品牌（deck.css）＋ A4 版面（guide.css）；PDF 用 render.mjs（自動依頁面尺寸輸出 A4）。
"""
import os
import re
import sys
from html import escape
from pathlib import Path

HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))
from deck_kit import Deck, GUIDE, LOGO  # noqa: E402

PREP, FLOWS, JUDGE, FORMS = "開始之前", "測試流程", "判定與回報", "可列印表單"
# 頁型 → (排序, 部分)
_RANK = {"cover": (0, ""), "toc": (1, ""), "prepare": (2, PREP), "roles": (3, PREP), "howto": (4, PREP),
         "page": (5, PREP), "flow": (6, FLOWS), "perms": (7, FLOWS), "judge": (8, JUDGE), "report": (9, JUDGE),
         "checklist": (10, FORMS), "issue": (11, FORMS), "back": (12, "")}
RESULTS = (("P", "通過", "ok", "每一步都和預期畫面相同，流程完成。"),
           ("M", "需改善", "info", "流程完成，但文字、版面、速度或提示不理想。"),
           ("F", "不通過", "danger", "做不下去、結果錯誤、看到不該看到的資料，或畫面和預期不同。"),
           ("B", "卡住", "warn", "帳號、資料或環境不對，無法判斷；補齊後再測。"),
           ("N", "不適用", "", "這次範圍不含，或這個身分本來就不用做；寫原因。"))
SEVERITY = (("高", "danger", "流程做不下去、資料錯誤或外洩、對外送錯（客人收到錯的東西或被扣款）"),
            ("中", "warn", "能完成但結果不對，或要繞路才做得到"),
            ("低", "info", "錯字、版面跑掉、提示不清楚，不影響完成"))
CRITICAL = ("看到別的身分或別人的資料（不該看到的）",
            "畫面說成功，但資料沒有存下來或存錯",
            "對外送出（訊息、Email、扣款）和預期不同",
            "出現錯誤代碼、程式錯誤訊息或整頁空白")
REPORT_FIELDS = ("流程編號與第幾步（例：T03 第 4 步）",
                 "測試身分與帳號代碼",
                 "做了什麼（照順序寫）",
                 "預期看到什麼（照指引抄）",
                 "實際看到什麼",
                 "截圖或錄影（整個畫面，含網址列）",
                 "發生時間、裝置與瀏覽器",
                 "嚴重度：高／中／低")
HOWTO = (("用指定身分登入", "每條流程標了身分與帳號代碼；換身分前先登出，或用另一個無痕視窗。"),
         ("照步驟操作", "一步做完再做下一步，不跳步、不另外點別的地方；需要輸入的照步驟給的值。"),
         ("對照預期畫面打勾", "和「預期畫面」相同就在右邊打勾；不同就停下來，先截整個畫面再繼續。"),
         ("記錄整條結果", "流程頁最下面填 P／M／F／B／N、測試者與日期；取這條流程裡最嚴重的那一步。"),
         ("回報", "F、M、B 都填一張問題回報單，照「回報方式」送出；重大問題發現就回報，不用等測完。"))
PREP_TODO = ("確認自己拿到的帳號是哪個身分（對照「身分與帳號」）",
             "帳號密碼私下提供、不寫在這份文件；不要轉給別人",
             "用無痕視窗登入，換身分前先登出",
             "準備好截圖方式（Windows：Win＋Shift＋S；Mac：⌘＋Shift＋4）",
             "印出或開好最後的「總檢查清單」與「問題回報單」")
BACK_CHECKS = ("每條流程都有結果（P／M／F／B／N），沒測的寫原因",
               "每個 F、M、B 都有問題回報單與截圖",
               "重大問題已經先回報",
               "截圖裡沒有密碼、驗證碼或與測試無關的個資",
               "總檢查清單與回報單一起交出")
FLOW_MAX_STEPS, FLOW_MAX_SHOTS, TITLE_MAX = 12, 2, 20
CHECK_ROWS, TOC_ROWS = 22, 26
_SECRET = re.compile(r"(密碼|password|passwd|pwd|token|api[ _-]?key|secret)\s*[:：=]\s*[^\s<＿_]", re.I)
_YES = ("可以", "看得到", "做得到", "✓", "✔", "O", "○")
_NO = ("不行", "看不到", "做不到", "不能", "✕", "✗", "X", "×")


def _box(label=""):
    return f'<span class="g-opt"><span class="g-box"></span>{label}</span>' if label else '<span class="g-box"></span>'


class Guide(Deck):
    """測試指引。A4 直式（210×297 mm），內容區約 686×900 px；全頁截圖寬 686 時高約 386。"""
    _BAR = 16

    def __init__(self, tenant, app, shots="shots", made=None, version="", site="", audience="", title=None,
                 extra_css="", purposes=None):
        super().__init__(tenant, app, purposes=[GUIDE], shots=shots, made=made, version=version, title=title,
                         extra_css=extra_css)
        self.site, self.audience = site, audience
        self._roles, self._flows = [], []

    @staticmethod
    def _check_purposes(purposes):
        return (GUIDE,)

    # ───────────── 頁面 ─────────────
    def _add(self, kind, title="", lede="", body="", **kw):
        if kind in ("cover", "toc", "prepare", "roles", "howto", "perms", "judge", "report", "back") and \
                any(s["kind"] == kind for s in self.slides):
            raise ValueError(f"{kind} 頁只能有一個")
        self.slides.append(dict(kind=kind, title=title, lede=lede, body=body, **kw))

    def cover(self, sub="照身分登入、逐條流程操作，<br>每一步對照預期畫面，不符合就回報。", goals=None, meta=()):
        """封面（深底，A4 直式）：App 名＋測試指引、一句話、三個目標、製作日章、底部資訊列
        （租戶／App／版本／測試站／對象／範圍「N 種身分・M 條流程」自動帶入）。"""
        goals = goals or (("照身分操作", "每條流程標好用哪個身分、哪個帳號登入。"),
                          ("對照預期畫面", "每一步寫了應該看到什麼，相同就打勾。"),
                          ("不對就回報", "照回報方式送出，附截圖與發生的步驟。"))
        self._add("cover", sub=sub, goals=list(goals), meta=list(meta))

    def toc(self, title="目錄", lede="點標題可直接跳到該頁。第一次測先讀「開始之前」，再照身分挑流程。"):
        self._add("toc", title=title, lede=lede)

    def prepare(self, env=(), todo=None, dont=(), lede="開始測之前，先把這頁打勾打完；缺東西就先問，不要用自己的帳號代替。"):
        """測試準備。env＝[(項目, 內容)]（測試站、期間、瀏覽器、測試資料…；site 有給會自動放第一列）；
        todo＝開始前要打勾的事（省略＝通用清單）；dont＝不要做的事（例：不要按「推播給全部客人」），放深底注意框。"""
        rows = [list(r) for r in env]
        if self.site and not any(str(r[0]) == "測試站" for r in rows):
            rows.insert(0, ["測試站", f"<b>{escape(self.site)}</b>"])
        body = self.table(["項目", "內容"], rows, ["130px", "auto"]) if rows else ""
        body += "<h3>開始前打勾</h3>" + self._checks(todo or PREP_TODO)
        if dont:
            body += self.note("<b>不要做的事</b><br>" + "<br>".join(f"・{x}" for x in dont), "warn")
        self._add("prepare", "測試準備", lede, body)

    def roles(self, rows, lede="每個身分看到的畫面、能做的事不同；每條流程都標了要用哪個身分。", note=""):
        """身分與帳號（必填）：rows＝[(身分, 帳號代碼, 這個身分平常做什麼, 這次測試重點)]。
        帳號代碼是「店長-1」這種代號，密碼私下給，**不寫進文件**。"""
        rows = [tuple(r) for r in rows]
        if not rows:
            raise ValueError("至少要有一個身分")
        if any(len(r) != 4 for r in rows):
            raise ValueError("每個身分 4 欄：(身分, 帳號代碼, 平常做什麼, 測試重點)")
        names = [self._plain(r[0]) for r in rows]
        if len(set(names)) != len(names):
            raise ValueError("身分名稱重複：" + "、".join(names))
        self._roles = rows
        body = self.table(["身分", "帳號代碼", "平常做什麼", "這次測試重點"],
                          [[f"<b>{r[0]}</b>", r[1], r[2], r[3]] for r in rows], ["92px", "96px", "auto", "auto"])
        body += self.note(note or "<b>帳號密碼另外私下提供</b>，不寫在這份文件。拿到後先登入確認右上角顯示的身分和這張表一致。")
        self._add("roles", "身分與帳號", lede, body)

    def howto(self, steps=None, lede="每條流程都照這五步走；同一條流程測第二次，另填一列，不要覆蓋第一次的結果。", note=None):
        """怎麼執行一條流程（省略＝自動放通用五步）。"""
        body = self.steps(list(steps or HOWTO), "tight")
        body += self.note(note or "<b>預期畫面</b>是製作時實際操作確認過的。名稱、數字、時間可能和截圖不同，"
                                  "判斷時看<b>位置、文字、狀態</b>對不對。看不懂預期在講什麼，就記 B 並回報。")
        self._add("howto", "怎麼執行一條流程", lede, body)

    def slide(self, part, title, lede, body, kicker=None, cls="", bg="light"):
        """自訂頁（例：測試範圍、名詞解釋）：排在「怎麼執行」之後、測試流程之前。"""
        self._add("page", title, lede, body, part_label=part, kicker=kicker or part)

    def raw(self, html, part="", cls="", title=None):
        raise ValueError("測試指引不用 raw()：自訂內容用 g.slide()")

    def divider(self, *a, **kw):
        raise ValueError("測試指引不用分隔頁：目錄依「開始之前／測試流程／判定與回報／可列印表單」自動分組")

    def flow(self, title, role, goal, steps, pre="", shot=None, caption="", passes="", fails="", minutes=None,
             code=None, maxh=400):
        """一條測試流程一頁（必填，至少一條）。
        title＝流程名（≤ 20 字，進目錄）；role＝用哪個身分（要在 roles() 裡）；goal＝一句話：測什麼、做完應該怎樣。
        steps＝[(操作, 預期畫面)]，≤ 12 步；操作寫點哪裡、輸入什麼（畫面上的字一字不差），預期畫面寫做完應該看到什麼
          （出現哪個提示、列表多一筆、狀態變成什麼）。**每一步都要有預期畫面**，而且是實際操作確認過的。
        pre＝前置條件（例：先完成 T01、要有一筆待出貨訂單）；shot＝預期畫面截圖名（shots.json），可給 1～2 張 list；
        caption＝圖說；passes／fails＝整條通過／不通過的判準（一句話，選配）；minutes＝預估分鐘數；code＝編號（省略＝T01、T02…）。"""
        if len(self._plain(title)) > TITLE_MAX:
            raise ValueError(f"流程名 ≤ {TITLE_MAX} 字（會進目錄）：{self._plain(title)}")
        if not self._plain(goal):
            raise ValueError(f"「{self._plain(title)}」要寫 goal：一句話講測什麼、做完應該怎樣")
        steps = [tuple(s) for s in steps]
        if not steps:
            raise ValueError(f"「{self._plain(title)}」沒有步驟")
        if len(steps) > FLOW_MAX_STEPS:
            raise ValueError(f"「{self._plain(title)}」超過 {FLOW_MAX_STEPS} 步：拆成兩條流程（第二條的 pre 寫先完成第一條）")
        for i, s in enumerate(steps, 1):
            if len(s) != 2 or not self._plain(s[0]):
                raise ValueError(f"「{self._plain(title)}」第 {i} 步要是 (操作, 預期畫面)")
            if not self._plain(s[1]):
                raise ValueError(f"「{self._plain(title)}」第 {i} 步沒有預期畫面：每一步都要寫做完應該看到什麼")
        shots = [] if not shot else [shot] if isinstance(shot, str) else list(shot)
        if len(shots) > FLOW_MAX_SHOTS:
            raise ValueError(f"每條流程最多 {FLOW_MAX_SHOTS} 張預期畫面截圖：挑最後結果那張")
        for s in shots:
            if s not in self.man:
                raise KeyError("shots.json 沒有這張截圖：" + s)
        code = code or f"T{len(self._flows) + 1:02d}"
        if any(f["code"] == code for f in self._flows):
            raise ValueError(f"流程編號重複：{code}")
        f = dict(code=code, title=title, role=role, goal=goal, steps=steps, pre=pre, shots=shots, caption=caption,
                 passes=passes, fails=fails, minutes=minutes, maxh=maxh)
        self._flows.append(f)
        self._add("flow", f"{code}　{self._plain(title)}", goal, flow=f)

    def permissions(self, rows, lede="同一個功能，不同身分應該看到的結果。逐格實際登入確認，和預期相同就打勾。", note=""):
        """權限檢查（選配）：rows＝[(功能或畫面, 身分1 預期, 身分2 預期, …)]，身分順序同 roles()。
        預期寫「可以／看不到／唯讀」這種短詞；可以→綠、看不到／不行→紅、其他→灰。"""
        rows = [tuple(r) for r in rows]
        if not rows:
            raise ValueError("permissions 至少一列")
        self._add("perms", "權限檢查", lede, rows=rows, note=note)

    def judge(self, critical=None, lede="先看每一步和預期畫面一不一樣，再判整條；整條取最嚴重的那一步。"):
        """判定標準（省略＝自動）：P／M／F／B／N、嚴重度、重大問題。critical＝這支 app 的重大問題（省略＝通用四項）。"""
        rows = [[self.chip(f"{k}｜{n}", c), d] for k, n, c, d in RESULTS]
        body = self.table(["結果", "什麼時候用"], rows, ["120px", "auto"])
        body += "<h3>嚴重度（回報時寫）</h3>" + self.table(
            ["嚴重度", "例子"], [[self.chip(k, c), d] for k, c, d in SEVERITY], ["120px", "auto"])
        body += self.note("<b>重大問題：發現就回報，不用等測完</b><br>" + "<br>".join(f"・{x}" for x in (critical or CRITICAL)),
                          "warn")
        self._add("judge", "判定標準", lede, body)

    def report(self, channel, to="", deadline="", sla=None, fields=None, example=None,
               lede="每個問題一則回報；同一個問題在不同流程出現，寫在同一則裡。"):
        """回報方式（必填）。channel＝回報到哪裡（LINE 群組名、Email、表單網址）；to＝誰收、誰回覆；deadline＝什麼時候前交；
        sla＝{嚴重度: 回覆時效}（FDE 承諾得了才寫，不寫就不放）；fields＝一則回報要包含什麼（省略＝通用 8 項）；
        example＝範例訊息（省略＝用第一條流程產一則填空範例）。"""
        if not self._plain(channel):
            raise ValueError("report() 要寫 channel：測試人員要知道回報到哪裡")
        if sla:
            bad = [k for k in sla if k not in {k for k, _, _ in SEVERITY}]
            if bad:
                raise ValueError("sla 的鍵只能是 高／中／低：" + "、".join(bad))
        self._add("report", "回報方式", lede, channel=channel, to=to, deadline=deadline, sla=dict(sla or {}),
                  fields=list(fields or REPORT_FIELDS), example=example)

    def back_cover(self, title="送出前確認", lead="一則看得懂、做得出來的回報，問題才修得快。", checks=None, contact=()):
        """封底（深底）：送出前的打勾清單＋聯絡列（固定帶 Urfit Technology Co., Ltd. · ai-go.app）。省略＝自動。"""
        self._add("back", title=title, lead=lead, checks=list(checks or BACK_CHECKS), contact=list(contact))

    # ───────────── 元件 ─────────────
    @staticmethod
    def _checks(items, cls=""):
        return f'<ul class="g-checks {cls}">' + "".join(f"<li>{_box()}<span>{x}</span></li>" for x in items) + "</ul>"

    @staticmethod
    def _blank(n=6):
        return '<span class="g-blank" style="width:%dem"></span>' % n

    def _result_bar(self):
        opts = "".join(_box(k) for k, *_ in RESULTS)
        return (f'<div class="g-result"><b>整條結果</b>{opts}<span class="g-sep"></span>'
                f'<span>測試者 {self._blank(5)}</span><span>日期 {self._blank(4)}</span><span>回報單 {self._blank(4)}</span></div>')

    def _role(self, name):
        for r in self._roles:
            if self._plain(r[0]) == self._plain(name):
                return r
        return None

    def _flow_body(self, f):
        r = self._role(f["role"])
        meta = [("身分", f"<b>{escape(self._plain(f['role']))}</b>"), ("帳號代碼", r[1] if r else "—")]
        if f["pre"]:
            meta.append(("前置條件", f["pre"]))
        if f["minutes"]:
            meta.append(("預估", f"{f['minutes']} 分鐘"))
        html = '<div class="g-meta">' + "".join(f"<div><span>{k}</span>{v}</div>" for k, v in meta) + "</div>"
        rows = [[f'<span class="sn">{i}</span>', a, e, _box()] for i, (a, e) in enumerate(f["steps"], 1)]
        html += self.table(["#", "操作", "預期畫面", "✓"], rows, ["34px", "44%", "auto", "26px"], "g-steps")
        if f["shots"]:
            if len(f["shots"]) == 1:
                html += self.fig(f["shots"][0], 686, f["maxh"], f["caption"])
            else:
                html += (self.row(*[self.col(self.shot(s, 329, f["maxh"])) for s in f["shots"]], gap=28)
                         + (self.cap(f["caption"]) if f["caption"] else ""))
        crit = [x for x in (f"<b>通過</b>　{f['passes']}" if f["passes"] else "",
                            f"<b>不通過</b>　{f['fails']}" if f["fails"] else "") if x]
        if crit:
            html += self.note("<br>".join(crit))
        return html + self._result_bar()

    def _perms_body(self, s):
        names = [self._plain(r[0]) for r in self._roles]
        bad = [r for r in s["rows"] if len(r) != len(names) + 1]
        if bad:
            raise ValueError(f"permissions 每列要有 {len(names) + 1} 欄：功能＋{'／'.join(names)}")

        def cell(v):
            t = self._plain(v)
            kind = "ok" if t in _YES else "danger" if t in _NO else ""
            return f'{_box()}{self.chip(escape(t), kind)}'
        rows = [[f"<b>{r[0]}</b>"] + [cell(v) for v in r[1:]] for r in s["rows"]]
        w = max(80, min(130, 460 // max(len(names), 1)))
        html = self.table(["功能／畫面"] + [escape(n) for n in names], rows, ["auto"] + [f"{w}px"] * len(names), "g-perms")
        return html + self.note(s["note"] or "<b>看不到</b>也要確認：選單裡沒有、直接輸入網址也進不去。"
                                             "看到不該看到的，記 F，嚴重度高。")

    def _report_body(self, s):
        cards = [("回報到", s["channel"]), ("給誰", s["to"]), ("期限", s["deadline"])]
        html = '<div class="g-cards">' + "".join(f'<div><span>{k}</span><b>{v}</b></div>' for k, v in cards if v) + "</div>"
        html += "<h3>一則回報要包含</h3>" + f'<ol class="g-fields">{"".join(f"<li>{x}</li>" for x in s["fields"])}</ol>'
        if s["sla"]:
            html += "<h3>回覆時效</h3>" + self.table(
                ["嚴重度", "例子", "回覆"], [[self.chip(k, c), d, f"<b>{s['sla'][k]}</b>"] for k, c, d in SEVERITY if k in s["sla"]],
                ["90px", "auto", "150px"])
        ex = s["example"]
        if ex is None:
            f = self._flows[0]
            step = min(2, len(f["steps"]))
            ex = (f"【測試回報】{f['code']} 第 {step} 步｜嚴重度：＿\n"
                  f"身分：{self._plain(f['role'])}（帳號代碼 {self._plain((self._role(f['role']) or ['', '＿'])[1])}）\n"
                  f"做了什麼：{self._plain(f['steps'][step - 1][0])}\n"
                  f"預期：{self._plain(f['steps'][step - 1][1])}\n"
                  "實際：＿＿＿＿（寫看到的畫面或訊息原文）\n"
                  "附件：截圖＿張\n時間／裝置：＿＿＿＿／＿＿＿＿")
        html += ("<h3>範例</h3>" + f'<div class="g-msg">{escape(self._plain(ex))}</div>')
        return html

    def _checklist_rows(self):
        rows = [[f"<b>{f['code']}</b>", escape(self._plain(f["title"])), escape(self._plain(f["role"])), str(len(f["steps"]))]
                for f in self._flows]
        if any(s["kind"] == "perms" for s in self.slides):
            rows += [["<b>權限</b>", f"權限檢查（{escape(self._plain(r[0]))}）", escape(self._plain(r[0])), "—"]
                     for r in self._roles]
        return [r + ["".join(_box() for _ in RESULTS), ""] for r in rows]

    def _checklist_body(self, rows, last):
        html = self.table(["編號", "流程", "身分", "步驟", "結果　P　M　F　B　N", "回報單編號"], rows,
                          ["56px", "auto", "92px", "44px", "150px", "96px"], "g-check")
        if last:
            tally = "".join(f"<span>{k} {self._blank(3)}</span>" for k, *_ in RESULTS)
            html += (f'<div class="g-tally"><b>合計</b>{tally}<span>未測 {self._blank(3)}</span></div>'
                     '<div class="small">通過率＝P ÷（P＋M＋F）；B、N、未測不算進分母。整批交出前，未測的要寫原因。</div>')
        return html

    def _issue_body(self, s):
        fields = s["fields"] if s else list(REPORT_FIELDS)
        top = (f'<div class="g-line"><span>回報單編號 {self._blank(5)}</span><span>流程／步驟 {self._blank(6)}</span>'
               f'<span>身分 {self._blank(5)}</span></div>'
               f'<div class="g-line">嚴重度　{_box("高")}　{_box("中")}　{_box("低")}　　結果　'
               + "　".join(_box(k) for k, *_ in RESULTS[1:4]) + "</div>")
        grow = {"做了什麼（照順序寫）": 3, "預期看到什麼（照指引抄）": 2, "實際看到什麼": 3}   # 剩下的高度依比例分給這三格
        skip = ("流程編號與第幾步（例：T03 第 4 步）", "測試身分與帳號代碼", "嚴重度：高／中／低")
        boxes = "".join(f'<div class="g-field" style="flex:{grow.get(x, 0)} 0 auto"><span>{x}</span></div>'
                        for x in fields if x not in skip)
        return top + boxes + f'<div class="g-line"><span>測試者 {self._blank(6)}</span><span>修正後重測 {_box("通過")}　{_box("仍有問題")}</span>' \
                             f'<span>日期 {self._blank(5)}</span></div>'

    # ───────────── 輸出 ─────────────
    def _layout(self):
        kinds = {s["kind"] for s in self.slides}
        if not self._roles:
            raise ValueError("缺「身分與帳號」：g.roles([(身分, 帳號代碼, 平常做什麼, 測試重點)])")
        if not self._flows:
            raise ValueError("至少要有一條測試流程：g.flow(…)")
        if "report" not in kinds:
            raise ValueError("缺「回報方式」：g.report(channel=…, to=…, deadline=…)")
        names = [self._plain(r[0]) for r in self._roles]
        stray = [f"{f['code']}「{self._plain(f['role'])}」" for f in self._flows if self._plain(f["role"]) not in names]
        if stray:
            raise ValueError(f"流程用了沒列在 roles() 的身分：{'、'.join(stray)}（身分有：{'／'.join(names)}）")
        slides = list(self.slides)
        for kind, fn in (("cover", self.cover), ("toc", self.toc), ("howto", self.howto), ("judge", self.judge),
                         ("back", self.back_cover)):
            if kind not in kinds:
                n = len(self.slides)
                fn()
                slides.append(self.slides.pop(n))
        rows = self._checklist_rows()
        chunks = self._chunks(rows, CHECK_ROWS)
        for k, chunk in chunks:
            slides.append(dict(kind="checklist", title="總檢查清單" + self._part_no(k, len(rows), CHECK_ROWS),
                               lede="每條流程測完填一列；也可以直接在流程頁最下面勾。", rows=chunk, last=k == len(chunks) - 1))
        slides.append(dict(kind="issue", title="問題回報單", lede="一個問題一張，可複印；拍照或掃描後連同截圖一起回報。"))
        slides.sort(key=lambda s: _RANK[s["kind"]][0])
        for s in slides:
            s["part"] = s.get("part_label") or _RANK[s["kind"]][1]
        # 目錄：列＝每頁（封面、目錄、封底除外），依部分分組；一組標題算 2 列
        listed = [i for i, s in enumerate(slides) if s["kind"] not in ("cover", "toc", "back")]
        load = sum(1 for _ in listed) + 2 * len({slides[i]["part"] for i in listed})
        n_toc = max(1, -(-load // TOC_ROWS))
        at = next(i for i, s in enumerate(slides) if s["kind"] == "toc")
        spec = slides[at]
        tocs = [dict(spec, title=spec["title"] + ("（續）" if k else ""), part="") for k in range(n_toc)]
        slides = slides[:at] + tocs + slides[at + 1:]
        entries, cur = [], None
        for i, s in enumerate(slides, 1):
            if s["kind"] in ("cover", "toc", "back"):
                continue
            if s["part"] != cur:
                cur = s["part"]
                entries.append(("h", cur, i))
            entries.append(("i", self._plain(s["title"]), i))
        pages, buf, used = [], [], 0
        for e in entries:
            cost = 2 if e[0] == "h" else 1
            if used + cost > TOC_ROWS and buf and len(pages) < n_toc - 1:
                pages.append(buf)
                buf, used = [], 0
            buf.append(e)
            used += cost
        pages.append(buf)
        for t, es in zip(tocs, pages + [[]] * (n_toc - len(pages))):
            t["body"] = '<div class="g-toc">' + "".join(
                f'<a class="g-toc-h" href="#p{pg:02d}">{escape(x)}</a>' if k == "h" else
                f'<a class="toc-i" href="#p{pg:02d}"><span class="t">{escape(x)}</span><span class="pg">{pg:02d}</span></a>'
                for k, x, pg in es) + "</div>"
        return slides

    def _cover_html(self, s):
        rows = [("租戶", self.tenant), ("App", self.app)] + ([("版本", self.version)] if self.version else []) \
            + ([("測試站", self.site)] if self.site else []) + ([("對象", self.audience)] if self.audience else []) \
            + [("範圍", f"{len(self._roles)} 種身分・{len(self._flows)} 條流程")] + s["meta"]
        meta = "".join(f"<div><span>{k}</span>{escape(str(v))}</div>" for k, v in rows)
        goals = "".join(f'<div class="g-goal"><div class="n">{i:02d}</div><div><b>{t}</b><span>{d}</span></div></div>'
                        for i, (t, d) in enumerate(s["goals"], 1))
        return (f'<div class="g-cover">{LOGO}<div class="cv-k">AI GO · {escape(self.tenant)} · {escape(self.title)}</div>'
                f'<h1><span class="app">{escape(self.app)}</span>{escape(self.title)}</h1><p class="cv-sub">{s["sub"]}</p>'
                f'<div class="g-goals">{goals}</div>'
                f'<div class="cv-date"><span>製作日</span><b>{self.made:%Y.%m.%d}</b></div>'
                f'<div class="cv-meta">{meta}</div></div>')

    def _back_html(self, s):
        items = "".join(f"<span>{x}</span>" for x in s["contact"] + ["Urfit Technology Co., Ltd. · Taipei", "ai-go.app"])
        return (f'<div class="g-back">{LOGO}<div class="cv-k">AI GO · {escape(self.tenant)} · CHECK &amp; SUBMIT</div>'
                f'<h1>{s["title"]}</h1><p>{s["lead"]}</p>{self._checks(s["checks"], "dark")}'
                f'<div class="contact">{items}</div></div>')

    def write(self, out=None):
        """輸出 HTML；out 省略＝「AI GO 租戶名 App名 測試指引 YYYYMMDD.html」。PDF 用 render.mjs 產同名 .pdf（A4）。"""
        out = Path(out or self.filename(".html")).resolve()
        self._src = os.path.relpath(self.shots, out.parent).replace("\\", "/")
        css = (HERE / "deck.css").read_text(encoding="utf-8") + (HERE / "guide.css").read_text(encoding="utf-8") \
            + self.extra_css
        slides = self._layout()
        report = next(s for s in slides if s["kind"] == "report")
        pages, n = [], len(slides)
        for i, s in enumerate(slides, 1):
            k = s["kind"]
            sid = f'id="p{i:02d}"'
            part = ("　·　" + s["part"]) if s.get("part") else ""
            foot = (f'<div class="foot"><span>AI GO · {escape(self.tenant)}　{escape(self.name)}{part}</span>'
                    f'<span class="pg">{i:02d} / {n:02d}</span></div>')
            if k == "cover":
                pages.append(f'<section {sid} class="slide a4 cover-slide">{self._cover_html(s)}</section>')
                continue
            if k == "back":
                pages.append(f'<section {sid} class="slide a4 back-slide">{self._back_html(s)}</section>')
                continue
            body = {"flow": lambda: self._flow_body(s["flow"]), "perms": lambda: self._perms_body(s),
                    "report": lambda: self._report_body(s), "issue": lambda: self._issue_body(report),
                    "checklist": lambda: self._checklist_body(s["rows"], s["last"])}.get(k, lambda: s["body"])()
            if k == "toc":
                kicker = "CONTENTS"
            elif k == "flow":
                kicker = f"{FLOWS} · {escape(self._plain(s['flow']['role']))}"
            else:
                kicker = s.get("kicker") or s["part"]
            cls = f"slide a4 g-{k}" + (" toc-slide" if k == "toc" else "")
            pages.append(f"""<section {sid} class="{cls}">
  <header><div class="kicker">{kicker}</div><h2>{s['title']}</h2><p class="lede">{s['lede']}</p></header>
  <div class="content">{body}</div>{foot}</section>""")
        html = "".join(pages).replace('src="shots/', f'src="{self._src}/')
        leak = _SECRET.search(self._plain(html))
        if leak:
            raise ValueError(f"文件裡疑似有密碼或金鑰「{leak.group(0)}…」：帳號密碼私下提供，不寫進測試指引")
        doc = f"""<!doctype html><html lang="zh-Hant"><head><meta charset="utf-8"><title>{escape(self.filename(""))}</title>
<link rel="preconnect" href="https://fonts.googleapis.com"><link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;700&family=Noto+Sans+TC:wght@400;500;700;900&display=block" rel="stylesheet">
<style>{css}</style></head><body class="a4-doc">{html}</body></html>"""
        out.write_text(doc, encoding="utf-8")
        print("pages", n, "→", out)
        print(f"測試指引：{len(self._roles)} 種身分、{len(self._flows)} 條流程"
              f"（{sum(len(f['steps']) for f in self._flows)} 步）；回報到 {self._plain(report['channel'])}")
        print("PDF：node <skill>/scripts/render.mjs --html", f'"{out.name}"', "--png preview（A4；超過 20 MB 自動壓縮）")
        return out
