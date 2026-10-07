/**
 * 整合測試執行器：照 itest.plan.mjs 把每一頁、每個可點元素、每條端到端流程實際跑一次，自動判定並存證。
 * 用法：
 *   node scripts/itest.mjs --config present.config.json [--plan itest.plan.mjs] [--out itest] [群組 …]
 *   node scripts/itest.mjs --config present.config.json --list        # 不開瀏覽器，只列出案例（GT1 測試計畫用）
 *
 * 計畫檔 export default { 群組名: async (t) => { … } }，t 提供：
 *   t.smoke(routes?)              每頁載入（預設 present.config.json 的 routes）
 *   t.sweep({ route, name, prepare, max, skip })   UI 巡檢：逐一點這頁所有「不會改資料」的可點元素
 *   t.case({ id, area, title, expect, steps, basis, mutates, retry, allow, allowStatus }, async (c) => { … })
 *   t.skip({ id, area, title, reason })            沒測的項目（例：會真的扣款），報告會列出原因
 * 可另外 export const labels = { e2e: "端到端流程" } 給群組取報告上的名字。
 *
 * 每個案例自動收：JS 例外、console 錯誤、API 4xx／5xx、連線失敗、畫面上的技術字樣與錯誤提示、空白、卡載入、橫向捲軸
 * （規則在 itest_core.mjs）。每個案例都截一張全頁 shots/it-<編號>.png（問題元素自動標框），報告只放未通過／疑慮的。
 * 產出：<out>/results.json（合併：這次跑的群組整組取代）、<out>/review.json（GT2 判讀檔，自動補未判讀的骨架）。
 */
import fs from "node:fs";
import path from "node:path";
import { pathToFileURL } from "node:url";
import { loadConfig, createSession, sleep } from "./lib.mjs";
import {
  GARBAGE, ALERT_SEL, ALERT_TEXT, LOADING_TEXT, DIALOG_SEL, STATUS, classify, safeId, packAllow, isDangerous,
  eventFindings, scanFindings, reaction, describeSweep, mergeResults, reviewSkeleton, pageScan, pageSnap, pageCandidates,
} from "./itest_core.mjs";

const argv = process.argv.slice(2);
const opt = (k, d) => { const i = argv.indexOf(k); if (i < 0) return d; const v = argv[i + 1]; argv.splice(i, 2); return v; };
const flag = (k) => { const i = argv.indexOf(k); if (i < 0) return false; argv.splice(i, 1); return true; };
const cfg = loadConfig(opt("--config", "present.config.json"));
const planFile = path.resolve(opt("--plan", path.join(cfg._dir, "itest.plan.mjs")));
const OUT = path.resolve(cfg._dir, opt("--out", "itest"));
const LIST = flag("--list");
const IT = cfg.itest || {};
const SETTLE = IT.settle_ms ?? 1200;          // 每個動作後等畫面穩定
const LOAD_WAIT = IT.loading_wait_ms ?? 8000; // 卡在「載入中」最多再等多久才算疑慮
const ROUTE_WAIT = IT.route_wait_ms ?? 2500;

const mod = await import(pathToFileURL(planFile).href);
const plan = mod.default, labels = mod.labels || {};
const want = argv.length ? argv : Object.keys(plan);
const unknown = want.filter((k) => !plan[k]);
if (unknown.length) { console.error("計畫裡沒有這些群組：", unknown.join("、"), "\n可用：", Object.keys(plan).join("、")); process.exit(2); }
fs.mkdirSync(OUT, { recursive: true });
const routes = () => cfg.routes || [["/", "home"]];
const stepText = (spec) => (typeof spec === "string" ? spec : spec?.text || spec?.starts || spec?.sel || "元素");

