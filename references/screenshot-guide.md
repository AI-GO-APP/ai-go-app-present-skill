# 截圖指引

## 基本設定

- 視窗 **1600×900、deviceScaleFactor 2**（輸出 3200×1800）：放進 16:9 頁面縮小後文字仍清楚
- 登入：
  - **runtime**（已安裝在租戶的 app）：`POST /api/v1/auth/login` 換 token → `localStorage.token` → 開 `{base}/runtime/{slug}#/{route}`
  - **preview**（developer 平台預覽頁）：PAT 寫進 `localStorage.dev_access_token` → 開預覽網址
- AI GO 的 App **掛在 shadow DOM**：`document.querySelector` 找不到東西，要從 shadow root 找（`lib.mjs` 的 `ROOT`／`FIND` 已處理）

## 截圖種類

| 種類 | 用在 | 做法 |
|---|---|---|
| 全頁＋圖解 | 大功能主畫面、頁面全景 | `shot(name, null, { full: true, marks: [...] })` |
| 局部 | 操作步驟、設定欄位 | `shot(name, spec 或 [spec, spec])`，取聯集＋pad |
| 視窗 | 新增／編輯表單 | `shot(name, { sel: ".modal" }, { pad: 0, scroll: false })` |
| 無標號全頁 | 其他頁面概覽 | `shot(name, null, { full: true })` |

`shots.json` 記每張圖的寬高與標號座標（CSS px，相對截圖左上角）；`deck_kit.Deck.shot()` 依縮放比例畫出藍框與編號。

## 找元素（spec）

```js
{ sel: "button", text: "開始人工回應" }        // 含文字的按鈕（預設取最內層）
{ sel: ".field", starts: "AI 模型" }            // 第一個 label 以此開頭的設定欄位（s.F("AI 模型")）
{ sel: ".pf-sec", text: "標籤", within: { sel: ".mc-profile" } }   // 在某區塊內找
{ sel: "button.conv", idx: 0 }                  // 第幾個
{ sel: "nav, aside", pick: "big" }              // 文字最多的（外層容器）
```

## 技巧與陷阱

1. **依滑鼠座標定位的選單**（PopMenu、右鍵選單）：用 `mouseClick`。程式 `el.click()` 沒有 clientX/Y，選單會出現在左上角。
2. **只截選單／視窗本身**：用選單內第一個與最後一個項目取聯集；不要和觸發按鈕聯集（中間會夾到不相關的畫面）。
3. **收合的區塊**（`<details>`、可收合面板）：先用 `s.run()` 打開，再截。
4. **內層捲動**：截圖前把容器 `scrollTop` 設好（例：測試對話要看第一則回覆 → 捲回頂端），否則會切在一半。
5. **比視窗高的元素**：clip 不能超出視窗。改截局部，或暫時把 viewport 加高。
6. **等 AI 回覆**：輪詢「思考中」字樣消失，再多等 1 秒讓來源／標籤渲染完。
7. **會改資料的操作**（切換模式、開關）：拍完立刻切回，並**確認真的切回**（找不到原本的按鈕才算成功）。不要按「儲存」。
8. **點開資料會有副作用**（未讀歸零、標為已讀）：拍前 `prep_state.py backup`，拍後 `restore`。
9. **空狀態**：拍之前用 app 的 action 預填示範資料；拍完視情況清掉或保留（示範租戶可保留，記錄下來）。
10. **密鑰**：渠道設定、金鑰設定頁逐張檢查。已連接的帳號通常不回顯密鑰，但新增表單如果預填了就不能用。
11. **挑有代表性的資料**：例如 AI 來源面板挑「核對通過、有引用」的那則，不要挑錯誤或空的那則當教學範例（除非那頁在教錯誤）。
12. **並排的兩張圖**：拍的時候就考慮版面（兩張各 ≤ 722 寬），太細長的圖（例：側欄）單獨放一欄。

## 截圖就是 UI 驗收

拍照時看到的每一個異常都先當 bug 查：
- 面板永遠顯示「尚無資料」→ 可能是前端讀錯回傳形狀（例：呼叫函式已經拆過信封，元件又拆一次）
- 欄位顯示 `['…']` → 後端把清單存成字串
- 區塊只有標題沒有內容 → 條件判斷漏了某種情況

修好、照 app 的發布規則上線後，重拍那幾張。這類 bug 單元測試常常測不到（測的是 action，不是畫面）。

## 驗收

```bash
python scripts/contact_sheet.py shots/*.png --out disc/sheet     # 每 9 張一張，左上角標檔名
```

逐張看過 `workflow.md` 的 G2 清單。有問題的單張再開大圖確認。
