# -*- coding: utf-8 -*-
"""簡報內容範例：複製成工作資料夾的 deck_content.py，照大綱改寫。
每一種頁型都示範一次（references/writing-guide.md 的「頁型」）。截圖名稱要和 shots.plan.mjs 一致。

執行：python deck_content.py   → deck.html → node <skill>/scripts/render.mjs --html deck.html --pdf 手冊.pdf --png preview
"""
import sys
from pathlib import Path

SKILL = Path(__file__).resolve().parent.parent / "scripts"      # 放到工作資料夾後，改成 skill 的 scripts 路徑
sys.path.insert(0, str(SKILL))
from deck_kit import Deck  # noqa: E402

d = Deck(shots="shots", title="XX 後台操作手冊", version="2026-09-28・VFS v12", brand="#C2410C")
T, S, N, C = d.table, d.steps, d.note, d.chip
P0, PA, PB, PC = "開始之前", "A　核心工作", "B　控制 AI", "C　其他與維護"

# ── 頁型 1：封面 ──
d.cover("AI GO・XX 應用", "XX 後台操作手冊",
        "一句話說清楚這份手冊教什麼：<br>核心工作怎麼做、關鍵設定在哪、改了會怎樣",
        [("適用", "demo 租戶「XX」"), ("版本", "2026-09-28・VFS v12"), ("對象", "接手後台的第一線人員（不需技術背景）")],
        hero="messages-full")

# ── 頁型 2：導讀（三欄目錄＋讀法）──
d.slide(P0, "這份手冊怎麼讀", "依重要性排列：先學核心工作，再學控制，最後是其他頁面與維護。", f"""
<div class="grid3">
  <div class="card part-a"><div class="pk">A</div><h3>核心工作</h3>{d.bullets(["全景", "找資料", "狀態與模式", "主要流程"])}</div>
  <div class="card part-b"><div class="pk">B</div><h3>控制 AI</h3>{d.bullets(["控制點地圖", "每個參數：情境 → 結果", "症狀 → 改哪裡"])}</div>
  <div class="card part-c"><div class="pk">C</div><h3>其他與維護</h3>{d.bullets(["其他頁面", "維護節奏", "目前設定值"])}</div>
</div>
<div class="howto">
  <div><span class="mk-demo">1</span>截圖上的藍色編號，對應同頁的編號說明</div>
  <div>{C("情境 → 結果")} 把設定改成這樣，使用者遇到時會發生什麼</div>
  <div>{C("注意", "warn")} 容易踩錯或會影響客人的地方</div>
</div>""")

# ── 頁型 3：分隔頁 ──
d.divider(PA, "PART A", "核心工作", "這部分教什麼（一句話）", ["全景", "找資料", "三種狀態", "流程：XX", "讀懂 XX"])

# ── 頁型 4：大功能全景（全頁截圖＋圖解編號）──
d.slide(PA, "XX 全景", "由左到右幾個區塊，先記住它們。", d.row(
    d.fig("messages-full", 1040),
    d.legend([(1, "區塊一", "做什麼"), (2, "區塊二", "做什麼"), (3, "區塊三", "做什麼")])))

# ── 頁型 5：一頁一個流程（步驟＋局部截圖）──
d.slide(PA, "流程：XX", "從哪裡開始、到哪裡結束，一頁看完。", d.row(
    d.col(S([("第一步", "做什麼、看哪裡"), ("第二步", "按哪個按鈕"), ("第三步", "完成後的狀態")]), 600),
    d.col(d.fig("list-head", 520, caption="② 的畫面") + d.fig("human-mode", 700, caption="③ 的畫面"))))

# ── 頁型 6：狀態機（三種模式）── 用 HTML 方塊＋箭頭，樣式見 deck.css 的 .modes
d.slide(PA, "三種狀態：誰在處理", "同一時間只有一種狀態。", """
<div class="modes">
  <div class="md ai"><b>狀態一</b><span>說明</span></div>
  <div class="md-arr"><span>觸發條件</span></div>
  <div class="md pend"><b>狀態二</b><span>說明</span></div>
  <div class="md-arr"><span>觸發條件</span></div>
  <div class="md hum"><b>狀態三</b><span>說明</span></div>
</div>
<div class="md-back">怎麼回到狀態一</div>""")

# ── 頁型 7：控制點地圖（流程 × 控制它的設定）──
d.slide(PB, "一次處理經過哪些控制點", "每格下方是控制它的設定。後面每一頁都是其中一格。", """
<div class="pipe">
  <div class="pp"><div class="pp-h">1 進線</div><div class="pp-b">要不要處理</div><ul><li>設定 A</li><li>設定 B</li></ul></div>
  <div class="pp"><div class="pp-h">2 判斷</div><div class="pp-b">哪一類</div><ul><li>設定 C</li></ul></div>
  <div class="pp"><div class="pp-h">3 取資料</div><div class="pp-b">能看到什麼</div><ul><li>設定 D</li></ul></div>
  <div class="pp"><div class="pp-h">4 組提示詞</div><div class="pp-b">怎麼做</div><ul><li>設定 E</li></ul></div>
  <div class="pp"><div class="pp-h">5 生成</div><div class="pp-b">誰來寫</div><ul><li>設定 F</li></ul></div>
  <div class="pp"><div class="pp-h">6 送出前</div><div class="pp-b">檢查</div><ul><li>設定 G</li></ul></div>
</div>""")

# ── 頁型 8：參數頁（左：欄位截圖；右：設定（目前）｜情境 → 結果）──
d.slide(PB, "開關與時段", "決定 AI 要不要回、什麼時間回。", d.row(
    d.col(d.fig("set-switches", 560) + d.fig("set-hours-custom", 560, caption="選「指定時段」後出現的欄位"), 560),
    d.col(T(["設定（目前）", "情境 → 結果"], [
        ["<b>設定名</b>（目前值）", "改成 X → 使用者遇到 Y 時會 Z。適合什麼場合。"],
        ["<b>設定名</b>（目前值）", "調高 → …；調低 → …。建議範圍 …"],
    ], ["210px", "auto"]) + N("<b>注意</b>：容易踩錯的地方", "warn"))))

# ── 頁型 9：症狀 → 改哪裡（速查表）──
d.slide(PB, "症狀 → 改哪裡：速查表", "遇到問題先看這張表。", T(["看到的狀況", "先檢查", "要改的地方"], [
    ["狀況一", "看哪裡確認", "改哪個設定／資料"],
    ["狀況二", "", "改哪個設定"],
], ["300px", "380px", "auto"], cls="compact dense"))

# ── 頁型 10：維護節奏（四欄）──
d.slide(PC, "維護節奏", "照頻率檢查。", f"""
<div class="grid4">
  <div class="card"><h3>每天</h3>{d.bullets(["項目"], "tight")}</div>
  <div class="card"><h3>每週</h3>{d.bullets(["項目"], "tight")}</div>
  <div class="card"><h3>活動上下檔</h3>{d.bullets(["項目"], "tight")}</div>
  <div class="card"><h3>改版</h3>{d.bullets(["項目"], "tight")}</div>
</div>""")

# ── 頁型 11：附錄：目前設定值（從線上讀，不要手打）──
d.slide(PC, "附錄：目前設定值一覽", "截至某日線上的設定。調整前先記下原值。", T(["設定", "目前值"], [
    ["設定 A", "值"], ["設定 B", "值"],
], ["300px", "auto"], cls="compact dense"))

d.write("deck.html")
