# 操作影片（操作說明／功能展示的 MP4 輸出）

操作說明與功能展示除了 16:9 簡報 PDF，也可以輸出成**有字卡與字幕的操作影片**（MP4，1920×1080）。
格式在 Phase 0 選：**簡報 PDF／影片／兩者都要**（`prompts.md` §0 第三題）。其他用途沒有影片格式。

| | 操作說明影片 | 功能展示影片 |
|---|---|---|
| 給誰 | 接手後台的人；自學、交接、新人訓練 | 決策者、demo、轉傳給沒參加會議的人 |
| 一章 | 一條流程 | 一個重點功能 |
| 章節字卡 | 流程名 | 功能名＋一句「這能幫你做什麼」（`v.chapter(名, 一句話)`） |
| 字幕 | 每一步都有，帶步驟編號 | 2～4 步、不編號；不教每個欄位 |
| 鏡頭 | 固定全景（要看得到東西在畫面哪裡） | **會動**：每一步推近到要操作的地方、做完拉回（zoom in／out），貝茲緩動 |
| 錄影解析度 | `--dsf 1.2`（預設，1920×1080） | **`--dsf 1.8`**（2880×1620，推近 1.5 倍後還是原生解析度） |
| 長度 | 一支 ≤ 10 分鐘；超過就拆（一支一組流程） | 1～3 分鐘 |

**一個用途一支影片**，不像 PDF 合成一份（讀者與節奏不同）。同時選了 PDF 和影片：P0～P3 共用（同一份大綱、同一批流程），
截圖和錄影分開跑。

## 架構

```
video.plan.mjs ─► record.mjs ─► raw.mkv ＋ events.jsonl ＋ session.json ─► video_post.py ─► MP4 ＋ SRT ＋ sheet.png
                  （網頁，主要）                                              （快轉、凍結、字卡、字幕、章節）
record_desktop.py（桌面／computer use，退路）─┘
```

- **`scripts/record.mjs`**（網頁，預設）：沿用截圖的登入與元素查找（`lib.mjs`），照計畫檔操作，畫面上有游標、點擊圈、
  逐字輸入；游標沿**貝茲弧線**移動、慢 → 快 → 慢（`scripts/motion.mjs`），不走直線。
  用 Chrome screencast 錄 1920×1080（視窗 1600×900 × `--dsf 1.2`），每一步的字幕時間精確到格。
  可重跑：介面改版後改計畫檔重錄，不必重新手動操作。headless 在背景跑，不佔用桌面。
- **`scripts/record_desktop.py`**（退路）：ffmpeg 錄桌面視窗／螢幕／區域，給**瀏覽器以外的畫面**，或真的要用 agent 的
  桌面操作工具（computer use）操作的情況。範圍內所有東西都會錄進去，目前只支援 Windows。
- **`scripts/video_post.py`**（後製，兩種錄法共用）：
  - **太慢**（等查詢、AI 回覆、computer use 思考）：畫面靜止超過 1.2 秒壓成 0.6 秒；超過 4 秒壓成 1.2 秒並在右上角標
    「快轉 ▶▶ 略過 N 秒」。只在一小塊轉圈的載入圖示也算靜止
  - **太快**（腳本瞬間點完、computer use 動作瞬間完成）：每一步前把「動作前」那一格停 1～3 秒，字幕與要點的位置（藍圈）
    先出現，讀得完才動；字數多停久一點（`--cps` 每秒字數，預設 5）
  - **鏡頭推近與拉回**（功能展示預設開，`scripts/video_zoom.py`）：每一步在讀字幕的停格裡推近 1.5 倍到要操作的地方，
    點下去、打完字才拉回全景看結果。接下來的變化都還在近景裡（同一張表單連續填欄位）就留在近景、跟著游標橫移到下一步；
    一有大變化跑到近景外（彈出視窗、換頁、列表更新）就拉回。推近、拉回、橫移都用 cubic-bezier 緩動（慢 → 快 → 慢）。
    點擊圈跟著畫面一起放大；字幕、字卡、快轉標示固定不動
  - 片頭（用途、App、租戶、製作日）→ 章節字卡（PART 01…）→ 內容 → 片尾（AI GO、Urfit），品牌色同簡報（`brand.md`）
  - MP4 內嵌章節（播放器可跳章）；另存同名 `.srt`；`--dir/sheet.png` 成片總表（GV 用）；`--dir/edit.json` 剪輯表
  - 檔名照規則：`AI GO 租戶名 App名 操作說明 YYYYMMDD.mp4`（租戶名、App 名錄影時自動取得）；拆多支加 `--part "1 新增與查詢"`

