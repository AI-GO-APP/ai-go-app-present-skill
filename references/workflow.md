# 工作流程與關卡

七個階段，四道關卡（G1～G4）。關卡沒過不要往下走。

```
P0 需求確認 ─► P1 探勘 ─► P2 大綱 ══G1 使用者核准══► P3 準備資料 ─► P4 截圖 ══G2 截圖驗收══►
P5 寫內容 ══G3 說法查證══► P6 排版輸出 ══G4 逐頁目視══► P7 交付與收尾
```

## P0 需求確認（先問，再動手）

問清楚這四件事（`prompts.md` §1 有問句範本）：

1. **對象**：誰要讀（第一線客服／店長／工程師／客戶決策者）→ 決定用詞深淺
2. **重心**：哪幾個功能是重點。預設：**核心工作流程 ＞ 可控制的參數與提示詞 ＞ 其他頁面**
3. **形式**：16:9 閱讀式簡報 PDF（預設）；頁數粗估；要不要附原始 markdown
4. **資料**：能不能直接用示範資料（不打碼）；哪些畫面拍不到（例如第三方後台）改用文字

同時**證明有截圖能力**：跑一次登入＋截首頁（`discover.mjs` 或單張），把圖給使用者看或自己看過。

## P1 探勘

- `node scripts/discover.mjs --config present.config.json` → `disc/*.png` ＋ `disc/ui.json`（分頁、按鈕、標題、欄位標籤、placeholder、title 屬性）
- 讀前端原始碼：路由表、每頁的分頁與欄位、`hint` 說明文字、元素的 class（之後截圖用）
- 讀後端：每個設定欄位在哪裡被使用、預設值、範圍、實際行為（`prompts.md` §3）
- 讀線上真實設定值（附錄與「目前值」欄要用真值）
- 大型 app 可以派 Explore 子代理並行盤點頁面（`prompts.md` §2）

## P2 大綱 → G1

用 `templates/outline.example.md` 的格式提出大綱，**等使用者核准才開拍**。大綱要寫：

- 章節與頁數、每頁一句話內容、截圖方式（全頁圖解／局部／無）
- 哪些東西只能用文字（拍不到的第三方畫面）
- 需要使用者確認的點（最多 3 個）

使用者常見的修正（先預設就這樣做）：
- 不要每個操作一頁；**一個流程一頁**
- **只有大功能用全頁截圖＋圖解**；操作過程只截局部
- 重心放在核心工作與 AI 控制，其他頁面精簡

## P3 準備資料

- 找一個**測試帳號／測試對話**當主角；不要用真實客人的對話做會改狀態的操作
- 備份會被截圖改到的狀態：`python scripts/prep_state.py backup --table … --fields …`
  （例：點開對話會把未讀歸零）
- 空白畫面拍不出教學價值：用 app 自己的 action 預填示範資料（例：客人卡、示範訂單）
- 需要真實 AI 回覆的畫面（例：帶記憶的回覆）可以用測試帳號送一則訊息 —— **會真的推到該 LINE 帳號**，只對自己的測試帳號做

## P4 截圖 → G2

- 寫 `shots.plan.mjs`（範本：`templates/shots.plan.example.mjs`），分群組，可單獨重跑：
  `node scripts/shoot.mjs --config present.config.json overview messages`
- 拍完：`python scripts/contact_sheet.py shots/*.png --out disc/sheet` 拼總表**逐張看過**
- **G2 驗收清單**（每張都要過）：
  - [ ] 沒有密鑰、token、完整信用卡／證件號（渠道設定頁特別注意）
  - [ ] 不是空狀態（除非這頁就是要教空狀態）
  - [ ] 選單、視窗出現在正確位置（沒有跑到左上角）
  - [ ] 內容沒有被切掉（內層捲動沒捲到位）
  - [ ] 圖解標號都有找到（shoot 輸出沒有「標號找不到」）
  - [ ] 畫面上看到的是**正確的行為** —— 截圖就是一次 UI 驗收，異常照下面的流程處理
- 拍完立刻還原：`prep_state.py restore`；模式、開關類的操作在計畫裡就要切回並確認

