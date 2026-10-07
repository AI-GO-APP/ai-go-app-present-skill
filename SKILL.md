---
name: ai-go-app-present
description: >
  Use when the user wants delivery material for an AI GO custom app: an operation manual, a weekly
  progress report to the client, a test report, a feature showcase, or an integration test run with report
  （操作說明／操作手冊、教學文件、使用說明、交接簡報；進度報告、週報、交付通知、給客戶的說明、跟客戶說做好了；
  測試報告、驗收數據、準確度；功能展示、功能導覽、demo 簡報；整合測試、端到端測試、E2E、UI 全點一次、驗收測試、
  QA、找 bug）。第一步一定先讓使用者選用途（五選、可多選、至少一種）：操作說明／測試報告／功能展示／整合測試產出
  16:9 閱讀式簡報 PDF（多選合成一份；整合測試會實際把每頁、每個 UI、每條流程點跑一次，通過的文字逐條列、
  未通過與疑慮逐項截圖），進度報告產出可直接貼給客戶的文字訊息（FDE 一週一則、週會前 48 小時）。
  含可重跑的截圖、測試、排版、渲染、訊息檢查腳本與提示詞。
---

# AI GO App 交付文件產生器

一支 AI GO custom app 交付給客戶的五種東西，都從這裡做：

| 用途 | 產出 | 給誰、什麼時候 | 細節 |
|---|---|---|---|
| **操作說明** | 16:9 閱讀式簡報 PDF | 接手後台的人；最後交付 | 真實截圖、大功能全頁圖解、一個流程一頁、每個設定「情境 → 結果」 |
| **測試報告** | 同上（1～2 頁） | 客戶決策者；有既有測試數據時 | 只整理開發過程已有的測試數據（準確度、正確率），照來源抄 |
| **功能展示** | 同上（約 5～10 頁） | 決策者、demo；不教操作 | 每個重點功能一頁：全頁截圖＋圖解＋一句「這能幫你做什麼」 |
| **整合測試** | 同上（頁數看結果） | 專案負責人、驗收；交付前 | **這次實際跑**：每頁、每個可點 UI、每條端到端流程都點一次並判斷合不合理；通過的逐條文字、未通過與疑慮逐項截圖（references/integration-test.md） |
| **進度報告** | 文字訊息（可補附圖） | FDE 給客戶；一週一則、週會前 48 小時 | 這週做好了什麼、怎麼驗、要決定的事、何時回覆（references/progress-report.md） |

PDF 類（操作說明／測試報告／功能展示／整合測試）多選時**合成一份**，順序固定：功能展示 → 測試報告 → 整合測試 → 操作說明。

**樣式固定為 AI GO 品牌 B2B 母版**（references/brand.md）：深底封面押製作日、**封面後一定是目錄頁**、
每頁左緣品牌藍條、全頁截圖包瀏覽器框、深底封底。**檔名固定為「AI GO 租戶名 App名 用途 YYYYMMDD」**（PDF 與 HTML 同名；用途照選的、依固定順序用「・」串，
例：`AI GO 展示公司 訂單中心 功能展示・操作說明 20261004.pdf`、`AI GO 展示公司 訂單中心 整合測試 20261007.pdf`；進度報告存檔也照這個規則）。
**交付的 PDF 是獨立檔案、小於 20 MB**：圖片與字型全部內嵌；超過就整份壓縮，壓到底仍超過要經使用者同意才交付。

## Phase -1：Skill 自我更新（每次觸發時執行，發現新版即強制同步）

> 若已裝 SessionStart hook（見 README「保持更新」），本階段會自動被跳過（節流），
> 不必重複執行。

```bash
python <skill>/scripts/check_update.py     # macOS / Linux 用 python3
```

- **零相依**——標準函式庫實作，不需要先 `npm install`，任何專案下都能直接跑。
- **腳本自己動手，不徵詢**：只要遠端 `VERSION` 比本地新，腳本就**直接把本機所有已註冊
  安裝強制同步到遠端 main**——git 安裝 `fetch` + `reset --hard` + `clean`，複製式安裝
  下載 `main.zip` 鏡像覆蓋。本地修改、分岔的 commit、多出來的檔案一律被遠端取代；
  不問使用者、不等回覆。你不需要也**不可以**替使用者做「要不要更新」的決定，
  也不可以為了保住本地修改而跳過本階段或改用 `--check-only`。
- **無輸出 = 沒事**：已是最新版、離線、或同一版本差 3 小時內已失敗過一次都靜默結束，
  直接往下走。（節流只抑制網路抓取與失敗重試；版本比對每次都做，
  所以本機多份安裝共用遠端快取，任一份落後都抓得到。）