需要：ffmpeg（skill 目錄 `npm install` 會裝 `ffmpeg-static`；或 PATH 上的 ffmpeg、環境變數 `FFMPEG`）、Pillow、Chrome。

## 流程

```
Phase 0（選了影片格式）→ P0 需求確認 → P1 探勘 → P2 大綱＋分鏡 ═G1═ → P3 準備資料
→ V1 寫錄影計畫 → V2 錄影 → V3 後製 ═GV 成片檢查═ → V4 交付與收尾
```

P0～P3 照 `workflow.md`，差別：

- **P0**：多問一句「影片給誰看、在哪裡播（會議投影／LINE 轉傳／內訓）」→ 決定長度與要不要拆
- **P2 大綱要附分鏡**（`templates/outline.example.md`「影片分鏡」）：每支影片的章節、每章的步驟字幕、預估長度。
  分鏡經使用者核准（G1）才開錄
- **P3**：錄影會真的改資料——跟截圖一樣先備份（`prep_state.py backup`），只用測試資料，錄完還原

### V1 寫錄影計畫

`cp <skill>/templates/video.plan.example.mjs video.plan.mjs`，照分鏡改（一支影片一個計畫檔，例 `video.manual.plan.mjs`、
`video.showcase.plan.mjs`）。API：

| 呼叫 | 做什麼 |
|---|---|
| `v.chapter(名, 一句話?)` | 章節字卡；功能展示第二行放「這能幫你做什麼」 |
| `v.go(route, 字幕?)` | 開頁面，載入完才出字幕 |
| `v.click(spec, 字幕)` | 游標移過去 → 字幕（停住）→ 點擊圈 → 點 |
| `v.type(spec, 文字, 字幕, {enter})` | 點欄位、清空、逐字輸入 |
| `v.select(spec, 值, 字幕)` | `<select>` 選值（值或選項文字） |
| `v.fill(spec, 值, 字幕)` | 直接填值（日期、時間這類鍵盤打不準的欄位，例 `"2026-12-01"`） |
| `v.say(字幕, spec?)` | 只講解不點；給 spec 會圈出那個元素 |
| `v.scroll(spec, 字幕?)`／`v.waitFor(spec)`／`v.hold(ms)` | 捲動／等元素出現／停一下 |
| `v.s` | `lib.mjs` 的 session（`T()`、`F()`、`get`、`run`、`p`…），計畫 API 沒有的事用它 |

spec 可以是 CSS 選擇器字串（取第一個），或截圖用的 spec 物件（`screenshot-guide.md`「找元素」），都會穿過 shadow DOM。

跨 App 的流程（例：業務管理「開立合約」→ 合約管理）：開新分頁的連結先用 `v.s.run` 拿掉 `target`，讓它在同一頁打開
（錄影只錄一個分頁）；片名預設取錄完當下的頁面標題，跨 App 時在 `present.config.json` 設 `app_name`。

**字幕寫法**（`writing-guide.md` 的語氣規則全部適用）：

- 一句一個動作、**24 字內**：做什麼＋會怎樣（「按『儲存』，新訂單排到列表最上面」）
- 寫在畫面上看得到的字（按鈕、分頁、欄位名照抄），不寫開發用語、不寫設計理由
- 結果要有依據（G3）：字幕說「會寄通知給客人」，就要查得到程式碼或實測；查不到就不寫
- 等待照實等（查詢、AI 回覆），不要為了短片跳過——後製會快轉並標出略過幾秒

### V2 錄影

```bash
node <skill>/scripts/record.mjs --config present.config.json --plan video.manual.plan.mjs --out video/manual
node <skill>/scripts/record.mjs --config present.config.json --plan video.showcase.plan.mjs --out video/showcase --dsf 1.8
```

