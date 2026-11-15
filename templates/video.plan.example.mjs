/**
 * 錄影計畫範例：複製成工作資料夾的 video.plan.mjs（一支影片一個計畫檔）再改。
 *   node <skill>/scripts/record.mjs --config present.config.json --plan video.plan.mjs --out video/manual
 *   python <skill>/scripts/video_post.py --dir video/manual --purpose 操作說明
 *
 * 規則（references/video.md 有完整說明）：
 *  - 照 G1 核准的分鏡寫：一個 chapter＝一條流程（操作說明）或一個功能（功能展示）
 *  - 字幕一句一個動作、24 字內：做什麼＋會怎樣（「按『儲存』，新訂單排到最上面」），不寫開發用語
 *  - click／type／select 的字幕在「游標到了、還沒點」那一刻出現，後製會在那裡停住讓人讀完
 *  - 等待（查詢、AI 回覆）照實等：後製會自動快轉並標「略過 N 秒」，不要為了短片故意省略等待
 *  - 只動測試資料；會對外送出（寄信、推播、扣款）的動作不錄。錄完照 P3 還原
 *  - spec：CSS 選擇器字串，或截圖用的 spec 物件（v.s.T("按鈕字")、v.s.F("欄位標籤")…），都會穿過 shadow DOM
 */
export default async (v) => {
  const { T, F } = v.s;

  // ── 操作說明：一條流程一章，每一步都有字幕 ──
  await v.chapter("新增一張訂單");
  await v.go("/orders", "打開「訂單」，列出目前所有訂單");
  await v.click(T("新增訂單"), "點右上角「＋ 新增訂單」");
  await v.type({ sel: "input", within: F("客戶名稱") }, "測試客戶 A", "輸入客戶名稱");
  await v.select({ sel: "select", within: F("品項") }, "冷萃茶包", "選擇品項");
  await v.type({ sel: "input", within: F("數量") }, "6", "填數量");
  await v.click(T("儲存"), "按「儲存」，新訂單排到列表最上面");

  await v.chapter("查詢訂單");
  await v.type({ sel: "input[placeholder*=搜尋]" }, "測試客戶", "在搜尋框輸入客戶名稱");
  await v.click(T("查詢"), "按「查詢」");
  await v.waitFor({ sel: "tr", text: "測試客戶 A" }, { timeout: 30000 });   // 實際等多久就等多久，後製會快轉
  await v.say("只剩下這位客戶的訂單", { sel: "table" });                   // 只講解不點：圈出表格
  await v.hold(1500);

  // ── 功能展示：一個功能一章，第二行寫「這能幫你做什麼」，每章 2～4 步、不教每個欄位 ──
  //    錄的時候加 --dsf 1.8：後製會在每一步推近鏡頭到要操作的地方、做完拉回（references/video.md）
  // await v.chapter("AI 自動分類來信", "新來的信件自動標上類別，客服不用逐封判斷");
  // await v.go("/inbox", "收件匣每一封都標好類別");
  // await v.say("點類別就能只看這一類", T("退換貨", "button"));
};
