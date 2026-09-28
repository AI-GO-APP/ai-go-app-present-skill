# ai-go-app-present-skill

把 AI GO custom app 做成 **16:9 閱讀式簡報 PDF 操作手冊**的 Agent Skill：
抓重點功能 → 規劃結構（使用者核准）→ 登入真實後台截圖（全頁圖解＋局部操作）→
查證每個設定「情境 → 結果」→ 排版輸出 → 逐頁目視驗收。

適用：客服後台、CRM、POS、ERP 等任何掛在 AI GO runtime 或 developer 預覽頁的 app。

## 安裝

```bash
# 專案內（或 ~/.claude/skills/ 供全域使用）
git clone https://github.com/AI-GO-APP/ai-go-app-present-skill.git .claude/skills/ai-go-app-present
cd .claude/skills/ai-go-app-present
npm install            # puppeteer-core
pip install pillow     # 總表
```

- Claude Code：放進 `.claude/skills/` 即可被觸發（說「幫 XX 做操作手冊」）
- 其他 agent：把 `SKILL.md` 與 `references/` 加進 rules／context
- 建議加裝自動更新 hook，見下方「保持更新」

> ⚠️ **工作資料夾不要放在 skill 安裝目錄裡**。自動更新會把安裝目錄強制同步成遠端 main，
> 裡面多出來的檔案（`present.config.json`、`shots/`、產出的 PDF…）會被清掉。

## 保持更新

Skill 內含版本標記（`VERSION`）與更新腳本（`scripts/check_update.py`），
比對本地與 GitHub 上的 `VERSION`；**遠端較新時直接把本機所有已註冊安裝強制同步到
遠端 main，不詢問、不保留本地修改**。腳本零相依（只用 Python 標準函式庫），
離線或逾時一律靜默略過。機制移植自 aigo-builder skill，行為與其一致。

**檢查頻率**

| 項目 | 頻率 |
|---|---|
| 觸發 | 每次 session 啟動或恢復（SessionStart hook）；沒裝 hook 時每次 skill 觸發（SKILL.md Phase -1） |
| 抓遠端 `VERSION` | 快取 3 小時（狀態存在 `~/.aigo/present_update_check.json`） |
| 本地 vs 遠端比對 | **每次都做**，不受節流影響 |
| 同步失敗重試 | 同一份安裝、同一個遠端版本 3 小時內只重試一次 |

沒有新版時 3 秒內結束、不輸出任何東西。

**強制同步的做法**：git 安裝（`git clone` 來的）執行 `git fetch origin main` →
`git reset --hard FETCH_HEAD` → `git clean -fd`（gitignore 的 `node_modules/` 不動）；
複製式安裝則下載遠端 `main.zip` 鏡像覆蓋——遠端有的檔案全部寫入，
本地多出來的檔案刪除（`.git`／`node_modules`／`.aigo`／`.claude`／`.env` 例外）。
**你在安裝目錄裡做的任何修改都會被覆蓋**；要改 skill 內容請對本 repo 開 PR。
同步後若 `package.json`／`package-lock.json` 的依賴有變，腳本會要求在該安裝執行 `npm install`。

**唯一不碰的是開發用副本**：本地版本高於遠端（維護者已 bump 尚未發布），或 git 副本
不在 `main`／`master` 分支（功能分支、worktree），腳本視為正在改 skill 的工作區而略過。
這是保護維護者未合併的工作，不是給使用者保留本地修改的開關。

**多安裝同步**：本機每份安裝執行檢查時會把自身路徑登記進共用狀態檔，累積成安裝清單；
任一安裝發現新版時，清單裡所有落後的安裝一起被同步。
限制：只認得「至少跑過一次檢查」的安裝——從未在任何 session 觸發過的副本無從發現。
狀態檔與 aigo-builder 的 `~/.aigo/update_check.json` **刻意分開**，兩者互不干擾。

**Claude Code / Codex（推薦加裝）**：用 SessionStart hook 在 skill 載入**之前**完成同步，
新版當下就生效。範本在 `resources/hooks/`，把 `<SKILL_DIR>` 換成本機 skill 路徑後合併進設定
（已有 aigo-builder 的 hook 時，加在同一個 `SessionStart` 陣列裡即可）：

| Agent | 設定檔 | 範本 |
|-------|--------|------|
| Claude Code | `~/.claude/settings.json` 或 `<專案>/.claude/settings.json` | `resources/hooks/claude-code.settings.example.json` |
| Codex CLI（>= v0.124.0） | `~/.codex/config.toml` 或 `<repo>/.codex/config.toml` | `resources/hooks/codex.config.example.toml` |

手動執行：

```bash
python scripts/check_update.py               # 檢查並同步（macOS/Linux 用 python3）；沒動作就沒輸出
python scripts/check_update.py --force       # 忽略節流（含失敗重試抑制）
python scripts/check_update.py --json        # 機器可讀輸出，含每份安裝的同步結果
python scripts/check_update.py --check-only  # 只報告不同步（維護者／CI 用）
```

### 維護者注意

- **所有變更一律走 PR**：功能分支 → PR → merge 進 main，不直接推 main（比照 aigo-builder；
  不設分支保護，靠這條慣例）。main 一有新版，所有安裝都會自動同步，合併前請確認內容可發布。
- 改動 skill 內容後要同步 bump `VERSION`（與 `package.json` 的 `version`），並在
  `CHANGELOG.md` 補一節，標題格式固定為 `## <版本> — <日期>`，否則使用者端不會收到更新。
- 舊版腳本只會讀到新版那一節的**前 20 行**：破壞性變更的警語要寫在該節最前面，
  並帶「破壞性」或「BREAKING」字樣。
- 開發請在功能分支上做。本機在 `main` 上的 clone 會被當成安裝，一有新版就被強制同步。
- 測試：`python -m unittest discover -s tests -v`（零相依，網路全部 mock）。

## 憑證

不放在 repo 裡。擇一：

| 模式 | 需要 |
|---|---|
| runtime（已安裝在租戶的 app） | `AIGO_EMAIL`／`AIGO_PASSWORD`，或 `AIGO_TOKEN` |
| preview（developer 預覽頁） | `DEVPORTAL_PAT` |

放環境變數，或放在 `present.config.json` 的 `env_file` 指向的檔案（預設 `~/.aigo/.env`）。

## 用法

見 [SKILL.md](SKILL.md) 的「快速開始」。完整流程與關卡在 [references/workflow.md](references/workflow.md)。

## 產出長什麼樣

- 樣式：AI GO 品牌 B2B 母版（深底封面押製作日、每頁左緣品牌藍條、全頁截圖包瀏覽器框、深底封底）
- 檔名：`AI GO 租戶名 App名 YYYYMMDD.pdf`（租戶名與 App 名自動取得）
- 封面 → 導讀 → 後台地圖 → 前置設定
- A 核心工作：全景圖解、找資料、狀態機、一個流程一頁、讀懂系統資訊、側欄面板、每天的節奏
- B 控制 AI：控制點地圖、每組參數「設定（目前值）｜情境 → 結果」、測試方法、症狀 → 改哪裡
- C 其他與維護：其他頁面、維護節奏、目前設定值附錄 → 封底

## 版本

見 [CHANGELOG.md](CHANGELOG.md)。