// ───────────── --list：不開瀏覽器，只收集案例 ─────────────
if (LIST) {
  const rows = [];
  for (const g of want) {
    const t = {
      cfg,
      smoke: async (rs = routes()) => { for (const [r, n] of rs) rows.push({ group: g, id: `SMK-${n}`, area: n, title: `「${n}」頁載入`, kind: "冒煙", note: r }); },
      sweep: async (o) => rows.push({ group: g, id: `SWP-${o.name}`, area: o.area || o.name, title: `巡檢「${o.name}」所有可點元素`, kind: "巡檢", note: o.route }),
      case: async (m) => rows.push({ group: g, id: m.id, area: m.area || "", title: m.title, kind: m.mutates ? "端到端（改資料）" : "端到端", note: m.expect || "" }),
      skip: async (m) => rows.push({ group: g, id: m.id, area: m.area || "", title: m.title, kind: "略過", note: m.reason || "" }),
    };
    await plan[g](t);
  }
  fs.writeFileSync(path.join(OUT, "plan.json"), JSON.stringify({ labels, cases: rows }, null, 1));
  console.log("| 群組 | 編號 | 區域 | 案例 | 類型 | 預期／路由／原因 |\n|---|---|---|---|---|---|");
  for (const r of rows) console.log(`| ${labels[r.group] || r.group} | ${r.id} | ${r.area} | ${r.title} | ${r.kind} | ${r.note} |`);
  console.log(`\n共 ${rows.length} 個案例（巡檢一頁算一個，實際點擊數執行時才知道）→ ${path.join(OUT, "plan.json")}`);
  process.exit(0);
}

// ───────────── 執行 ─────────────
const s = await createSession(cfg);
const p = s.p;
const events = [];
let acceptDialogs = false;
p.on("pageerror", (e) => events.push({ type: "pageerror", text: e.message || String(e) }));
p.on("console", (m) => { if (m.type() === "error") events.push({ type: "console", text: m.text() }); });
p.on("response", (r) => { if (r.status() >= 400) events.push({ type: "http", status: r.status(), url: r.url(), method: r.request().method() }); });
p.on("requestfailed", (r) => events.push({ type: "network", url: r.url(), error: r.failure()?.errorText || "" }));
let requests = 0;
p.on("request", () => { requests++; });
p.on("dialog", async (d) => { events.push({ type: "dialog", text: d.message(), accepted: acceptDialogs }); try { await (acceptDialogs ? d.accept() : d.dismiss()); } catch { /* 已關 */ } });

const meta = { started: new Date().toISOString(), base: cfg.base, mode: cfg.mode || "runtime", slug: cfg.slug || "",
  viewport: `${cfg.viewport.w}×${cfg.viewport.h}`, browser: await s.browser.version(), plan: path.basename(planFile),
  account: IT.account || "", labels };
const fresh = [];
let group = "";

class Fail extends Error { constructor(msg, level = "fail", markSpec) { super(msg); this.level = level; this.markSpec = markSpec; } }

async function scan(allow, baseline) {
  let r = await p.evaluate(pageScan, { patterns: GARBAGE, alert: ALERT_TEXT, alertSel: ALERT_SEL, loading: LOADING_TEXT, allow: packAllow(allow), baseline });
  if (r.loading) {                                   // 等載入完；超過 LOAD_WAIT 才算疑慮
    for (let waited = 0; r.loading && waited < LOAD_WAIT; waited += 1000) {
      await sleep(1000);
      r = await p.evaluate(pageScan, { patterns: GARBAGE, alert: ALERT_TEXT, alertSel: ALERT_SEL, loading: LOADING_TEXT, allow: packAllow(allow), baseline });
    }
  }
  return r;
}