### 截圖中發現異常：確認 → 修 → 發布 → 重拍 → 繼續

截圖計畫是**暫停**，不是放棄。修好後只重跑受影響的群組（`shoot.mjs --config … 群組名`），再接著拍。

**確認清單**（全部成立才算 bug；有一項不成立就不是，照該項處理後繼續拍）：

- [ ] 重現兩次以上（重新載入頁面再做一次）
- [ ] 對照後端程式碼或線上設定，畫面顯示的和實際行為**不一致**（例：後端有回資料、畫面顯示「尚無資料」）
- [ ] 不是資料問題：不是空資料、不是測試帳號沒權限、不是示範資料還沒預填
- [ ] 不是平台規則：簽核 `pending`／「需要簽核審批」是租戶簽核攔截、發布後 503 是 runner 冷啟動、
      409 先讀 `code`——這些查 aigo-builder 的 `references/troubleshooting.md`，不是 app 的 bug
- [ ] 不是截圖方式造成：程式 `el.click()` 讓選單跑到左上角、內層捲動沒歸位、viewport 太窄（`pitfalls.md` 截圖段）

**確認是 bug 之後，直接修，不徵詢**：

1. 用 aigo-builder skill 修：review 現況 → 改 → 過驗證閘門 → 發布，照該 app 的發布規則走（發布 → PR → merge）
2. 重拍受影響的群組，過一次 G2
3. 記進該 app 的評估紀錄；交付時在對話裡列出修了什麼（P7）。**不寫進手冊**（`writing-guide.md`「不插播」）
4. 繼續原本的截圖計畫

**四種例外，停下來問使用者再動**：

| 例外 | 為什麼 |
|---|---|
| 要改資料結構或刪資料 | 不可逆，且影響手冊以外的東西 |
| 修法會改變對客人的外送行為（LINE 推播、Email、旅程） | 會真的送到客人那邊 |
| 修法不確定，或牽動多處、多個 app | 不該在截圖流程裡順手做大改 |
| 判定是平台問題（app 程式沒錯、平台行為不符文件） | 走 aigo-builder 的回報流程，那邊規定要問過使用者才能送 |

問的時候給非技術語言的一句話：看到什麼、確認了什麼、打算怎麼修、不修會怎樣。

## P5 寫內容 → G3

- `deck_content.py`（範本：`templates/deck_content.example.py`），寫作規則見 `writing-guide.md`
- **G3 說法查證**：每一句「系統會怎樣」都要能指到程式碼、線上設定或實測結果。
  查不到的說法刪掉或改成「請洽維運」。`prompts.md` §4 是查證清單。
- 「目前值」一律從線上讀，不要憑印象

## P6 排版輸出 → G4

```bash
python deck_content.py                       # →「AI GO 租戶名 App名 YYYYMMDD.html」
node <skill>/scripts/render.mjs --html "AI GO 租戶名 App名 YYYYMMDD.html" --png preview   # 同名 PDF
python <skill>/scripts/contact_sheet.py "preview/p*.png" --rows 2 --out disc/pv --no-label
```

- 樣式固定為 AI GO 品牌 B2B 母版（`brand.md`）；檔名與封面製作日自動產生

- `render.mjs` 會列出超出下緣、超出右緣、擠壓重疊的頁；**沒列出不代表好看**
- **G4 逐頁目視**：看總表找問題，再開單頁大圖確認（`layout-guide.md` 的檢查表）
- 修 → 重跑，直到沒有溢出、沒有擠壓、沒有孤字標題

## P7 交付與收尾

- 用 SendUserFile 把 PDF 給使用者（display: attach）；檔名必須是「AI GO 租戶名 App名 YYYYMMDD.pdf」
- 截圖時修的 bug（P4）：確認已記進該 app 的評估紀錄，並在交付對話裡列出「修了什麼、影響哪些畫面」；不寫進手冊
- 還原資料狀態（`prep_state.py restore`／`diff` 確認）
- PDF 是二進位大檔，**不要預設放進程式碼 repo**；問使用者要不要放 `docs/`
- 工作資料夾保留 `present.config.json`、`shots.plan.mjs`、`deck_content.py`，介面改版時重跑即可
