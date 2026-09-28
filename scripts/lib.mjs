/**
 * ai-go-app-present：截圖共用函式庫。
 * - 登入 AI GO（runtime：帳密換 token 寫進 localStorage.token；preview：PAT 寫進 localStorage.dev_access_token）
 * - App 掛在 shadow DOM：所有查找都從 shadow root 開始
 * - shot()：全頁或局部（多個元素取聯集）截圖，並把圖解標號座標寫進 shots.json
 *
 * 用法（由 shoot.mjs / discover.mjs 呼叫）：
 *   const s = await createSession(cfg);  await s.go("/messages");  await s.shot("name", spec, {...});
 */
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import { createRequire } from "node:module";
import { fileURLToPath } from "node:url";

const SKILL_DIR = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");

export const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
const expand = (p) => (p && p.startsWith("~") ? path.join(os.homedir(), p.slice(1)) : p);

/** 讀 present.config.json（相對路徑以設定檔所在資料夾為準） */
export function loadConfig(file = "present.config.json") {
  const abs = path.resolve(file);
  const cfg = JSON.parse(fs.readFileSync(abs, "utf8"));
  cfg._dir = path.dirname(abs);
  cfg.base = (cfg.base || "https://demo.ai-go.app").replace(/\/$/, "");
  cfg.viewport = { w: 1600, h: 900, dsf: 2, ...(cfg.viewport || {}) };
  cfg.out = path.resolve(cfg._dir, cfg.out || "shots");
  return cfg;
}