/** 截圖：全頁，發現裡有 markSel／markSpec 的元素編號標框（1、2…），回傳截圖名 */
async function evidence(id, findings) {
  const name = "it-" + safeId(id);
  const marks = [];
  for (const f of findings) {
    const spec = f.markSpec || (f.markSel ? { sel: f.markSel } : null);
    if (f.kind === "text" && f.markRect) { f.mark = marks.length + 1; marks.push({ n: f.mark, rect: f.markRect }); }   // 字樣：框那段字
    else if (spec && (await s.get(spec))) { f.mark = marks.length + 1; marks.push({ n: f.mark, spec }); }
    else if (f.markRect) { f.mark = marks.length + 1; marks.push({ n: f.mark, rect: f.markRect }); }   // 元素被重繪掉了：標點擊前的位置
  }
  if (marks.length && marks.every((m) => m.spec)) { try { const el = await s.get(marks[0].spec); await p.evaluate((e) => e.scrollIntoView({ block: "center" }), el); await sleep(300); } catch { /* 照拍 */ } }
  await s.shot(name, null, { full: true, marks, note: "整合測試 " + id });
  return name;
}

function record(m, status, findings, extra = {}) {
  const c = { id: m.id, group, area: m.area || "", title: m.title, steps: extra.steps || m.steps || [], expect: m.expect || "",
    basis: m.basis || "", status, findings: findings.map(({ markSel, markSpec, markRect, ...f }) => f), notes: extra.notes || [],
    shot: extra.shot || "", runs: extra.runs || 1, ms: extra.ms || 0, at: new Date().toISOString(), ...(m.reason ? { reason: m.reason } : {}) };
  fresh.push(c);
  const tag = { pass: "PASS ", fail: "FAIL ", doubt: "DOUBT", skip: "SKIP " }[status];
  console.log(`${tag} ${c.id}  ${c.title}${findings.length && status !== "pass" ? "\n       " + findings.filter((f) => f.level !== "info").slice(0, 3).map((f) => f.text).join("\n       ") : ""}`);
  return c;
}

/** 案例裡的 c：session 的操作（會自動記成步驟）＋斷言 */
function makeCtx(m, log, notes, allow, allowStatus, marks) {
  const wrap = (fn, describe) => async (...a) => { log.push(describe(...a)); return fn(...a); };
  const poll = async (fn, timeout) => { const end = Date.now() + timeout; for (;;) { if (await fn()) return true; if (Date.now() > end) return false; await sleep(250); } };
  const rootText = () => s.run(`const top = root === document ? document.body : root; return (top.innerText ?? [...top.querySelectorAll("*")].map((e) => e.textContent).join(" ")).replace(/\\s+/g, " ");`);
  const c = {
    ...s,
    go: wrap((route, wait = ROUTE_WAIT) => s.go(route, wait), (route) => `打開 ${route}`),
    click: wrap((spec, wait = SETTLE) => s.click(spec, wait), (spec) => `點「${stepText(spec)}」`),
    mouseClick: wrap((spec, wait = SETTLE) => s.mouseClick(spec, wait), (spec) => `點「${stepText(spec)}」`),
    type: wrap((spec, text, o) => s.type(spec, text, o), (spec, text) => `在「${stepText(spec)}」輸入「${String(text).slice(0, 30)}」`),
    step: (text) => log.push(text),                       // 手動補一句步驟（例：「等 AI 回覆」）
    note: (text) => notes.push(text),                     // 通過時的觀察（寫進報告的「結果」）
    allow: (...xs) => { for (const x of xs) (typeof x === "number" ? allowStatus : allow).push(x); },
    mark: (spec) => marks.push(spec),
    acceptDialogs: (v = true) => { acceptDialogs = v; },
    expect: (cond, msg, spec) => { if (!cond) throw new Fail(msg, "fail", spec); },
    async expectVisible(spec, msg, { timeout = 6000 } = {}) {
      if (!(await poll(() => s.get(spec), timeout))) throw new Fail(msg || `沒有出現「${stepText(spec)}」`);
    },
    async expectGone(spec, msg, { timeout = 6000 } = {}) {
      if (!(await poll(async () => !(await s.get(spec)), timeout))) throw new Fail(msg || `「${stepText(spec)}」沒有消失`, "fail", spec);
    },
    async expectText(text, msg, { timeout = 6000 } = {}) {
      allow.push(text);
      if (!(await poll(async () => (await rootText()).includes(text), timeout))) throw new Fail(msg || `畫面沒有出現「${text}」`);
    },
    async expectNoText(text, msg, { timeout = 1500 } = {}) {
      if (!(await poll(async () => !(await rootText()).includes(text), timeout))) throw new Fail(msg || `畫面不該出現「${text}」`, "fail", { text, sel: "*" });
    },
    async expectUrl(part, msg, { timeout = 6000 } = {}) {
      if (!(await poll(async () => p.url().includes(part), timeout))) throw new Fail(msg || `網址沒有變成含「${part}」（現在 ${p.url()}）`);
    },
    doubt(msg, spec) { marks.push(spec); notes.push({ doubt: msg, spec }); },
    fail(msg, spec) { throw new Fail(msg, "fail", spec); },
  };
  return c;
}