- **有輸出 = 已經同步過了（或同步失敗）**，逐行處理：
  - **「已同步」**→ **立刻重新讀取 `SKILL.md` 與相關 `references/`**，讓新版指令在本回合
    就生效；把版本落差與變更摘要**告知**使用者（告知，不是徵詢——更新已完成，
    沒有拒絕的選項）。
  - **「npm 依賴有變動」**→ 在腳本列出的安裝目錄**直接執行 `npm install`**，再用截圖／渲染腳本。
    不重裝的話 puppeteer-core 版本對不上，錯誤訊息通常不會指向真正原因。
  - **「失敗」**→ 把失敗原因與腳本印出的手動指令給使用者，請他們處理完再繼續。
    若同時有「破壞性變更」警語（`--json` 為 `"breaking": true`）：明確告訴使用者
    「不處理的話會遇到什麼」，後續遇到相關錯誤時**優先回頭懷疑版本落差**。
  - **「開發副本，略過」**→ 那份是正在改 skill 的工作區（本地版本高於遠端，或 git 不在
    main／master 分支），不是安裝，不用處理也不用提。

## Phase 0：選用途（強制，每次製作的第一步）

Phase -1 之後、做任何事之前，**一定先讓使用者選這次的用途**——每次都問，不從需求推測、不沿用上一次：

- 用 AskUserQuestion **一次問兩題**（每題最多 4 個選項，所以拆開；問法見 references/prompts.md §0）：
  1. PDF 文件（`multiSelect: true`）：**操作說明／測試報告／功能展示／整合測試**
  2. 進度報告（單選）：**要／不用**（文字訊息）
  可以把從需求推測的那個標成建議，但要使用者自己選
- 兩題合計**至少一種**；都沒選就不往下做
- 選完照下表走，選了幾種就做幾種：

| 選了 | 接著做 |
|---|---|
| 操作說明／測試報告／功能展示（任一） | P0～P7（references/workflow.md）；`Deck(purposes=[…])` 傳入選的 PDF 類用途，合成一份 PDF |
| 整合測試 | IT0～IT7（references/integration-test.md）：範圍與安全 → 盤點 → 測試計畫（GT1）→ `scripts/itest.mjs` 執行 → 判讀（GT2）→ `d.itest()`；和其他 PDF 用途合成一份時共用 P6／P7 |
| 進度報告 | references/progress-report.md：問交付站連結與對方有沒有會用 AI 的人 → `scripts/progress.py` 產文字訊息 |

`Deck` 沒給 `purposes` 會直接報錯；`purposes` 放了「進度報告」也會報錯（它不出 PDF）。

## 何時用

- 「幫 {app} 做一份操作手冊／教學文件／交接簡報，要附截圖」
- 「這週要給客戶的說明」「跟王經理說做好了」「週報」
- 「把準確度測試結果整理給客戶看」「做一份功能展示給老闆 demo」
- 「交付前把整個 app 全部點過一遍」「跑一次整合測試／端到端測試，列出有問題的地方」
- 介面改版後要重出手冊（工作資料夾還在就從 P4 重跑）

不管哪一種說法，都先走 Phase 0 讓使用者選用途。

## 需要的東西

| 項目 | 說明 |
|---|---|
| Node 18+ ＋ `npm install`（skill 目錄） | 裝 puppeteer-core；自我更新提示依賴有變時要重跑 |
| Google Chrome | 或設 `CHROME_PATH` |
| Python 3 ＋ Pillow ＋ pypdf | 排版、總表、PDF 壓縮（`pip install pillow pypdf`） |
| Ghostscript（選配） | 有的話 PDF 壓縮優先用它（`gs`／`gswin64c`），沒有就用 pypdf |
| 登入憑證 | runtime：`AIGO_EMAIL`／`AIGO_PASSWORD`（或 `AIGO_TOKEN`）；preview：`DEVPORTAL_PAT`。放環境變數或 `env_file`，**不要寫進任何 repo** |
| app 原始碼 | 讀路由、欄位、後端行為（說法查證要用） |

只選進度報告時只需要 Python 3（零相依）；要補附圖才需要截圖工具與登入憑證。
整合測試需要的和截圖一樣（Node＋Chrome＋登入憑證），另外要一個可以改資料的**測試帳號**。

## 流程（PDF 類，詳見 references/workflow.md）