/** 讀 KEY=VALUE 檔；找不到就回空物件（值不外印） */
export function readEnv(file) {
  const f = expand(file);
  if (!f || !fs.existsSync(f)) return {};
  return Object.fromEntries(fs.readFileSync(f, "utf8").split(/\r?\n/).filter((l) => l.includes("=") && !l.trim().startsWith("#"))
    .map((l) => { const i = l.indexOf("="); return [l.slice(0, i).trim(), l.slice(i + 1).trim().replace(/^["']|["']$/g, "")]; }));
}

function loadPuppeteer(cfg) {
  const tries = [cfg._dir, process.cwd(), SKILL_DIR];
  for (const d of tries) {
    try { return createRequire(path.join(d, "package.json"))("puppeteer-core"); } catch { /* 下一個 */ }
  }
  throw new Error("找不到 puppeteer-core：在 skill 目錄或工作目錄執行 npm install");
}

function chromePath(cfg) {
  const c = [cfg.chrome, process.env.CHROME_PATH,
    "C:/Program Files/Google/Chrome/Application/chrome.exe",
    "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
    "/usr/bin/google-chrome", "/usr/bin/chromium"].filter(Boolean);
  const hit = c.find((p) => fs.existsSync(p));
  if (!hit) throw new Error("找不到 Chrome：在 present.config.json 設 chrome 或環境變數 CHROME_PATH");
  return hit;
}

async function getToken(cfg) {
  if (process.env.AIGO_TOKEN) return process.env.AIGO_TOKEN;
  const env = readEnv(cfg.env_file || "~/.aigo/.env");
  if (cfg.mode === "preview") {
    const pat = process.env.DEVPORTAL_PAT || env.DEVPORTAL_PAT;
    if (!pat) throw new Error("preview 模式需要 DEVPORTAL_PAT（環境變數或 env_file）");
    return pat;
  }
  const email = process.env.AIGO_EMAIL || env.AIGO_EMAIL, password = process.env.AIGO_PASSWORD || env.AIGO_PASSWORD;
  if (!email || !password) throw new Error("runtime 模式需要 AIGO_EMAIL／AIGO_PASSWORD（環境變數或 env_file）");
  const r = await fetch(`${cfg.base}/api/v1/auth/login`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ email, password }) });
  const tok = (await r.json()).access_token;
  if (!tok) throw new Error("登入失敗（HTTP " + r.status + "）");
  return tok;
}

/** 找到掛 App 的 shadow root；沒有 shadow DOM 的頁面退回 document */
export const ROOT = `(() => { const h = [...document.querySelectorAll("div")].find((x) => x.shadowRoot); return h ? h.shadowRoot : document; })()`;

/**
 * 元素描述（spec）：
 *   sel     CSS 選擇器（預設 *）
 *   text    元素文字包含
 *   starts  元素內第一個 lsel（預設 label）的文字開頭 —— 用來抓「某個設定欄位」
 *   within  先找到另一個 spec，再在它裡面找
 *   pick    small（預設：文字最短＝最內層）｜big｜first｜last；idx 取第幾個（可負數）
 *   doc     連 document（shadow 外）一起找
 */
const FIND = `function __find(s, scope) {
  const norm = (t) => (t || "").replace(/\\s+/g, " ").trim();
  scope = scope || ${ROOT};
  if (s.within) { scope = __find(s.within, scope); if (!scope) return null; }
  let els = [...scope.querySelectorAll(s.sel || "*")];
  if (s.doc) els = els.concat([...document.querySelectorAll(s.sel || "*")]);
  if (s.text) els = els.filter((e) => norm(e.textContent).includes(s.text));
  if (s.starts) els = els.filter((e) => { const l = e.querySelector(s.lsel || "label"); return l && norm(l.textContent).startsWith(s.starts); });
  els = els.filter((e) => e.getClientRects().length);
  if (s.pick === "first") return els[0] || null;
  if (s.pick === "last") return els[els.length - 1] || null;
  if (typeof s.idx === "number") return els.at(s.idx) || null;
  els.sort((a, b) => (s.pick === "big" ? b.textContent.length - a.textContent.length : a.textContent.length - b.textContent.length));
  return els[0] || null;
}`;

export async function createSession(cfg, { dsf } = {}) {
  const puppeteer = loadPuppeteer(cfg);
  const tok = await getToken(cfg);
  const browser = await puppeteer.launch({ executablePath: chromePath(cfg), headless: "new", args: ["--no-sandbox", "--lang=zh-TW", "--font-render-hinting=none"] });
  const { w: VW, h: VH } = cfg.viewport;
  const p = await browser.newPage();
  await p.setViewport({ width: VW, height: VH, deviceScaleFactor: dsf || cfg.viewport.dsf });
  if (cfg.mode === "preview") {
    await p.goto("https://developer.ai-go.app/login", { waitUntil: "domcontentloaded" });
    await p.evaluate((t) => localStorage.setItem("dev_access_token", t), tok);
  } else {
    await p.goto(`${cfg.base}/login`, { waitUntil: "domcontentloaded" });
    await p.evaluate((t) => localStorage.setItem("token", t), tok);
  }
  fs.mkdirSync(cfg.out, { recursive: true });
  const MANF = path.join(cfg.out, "shots.json");
  const MAN = fs.existsSync(MANF) ? JSON.parse(fs.readFileSync(MANF, "utf8")) : {};
  const save = () => fs.writeFileSync(MANF, JSON.stringify(MAN, null, 1));

  const appUrl = (route = "/") => (cfg.mode === "preview" ? `${cfg.preview_url}#${route}` : `${cfg.base}/runtime/${cfg.slug}#${route}`);
  async function go(route = "/", wait = 3000) { await p.goto(appUrl(route), { waitUntil: "networkidle2", timeout: 90000 }); await sleep(wait); }
  const get = async (spec) => (await p.evaluateHandle(`(${FIND})(${JSON.stringify(spec)})`)).asElement();
  const rect = (el) => p.evaluate((e) => { const r = e.getBoundingClientRect(); return { x: r.x, y: r.y, w: r.width, h: r.height }; }, el);
  async function must(spec) { const el = await get(spec); if (!el) throw new Error("找不到 " + JSON.stringify(spec)); return el; }
  /** 程式點擊（按鈕、分頁）。會依滑鼠座標定位的選單請用 mouseClick */
  async function click(spec, wait = 900) { const el = await must(spec); await p.evaluate((e) => { e.scrollIntoView({ block: "center" }); e.click(); }, el); await sleep(wait); }
  /** 真實滑鼠點擊：PopMenu 這類用 event.clientX/Y 定位的選單必須用它，否則選單會跑到左上角 */
  async function mouseClick(spec, wait = 1000) {
    const el = await must(spec); await p.evaluate((e) => e.scrollIntoView({ block: "center" }), el); await sleep(300);
    const r = await rect(el); await p.mouse.click(r.x + r.w / 2, r.y + r.h / 2); await sleep(wait);
  }
  async function scrollTo(spec, block = "center") { const el = await must(spec); await p.evaluate((e, b) => e.scrollIntoView({ block: b }), el, block); await sleep(500); return el; }
  async function type(spec, text, { enter = false } = {}) { const el = await must(spec); await el.click({ clickCount: 3 }); await el.type(text, { delay: 5 }); if (enter) await el.press("Enter"); }
  /** 在頁面（shadow root 內）執行一段 JS；root 變數＝shadow root */
  const run = (js) => p.evaluate(`(() => { const root = ${ROOT}; ${js} })()`);

  /**
   * 截圖。specs=null＋full=true：整個視窗；否則取 specs（單一或陣列）的聯集＋pad。
   * marks=[{n, spec}]：圖解標號，存成相對截圖左上角的 CSS px 座標。
   * 截圖區必須在視窗內：比視窗高的元素請先加大 viewport 或改截局部。
   */
  async function shot(name, specs, { pad = 14, marks = [], scroll = true, block = "center", full = false, note = "" } = {}) {
    let clip;
    if (full || !specs) clip = { x: 0, y: 0, w: VW, h: VH };
    else {
      const arr = Array.isArray(specs) ? specs : [specs];
      if (scroll) await scrollTo(arr[0], block);
      const rs = [];
      for (const s of arr) rs.push(await rect(await must(s)));
      const x0 = Math.min(...rs.map((r) => r.x)), y0 = Math.min(...rs.map((r) => r.y));
      const x1 = Math.max(...rs.map((r) => r.x + r.w)), y1 = Math.max(...rs.map((r) => r.y + r.h));
      clip = { x: Math.max(0, x0 - pad), y: Math.max(0, y0 - pad) };
      clip.w = Math.min(VW, x1 + pad) - clip.x; clip.h = Math.min(VH, y1 + pad) - clip.y;
    }
    const ms = [];
    for (const m of marks) {
      const el = await get(m.spec);
      if (!el) { console.log("  (標號找不到)", name, m.n, JSON.stringify(m.spec)); continue; }
      const r = await rect(el);
      ms.push({ n: m.n, x: r.x - clip.x, y: r.y - clip.y, w: r.w, h: r.h });
    }
    await p.screenshot({ path: path.join(cfg.out, `${name}.png`), clip: { x: clip.x, y: clip.y, width: clip.w, height: clip.h } });
    MAN[name] = { w: Math.round(clip.w), h: Math.round(clip.h), full: !!(full || !specs), marks: ms, note };
    save();
    console.log("OK", name, Math.round(clip.w) + "x" + Math.round(clip.h), ms.length ? ms.length + " marks" : "");
  }
  /** 一個步驟失敗不拖垮整批：記 FAIL 並存一張 _fail-*.png 方便看當下畫面 */
  async function step(name, fn) {
    try { await fn(); } catch (e) { console.log("FAIL", name, String(e.message || e).slice(0, 200)); await p.screenshot({ path: path.join(cfg.out, `_fail-${name}.png`) }); }
  }
  /**
   * 瀏覽器以外的畫面：交給 scripts/desktop_shot.py（桌面視窗／整個螢幕／區域），寫進同一份 shots.json。
   * opts：{ title, screen, region: "x,y,w,h", from, marks: [{n, x, y, w, h}], delay, note, noFocus }
   * 終端指令不要拍：用 deck_kit 的 Deck.term() 渲染。
   */
  async function desktop(name, { title, screen, region, from, marks = [], delay, note, noFocus } = {}) {
    const args = [path.join(SKILL_DIR, "scripts", "desktop_shot.py"), "--name", name, "--out", cfg.out];
    if (title) args.push("--title", title);
    if (screen) args.push("--screen");
    if (from) args.push("--from", from);
    if (region) args.push("--region", region);
    if (delay != null) args.push("--delay", String(delay));
    if (note) args.push("--note", note);
    if (noFocus) args.push("--no-focus");
    for (const m of marks) args.push("--mark", `${m.n}:${m.x},${m.y},${m.w},${m.h}`);
    const { spawnSync } = await import("node:child_process");
    const r = spawnSync(cfg.python || (process.platform === "win32" ? "python" : "python3"), args, { encoding: "utf8" });
    if (r.status !== 0) throw new Error("desktop_shot 失敗：" + (r.stderr || r.stdout || "").trim().slice(0, 300));
    Object.assign(MAN, JSON.parse(fs.readFileSync(MANF, "utf8")));  // 它改了檔案，記憶體要跟上，否則下一次 save() 會蓋掉
    console.log((r.stdout || "").trim());
  }
  const T = (text, sel = "button") => ({ sel, text });
  const F = (starts, extra = {}) => ({ sel: ".field", starts, ...extra });
  /** 租戶名（/auth/me 的 tenant_name；preview 模式或設定檔有填就用設定檔）與 App 名（頁面標題去掉「 — AI GO」） */
  async function meta() {
    let tenant = cfg.tenant || "";
    if (!tenant && cfg.mode !== "preview") {
      try { const r = await fetch(`${cfg.base}/api/v1/auth/me`, { headers: { Authorization: "Bearer " + tok } }); tenant = (await r.json()).tenant_name || ""; } catch { /* 留空 */ }
    }
    const title = await p.title();
    const app = cfg.app_name || title.replace(/\s*[—–-]\s*AI GO\s*$/, "").trim();
    return { tenant, app, title };
  }
  return { p, browser, cfg, meta, go, get, rect, must, click, mouseClick, scrollTo, type, run, shot, desktop, step, sleep, T, F, ROOT, close: () => browser.close() };
}