- **功能展示加 `--dsf 1.8`**：後製會推近鏡頭，錄 2880×1620 推近後才清楚。用預設 1.2 錄也能後製，只是近景會稍微糊
- 計畫中斷（找不到元素、等不到結果）會照樣存下錄到的部分並回傳 1：看最後幾秒的畫面修計畫重錄
- 錄影中發現 bug：跟截圖同一套規則（`workflow.md` P4「截圖中發現異常」）——確認是 bug 就修好上線、重錄，不必徵詢

### V3 後製

```bash
python <skill>/scripts/video_post.py --dir video/manual --purpose 操作說明 [--subtitle "示範帳號：店長"]
python <skill>/scripts/video_post.py --dir video/showcase --purpose 功能展示
```

可調：`--idle`（幾秒以上算靜止，預設 1.2）、`--cps`（字幕每秒字數，預設 5，讀者年紀大或字幕長就調低）、
`--no-intro`／`--no-outro`、`--keep-head`（保留第一個字幕之前的畫面）、
`--zoom auto|on|off`（鏡頭推近；auto＝功能展示開、操作說明關）、`--zoom-scale`（推近幾倍，預設 1.5）。

### GV 成片檢查（不能跳）

打開 `video/…/sheet.png`（成片平均取 48 格），再抽看每章開頭與每個快轉處，逐項確認：

- [ ] 每個停住的畫面是**動作前**：游標或藍圈在要點的東西上，還沒點下去
- [ ] 字幕和畫面一致：說「排到最上面」的那格真的在最上面；字幕沒有被切掉或擠成兩行
- [ ] 快轉標示只出現在等待，沒有把重要的變化快轉掉
- [ ] （功能展示）推近時要操作的東西在畫面裡、沒被字幕蓋住；動作的結果（新的一列、彈出視窗、查詢結果）是在全景看到的，
      沒有停在近景看不到；沒有一直推進拉出讓人頭暈——太頻繁就調低 `--zoom-scale`，或那一支用 `--zoom off`
- [ ] 沒有密鑰、真實個資、和這支 app 無關的視窗或通知（桌面錄影特別注意）
- [ ] 片頭的 App 名、租戶名、製作日正確；長度符合用途（操作說明一支 ≤ 10 分鐘、功能展示 1～3 分鐘）

有問題：字幕寫錯→改計畫檔重錄；節奏不對→調 `--idle`／`--cps` 重跑後製（不用重錄）；鏡頭不對→調 `--zoom`／`--zoom-scale` 重跑後製。

### V4 交付與收尾

- 交 MP4（＋同名 `.srt` 給要自己加字幕或翻譯的人）；PDF 和影片都選了就一起交
- 還原資料（`prep_state.py restore`），確認測試資料清乾淨
- 檔案大小：1080p 一般每分鐘 1～3 MB；超過 200 MB 先問使用者

## 桌面錄影（computer use 或瀏覽器以外的畫面）

網頁一律優先用 `record.mjs`。只有畫面不在瀏覽器裡，或必須由 agent 的桌面操作工具動手時才用：

```bash
python <skill>/scripts/record_desktop.py start --dir video/desk --window "視窗標題"   # 放背景跑
python <skill>/scripts/record_desktop.py chapter --dir video/desk "新增一張訂單"
python <skill>/scripts/record_desktop.py say --dir video/desk "點「新增」" --xy 812,440    # 每個動作「之前」記
#   … 用桌面操作工具做那個動作 …
python <skill>/scripts/record_desktop.py stop --dir video/desk
python <skill>/scripts/video_post.py --dir video/desk --purpose 操作說明 --tenant 租戶名 --app App名
```

- **`say` 放在動作之前**（建議）：後製把字幕對到下一次畫面變化的前一格，最準
- 忘了記才用 `did`（動作之後）：後製往回找動作前的思考停頓；動作後若有超過 2.5 秒的連鎖變化，可能對錯，GV 要特別看
- `--xy` 是螢幕實體像素；截圖有縮放時加 `--scale`
- computer use 的思考時間（每步 3～10 秒）後製會自動快轉，不必刻意加快
- 開錄前關掉通知與不相干的視窗；`--window` 只錄那個視窗的範圍，但蓋在上面的東西一樣會被錄到
