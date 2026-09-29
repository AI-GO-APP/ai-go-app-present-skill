# -*- coding: utf-8 -*-
"""ai-go-app-present：AI GO 品牌 16:9 閱讀式簡報元件（每頁 1600×900 px＝母版 1280×720 的 1.25 倍）。

內容檔（見 templates/deck_content.example.py）這樣用：

    from deck_kit import Deck
    d = Deck.from_meta("disc/meta.json", shots="shots", version="VFS v12")   # 或 Deck(tenant=…, app=…)
    d.cover(...); d.slide(part, title, lede, body); ...; d.back_cover(...)
    html = d.write()          # →「AI GO 租戶名 App名 YYYYMMDD.html」，PDF 同名

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
_TOC_HOWTO_ROWS = 3     # 目錄第一頁底部「讀法」列佔掉的列數


def deck_filename(tenant, app, made, ext=".pdf"):
    """檔名規則：「AI GO 租戶名 App名 YYYYMMDD」。檔名不能用的字元換成底線。"""
    clean = lambda t: "".join("_" if ch in _BAD else ch for ch in str(t)).strip()
    return f"AI GO {clean(tenant)} {clean(app)} {made:%Y%m%d}{ext}"


class Deck:
    def __init__(self, tenant, app, shots="shots", made=None, version="", title="後台操作手冊", extra_css=""):
        """tenant＝租戶名（例：展示股份有限公司）；app＝平台上的 App 名；made＝製作日（預設今天，台灣時間）。"""
        self.shots = Path(shots).resolve()
        mf = self.shots / "shots.json"
        self.man = json.loads(mf.read_text(encoding="utf-8")) if mf.exists() else {}
        self.tenant, self.app, self.title, self.version, self.extra_css = tenant, app, title, version, extra_css
        if isinstance(made, str):
            made = _dt.date.fromisoformat(made)
        self.made = made or _dt.datetime.now(TW).date()
        self.slides = []
        self._src = "shots"

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
        return deck_filename(self.tenant, self.app, self.made, ext)

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
        self.slides.append(dict(part=part, title=title, lede=lede, body=body, kicker=kicker or part, cls=f"{cls} {bg}".strip()))

    def raw(self, html, part="", cls="", title=None):
        """自訂整頁 HTML。title 有給才會列進目錄。"""
        self.slides.append(dict(raw=html, part=part, cls=cls, title=title))

    def cover(self, sub, meta=(), hero=None, hero_w=720, kicker=None):
        """封面（深底）：logo、眉標、App 名＋手冊名、一句話、製作日章、底部資訊列。
        meta：額外的 [(欄名, 內容)]，接在「租戶／App／版本」之後；hero：右側截圖名（包瀏覽器框）。"""
        rows = [("租戶", self.tenant), ("App", self.app)] + ([("版本", self.version)] if self.version else []) + list(meta)
        m = "".join(f"<div><span>{k}</span>{v}</div>" for k, v in rows)
        h = self.shot(hero, hero_w, 620, marks=False, frame=True) if hero else ""
        k = kicker or f"AI GO · {escape(self.tenant)} · 操作手冊"
        self.raw(f"""<div class="cover"><div class="cv-l">{LOGO}<div class="cv-k">{k}</div>
