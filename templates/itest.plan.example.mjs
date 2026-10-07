/**
 * 整合測試計畫範例：複製成工作資料夾的 itest.plan.mjs 再改（references/integration-test.md）。
 *
 *   node <skill>/scripts/itest.mjs --config present.config.json --list    # 列案例（GT1 給使用者核准）
 *   node <skill>/scripts/itest.mjs --config present.config.json           # 全部跑
 *   node <skill>/scripts/itest.mjs --config present.config.json e2e       # 只重跑一組
 *
 * 規則：
 *  - 編號（id）就是報告上的編號：SMK／SWP 由腳本產生；自己寫的用 E2E-01、FRM-01、ROL-01…
 *  - expect 寫預期結果，要有依據（規格、程式碼、線上設定）；basis 記依據（不印進報告，判讀用）
 *  - 會改資料的流程 mutates: true，只用測試資料（名稱前綴 IT-），跑完清掉
 *  - 會對外送出（LINE 推播、Email、付款）的不測，用 t.skip 寫原因
 *  - 通過時用 c.note() 寫一句看到什麼——報告的「結果」欄就是這句
 */
const TAG = "IT-" + new Date(Date.now() + 8 * 3600e3).toISOString().slice(0, 10).replace(/-/g, "");   // 測試資料前綴

/** 報告上的群組名稱（沒給就用預設：冒煙測試、UI 巡檢、端到端流程、表單驗證、權限與角色） */
export const labels = { smoke: "冒煙測試（每頁載入）", sweep: "UI 巡檢（逐一點擊）", e2e: "端到端流程", form: "表單驗證" };

export default {
  // 1. 冒煙：present.config.json 的 routes 每一頁都打開一次
  smoke: async (t) => {
    await t.smoke();
  },

  // 2. UI 巡檢：每個畫面狀態一個 sweep。會改資料的按鈕（刪除、儲存、送出…）自動略過
  sweep: async (t) => {
    await t.sweep({ route: "/", name: "總覽" });
    await t.sweep({ route: "/orders", name: "訂單列表", area: "訂單" });
    // 分頁裡的內容：prepare 先切到那個分頁，再巡檢
    await t.sweep({ route: "/settings", name: "設定-AI", area: "設定", prepareText: "切到「AI 設定」分頁",
      prepare: async (c) => { await c.click(c.T("AI 設定")); } });
    // 這頁有不想點的（例：「重新產生」會花錢）
    await t.sweep({ route: "/reports", name: "報表", skip: ["重新產生"] });
  },

  // 3. 端到端：核心流程從頭到尾，結果對回後端
  e2e: async (t) => {
    await t.case({ id: "E2E-01", area: "訂單", title: "建立訂單後列表出現", mutates: true,
      expect: "按「建立」後出現成功提示，列表最上面是新訂單，後端查得到", basis: "src/pages/Orders.tsx、actions/create_order.py" }, async (c) => {
      await c.go("/orders");
      await c.click(c.T("新增訂單"));
      await c.type({ sel: "input[name=customer]" }, `${TAG} 測試客人`);
      await c.type({ sel: "input[name=amount]" }, "1200");
      await c.click(c.T("建立"));
      await c.expectText("已建立");
      await c.expectVisible({ sel: "tr", text: `${TAG} 測試客人` }, "列表沒有出現剛建立的訂單");
      const r = await c.api(`/api/v1/apps/your-app/orders?customer=${encodeURIComponent(TAG)}`);   // 對回後端（路徑照 app 實際的）
      c.expect(r.status === 200 && JSON.stringify(r.data).includes("1200"), "後端查不到這筆訂單，或金額不是 1200");
      c.note(`列表最上面出現「${TAG} 測試客人」，金額 1,200，後端資料一致`);
    });

    await t.case({ id: "E2E-02", area: "訂單", title: "搜尋找得到剛建立的訂單", expect: "輸入客人名稱只剩那一筆" }, async (c) => {
      await c.go("/orders");
      await c.type({ sel: "input[type=search]" }, TAG, { enter: true });
      await c.expectVisible({ sel: "tr", text: TAG });
      const rows = await c.run(`return root.querySelectorAll("tbody tr").length`);
      c.expect(rows === 1, `搜尋結果應該只有 1 筆，實際 ${rows} 筆`);
      // 能用但不合理 → 記疑慮、繼續跑（例：計數和列表對不上）
      const count = await c.run(`return (root.querySelector(".result-count")?.textContent || "").trim()`);
      if (count && !count.includes("1")) c.doubt(`筆數寫「${count}」，和列表的 1 筆對不上`, { sel: ".result-count" });
      c.note("只剩剛建立的那一筆，筆數顯示 1");
    });

    await t.case({ id: "E2E-03", area: "訂單", title: "刪除測試訂單", mutates: true, expect: "確認後列表與後端都沒有這筆" }, async (c) => {
      await c.go("/orders");
      await c.click({ sel: "tr", text: TAG });
      c.acceptDialogs();                                     // 這個 app 用原生 confirm 確認刪除
      await c.click(c.T("刪除"));
      await c.expectGone({ sel: "tr", text: TAG }, "刪除後列表還看得到");
      c.note("確認刪除後列表立即消失");
    });

    // 不測的要寫原因，報告最後一頁會列出來
    await t.skip({ id: "E2E-04", area: "訂單", title: "付款連結實際付款", reason: "會真的扣款；請在金流測試模式另外驗" });
    await t.skip({ id: "E2E-05", area: "通知", title: "LINE 出貨通知", reason: "會推播給真實客人；只在使用者的測試 LINE 帳號手動驗" });
  },

  // 4. 表單驗證：擋得住、訊息看得懂
  form: async (t) => {
    const cases = [
      ["FRM-01", "客人名稱空白", "", "1200", "請輸入客人名稱"],
      ["FRM-02", "金額是負數", `${TAG} 驗證`, "-5", "金額必須大於 0"],
      ["FRM-03", "金額不是數字", `${TAG} 驗證`, "abc", "請輸入數字"],
    ];
    for (const [id, title, name, amount, msg] of cases) {
      await t.case({ id, area: "訂單", title, expect: `擋下來並提示「${msg}」，不建立訂單`, allowStatus: [400, 422] }, async (c) => {
        await c.go("/orders");
        await c.click(c.T("新增訂單"));
        if (name) await c.type({ sel: "input[name=customer]" }, name);
        await c.type({ sel: "input[name=amount]" }, amount);
        await c.click(c.T("建立"));
        await c.expectText(msg, `沒有提示「${msg}」`);       // 預期中的錯誤訊息：自動放行，不算疑慮
        await c.expectNoText("已建立");
        c.note(`顯示「${msg}」，沒有建立`);
        await c.click(c.T("取消"));
      });
    }
  },
};
