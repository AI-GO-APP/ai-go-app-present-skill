# Changelog

## 0.9.1 — 2026-10-04

### 交付通知修正（審查發現）

- **對方有 AI、這週有好幾件事時**：上段原本只列功能名，看不到每件做了什麼，需求方無從判斷「是不是我要的」。
  改成一件一行「一、「功能」：做了什麼」
- **安全檢查漏看預期結果**：「按「儲存」→ 預期：客人收到推播」原本會過。`expect` 也檢查危險動作
- **週會時間帶時區會當掉**（`2026-10-07T14:00:00+08:00`）：改成換算成台灣時間
- **週會當天開過了還不算過期**：期限改用時間點比（只寫日期＝那天結束前）；`meeting` 已過但 `reply_by` 還沒到時提醒確認週會日。
  `reply_by` 也可以寫到時間（`2026-10-06 18:00`）
- **禁用詞回到 issue 清單**：拿掉自行加的「後端、前端、資料庫、伺服器、快取、原始碼、資料結構、錯誤代碼、資料中心」等
  （「資料中心」是客戶畫面看得到的名稱）；英文叫法照樣由英文通則擋。「分支機構」不再被「分支」誤擋
- **危險動作拿掉「移除」「封存」**：「按「移除」把篩選條件拿掉」這類無害操作不再被擋
- **「404 頁面」漏擋**：「頁」「行」不再當數量單位
- **整則超過 10 步提醒**（FDE 一週一則後總步數沒上限）
- `handoff.md` 範例改成範本的實際輸出（原本少第 4 步與單件連結）
- 補記 0.9.0 漏寫的：測試用參數 `--today` 改名 `--now`（可寫到時間）
- 測試：`tests/test_handoff.py` 32 項

## 0.9.0 — 2026-10-04

⚠️ **破壞性（交付通知輸入檔）**：`handoff.json` 格式改了——拿掉 `site`、`mode`、`ai_helper`、`changes`，
改成 `items`（每件事＋步驟）＋必填 `with_ai`；FDE 必填 `meeting`。0.8.0 的輸入檔要照
`templates/handoff.example.json` 重寫。手冊流程不受影響。

### 交付通知修正（issue #8 回饋）

- **不分測試站、正式站**：`url` 就是交付站，每次問使用者要連結。拿掉 `site` 與「只在測試站才產 AI 段」的規則；
  給 AI 的規則改成「只在這個網址上操作」
- **不讀客戶資料**：拿掉「看客戶資料『會用 AI 開發的人』那一欄」。改成每次問使用者對方有沒有會用 AI 的人，
  填 `with_ai: true／false`；沒填直接報錯（不能預設、不能猜）
- **FDE 一週一則**：一則涵蓋這週所有做好的事（每件 1～5 步）＋要對方決定的事，週會前 **48 小時**交
  （`meeting` 寫到時間，不到 48 小時提醒）；回覆期限預設＝週會開始前。本週薄版併進這則，拿掉 `mode: weekly`
- RD 照舊做完就交；只有一件事時版面同 0.8.0
- 有 AI 時：決定的事放上段給人，不給 AI；下段多件事分「一、二、」，回報「每個功能的每一步」
- 範本：`handoff.example.json` 改成 FDE 週交付、新增 `handoff.rd.example.json`、刪除 `handoff.weekly.example.json`
- 文件：`handoff.md` 重寫、`prompts.md` §9 改成每次要問的兩件事、`pitfalls.md`、SKILL.md、README
- 測試：`tests/test_handoff.py` 改寫（28 項）

## 0.8.0 — 2026-10-04

### 交付通知（新入口，issue #8）

RD 或 FDE 做完一件事，產出一則可以直接貼給需求方的短訊息，不再只回「做好了」、不再靠人轉述。
和操作手冊是兩個入口：不走 P0～P7。**只產文字，不自動發送。**

- **`scripts/handoff.py`**（標準函式庫）：讀 `handoff.json` 組訊息，固定五段——做好了什麼／在哪裡看（測試站或
  正式站＋連結）／驗什麼怎麼驗（1～5 步）／何時回覆「可以」或「不行」（日期含星期）／不行回給誰、附什麼
- **需求方有 AI 時**：`ai_helper` 有填且在測試站 → 上下兩段。上段給人看（不列步驟、看完 AI 回報後回覆），
  下段整段貼給對方的 AI：只在測試站、不刪資料、不送訊息、用已登入的瀏覽器；每步「做什麼。預期：…」；
  固定回報格式（通過／不通過＋截圖＋看到什麼）。在正式站就只產給人看的版本
