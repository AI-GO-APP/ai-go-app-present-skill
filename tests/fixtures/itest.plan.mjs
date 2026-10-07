// tests/itest_runner.test.mjs 用的整合測試計畫（對 tests/fixtures/itest-app.html 跑）
export const labels = { smoke: "冒煙測試", sweep: "UI 巡檢", e2e: "端到端流程" };

export default {
  smoke: async (t) => { await t.smoke(); },
  sweep: async (t) => { await t.sweep({ route: "#/", name: "home", area: "總覽" }); },
  e2e: async (t) => {
    await t.case({ id: "E2E-01", area: "訂單", title: "名稱空白不能建立", expect: "提示「請輸入名稱」，列表不變", mutates: true }, async (c) => {
      await c.go("#/orders");
      await c.click({ sel: "button", text: "建立" });
      await c.expectText("請輸入名稱");
      c.note("顯示「請輸入名稱」，沒有建立空白訂單");
    });
    await t.case({ id: "E2E-02", area: "訂單", title: "建立訂單後列表出現", expect: "列表多一筆「測試客人」", mutates: true }, async (c) => {
      await c.go("#/orders");
      await c.type({ sel: "#name" }, "測試客人");
      await c.click({ sel: "button", text: "建立" });
      await c.expectVisible({ sel: ".row", text: "測試客人" });
      c.note("列表最下面出現「A002 測試客人」");
    });
    await t.case({ id: "E2E-03", area: "總覽", title: "刪除鈕沒有被巡檢點到", expect: "資料完整" }, async (c) => {
      await c.go("#/");
      await c.expectText("資料完整");
      await c.expectNoText("已全部刪除");
    });
    await t.case({ id: "E2E-04", area: "訂單", title: "找不到的按鈕要記未通過", expect: "有「匯出」按鈕" }, async (c) => {
      await c.go("#/orders", 300);
      await c.expectVisible({ sel: "button", text: "匯出" }, "訂單頁沒有「匯出」按鈕", { timeout: 500 });
    });
    await t.skip({ id: "E2E-05", area: "付款", title: "線上付款", reason: "會真的扣款，改由人工在測試商店驗" });
  },
};
