# Changelog

## 0.4.0 — 2026-09-29

**行為變更**：截圖時發現 app 的 bug，過確認清單後**直接修好上線、重拍、繼續**，不再徵詢；
只有改資料結構、改對客人的外送行為、修法不確定、平台問題四種例外才停下來問。

- **只寫功能與操作，不插播**（`writing-guide.md` 新節、SKILL.md 核心原則 10）：禁寫開發歷史、設計理由、
  技術架構、比較與評價、查證依據、製作過程；介紹只在封面一句話與導讀頁；附刪除測試。
  G3 查證加「🚫 插播」結論；大綱不設簡介章；`pitfalls.md` 記「探勘讀過的設計脈絡會滲進手冊」
- **截圖中順帶驗收**（`workflow.md` P4 新節、SKILL.md 核心原則 6）：五項確認清單（重現、對照後端、
  非資料問題、非平台規則、非截圖方式）→ 用 aigo-builder 修 → 發布 → 只重拍受影響群組 → 繼續。
  修了什麼記進 app 評估紀錄、交付時在對話裡列出，不寫進手冊。`screenshot-guide.md`／`pitfalls.md`
  補「看起來像 bug 其實不是」：簽核攔截、冷啟動 503、空資料、程式點擊；G2 回報格式加「確認依據」欄

## 0.3.0 — 2026-09-28

📣 **0.2.0 以前的安裝沒有自動更新**：請手動更新一次（git 安裝在 skill 目錄執行
`git pull`；複製式安裝重新下載），之後的新版就會自動同步。

### Skill 自我更新機制（移植自 aigo-builder）

- 新增 `scripts/check_update.py`（零相依）：比對本地與遠端 `VERSION`，遠端較新時**不詢問、
  直接把本機所有已註冊安裝強制同步到遠端 main**（git：`fetch` → `reset --hard` → `clean -fd`；
  複製式：`main.zip` 鏡像覆蓋）。本地版本高於遠端或不在 main／master 的 git 副本視為開發副本，略過
- 檢查頻率：遠端 `VERSION` 快取 3 小時、版本比對每次都做、同步失敗 3 小時內不重試；
  沒新版時靜默
- 狀態檔 `~/.aigo/present_update_check.json`，與 aigo-builder 分開（共用會被 builder 的 main 覆蓋）
- 同步後比對 npm 依賴（`package.json` 依賴欄位＋`package-lock.json` 套件清單，排除版本號），
  有變就要求執行 `npm install`
- SKILL.md 新增「Phase -1：Skill 自我更新」；README 新增「保持更新」
- 新增 SessionStart hook 範本 `resources/hooks/`（Claude Code、Codex）
- 新增 `tests/test_check_update.py`（29 項，零相依，Python 3.9＋）

## 0.2.0 — 2026-09-28

- **樣式統一為 AI GO 品牌 B2B 母版**（`references/brand.md`）：品牌藍 #1F80FF、Inter＋Noto Sans TC、每頁左緣藍條、
  母版三欄卡片與表格樣式、深底封面／分隔頁／封底、注意框改深底收束卡；移除自訂品牌色參數
- **封面押製作日**（`Deck(made=…)`，預設今天台灣時間）；封面帶 AI GO 圖標與租戶／App／版本資訊列；新增 `back_cover()`
- **檔名固定為「AI GO 租戶名 App名 YYYYMMDD」**：`Deck.filename()`／`write()` 自動套用，PDF 與 HTML 同名
- `discover.mjs` 自動取租戶名（/auth/me）與 App 名（頁面標題）寫進 `disc/meta.json`；`Deck.from_meta()` 讀取
- 全頁截圖自動包深色瀏覽器框（品牌規則：產品截圖不裸貼）；`slide(bg="soft")` 淺灰襯底
- `render.mjs` 新增「擠壓重疊」檢查（flex 壓扁造成截圖與表格重疊）
- 版面規格改為內容區 1392×650、並排圖每張 ≤ 680

## 0.1.0 — 2026-09-28

- 初版：七階段流程與四道關卡（需求確認、大綱核准、截圖驗收、說法查證、逐頁目視）
- 腳本：`lib.mjs`（登入、shadow DOM 查找、全頁／局部聯集截圖與圖解座標、mouseClick）、`discover.mjs`、`shoot.mjs`、`prep_state.py`、`deck_kit.py`＋`deck.css`、`render.mjs`（含溢出檢查）、`contact_sheet.py`
- 範本：設定檔、截圖計畫、11 種頁型的簡報內容、大綱提案
- 指引：寫作（情境 → 結果）、截圖、版面、提示詞、踩雷清單
- 來源：一支 LINE AI 客服後台 40 頁操作手冊的實作經驗