<h1><span class="app">{escape(self.app)}</span>{escape(self.title)}</h1><p class="cv-sub">{sub}</p>
<div class="cv-date"><span>製作日</span><b>{self.made:%Y.%m.%d}</b></div>
<div class="cv-meta">{m}</div></div><div class="cv-r">{h}</div></div>""", cls="cover-slide")

    def divider(self, part, label, title, desc, items=None):
        """分隔頁（深底）：PART 標籤、標題、一句話、本部分頁目。
        items 省略＝write() 時自動列出本部分每一頁的標題與頁碼（建議）；給字串清單則照給的列。
        分隔頁同時是目錄的分組：label（PART A）＋title（核心工作）。"""
        self.slides.append(dict(kind="divider", part=part, label=label, title=title, desc=desc, items=items,
                                cls="divider-slide"))

    def toc(self, title="目錄", lede="點標題可直接跳到該頁。", howto=True):
        """目錄頁：write() 時依實際頁序產生（分隔頁＝分組、內容頁＝列、頁碼可點）。
        放在呼叫的位置；沒呼叫的話 write() 自動插在封面後面——每份手冊一定有目錄。
        howto=True：底部放「讀法」列（編號、情境 → 結果、注意）；列太多放不下時省略。
        列多時自動縮字級（dense），再多就拆成「（續）」欄與多頁。"""
        if any(x.get("kind") == "toc" for x in self.slides):
            raise ValueError("目錄只能有一個（d.toc() 呼叫了兩次）")
        self.slides.append(dict(kind="toc", title=title, lede=lede, howto=howto))

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
        """依頁序把可列入目錄的頁分組：[{label, title, page, rows:[(標題, 頁碼)]}]。
        slides 為最終頁序；分隔頁開新組，第一個分隔頁之前的頁歸在第一頁的 part 底下。"""
        groups = []
        for i, s in enumerate(slides, 1):
            kind = s.get("kind")
            if kind == "divider":
                groups.append(dict(label=self._plain(s["label"]), title=self._plain(s["title"]), page=i, rows=[]))
                continue
            if kind == "toc" or s.get("cls") in ("cover-slide", "back-slide"):
                continue
            title = self._plain(s.get("title"))
            if not title:
                continue
            if not groups:
                groups.append(dict(label="", title=self._plain(s.get("part")) or "開始之前", page=i, rows=[]))
            groups[-1]["rows"].append((title, i))
        return groups

    @staticmethod
    def _toc_pages(groups, howto):
        """把分組排成目錄頁：每頁最多 4 欄；組太長就拆成「（續）」欄。回傳 (pages, dense, howto_at)。
        pages：[[欄, …], …]，欄＝(group, rows, 是否續欄)。
        讀法列放在最後一頁（每欄都留得出 _TOC_HOWTO_ROWS 列時）；放不下就省略（howto_at=None），不為它多開一頁。"""
        longest = max((len(g["rows"]) for g in groups), default=0)
        dense = longest > _TOC_ROWS - (_TOC_HOWTO_ROWS if howto else 0)
        cap = _TOC_ROWS_DENSE if dense else _TOC_ROWS
        cols = []
        for g in groups:
            rows = g["rows"] or [None]
            for k in range(0, len(rows), cap):
                cols.append((g, [r for r in rows[k:k + cap] if r], k > 0))
        pages = [cols[k:k + 4] for k in range(0, len(cols), 4)] or [[]]
        fits = all(len(rows) <= cap - _TOC_HOWTO_ROWS for _, rows, _ in pages[-1])
        return pages, dense, (len(pages) - 1 if howto and fits else None)

    def _toc_body(self, cols, dense, howto):
        html = []
        if cols:
            n = max(len(cols), 3)
            html.append(f'<div class="toc{" dense" if dense else ""}" style="grid-template-columns:repeat({n},minmax(0,1fr))">')
            for g, rows, cont in cols:
                letter = g["label"].split()[-1] if g["label"] else ""
                head = escape(g["title"]) + ("（續）" if cont else "")
                html.append(f'<div class="toc-col"><a class="toc-h" href="#p{g["page"]:02d}">'
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
        """展開目錄、算頁碼。回傳最終頁序（每頁一個 dict；目錄頁帶 body、分隔頁帶 items）。"""
        slides = list(self.slides)
        at = next((i for i, s in enumerate(slides) if s.get("kind") == "toc"), None)
        if at is None:   # 目錄必須有：自動插在封面後面（沒有封面就放第一頁）
            at = next((i + 1 for i, s in enumerate(slides) if s.get("cls") == "cover-slide"), 0)
            slides.insert(at, dict(kind="toc", title="目錄", lede="點標題可直接跳到該頁。", howto=True))
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
        """輸出 HTML；out 省略＝依檔名規則「AI GO 租戶名 App名 YYYYMMDD.html」。PDF 用同名 .pdf。
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
        print("PDF：node <skill>/scripts/render.mjs --html", f'"{out.name}"',
              "--png preview（PDF 與 HTML 同名；超過 20 MB 自動壓縮）")
        return out