```
Phase 0 選用途 → P0 需求確認 → P1 探勘 → P2 大綱 ═G1 使用者核准═ → P3 準備資料 → P4 截圖 ═G2 截圖驗收═
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
cp <skill>/templates/deck_content.example.py deck_content.py             # P5：改 SKILL 路徑、purposes 後照大綱寫
python deck_content.py                                                   # →「AI GO 租戶名 App名 用途 YYYYMMDD.html」
node <skill>/scripts/render.mjs --html "AI GO 租戶名 App名 用途 YYYYMMDD.html" --png preview   # 同名 PDF；> 20 MB 自動壓縮
python <skill>/scripts/contact_sheet.py "preview/p*.png" --rows 2 --out disc/pv --no-label   # G4
```

整合測試（references/integration-test.md）：

```bash
cp <skill>/templates/itest.plan.example.mjs itest.plan.mjs               # 改成這支 app 的案例
node <skill>/scripts/itest.mjs --config present.config.json --list       # 列案例 → 照 templates/itest.outline.example.md 提計畫（GT1）
node <skill>/scripts/itest.mjs --config present.config.json              # 執行 → itest/results.json、itest/review.json
python <skill>/scripts/contact_sheet.py "shots/it-*.png" --out disc/it-sheet   # GT2：看截圖，寫 review.json 的判讀
python deck_content.py                                                   # d.itest() 產報告頁；之後同 P6 render.mjs
```

進度報告：

```bash
cp <skill>/templates/progress.example.json progress.json
python <skill>/scripts/progress.py progress.json [--ui disc/ui.json] [--out "AI GO 租戶名 App名 進度報告 YYYYMMDD.txt"]
```

## 核心原則

0. **用途由使用者選**：Phase 0 每次都問、至少一種；只做選了的用途，沒選的不順手加。
1. **先問再做**：對象、重心、形式、資料（references/prompts.md §1）。使用者說過的不再問。
2. **預設比重**：核心工作流程 ＞ 可控制的參數與提示詞 ＞ 其他頁面。
3. **一個流程一頁**；**只有大功能用全頁截圖＋圖解**；操作過程只截局部。
   瀏覽器以外的畫面：終端指令用 `d.term()` 渲染不截圖；桌面程式用 `desktop_shot.py` 截視窗；
   agent 的桌面操作工具只當退路（references/screenshot-guide.md）。
4. **參數頁的核心是「設定（目前值）｜情境 → 結果」**：改成什麼 → 遇到什麼情況 → 會發生什麼（references/writing-guide.md）。
5. **每句行為描述都要有依據**（程式碼／線上設定／實測）；前端說明可能過時，以後端為準。
6. **截圖就是驗收**：異常先照 `workflow.md` P4 的確認清單查；確認是 bug 就用 aigo-builder 修好上線、
   重拍受影響的群組、繼續截圖計畫，**不必徵詢**；只有改資料結構、改對客人的外送行為、修法不確定、
   平台問題四種例外才停下來問。
7. **截圖的副作用要還原**：未讀、模式、開關；會對外送出的操作只對自己的測試帳號做。
8. **密鑰零容忍**：每張截圖檢查；憑證只放本機。
9. **品牌不改**：色彩、字體、版型照 AI GO 母版；App 自己的品牌色只出現在截圖裡。
10. **只寫功能與操作，不插播**：不寫開發歷史、設計理由、技術架構、比較與評價、查證依據、製作過程
    （references/writing-guide.md）。介紹只在封面一句話與目錄頁。
11. **一定有目錄頁**：`Deck.write()` 依實際頁序自動產生（分隔頁＝分組、頁碼可點、PDF 附書籤），
    不要手刻、也不要刪。頁標題就是目錄列，寫短一點（約 16 字內）。
12. **交付檔獨立、小於 20 MB**：圖片一律用本機截圖（不引用網址）；`render.mjs` 超過 20 MB 自動呼叫
    `compress_pdf.py` 整份壓縮。壓到畫質底線仍超過（exit 2）→ **先問使用者**，同意就照現況交付
    （references/workflow.md P7）。
13. **測試報告只用既有數據**：使用者選了測試報告才做（要實際跑測試的是「整合測試」，兩者不混用）。探勘時找開發歷程已有的測試數據（OCR 準確度、AI 判斷正確率等
    交付品質）；找不到就告訴使用者、請他提供或拿掉這個用途，**不為了報告另外跑測試**。`d.acceptance()` 1～2 頁，
    只寫指標、定義、結果、樣本、日期與範圍；數字照來源抄，`sources` 必填（references/writing-guide.md「測試報告」）。
14. **功能展示不教操作**：使用者選了功能展示才做。`d.showcase()` 每個重點功能一頁、約 5～10 頁；
    一句「這能幫你做什麼」寫它做什麼、會怎樣，不寫形容詞與推銷語（references/writing-guide.md「功能展示」）。
