/**
 * 整合測試執行器：規則單元測試（itest_core.mjs）＋ 對本機測試頁實跑一次（需要 Chrome，找不到就略過）。
 * 執行：node --test tests/
 */
import test from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import { spawnSync } from "node:child_process";
import { fileURLToPath, pathToFileURL } from "node:url";
import {
  classify, isDangerous, eventFindings, scanFindings, reaction, describeSweep, mergeResults, reviewSkeleton, safeId, GARBAGE,
} from "../scripts/itest_core.mjs";

const HERE = path.dirname(fileURLToPath(import.meta.url));
const SKILL = path.resolve(HERE, "..");

test("classify：fail > doubt > pass，info 不影響", () => {
  assert.equal(classify([]), "pass");
  assert.equal(classify([{ level: "info" }]), "pass");
  assert.equal(classify([{ level: "doubt" }, { level: "info" }]), "doubt");
  assert.equal(classify([{ level: "doubt" }, { level: "fail" }]), "fail");
});

test("isDangerous：會改資料、對外送出的不點", () => {
  for (const t of ["刪除", "儲存設定", "送出", "確定", "Delete", "登出", "匯出 CSV", "標為已讀", "對話結束，轉回 AI 自動回應"]) assert.ok(isDangerous(t), t);
  for (const t of ["全部", "新增訂單", "下一頁", "設定", "取消", "查看詳情"]) assert.ok(!isDangerous(t), t);
  assert.ok(isDangerous("同意條款", ["同意"]));
});

test("GARBAGE 規則：技術字樣抓得到、正常中文不誤判", () => {
  const hit = (t) => GARBAGE.filter((g) => new RegExp(g.src, g.flags).test(t)).map((g) => g.label);
  assert.deepEqual(hit("本月營收：undefined 元"), ["畫面出現 undefined"]);
  assert.deepEqual(hit("金額：NaN 元"), ["畫面出現 NaN"]);
  assert.ok(hit("TypeError: x is not a function").includes("畫面露出程式錯誤名稱"));
  assert.ok(hit('{"detail":"Not Found"}').includes("畫面露出 JSON 錯誤原文"));
  assert.ok(hit("你好 {{name}}").includes("畫面出現沒有代換的變數"));
  assert.deepEqual(hit("訂單 A001 已完成，金額 1,200 元"), []);
  assert.deepEqual(hit("Nancy 的訂單"), []);          // 單字邊界：不把 Nancy 當 NaN
});

test("eventFindings：分級、忽略與放行", () => {
  const f = eventFindings([
    { type: "pageerror", text: "boom\n  at x" },
    { type: "console", text: "Failed to load resource: 404" },
    { type: "console", text: "something bad" },
    { type: "http", status: 500, url: "https://x.ai-go.app/api/v1/orders?page=1", method: "POST" },
    { type: "http", status: 404, url: "https://x/favicon.ico" },
    { type: "http", status: 422, url: "https://x/api/v1/orders" },
    { type: "network", url: "https://x/a.js", error: "net::ERR_ABORTED" },
    { type: "network", url: "https://x/b.js", error: "net::ERR_FAILED" },
    { type: "dialog", text: "確定刪除？", accepted: false },
  ], { allowStatus: [422] });
  assert.deepEqual(f.map((x) => [x.kind, x.level]), [["pageerror", "fail"], ["console", "doubt"], ["http", "fail"], ["network", "doubt"], ["dialog", "info"]]);
  assert.match(f[2].text, /API 回應 500：POST \/api\/v1\/orders\?page=1/);
  assert.match(f[4].text, /已按取消/);
  assert.equal(eventFindings([{ type: "http", status: 403, url: "https://x/api" }])[0].level, "doubt");
  assert.equal(eventFindings([{ type: "console", text: "ResizeObserver loop" }], { ignoreConsole: ["ResizeObserver"] }).length, 0);
});