async function attempt(m, fn) {
  const log = [], notes = [], allow = [...(IT.allow_text || []), ...(m.allow || [])], allowStatus = [...(m.allowStatus || [])], marks = [];
  const mark = events.length, t0 = Date.now();
  const findings = [];
  acceptDialogs = false;
  try { await fn(makeCtx(m, log, notes, allow, allowStatus, marks)); } catch (e) {
    findings.push({ level: e.level || "fail", kind: e instanceof Fail ? "assert" : "exception",
      text: e instanceof Fail ? e.message : "操作失敗：" + String(e.message || e).split("\n")[0].slice(0, 160), markSpec: e.markSpec });
  }
  await sleep(300);
  const sc = await scan(allow, []);
  findings.push(...scanFindings(sc, { loadingSec: Math.round(LOAD_WAIT / 1000) }));
  findings.push(...eventFindings(events.slice(mark), { ignoreUrls: IT.ignore_urls, ignoreConsole: IT.ignore_console, allowStatus, allow }));
  const plain = [];
  for (const n of notes) {
    if (typeof n === "string") plain.push(n);
    else findings.push({ level: "doubt", kind: "manual", text: n.doubt, markSpec: n.spec });
  }
  for (const spec of marks) if (spec && !findings.some((f) => f.markSpec === spec)) findings.push({ level: "info", kind: "mark", text: "標記：" + stepText(spec), markSpec: spec });
  return { findings, steps: m.steps || log, notes: plain, ms: Date.now() - t0, status: classify(findings) };
}

async function runCase(m, fn) {
  if (!m.id || !m.title) throw new Error("t.case 要有 id 與 title：" + JSON.stringify(m));
  let r = await attempt(m, fn), runs = 1;
  const retry = m.retry ?? (m.mutates ? 0 : 1);
  if (r.status === "fail" && retry > 0) {          // 重現：未通過的再跑一次；第二次過了＝偶發，記疑慮
    const first = r;
    r = await attempt(m, fn); runs = 2;
    if (r.status === "pass") {
      r.findings.push({ level: "doubt", kind: "flaky", text: "偶發：第一次未通過（" + first.findings.find((f) => f.level === "fail")?.text + "），重跑通過" });
      r.status = "doubt";
    } else r.findings.push({ level: "info", kind: "repro", text: "重跑一次仍未通過（重現 2 次）" });
  }
  const shot = await evidence(m.id, r.findings);
  return record(m, r.status, r.findings, { steps: r.steps, notes: r.notes, shot, runs, ms: r.ms });
}

async function smoke(rs = routes()) {
  for (const [route, name] of rs) {
    await runCase({ id: `SMK-${name}`, area: name, title: `「${name}」頁載入`, expect: "頁面有內容、沒有錯誤訊息、API 都成功" }, async (c) => {
      await c.go(route);
      c.note("頁面正常顯示，沒有錯誤訊息，API 都成功");
    });
  }
}

