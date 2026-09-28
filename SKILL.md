---
name: ai-go-app-present
description: >
  Use when the user asks for an operation manual, tutorial, user guide, feature walkthrough
  or handover deck for an AI GO custom app（操作手冊、教學文件、使用說明、功能導覽、交接簡報、
  閱讀式簡報 PDF）。抓重點功能 → 規劃結構並經使用者核准 → 登入真實後台截圖（全頁圖解＋局部操作）→
  查證每個參數「情境 → 結果」→ 產出 16:9 閱讀式簡報 PDF。含可重跑的截圖、排版、渲染腳本與提示詞。
---

# AI GO App 操作手冊產生器

把一支 AI GO custom app 做成「讀得懂、照著做得出來」的 16:9 閱讀式簡報 PDF：
真實後台截圖、大功能全頁圖解、一個流程一頁、每個設定都講清楚「改了在什麼情境會怎樣」。

**樣式固定為 AI GO 品牌 B2B 母版**（references/brand.md）：深底封面押製作日、每頁左緣品牌藍條、
全頁截圖包瀏覽器框、深底封底。**檔名固定為「AI GO 租戶名 App名 YYYYMMDD」**（PDF 與 HTML 同名）。

## 何時用

- 「幫 {app} 做一份操作手冊／教學文件／交接簡報，要附截圖」
- 「教一個人怎麼用這個後台，從串接到每頁功能與維護」
- 介面改版後要重出手冊（工作資料夾還在就從 P4 重跑）

## 需要的東西

| 項目 | 說明 |
|---|---|
| Node 18+ ＋ `npm install`（skill 目錄） | 裝 puppeteer-core |
| Google Chrome | 或設 `CHROME_PATH` |
| Python 3 ＋ Pillow | 排版與總表（`pip install pillow`） |
| 登入憑證 | runtime：`AIGO_EMAIL`／`AIGO_PASSWORD`（或 `AIGO_TOKEN`）；preview：`DEVPORTAL_PAT`。放環境變數或 `env_file`，**不要寫進任何 repo** |
| app 原始碼 | 讀路由、欄位、後端行為（說法查證要用） |

## 流程（詳見 references/workflow.md）

```
P0 需求確認 → P1 探勘 → P2 大綱 ═G1 使用者核准═ → P3 準備資料 → P4 截圖 ═G2 截圖驗收═
→ P5 寫內容 ═G3 說法查證═ → P6 排版輸出 ═G4 逐頁目視═ → P7 交付與收尾
```

**關卡不能跳**：G1 沒核准不開拍；G2 沒看過每張不寫內容；G3 查不到依據的說法不寫進去；G4 沒看過每頁不交付。

### 快速開始

```bash
# 在工作資料夾（例：{app}-work/guide/）
cp <skill>/templates/present.config.example.json present.config.json   # 改 slug、routes、title、brand
node <skill>/scripts/discover.mjs --config present.config.json          # P1：每頁小圖＋ui.json
#   → 依 templates/outline.example.md 提大綱，等使用者核准（G1）
python <skill>/scripts/prep_state.py backup --table … --fields … --where …   # P3：備份會被改到的狀態
cp <skill>/templates/shots.plan.example.mjs shots.plan.mjs               # 改成這支 app 的截圖計畫
node <skill>/scripts/shoot.mjs --config present.config.json [群組…]      # P4
python <skill>/scripts/contact_sheet.py "shots/*.png" --out disc/sheet   # G2：逐張看
python <skill>/scripts/prep_state.py restore --table …                   # 還原
cp <skill>/templates/deck_content.example.py deck_content.py             # P5：改 SKILL 路徑後照大綱寫
python deck_content.py                                                   # →「AI GO 租戶名 App名 YYYYMMDD.html」
node <skill>/scripts/render.mjs --html "AI GO 租戶名 App名 YYYYMMDD.html" --png preview   # 同名 PDF
python <skill>/scripts/contact_sheet.py "preview/p*.png" --rows 2 --out disc/pv --no-label   # G4
```

## 核心原則

1. **先問再做**：對象、重心、形式、資料（references/prompts.md §1）。使用者說過的不再問。
2. **預設比重**：核心工作流程 ＞ 可控制的參數與提示詞 ＞ 其他頁面。
3. **一個流程一頁**；**只有大功能用全頁截圖＋圖解**；操作過程只截局部。
4. **參數頁的核心是「設定（目前值）｜情境 → 結果」**：改成什麼 → 遇到什麼情況 → 會發生什麼（references/writing-guide.md）。
5. **每句行為描述都要有依據**（程式碼／線上設定／實測）；前端說明可能過時，以後端為準。
6. **截圖就是 UI 驗收**：看到異常先當 bug 查，修好照 app 發布規則上線再重拍。
7. **截圖的副作用要還原**：未讀、模式、開關；會對外送出的操作只對自己的測試帳號做。
8. **密鑰零容忍**：每張截圖檢查；憑證只放本機。
9. **品牌不改**：色彩、字體、版型照 AI GO 母版；App 自己的品牌色只出現在截圖裡。

## 檔案

| 路徑 | 內容 |
|---|---|
| `scripts/lib.mjs` | 登入、shadow DOM 查找、`shot()`（全頁／局部聯集／圖解座標）、`mouseClick`、`step` |
| `scripts/discover.mjs` | 探勘：每頁小圖＋分頁／按鈕／欄位／placeholder 清單 |
| `scripts/shoot.mjs` | 依 `shots.plan.mjs` 分群組截圖 |
| `scripts/prep_state.py` | 資料狀態備份／還原／比對（標準函式庫） |
| `scripts/deck_kit.py` ＋ `deck.css` | AI GO 品牌簡報元件（瀏覽器框截圖＋圖解、步驟、表格、提示框、封面押製作日、分隔頁、封底）與檔名規則 |
| `scripts/render.mjs` | HTML → 同名 PDF ＋ 每頁 PNG ＋ 溢出／擠壓檢查 |
| `scripts/contact_sheet.py` | 截圖／預覽總表 |
| `templates/` | 設定檔、截圖計畫、簡報內容（11 種頁型）、大綱提案範本 |
| `references/workflow.md` | 七階段與四道關卡 |
| `references/brand.md` | AI GO 品牌規範（色彩、字體、幾何、固定頁、截圖框、檔名） |
| `references/writing-guide.md` | 語氣、頁型、「情境 → 結果」寫法、說法查證 |
| `references/screenshot-guide.md` | 截圖種類、spec 寫法、12 個技巧 |
| `references/layout-guide.md` | 畫布、圖片尺寸、字級、G4 檢查表 |
| `references/prompts.md` | 需求確認、頁面盤點、參數效果、說法查證、截圖與簡報檢查、大綱提案 |
| `references/pitfalls.md` | 實戰踩雷 |
