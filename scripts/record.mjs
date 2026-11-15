/**
 * 網頁操作錄影：照 video.plan.mjs 操作 app，同時錄下畫面與每一步的字幕時間，交給 video_post.py 後製。
 *
 *   node scripts/record.mjs --config present.config.json --plan video.plan.mjs --out video/manual [--dsf 1.2]
 *
 * 計畫檔：export default async (v) => { ... }，v 是：
 *   v.chapter(標題, 一句話?)        章節字卡（功能展示放「這能幫你做什麼」）
 *   v.go(route, 字幕?)              開頁面（等載入完才記字幕）
 *   v.click(spec, 字幕, {wait})      游標移過去 → 記字幕（後製在這裡凍結：游標到了、還沒點）→ 點擊
 *   v.type(spec, 文字, 字幕, {enter, delay})   點欄位、清空、逐字輸入
 *   v.select(spec, 值, 字幕)        下拉選單（<select>）選值
 *   v.say(字幕, spec?)              只講解不點；給 spec 會圈出那個元素
 *   v.scroll(spec, 字幕?)           平滑捲到元素
 *   v.waitFor(spec, {timeout})      等元素出現（例：查詢結果）
 *   v.hold(ms)                      停一下（後製會把太長的靜止快轉）
 *   v.s                             lib.mjs 的 session（get／run／T／F／p …），做計畫 API 沒有的事
 * spec：CSS 選擇器字串（取第一個），或跟截圖一樣的 spec 物件（screenshot-guide.md「找元素」）；都會穿過 shadow DOM。
 *
 * 錄法：Chrome DevTools 的 screencast（畫面有變才送一格 JPEG，附時間戳）→ 依時間戳組成固定 30 fps 的 raw.mkv。
 * 視窗 1600×900 × dsf 1.2 ＝ 1920×1080，文字比 Playwright recordVideo 的 webm 清楚。
 * 輸出：--out 資料夾裡的 raw.mkv、events.jsonl、session.json（含租戶名與 App 名，後製自動帶檔名）。
 */
import fs from "node:fs";
import path from "node:path";
import { spawnSync } from "node:child_process";
import { fileURLToPath, pathToFileURL } from "node:url";
import { loadConfig, createSession, sleep } from "./lib.mjs";

const SKILL_DIR = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const argv = process.argv.slice(2);
const opt = (k, d) => { const i = argv.indexOf(k); return i < 0 ? d : argv[i + 1]; };
const cfg = loadConfig(opt("--config", "present.config.json"));
const planFile = path.resolve(opt("--plan", path.join(cfg._dir, "video.plan.mjs")));
const outDir = path.resolve(opt("--out", path.join(cfg._dir, "video")));
const DSF = +opt("--dsf", "1.2");
const FPS = 30;

function ffmpegBin() {
  if (process.env.FFMPEG) return process.env.FFMPEG;
  const exe = process.platform === "win32" ? "ffmpeg.exe" : "ffmpeg";
  const local = path.join(SKILL_DIR, "node_modules", "ffmpeg-static", exe);
  return fs.existsSync(local) ? local : "ffmpeg";
}

// 頁面裡的假游標＋點擊圈（headless 沒有系統游標）。掛在 document 最外層，不受 app 的 shadow DOM 影響
const CURSOR = `(() => {
  if (window.__recCursor) return;
  const make = () => {
    let c = document.getElementById("__rec_cursor");
    if (c) return c;
    c = document.createElement("div");
    c.id = "__rec_cursor";
    c.innerHTML = '<svg width="30" height="30" viewBox="0 0 24 24"><path d="M4 2l15 11-6.5 1 3.8 7.2-2.6 1.3-3.7-7.2L4 20z" fill="#fff" stroke="#050E1F" stroke-width="1.4" stroke-linejoin="round"/></svg>';
    Object.assign(c.style, { position: "fixed", left: "0", top: "0", zIndex: 2147483647, pointerEvents: "none",
      transform: "translate(" + (window.__recX ?? innerWidth / 2) + "px," + (window.__recY ?? innerHeight / 2) + "px)",
      filter: "drop-shadow(0 1px 2px rgba(0,0,0,.35))" });
    document.documentElement.appendChild(c);
    return c;
  };
  window.__recCursor = (x, y, ms) => { const e = make(); e.style.transition = "transform " + ms / 1000 + "s cubic-bezier(.4,0,.2,1)";
    e.style.transform = "translate(" + x + "px," + y + "px)"; window.__recX = x; window.__recY = y; };
  window.__recRipple = (x, y) => { const r = document.createElement("div");
    Object.assign(r.style, { position: "fixed", left: x - 22 + "px", top: y - 22 + "px", width: "44px", height: "44px", borderRadius: "50%",
      border: "3px solid #1F80FF", background: "rgba(31,128,255,.18)", zIndex: 2147483646, pointerEvents: "none",
      transform: "scale(.4)", opacity: "1", transition: "transform .5s ease-out, opacity .6s ease-out" });
    document.documentElement.appendChild(r); requestAnimationFrame(() => { r.style.transform = "scale(1.4)"; r.style.opacity = "0"; });
    setTimeout(() => r.remove(), 800); };
  if (document.readyState === "loading") addEventListener("DOMContentLoaded", make); else make();
})()`;

