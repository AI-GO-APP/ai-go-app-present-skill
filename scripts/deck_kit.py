# -*- coding: utf-8 -*-
"""ai-go-app-present：AI GO 品牌 16:9 閱讀式簡報元件（每頁 1600×900 px＝母版 1280×720 的 1.25 倍）。

內容檔（見 templates/deck_content.example.py）這樣用：

    from deck_kit import Deck
    d = Deck.from_meta("disc/meta.json", shots="shots", version="VFS v12")   # 或 Deck(tenant=…, app=…)
    d.cover(...); d.slide(part, title, lede, body); ...; d.back_cover(...)
    html = d.write()          # →「AI GO 租戶名 App名 YYYYMMDD.html」，PDF 同名

版面預算（見 references/layout-guide.md）：內容區約 1392×650；兩張並排圖每張 ≤ 680 寬。
品牌規則：品牌藍不換色、每頁左緣藍條、封面／分隔頁／封底深底（見 references/brand.md）。
"""
import datetime as _dt
import json
import os
from html import escape
from pathlib import Path

HERE = Path(__file__).resolve().parent
TW = _dt.timezone(_dt.timedelta(hours=8))
LOGO = ('<div class="logo"><svg viewBox="0 0 24 24" fill="none" stroke="#1F80FF" stroke-width="1.6" stroke-linecap="round">'
        '<path d="M12 3 L4.5 20 M12 3 L19.5 20 M8 13 h8"/><circle cx="12" cy="3" r="1.6" fill="#1F80FF"/></svg></div>')
_BAD = set('<>:"/\\|?*')


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
        全頁截圖自動包深色瀏覽器框（品牌規則：產品截圖不裸貼）；frame=True/False 可強制。"""
        if name not in self.man:
            raise KeyError("shots.json 沒有這張截圖：" + name)
        m = self.man[name]
        framed = m.get("full", m["w"] >= 1600 and m["h"] >= 900) if frame is None else frame
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
            return (f'<div class="shot framed {cls}" style="width:{W}px;height:{H + bar}px">'
                    f'<div class="bar"><i></i><i></i><i></i></div>{img}</div>')
        return f'<div class="shot {cls}" style="width:{W}px;height:{H}px">{img}</div>'

    @staticmethod
    def cap(text):
        return f'<div class="cap">{text}</div>'

    def fig(self, name, maxw, maxh=None, caption="", marks=True):
        return f'<figure>{self.shot(name, maxw, maxh, marks)}{self.cap(caption) if caption else ""}</figure>'

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

    def raw(self, html, part="", cls=""):
        self.slides.append(dict(raw=html, part=part, cls=cls))

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

    def divider(self, part, label, title, desc, items):
        """分隔頁（深底）：PART 標籤、標題、一句話、本部分頁目。"""
        self.raw(f"""<div class="divider"><div class="dv-k">{label}</div><h1>{title}</h1><p>{desc}</p>
<div class="dv-list">{self.bullets(items)}</div></div>""", part=part, cls="divider-slide")

    def back_cover(self, title="有問題時", lead="", contact=()):
        """封底（深底）：logo、一句話、摘要、聯絡列（固定帶 Urfit Technology Co., Ltd. · ai-go.app）。"""
        items = "".join(f"<span>{x}</span>" for x in list(contact) + ["Urfit Technology Co., Ltd. · Taipei", "ai-go.app"])
        self.raw(f"""<div class="back">{LOGO}<div class="cv-k" style="margin:0 0 26px">AI GO · {escape(self.tenant)}</div>
<h1>{title}</h1><p>{lead}</p><div class="contact">{items}</div></div>""", cls="back-slide")

    # ───────────── 輸出 ─────────────
    def write(self, out=None):
        """輸出 HTML；out 省略＝依檔名規則「AI GO 租戶名 App名 YYYYMMDD.html」。PDF 用同名 .pdf。"""
        out = Path(out or self.filename(".html")).resolve()
        self._src = os.path.relpath(self.shots, out.parent).replace("\\", "/")
        # 截圖路徑在 shot() 時已經寫進 HTML，這裡統一換成相對 out 的路徑
        css = (HERE / "deck.css").read_text(encoding="utf-8") + self.extra_css
        pages, n = [], len(self.slides)
        for i, s in enumerate(self.slides, 1):
            part = ("　·　" + s["part"]) if s.get("part") else ""
            foot = (f'<div class="foot"><span>AI GO · {escape(self.tenant)}　{escape(self.name)}{part}</span>'
                    f'<span class="pg">{i:02d} / {n:02d}</span></div>')
            if "raw" in s:
                bare = s.get("cls") in ("cover-slide", "back-slide")
                pages.append(f'<section class="slide {s.get("cls", "")}">{s["raw"]}{"" if bare else foot}</section>')
            else:
                pages.append(f"""<section class="slide {s['cls']}">
  <header><div class="kicker">{s['kicker']}</div><h2>{s['title']}</h2><p class="lede">{s['lede']}</p></header>
  <div class="content">{s['body']}</div>{foot}</section>""")
        html = "".join(pages).replace('src="shots/', f'src="{self._src}/')
        doc = f"""<!doctype html><html lang="zh-Hant"><head><meta charset="utf-8"><title>{escape(self.filename(""))}</title>
<link rel="preconnect" href="https://fonts.googleapis.com"><link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;700&family=Noto+Sans+TC:wght@400;500;700;900&display=block" rel="stylesheet">
<style>{css}</style></head><body>{html}</body></html>"""
        out.write_text(doc, encoding="utf-8")
        print("slides", n, "→", out)
        print("PDF：node <skill>/scripts/render.mjs --html", f'"{out.name}"', "--png preview（PDF 與 HTML 同名）")
        return out
