/**
 * 截圖計畫範例：複製成工作資料夾的 shots.plan.mjs 再改。
 * 每個群組是一個 async 函式，拿到 session s（見 scripts/lib.mjs）。
 *
 * 規則（references/screenshot-guide.md 有完整說明）：
 *  - 大功能（整頁的主畫面）：full 截圖 ＋ marks 圖解標號（1、2、3…），標號順序＝說明順序
 *  - 操作步驟：只截局部（specs 取聯集），不要整頁
 *  - 每個會改資料的動作，拍完立刻復原（模式切回、選單關掉、表單取消）
 *  - 每一張都包在 s.step() 裡：一張失敗不影響其他張，失敗會留 _fail-*.png
 */
export default {
  // 1. 總覽頁：全頁＋圖解
  overview: async (s) => {
    await s.go("/", 3500);
    await s.step("overview-full", () => s.shot("overview-full", null, { full: true, marks: [
      { n: 1, spec: { sel: "nav, aside, .side, .sidebar", pick: "big" } },
      { n: 2, spec: s.T("更新數據") },
    ] }));
    // 分頁切換後再拍
    await s.step("overview-tab2", async () => { await s.click(s.T("第二個分頁")); await s.shot("overview-tab2", null, { full: true }); });
  },

  // 2. 核心工作頁：先拍局部，再開一筆資料拍全景
  messages: async (s) => {
    await s.go("/messages", 3500);
    await s.step("list-head", () => s.shot("list-head", { sel: ".mc-list-head" }, { pad: 6 }));
    // 兩個元素取聯集：列表前兩筆
    await s.step("list-items", () => s.shot("list-items", [{ sel: "button.conv", idx: 0 }, { sel: "button.conv", idx: 1 }], { pad: 4 }));
    await s.step("full", async () => {
      await s.click({ sel: "button.conv", text: "測試帳號名稱" }, 3500);
      await s.shot("messages-full", null, { full: true, marks: [
        { n: 1, spec: { sel: ".mc-list" } }, { n: 2, spec: { sel: ".chat-msgs" } }, { n: 3, spec: { sel: ".mc-profile" } },
      ] });
    });
    // <details> 收合的面板：先用 JS 打開再拍
    await s.step("detail-panel", async () => {
      await s.run(`const d = [...root.querySelectorAll("details.ai-src")].pop(); if (d) { d.open = true; d.closest(".msg-row").setAttribute("data-guide", "row"); }`);
      await s.sleep(400);
      await s.shot("detail-panel", { sel: "[data-guide=row]" }, { pad: 10, marks: [{ n: 1, spec: { sel: "details.ai-src summary" } }] });
    });
    // 依滑鼠座標定位的選單：一定用 mouseClick；只截選單本身
    await s.step("assign-menu", async () => {
      await s.mouseClick(s.T("指派給成員"), 1200);
      await s.shot("assign-menu", [{ sel: "button,div", text: "移至未指派" }, { sel: "button,div", text: "最後一個成員名" }], { pad: 10, scroll: false });
      await s.p.keyboard.press("Escape"); await s.p.mouse.click(1000, 450); await s.sleep(400);
    });
    // 會改狀態的操作：拍完立刻復原，並確認真的復原了
    await s.step("human-mode", async () => {
      await s.click(s.T("開始人工回應"), 2500);
      await s.shot("human-mode", { sel: ".chat-input" }, { pad: 6, block: "end" });
      await s.click(s.T("對話結束，轉回 AI 自動回應"), 2500);
      if (await s.get(s.T("對話結束，轉回 AI 自動回應"))) throw new Error("沒有復原成 AI 模式，請手動處理");
    });
  },

  // 3. 設定頁：逐欄局部截圖（F(標籤開頭) 抓 .field）
  settings: async (s) => {
    await s.go("/settings", 3500);
    await s.step("settings-full", () => s.shot("settings-full", null, { full: true, marks: [
      { n: 1, spec: s.T("全域設定") }, { n: 2, spec: s.F("AI 模型") },
    ] }));
    const fields = [
      ["set-switches", [s.F("啟用 AI 自動回覆"), s.F("顧客進線時由 AI 優先回覆")]],
      ["set-model", [s.F("AI 模型"), s.F("備援模型")]],
      ["set-persona", [s.F("客服人設與說明")]],
    ];
    for (const [n, specs] of fields) await s.step(n, () => s.shot(n, specs, { pad: 10 }));
    // 先切成另一個選項拍，再切回原值（不要按儲存）
    await s.step("set-hours-custom", async () => {
      await s.click(s.T("指定時段"), 700); await s.shot("set-hours-custom", s.F("回應時段"), { pad: 10 });
      await s.click(s.T("全天候"), 500);
    });
    // 視窗（modal）只截視窗本身
    await s.step("modal", async () => {
      await s.click(s.T("新增 FAQ"), 1200); await s.shot("faq-modal", { sel: ".modal" }, { pad: 0, scroll: false });
      const c = await s.get(s.T("取消")); if (c) await s.click(s.T("取消"), 500);
    });
  },

  // 4. 測試對話類：送一句、等 AI 回、內層捲回頂端再拍
  test_chat: async (s) => {
    await s.go("/settings", 3000);
    await s.step("test-chat", async () => {
      await s.click(s.T("測試對話"), 1500);
      await s.type({ sel: ".test-card input", pick: "first" }, "一句典型的客人問題");
      await s.click({ sel: ".test-card button", text: "送出" }, 1500);
      for (let i = 0; i < 60; i++) { if (!(await s.get({ sel: ".test-card .muted-line", text: "思考中" }))) break; await s.sleep(1000); }
      await s.run(`const c = root.querySelector(".test-card"); c.scrollIntoView({ block: "start" }); [...c.querySelectorAll("*")].forEach((e) => { if (e.scrollHeight > e.clientHeight + 4) e.scrollTop = 0; });`);
      await s.sleep(600);
      await s.shot("test-chat", { sel: ".test-card" }, { pad: 6, scroll: false });
    });
  },
};