15. **進度報告只給 FDE、只產文字**：一週一則、週會前 48 小時交；每次問交付站連結與對方有沒有會用 AI 的人，
    不讀客戶資料；有助於說明時補附圖；不自動發送（references/progress-report.md）。
16. **整合測試全部點過、每個問題都看過**：使用者選了整合測試才做。冒煙（每頁）＋UI 巡檢（每個可點元素）＋
    端到端（核心流程，結果對回後端）＋表單驗證；計畫經使用者核准才跑（GT1）。巡檢只點不會改資料的元素，
    端到端只動測試資料，會對外送出或扣款的寫進 `t.skip` 附原因。自動偵測只抓明顯的錯，**畫面與訊息合不合理要看截圖判斷**，
    每個未通過／疑慮都寫判讀才能出報告（GT2，`d.itest()` 會擋）。跑的過程不修 bug；交付後問使用者要不要修，
    修完重跑、標「修正後重測通過」（references/integration-test.md）。

## 檔案

| 路徑 | 內容 |
|---|---|
| `scripts/lib.mjs` | 登入、shadow DOM 查找、`shot()`（全頁／局部聯集／圖解座標）、`mouseClick`、`step` |
| `scripts/discover.mjs` | 探勘：每頁小圖＋分頁／按鈕／欄位／placeholder 清單 |
| `scripts/shoot.mjs` | 依 `shots.plan.mjs` 分群組截圖 |
| `scripts/prep_state.py` | 資料狀態備份／還原／比對（標準函式庫） |
| `scripts/desktop_shot.py` | 瀏覽器以外的畫面：桌面視窗／螢幕／區域截圖，進同一份 `shots.json`（Windows 零相依；macOS／Linux 盡力） |
| `scripts/deck_kit.py` ＋ `deck.css` | AI GO 品牌簡報元件（瀏覽器框／視窗框截圖＋圖解、終端框 `term()`、步驟、表格、提示框、封面押製作日、自動目錄 `toc()`、用途 `purposes`／`section()`、測試報告 `acceptance()`、功能展示 `showcase()`、整合測試 `itest()`、分隔頁（自動頁目）、封底）與檔名規則 |
| `scripts/render.mjs` | HTML → 同名 PDF（含書籤）＋ 每頁 PNG ＋ 溢出／擠壓、目錄、獨立性檢查；超過 20 MB 自動壓縮 |
| `scripts/compress_pdf.py` | 整份 PDF 壓縮（Ghostscript 或 pypdf）＋ 驗證頁數／圖片／連結／書籤不變、無外部參照、字型內嵌 |
| `scripts/contact_sheet.py` | 截圖／預覽總表 |
| `scripts/itest.mjs` ＋ `itest_core.mjs` | 整合測試：冒煙／UI 巡檢／端到端案例執行、自動偵測（JS 例外、API 錯誤、技術字樣、錯誤提示、沒反應、卡載入）、問題截圖標框、重現、`--list` 列案例；產出 `itest/results.json` 與判讀檔 `review.json` |
| `scripts/progress.py` | 進度報告：組訊息（一週一則，對方有 AI 時上下兩段，可附圖）＋用語與安全檢查（標準函式庫） |
| `scripts/check_update.py` | Skill 自我更新（Phase -1；零相依） |
| `resources/hooks/` | SessionStart 更新檢查 hook 範本（Claude Code／Codex） |
| `templates/` | 設定檔、截圖計畫、簡報內容（11 種頁型）、大綱提案範本、進度報告輸入（`progress.example.json`）、整合測試計畫（`itest.plan.example.mjs`）與計畫提案（`itest.outline.example.md`） |
| `references/workflow.md` | 七階段與四道關卡 |
| `references/brand.md` | AI GO 品牌規範（色彩、字體、幾何、固定頁、截圖框、檔名） |
| `references/writing-guide.md` | 語氣、頁型、「情境 → 結果」寫法、說法查證 |
| `references/screenshot-guide.md` | 截圖種類、spec 寫法、12 個技巧 |
| `references/layout-guide.md` | 畫布、圖片尺寸、字級、G4 檢查表 |
| `references/prompts.md` | 需求確認、頁面盤點、參數效果、說法查證、截圖與簡報檢查、大綱提案、選用途、測試數據盤點、進度報告詢問、整合測試範圍／盤點／判讀 |
| `references/integration-test.md` | 整合測試：架構（四個測試層、自動偵測、合理性判讀）、IT0～IT7、案例 API、判讀檔、報告頁、安全規則 |
| `references/progress-report.md` | 進度報告：要問的兩件事、訊息格式、附圖、上下兩段、用語規則、安全規則 |
| `references/pitfalls.md` | 實戰踩雷 |