- **本週薄版**（`mode: weekly`）：只放本週變動和要對方決定的事（問句＋選項）
- **用語檢查**：開發用語、英文與縮寫（白名單外一律擋）、錯誤代碼、內部叫法；「」裡（照畫面抄的字）與網址不檢查。
  `--ui disc/ui.json` 把畫面上的英文加進白名單，並核對「」裡的字在畫面上找得到
- **安全檢查**：步驟不能有刪除、清空、發送、推播、退款…；訊息不能有帳號密碼、金鑰、帶 token 的網址
- **回覆期限**：`reply_by`；沒寫時 FDE 用週會前一天，其他用今天起第 2 個工作日；FDE 沒在週會前 2 天交會提醒
- 檢查沒過 exit 1、只印哪一句哪個詞，不印訊息（避免把沒改好的版本貼出去）
- 文件：`references/handoff.md`（新）、`prompts.md` §9、`pitfalls.md`「交付通知」、SKILL.md 入口與 description 觸發詞、README
- 範本：`templates/handoff.example.json`、`templates/handoff.weekly.example.json`
- 測試：`tests/test_handoff.py`（26 項：五段、上下兩段切換、正式站退回、期限、用語、白名單、ui.json、安全、薄版、CLI）

## 0.7.0 — 2026-09-29

### 驗收數據章（選配）

開發歷程有重要測試數據（例：OCR 辨識準確度、AI 判斷正確率）時，大綱階段問使用者要不要放進手冊；
同意才放，預設是**目錄後第一章**、1～2 頁，只寫指標、定義、結果、樣本、日期與測試範圍。
沒找到就不問、不出這章；不為了手冊另外跑測試。

- **`Deck.acceptance(cards, rows, note, sources)`**：上方 ≤ 4 張指標卡（大數字＋名稱＋一句定義）、
  下方「指標｜定義｜結果｜樣本｜測試日期」表 ≤ 8 列、底部一句測試範圍。最多 2 頁，超過上限直接報錯。
  寫在哪都會被移到目錄後（`after_toc=False` 照呼叫順序）
- **`sources` 必填**：來源不印進手冊，`write()` 時印出來供 G3 查證與 P7 交付回報
- **目錄**：分隔頁之前的頁依 part 分組；「驗收數據」與「開始之前」疊在第一欄，四個 PART 仍一頁放完
- 流程：`workflow.md` P1 盤點、P2 詢問、P5 查證、P7 回報；`prompts.md` §1 第 6 問、新增 §8 盤點與詢問範本
- 寫作：`writing-guide.md`「不插播」加驗收數據例外（範圍很窄）、新節「驗收數據」、頁型表；
  `layout-guide.md` 版面規格；`pitfalls.md` 四條（沒問就放、美化數字、工程測試當品質、另外跑測試）
- 範本：簡報範本加一頁發票 OCR 示範；大綱範本加選配章與固定詢問；SKILL.md 核心原則 13
- 測試：`tests/test_deck_acceptance.py`（8 項：位置、順序、上限與必填檢查、來源不入 HTML、目錄疊欄）

## 0.6.1 — 2026-09-29

### 修正

- **`render.mjs` 大份手冊產 PDF 逾時**：`page.pdf()` 沿用 puppeteer 預設 30 秒，頁多、全頁截圖多時
  （回報案例：52 頁、11.7 MB，約需 1 分鐘）會丟 `TimeoutError`，PDF 與預覽 PNG 都沒產生。
  改為預設 10 分鐘，可用 `--pdf-timeout <秒>` 調整；CDP 指令上限（`protocolTimeout`，預設 180 秒）一併拉高，
  否則實際上限仍卡在 3 分鐘

## 0.6.0 — 2026-09-29

**行為變更**：每份手冊一定有目錄頁；交付的 PDF 超過 20 MB 會自動整份壓縮。
⚠️ **破壞性（依賴）**：新增 Python 依賴 **pypdf**，請執行 `pip install pypdf`（Ghostscript 選配）。
沒裝的話，PDF 超過 20 MB 時壓縮會失敗、`render.mjs` exit 1。

### 目錄頁（必備、自動產生）