async function sweep({ route, name, area, prepare, prepareText, max = IT.sweep_max ?? 60, skip = [] }) {
  if (!route || !name) throw new Error("t.sweep 要有 route 與 name");
  const base = `SWP-${name}`;
  const intro = [`打開 ${route}`, ...(prepareText ? [prepareText] : [])];
  const allow = [...(IT.allow_text || [])];
  const extraSkip = [...(IT.sweep_skip || []), ...skip];
  const ctxFor = () => makeCtx({}, [], [], allow, [], []);
  // 重新載入整頁（只換 hash 不會重載，上一個點擊留下的狀態會帶過來）
  let first = [], baseline = [];
  // 重新載入後畫面回到初始狀態，基準也回到初始（之後出現過的問題只算第一次，重載就重來）
  const reset = async () => { await p.goto("about:blank"); await s.go(route, ROUTE_WAIT); if (prepare) await prepare(ctxFor()); await sleep(400); baseline = [...first]; };
  await reset();
  const baseScan = await scan(allow, []);
  first = baseScan.items.map((x) => x.key);   // 原本就在畫面上的問題記在冒煙案例，不重複算到每次點擊
  baseline = [...first];
  const all = await p.evaluate(pageCandidates, null);
  const origin = new URL(s.appUrl(route)).origin;
  const clicked = [], skipped = [], issues = [];
  const todo = [];
  for (const x of all) {
    const external = x.tag === "a" && (x.target === "_blank" || x.download || /^(mailto|tel|javascript):/i.test(x.href)
      || (/^https?:/i.test(x.href) && !x.href.startsWith(origin)));
    if (x.type === "submit" || isDangerous(x.label, extraSkip) || external) skipped.push(x);
    else todo.push(x);
  }
  const over = todo.splice(max);
  let k = 0;
  const once = async (x) => {
    let pos = await p.evaluate(pageCandidates, { key: x.key, n: x.n });
    if (!pos) { await reset(); pos = await p.evaluate(pageCandidates, { key: x.key, n: x.n }); }
    if (!pos) return null;
    await sleep(250);
    pos = await p.evaluate(pageCandidates, { key: x.key, n: x.n });
    const before = await p.evaluate(pageSnap, DIALOG_SEL);
    const mark = events.length; requests = 0;
    await p.mouse.click(pos.x, pos.y);
    await sleep(SETTLE);
    const sc = await scan(allow, baseline);
    baseline.push(...sc.items.map((i) => i.key));
    const after = await p.evaluate(pageSnap, DIALOG_SEL);
    const react = reaction(before, after, requests, x.abs);
    const f = [...scanFindings(sc, { loadingSec: Math.round(LOAD_WAIT / 1000) }),
      ...eventFindings(events.slice(mark), { ignoreUrls: IT.ignore_urls, ignoreConsole: IT.ignore_console, allow })];
    if (!react) f.push({ level: "doubt", kind: "noreact", text: "點了沒有任何反應（畫面、網址都沒變，也沒有送出請求）" });
    return { before, after, react, findings: f, rect: pos.rect };
  };
  const recover = async (r) => {
    if (!r || r.after.url !== r.before.url) return reset();
    await p.keyboard.press("Escape"); await sleep(300);
    const now = await p.evaluate(pageSnap, DIALOG_SEL);
    if (now.dialogs > r.before.dialogs) {
      const closer = await s.get({ sel: "button,[role=button]", text: "取消" }) || await s.get({ sel: "button,[role=button]", text: "關閉" });
      if (closer) { await p.evaluate((e) => e.click(), closer); await sleep(400); }
      if ((await p.evaluate(pageSnap, DIALOG_SEL)).dialogs > r.before.dialogs) await reset();
    }
  };
  for (const x of todo) {
    let r = await once(x);
    if (!r) { skipped.push({ ...x, label: x.label + "（畫面變了找不到）" }); continue; }
    const level = classify(r.findings);
    if (level !== "pass") {
      k++;
      const id = `${base}-${String(k).padStart(2, "0")}`;
      const findings = [{ level: "info", kind: "mark", text: `點的是「${x.label}」`, markSpec: { sel: "[data-itest-cur]" }, markRect: r.rect }, ...r.findings];
      const shot = await evidence(id, findings);
      // 重現：回到同一個狀態再點一次；之後整頁重載，問題狀態不帶到下一個元素
      await reset();
      const again = await once(x);
      const flaky = !!again && classify(again.findings) === "pass";
      if (flaky) findings.push({ level: "doubt", kind: "flaky", text: "偶發：重點一次就正常" });
      else findings.push({ level: "info", kind: "repro", text: "重點一次結果相同（重現 2 次）" });
      issues.push(record({ id, area: area || name, title: `點「${x.label}」`, expect: "有反應（換頁、開視窗或更新畫面），沒有錯誤" },
        flaky ? "doubt" : classify(findings), findings, { steps: [...intro, `點「${x.label}」`], shot, runs: 2 }));
      await reset();
      continue;
    }
    clicked.push({ label: x.label, reaction: r.react });
    await recover(r);
  }
  for (const x of over) skipped.push({ ...x, label: x.label + "（超過上限未點）" });
  const sum = [{ level: all.length ? "info" : "doubt", kind: "sweep", text: all.length ? describeSweep(clicked, skipped) : "這頁找不到任何可點的元素" }];
  const notes = [describeSweep(clicked, skipped) + (issues.length ? `；另有 ${issues.length} 個點了有問題，見 ${issues.map((i) => i.id).join("、")}` : "")];
  record({ id: base, area: area || name, title: `巡檢「${name}」所有可點元素`, expect: "每個元素點了都有合理反應、沒有錯誤" },
    classify(sum), sum, { steps: intro, notes, runs: 1 });
}