async function main() {
  const plan = (await import(pathToFileURL(planFile).href)).default;
  if (typeof plan !== "function") throw new Error("計畫檔要 export default async (v) => { ... }");
  fs.rmSync(outDir, { recursive: true, force: true });
  const frameDir = path.join(outDir, "_frames");
  fs.mkdirSync(frameDir, { recursive: true });

  const s = await createSession(cfg, { dsf: DSF });
  const p = s.p;
  const { w: VW, h: VH } = cfg.viewport;
  await p.evaluateOnNewDocument(CURSOR);

  // ── screencast：每一格存檔＋時間戳（秒，和 Date.now() 同一個時鐘）──
  const frames = [];
  const cdp = await p.createCDPSession();
  let writing = Promise.resolve();
  cdp.on("Page.screencastFrame", ({ data, metadata, sessionId }) => {
    const i = frames.length;
    const file = `f${String(i).padStart(6, "0")}.jpg`;
    frames.push({ file, ts: metadata.timestamp ?? Date.now() / 1000 });
    writing = writing.then(() => fs.promises.writeFile(path.join(frameDir, file), Buffer.from(data, "base64")));
    cdp.send("Page.screencastFrameAck", { sessionId }).catch(() => {});
  });

  const events = [];
  const log = (kind, text, extra = {}) => {
    const ev = { ts: Date.now() / 1000, kind, when: "at", text, ...extra };
    events.push(ev);
    console.log(kind === "chapter" ? "══ " + text : "  " + (text || ""));
  };
  let cur = { x: VW / 2, y: VH / 2 };
  const px = (v) => Math.round(v * DSF);   // CSS px → 錄影畫面像素
  async function moveTo(x, y) {
    const d = Math.hypot(x - cur.x, y - cur.y), ms = Math.round(Math.min(900, 300 + d * 0.6));
    await p.evaluate((a, b, m) => window.__recCursor && window.__recCursor(a, b, m), x, y, ms);
    await p.mouse.move(x, y, { steps: 8 });
    cur = { x, y };
    await sleep(ms + 200);
  }
  // spec 可以直接寫 CSS 選擇器字串（取第一個），或 lib.mjs 的 spec 物件
  const norm = (spec) => (typeof spec === "string" ? { sel: spec, pick: "first" } : spec);
  async function target(spec) {
    const el = await s.must(norm(spec));
    await p.evaluate((e) => e.scrollIntoView({ block: "center", behavior: "smooth" }), el);
    await sleep(450);
    const r = await s.rect(el);
    return { el, x: Math.round(r.x + r.w / 2), y: Math.round(r.y + r.h / 2) };
  }
  const v = {
    s,
    async chapter(text, sub = "") { log("chapter", text, sub ? { sub } : {}); },
    async go(route, text, wait = 2500) {
      await s.go(route, wait);
      await p.evaluate((a, b) => window.__recCursor && window.__recCursor(a, b, 0), cur.x, cur.y);
      if (text) log("step", text);
      await sleep(300);
    },
    async click(spec, text, { wait = 1200 } = {}) {
      const { x, y } = await target(spec);
      await moveTo(x, y);
      log("step", text, { x: px(x), y: px(y) });
      await p.evaluate((a, b) => window.__recRipple(a, b), x, y);
      await p.mouse.click(x, y);
      await sleep(wait);
    },
    async type(spec, value, text, { enter = false, delay = 60, wait = 600 } = {}) {
      const { el, x, y } = await target(spec);
      await moveTo(x, y);
      log("step", text, { x: px(x), y: px(y) });
      await p.evaluate((a, b) => window.__recRipple(a, b), x, y);
      await p.mouse.click(x, y);
      await p.evaluate((e) => { if ("value" in e) { e.value = ""; e.dispatchEvent(new Event("input", { bubbles: true })); } }, el);
      await p.keyboard.type(value, { delay });
      if (enter) await p.keyboard.press("Enter");
      await sleep(wait);
    },
    async select(spec, value, text, { wait = 900 } = {}) {
      const { el, x, y } = await target(spec);
      await moveTo(x, y);
      log("step", text, { x: px(x), y: px(y) });
      await p.evaluate((a, b) => window.__recRipple(a, b), x, y);
      await p.evaluate((e, val) => {
        const o = [...e.options].find((k) => k.value === val || k.textContent.trim() === val);
        if (!o) throw new Error("選單裡沒有 " + val);
        e.value = o.value; e.dispatchEvent(new Event("input", { bubbles: true })); e.dispatchEvent(new Event("change", { bubbles: true }));
      }, el, value);
      await sleep(wait);
    },
    async say(text, spec, { wait = 300 } = {}) {
      if (!spec) { log("step", text); await sleep(wait); return; }
      const { x, y } = await target(spec);
      await moveTo(x, y);
      log("step", text, { x: px(x), y: px(y), act: false });
      await sleep(wait);
    },
    async scroll(spec, text) {
      const el = await s.must(norm(spec));
      if (text) log("step", text);
      await p.evaluate((e) => e.scrollIntoView({ block: "start", behavior: "smooth" }), el);
      await sleep(900);
    },
    async waitFor(spec, { timeout = 30000 } = {}) {
      const t0 = Date.now();
      while (Date.now() - t0 < timeout) { if (await s.get(norm(spec))) return; await sleep(250); }
      throw new Error("等不到 " + JSON.stringify(spec));
    },
    hold: (ms) => sleep(ms),
  };

  let err = null, meta = {};
  await cdp.send("Page.startScreencast", { format: "jpeg", quality: 92, maxWidth: px(VW), maxHeight: px(VH), everyNthFrame: 1 });
  try {
    await plan(v);
    await sleep(1500);
    meta = await s.meta().catch(() => ({}));
  } catch (e) { err = e; console.error("計畫中斷：", e.message); }
  const stopTs = Date.now() / 1000;
  await cdp.send("Page.stopScreencast").catch(() => {});
  await writing;
  await s.close();
  if (!frames.length) throw new Error("沒有錄到任何畫面");

  // ── 依時間戳組成固定幀率的 raw.mkv（沒變的畫面 screencast 不送格：上一格一直延續到下一格）──
  const t0 = frames[0].ts;
  const list = ["ffconcat version 1.0"];
  frames.forEach((f, i) => {
    const next = i + 1 < frames.length ? frames[i + 1].ts : stopTs;
    list.push(`file '${f.file}'`, `duration ${Math.max(0.001, next - f.ts).toFixed(4)}`);
  });
  list.push(`file '${frames.at(-1).file}'`);
  fs.writeFileSync(path.join(frameDir, "list.ffconcat"), list.join("\n") + "\n");
  const W = px(VW) - (px(VW) % 2), H = px(VH) - (px(VH) % 2);
  const r = spawnSync(ffmpegBin(), ["-hide_banner", "-nostdin", "-y", "-f", "concat", "-safe", "0", "-i", "list.ffconcat",
    "-vf", `fps=${FPS},scale=${W}:${H}:flags=lanczos,format=yuv420p`, "-c:v", "libx264", "-preset", "veryfast", "-crf", "14",
    "-g", String(FPS), path.join(outDir, "raw.mkv")], { cwd: frameDir, encoding: "utf8" });
  if (r.status !== 0) throw new Error("ffmpeg 組影片失敗：" + (r.stderr || "").slice(-1500) + "\n（skill 目錄 npm install 會裝 ffmpeg-static，或設 FFMPEG）");
  fs.writeFileSync(path.join(outDir, "events.jsonl"), events.map((e) => JSON.stringify(e)).join("\n") + "\n");
  fs.writeFileSync(path.join(outDir, "session.json"), JSON.stringify({ kind: "web", raw: "raw.mkv", region: [0, 0, W, H],
    video_start: t0, dsf: DSF, frames: frames.length, seconds: +(stopTs - t0).toFixed(2), meta, state: "done" }, null, 1));
  fs.rmSync(frameDir, { recursive: true, force: true });
  console.log(`錄影結束 ${path.join(outDir, "raw.mkv")}（${(stopTs - t0).toFixed(1)}s，${frames.length} 格，${events.filter((e) => e.kind === "step").length} 步）`);
  if (err) process.exit(1);
}

main().catch((e) => { console.error(e.message || e); process.exit(1); });
