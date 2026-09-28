# -*- coding: utf-8 -*-
"""ai-go-app-present：16:9 閱讀式簡報元件（每頁 1600×900 px）。

內容檔（見 templates/deck_content.example.py）這樣用：

    from deck_kit import Deck
    d = Deck(shots="shots", title="XX 後台操作手冊", version="2026-09-28・VFS v12")
    d.cover(...); d.slide(part, title, lede, body); ...
    d.write("deck.html")

版面預算（見 references/layout-guide.md）：內容區約 1480×680；兩張並排圖每張 ≤ 722 寬。
"""
import json
import os
from html import escape
from pathlib import Path

HERE = Path(__file__).resolve().parent


class Deck:
    def __init__(self, shots="shots", title="操作手冊", version="", brand=None, extra_css=""):
        self.shots = Path(shots).resolve()
        mf = self.shots / "shots.json"
        self.man = json.loads(mf.read_text(encoding="utf-8")) if mf.exists() else {}
        self.title, self.version, self.brand, self.extra_css = title, version, brand, extra_css
        self.slides = []
        self._src = "shots"

    # ───────────── 元件 ─────────────
    def shot(self, name, maxw, maxh=None, marks=True, cls=""):
        """截圖，依 maxw／maxh 等比縮放；marks=True 疊上 shots.json 記的藍色編號框。"""
        if name not in self.man:
            raise KeyError("shots.json 沒有這張截圖：" + name)
        m = self.man[name]
        s = maxw / m["w"]
        if maxh:
            s = min(s, maxh / m["h"])
        W, H = round(m["w"] * s), round(m["h"] * s)
        mk = ""
        if marks:
            for k in m.get("marks", []):
                x, y = max(0, k["x"] * s) + 2, max(0, k["y"] * s) + 2
                w, h = min(W - x - 2, k["w"] * s - 4), min(H - y - 2, k["h"] * s - 4)
                mk += (f'<div class="mk" style="left:{x:.0f}px;top:{y:.0f}px;width:{max(w, 8):.0f}px;'
                       f'height:{max(h, 8):.0f}px"><b>{k["n"]}</b></div>')
        return (f'<div class="shot {cls}" style="width:{W}px;height:{H}px">'
                f'<img src="{self._src}/{name}.png" alt="">{mk}</div>')

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
    def slide(self, part, title, lede, body, kicker=None, cls=""):
        self.slides.append(dict(part=part, title=title, lede=lede, body=body, kicker=kicker or part, cls=cls))

    def raw(self, html, part="", cls=""):
        self.slides.append(dict(raw=html, part=part, cls=cls))

    def cover(self, kicker, title, sub, meta, hero=None, hero_w=740):
        """meta: [(欄名, 內容)]；hero: 截圖名（斜放在右側）。"""
        m = "".join(f"<div><span>{k}</span>{v}</div>" for k, v in meta)
        h = self.shot(hero, hero_w, marks=False, cls="tilt") if hero else ""
        self.raw(f"""<div class="cover"><div class="cv-l"><div class="cv-k">{kicker}</div><h1>{title}</h1>
<p class="cv-sub">{sub}</p><div class="cv-meta">{m}</div></div><div class="cv-r">{h}</div></div>""", cls="cover-slide")

    def divider(self, part, label, title, desc, items):
        self.raw(f"""<div class="divider"><div class="dv-k">{label}</div><h1>{title}</h1><p>{desc}</p>
<div class="dv-list">{self.bullets(items)}</div></div>""", part=part, cls="divider-slide")

    # ───────────── 輸出 ─────────────
    def write(self, out="deck.html"):
        out = Path(out).resolve()
        self._src = os.path.relpath(self.shots, out.parent).replace("\\", "/")
        # 截圖路徑在 shot() 時已經寫進 HTML，這裡統一換成相對 out 的路徑
        css = (HERE / "deck.css").read_text(encoding="utf-8")
        if self.brand:
            css += "\n:root { --brand: %s; }\n" % self.brand
        css += self.extra_css
        pages, n = [], len(self.slides)
        for i, s in enumerate(self.slides, 1):
            part = ("　·　" + s["part"]) if s.get("part") else ""
            foot = f'<div class="foot"><span>{escape(self.title)}{part}</span><span>{i} / {n}</span></div>'
            if "raw" in s:
                pages.append(f'<section class="slide {s.get("cls", "")}">{s["raw"]}{foot if i > 1 else ""}</section>')
            else:
                pages.append(f"""<section class="slide {s['cls']}">
  <header><div class="kicker">{s['kicker']}</div><h2>{s['title']}</h2><p class="lede">{s['lede']}</p></header>
  <div class="content">{s['body']}</div>{foot}</section>""")
        html = "".join(pages).replace('src="shots/', f'src="{self._src}/')
        doc = f"""<!doctype html><html lang="zh-Hant"><head><meta charset="utf-8"><title>{escape(self.title)}</title>
<link rel="preconnect" href="https://fonts.googleapis.com"><link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Noto+Sans+TC:wght@400;500;700;900&display=block" rel="stylesheet">
<style>{css}</style></head><body>{html}</body></html>"""
        out.write_text(doc, encoding="utf-8")
        print("slides", n, "→", out)
        return out
