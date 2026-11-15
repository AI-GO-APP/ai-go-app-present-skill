// record.mjs 的測試計畫：對 tests/fixtures/video-demo.html（不登入，mode=url）
export default async (v) => {
  await v.chapter("新增一張訂單");
  await v.go("/video-demo.html", "打開訂單中心，畫面列出目前所有訂單");
  await v.click("#add", "點右上角「＋ 新增訂單」");
  await v.type("#cust", "山角烘焙坊", "輸入客戶名稱");
  await v.select("#item", "冷萃茶包", "選擇品項");
  await v.type("#qty", "6", "填數量");
  await v.click("#save", "按「儲存」，新訂單出現在列表最上面");
  await v.chapter("查詢訂單", "輸入客戶名稱就能找到他的所有訂單");
  await v.type("#q", "山角", "在搜尋框輸入客戶名稱");
  await v.click("#find", "按「查詢」，系統約 5 秒後回結果");
  await v.waitFor({ sel: "#spin", text: "查詢中" }, { timeout: 3000 }).catch(() => {});
  await v.hold(5600);
  await v.say("只剩下符合的訂單", "table");
  await v.hold(1200);
};