- **`Deck.toc()`**：`write()` 時依實際頁序產生——分隔頁＝分組（PART 標籤＋標題）、每頁標題＝一列＋頁碼、
  底部讀法列（原本導讀頁的編號／情境 → 結果／注意）。沒呼叫也會**自動插在封面後面**，不能省略
- 列多時自動切 dense 字級；一個 PART 超過 18 頁拆成「（續）」欄，4 欄放不下拆成「目錄（續）」頁；讀法列放不下就省略
- 每頁帶 `id="pNN"`，目錄列是可點的內部連結；PDF 另依分隔頁與頁標題產生**書籤側欄**（`outline: true`）
- **分隔頁頁目自動列**：`divider(..., items=None)` 自動列出本部分每頁標題與頁碼；手寫 `items` 照舊
- `raw(..., title=)`：自訂頁給標題才會列進目錄
- `render.mjs` 檢查目錄存在、每列頁碼等於連到的頁，不過就 exit 1
- 範本：導讀頁併入目錄頁、前置頁移到第一個分隔頁之前、B／C 補分隔頁；`writing-guide.md` 頁型表「導讀」改「目錄」

### PDF 大小與獨立性

- **`scripts/compress_pdf.py`**（新）：整份 PDF 壓縮。有 Ghostscript 用 pdfwrite `/printer`→`/ebook`；
  否則 pypdf 無損整理＋把內嵌圖片重編 JPEG（品質 85 → 75 → 65 → 60，後兩階長邊縮到 2560／1920）。
  每一階都驗證頁數、頁面尺寸、每頁圖片數、內部連結、書籤不變，且無外部參照、字型已內嵌，取第一個壓進上限的版本
- **`render.mjs`**：PDF 超過 `--max-mb`（預設 20）自動呼叫壓縮；原檔搬到 `disc/…original.pdf`。
  壓到底線仍超過 → **exit 2**：正式檔名已換成最小版，交付前要問使用者（直接交付／分冊／減頁），同意即可交付。
  `--no-compress` 可關閉。預覽 PNG 用原始畫質產生
- **獨立性檢查**：`render.mjs` 擋下網路圖片、背景圖網址、iframe／video／object（exit 1）；
  `compress_pdf.py --check` 確認成品圖片與字型都內嵌、沒有外部參照
- `workflow.md` P6／P7、`layout-guide.md`（目錄規格、G4、常見修法）、`brand.md` 固定頁、`pitfalls.md`、SKILL.md 核心原則 11、12
- 測試：`tests/test_deck_toc.py`（目錄位置、頁碼、續頁、分隔頁頁目、跳脫）、
  `tests/test_compress_pdf.py`（壓縮、超標 exit 2、原檔保留、連結與書籤保留；需 pypdf＋Pillow，沒裝跳過）

## 0.5.0 — 2026-09-29

### 瀏覽器以外的畫面：終端框、桌面視窗截圖、桌面操作工具退路

- **`Deck.term()` 終端框**：終端指令不截圖，把指令與實際輸出渲染成品牌深色終端（`redact` 遮密鑰）；
  新頁型「指令」
- **`scripts/desktop_shot.py`**（新，標準函式庫）：依視窗標題／整個螢幕／區域截圖，寫進同一份 `shots.json`
  （`kind: "desktop"`），整個視窗／螢幕 `Deck.shot()` 自動包**視窗框**（深色列＋視窗標題），`--region`／`--from`
  裁的局部不包框；`fig()` 新增 `frame` 參數。Windows 用 Win32／GDI 零相依、
  已處理 DPI；macOS 走 osascript＋screencapture、Linux 走 xdotool＋import，盡力支援；`--from` 裁既有圖
  （agent 桌面操作工具存下來的）需要 Pillow；`--list` 列可見視窗
- **`s.desktop(name, opts)`**：截圖計畫裡直接呼叫，桌面截圖與瀏覽器截圖同一份計畫、可單獨重跑
- `screenshot-guide.md` 新節「瀏覽器以外的畫面」：決策表（能渲染就不截圖、能腳本就不手動、手動只當退路）、
  桌面截圖的 G2 額外檢查、桌面操作工具的限制；`prompts.md` §1 加問「有沒有瀏覽器以外的步驟」；
  `pitfalls.md` 補終端入鏡、通知入鏡、標題找不到、DPI；範本補指令頁、桌面視窗頁、desktop 群組
- `tests/test_desktop_shot.py`：PNG 編碼、參數解析、manifest 併寫、deck_kit 視窗框與終端框；Windows 上另測真實擷取

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
