# 設計：Skill 自我更新機制

> 狀態：0.3.0 實作。來源：aigo-builder skill（`AI-GO-APP/aigo-app-builder-skill` 1.47.0）的
> `scripts/check_update.py`，機制與行為與其一致；本文記錄移植時的取捨，日後對照上游修正時先讀。

## 目標

使用者機器上的每一份本 skill 安裝，在遠端 main 發布新版後，於下一次 session 啟動（或下一次
skill 觸發）時自動跟上，不需要使用者記得 `git pull`，也不讓舊版的截圖／排版規則殘留。

## 機制摘要

| 元件 | 做法 |
|---|---|
| 比對基準 | 本地 `VERSION` vs `raw.githubusercontent.com/<repo>/main/VERSION`，semver 比較 |
| 觸發 | 主：SessionStart hook（`startup\|resume`，timeout 120s）。備：SKILL.md Phase -1 |
| 頻率 | 遠端 VERSION 快取 3 小時；本地 vs 遠端比對每次都做；同步失敗 3 小時內不重試 |
| 發現新版 | 不徵詢，強制同步：git `fetch` → `reset --hard FETCH_HEAD` → `clean -fd`；複製式 `main.zip` 鏡像 |
| 多安裝 | 狀態檔登記每份安裝，任一份發現新版就同步所有落後的安裝 |
| 開發副本 | 本地版本高於遠端、或 git 不在 main／master → 略過 |
| 輸出 | 只在「已同步／失敗」時出聲；其餘靜默，不污染 context |

## 與 builder 的差異（刻意的）

1. **狀態檔獨立**：`~/.aigo/present_update_check.json`（builder 用 `~/.aigo/update_check.json`）。
   builder 的 `_sync_all` 會拿註冊表裡**每一份**安裝的 VERSION 去比 builder 的遠端版本；
   共用註冊表的話，本 skill 的 0.x 會被判成落後於 builder 的 1.x，整包被 builder 的 main 覆蓋。
2. **npm 依賴偵測**：builder 的 Python 依賴由 uv 自動處理；本 skill 依賴 `node_modules/`
   （puppeteer-core），同步會保留它但不會重裝。同步前後比對依賴指紋，變了就要求 `npm install`。
   指紋只取 `package.json` 的依賴欄位與 `package-lock.json` 的 `packages`（去掉根套件
   `version`）——每次發版都 bump 的版本號若納入，會每次都誤報。
3. **不保留舊版相容層**：builder 的 `--apply`／`--apply-all` 旗標與狀態檔頂層舊鍵是它自己的
   歷史包袱，本 skill 從 0.3.0 才有更新機制，不需要。
4. **節流秒數可由環境變數覆寫**（`AIGO_PRESENT_UPDATE_THROTTLE`），測試用。
5. **有單元測試**：`tests/test_check_update.py`，網路與安裝目錄全部 mock／暫存，
   Python 3.9 與目前版本都要過。

## 前提

- repo 必須是**公開**的：腳本匿名抓 raw `VERSION`／`CHANGELOG.md` 與 `archive/refs/heads/main.zip`，
  私有 repo 一律 404，更新機制等於不作動（靜默，不會報錯）。
- 工作資料夾不能放在 skill 安裝目錄內（同步會清掉多出來的檔案）。
- 維護者在功能分支上開發；本機在 main 上的 clone 會被當成安裝強制同步。

## 取捨：為什麼強制覆蓋而不是詢問

沿用 builder 1.28.0 的結論：「發現新版→詢問→使用者可拒絕」實務上讓安裝長期停在舊版，
而舊版造成的錯誤訊息通常不指向版本落差。保留本地修改的開關會變成停在舊版的後門；
要改 skill 內容走 PR。開發副本判定是唯一例外，用來保護維護者未合併的工作。

## 已知限制

- 只認得至少跑過一次檢查的安裝。
- 狀態檔多 session 併發寫入為 last-writer-wins，偶爾丟一筆註冊，下次執行補回。
- 0.2.0 以前的安裝沒有腳本，需手動更新一次（CHANGELOG 0.3.0 開頭已註明）。