async function skipCase(m) {
  if (!m.reason) throw new Error("t.skip 要寫 reason（為什麼不測）：" + m.id);
  record(m, "skip", [], {});
}

const t = { cfg, s, sleep, smoke, sweep, case: runCase, skip: skipCase };
try {
  for (const g of want) {
    group = g;
    console.log("── " + (labels[g] ? `${labels[g]}（${g}）` : g));
    try { await plan[g](t); } catch (e) {
      console.log("群組中斷：", String(e.message || e).split("\n")[0]);
      record({ id: `GRP-${g}`, title: `群組「${labels[g] || g}」中途中斷`, expect: "整組跑完" }, "fail",
        [{ level: "fail", kind: "exception", text: "群組中斷：" + String(e.message || e).split("\n")[0].slice(0, 200) }],
        { shot: await evidence(`GRP-${g}`, []).catch(() => "") });
    }
  }
} finally {
  const info = await s.meta().catch(() => ({}));
  await s.close();
  meta.finished = new Date().toISOString();
  meta.tenant = info.tenant || ""; meta.app = info.app || "";
  const RES = path.join(OUT, "results.json"), REV = path.join(OUT, "review.json");
  const old = fs.existsSync(RES) ? JSON.parse(fs.readFileSync(RES, "utf8")) : null;
  const cases = mergeResults(old, fresh, want);
  fs.writeFileSync(RES, JSON.stringify({ meta: { ...(old?.meta || {}), ...meta, labels: { ...(old?.meta?.labels || {}), ...labels } }, cases }, null, 1));
  const prev = fs.existsSync(REV) ? JSON.parse(fs.readFileSync(REV, "utf8")) : {};
  const { review, todo } = reviewSkeleton(cases, prev);
  fs.writeFileSync(REV, JSON.stringify(review, null, 1));
  const n = (st) => cases.filter((c) => c.status === st).length;
  console.log(`\n整合測試：${cases.length} 個案例｜${STATUS.pass} ${n("pass")}｜${STATUS.fail} ${n("fail")}｜${STATUS.doubt} ${n("doubt")}｜${STATUS.skip} ${n("skip")}`);
  console.log("→", RES);
  if (todo.length) console.log(`GT2：${todo.length} 個未通過／疑慮案例待判讀（${REV}）：${todo.join("、")}`);
  console.log("看截圖：python <skill>/scripts/contact_sheet.py \"shots/it-*.png\" --out disc/it-sheet");
}