test("scanFindings／reaction／describeSweep", () => {
  const f = scanFindings({ items: [{ level: "doubt", label: "畫面出現 NaN", snippet: "NaN 元", mark: "1" }], blank: true, loading: true, overflow: 1700 }, { loadingSec: 8 });
  assert.deepEqual(f.map((x) => x.kind), ["text", "blank", "loading", "overflow"]);
  assert.equal(f[0].markSel, '[data-itest-mark="1"]');
  const a = { url: "u", h: 1, dialogs: 0 };
  assert.equal(reaction(a, { ...a, url: "v" }, 0), "換頁");
  assert.equal(reaction(a, { ...a, dialogs: 1 }, 0), "開啟視窗");
  assert.equal(reaction(a, { ...a, h: 2 }, 0), "畫面更新");
  assert.equal(reaction(a, a, 3), "送出讀取請求");
  assert.equal(reaction(a, a, 0), null);
  assert.equal(reaction(a, a, 0, "u"), "已在此頁");
  const d = describeSweep([{ label: "全部", reaction: "畫面更新" }], [{ label: "刪除" }]);
  assert.match(d, /點了 1 個/); assert.match(d, /略過 1 個.*「刪除」/);
});

test("mergeResults：重跑的群組整組取代、編號不能重複", () => {
  const old = { cases: [{ id: "A", group: "g1" }, { id: "B", group: "g2" }] };
  assert.deepEqual(mergeResults(old, [{ id: "C", group: "g2" }], ["g2"]).map((c) => c.id), ["A", "C"]);
  assert.throws(() => mergeResults(null, [{ id: "X" }, { id: "X" }], ["g"]), /重複/);
});

test("reviewSkeleton：補未判讀、重跑過要重判、修好的留 fixed 欄", () => {
  const cases = [{ id: "F", status: "fail", at: "t2" }, { id: "P", status: "pass", at: "t2" }, { id: "D", status: "doubt", at: "t1" }];
  const prev = { P: { run: "t1", status: "fail", judgement: "原本按了沒反應" }, D: { run: "t1", status: "doubt", judgement: "已判讀" } };
  const { review, todo } = reviewSkeleton(cases, prev);
  assert.deepEqual(todo, ["F"]);
  assert.equal(review.F.run, "t2");
  assert.equal(review.P.fixed, "");
  assert.equal(review.P.previous_judgement, "原本按了沒反應");
  assert.equal(review.D.judgement, "已判讀");                 // 沒重跑：保留
  assert.match(safeId("E2E 01/a"), /^E2E_01_a$/);
});

const chrome = [process.env.CHROME_PATH, "C:/Program Files/Google/Chrome/Application/chrome.exe",
  "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome", "/usr/bin/google-chrome", "/usr/bin/chromium"].filter(Boolean).find((p) => fs.existsSync(p));
const hasPuppeteer = fs.existsSync(path.join(SKILL, "node_modules", "puppeteer-core"));

test("實跑：本機測試頁", { skip: !(chrome && hasPuppeteer) && "沒有 Chrome 或 puppeteer-core", timeout: 240000 }, () => {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), "itest-"));
  const app = pathToFileURL(path.join(HERE, "fixtures", "itest-app.html")).href;
  fs.writeFileSync(path.join(dir, "present.config.json"), JSON.stringify({
    mode: "url", base: app, chrome, viewport: { w: 1280, h: 800, dsf: 1 }, out: "shots", tenant: "測試租戶", app_name: "訂單中心",
    routes: [["#/", "home"], ["#/orders", "orders"], ["#/broken", "broken"]],
    itest: { settle_ms: 500, route_wait_ms: 400, loading_wait_ms: 1000 },
  }));
  const run = (...a) => spawnSync(process.execPath, [path.join(SKILL, "scripts", "itest.mjs"), "--config", path.join(dir, "present.config.json"),
    "--plan", path.join(HERE, "fixtures", "itest.plan.mjs"), ...a], { encoding: "utf8", timeout: 220000 });

  const ls = run("--list");
  assert.equal(ls.status, 0, ls.stderr);
  assert.match(ls.stdout, /\| 冒煙測試 \| SMK-home \|/);
  assert.match(ls.stdout, /共 9 個案例/);

  const r = run();
  assert.equal(r.status, 0, r.stderr + r.stdout);
  const res = JSON.parse(fs.readFileSync(path.join(dir, "itest", "results.json"), "utf8"));
  const by = Object.fromEntries(res.cases.map((c) => [c.id, c]));
  const texts = (id) => by[id].findings.map((f) => f.text).join("\n");

  assert.equal(by["SMK-home"].status, "pass");
  assert.equal(by["SMK-broken"].status, "doubt");
  assert.match(texts("SMK-broken"), /undefined/);
  assert.match(texts("SMK-broken"), /console 錯誤：broken page render/);

  const sweepIssues = res.cases.filter((c) => c.id.startsWith("SWP-home-"));
  const t = (label) => sweepIssues.find((c) => c.title === `點「${label}」`);
  assert.equal(t("壞掉的按鈕")?.status, "fail", JSON.stringify(sweepIssues.map((c) => c.title)));
  assert.match(t("壞掉的按鈕").findings.map((f) => f.text).join(), /未攔截的例外/);
  assert.equal(t("顯示金額")?.status, "doubt");
  assert.match(t("顯示金額").findings.map((f) => f.text).join(), /NaN/);
  assert.doesNotMatch(t("顯示金額").findings.map((f) => f.text).join(), /偶發/);   // 重點一次也要抓到同一個問題
  assert.equal(t("沒反應")?.status, "doubt");
  assert.match(t("沒反應").findings.map((f) => f.text).join(), /沒有任何反應/);
  assert.ok(!t("全部") && !t("新增訂單") && !t("刪除全部") && !t("總覽"));
  assert.equal(by["SWP-home"].status, "pass");
  assert.match(by["SWP-home"].notes[0], /「新增訂單」（開啟視窗）/);
  assert.match(by["SWP-home"].notes[0], /略過 1 個.*「刪除全部」/);
  assert.ok(fs.existsSync(path.join(dir, "shots", `${t("顯示金額").shot}.png`)));
  const man = JSON.parse(fs.readFileSync(path.join(dir, "shots", "shots.json"), "utf8"));
  assert.ok(man[t("顯示金額").shot].marks.length >= 2, "點的元素與 NaN 都要標框");

  assert.equal(by["E2E-01"].status, "pass", texts("E2E-01"));       // 預期的錯誤訊息被 expectText 放行
  assert.equal(by["E2E-02"].status, "pass", texts("E2E-02"));
  assert.deepEqual(by["E2E-02"].steps, ["打開 #/orders", "在「#name」輸入「測試客人」", "點「建立」"]);
  assert.equal(by["E2E-03"].status, "pass", texts("E2E-03"));       // 巡檢沒按到刪除
  assert.equal(by["E2E-04"].status, "fail");
  assert.equal(by["E2E-04"].runs, 2);
  assert.match(texts("E2E-04"), /沒有「匯出」按鈕/);
  assert.equal(by["E2E-05"].status, "skip");

  const review = JSON.parse(fs.readFileSync(path.join(dir, "itest", "review.json"), "utf8"));
  for (const c of res.cases.filter((x) => x.status === "fail" || x.status === "doubt")) {
    assert.equal(review[c.id]?.run, c.at, c.id);
    assert.equal(review[c.id].judgement, "");
  }
  assert.match(r.stdout, /GT2：\d+ 個未通過／疑慮案例待判讀/);

  // 只重跑一組：其他組保留
  const r2 = run("e2e");
  assert.equal(r2.status, 0);
  const res2 = JSON.parse(fs.readFileSync(path.join(dir, "itest", "results.json"), "utf8"));
  assert.ok(res2.cases.some((c) => c.id === "SWP-home"));
  assert.equal(res2.meta.labels.sweep, "UI 巡檢");
  fs.rmSync(dir, { recursive: true, force: true });
});
