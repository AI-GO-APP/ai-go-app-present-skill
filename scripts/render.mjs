/**
 * deck.html → PDF（＋每頁預覽 PNG），並做版面檢查。
 * 用法：node scripts/render.mjs --html deck.html --pdf 手冊.pdf [--png preview]
 * 版面檢查只看 .content 內的元素（封面、分隔頁、頁尾不算），超出下緣或右緣的頁會列出來。
 * 檢查通過不代表好看：一定要再用 contact_sheet.py 拼總表「看過」每一頁。
 */
import fs from "node:fs";
import path from "node:path";
import { pathToFileURL, fileURLToPath } from "node:url";
import { createRequire } from "node:module";

const argv = process.argv.slice(2);
const opt = (k, d) => { const i = argv.indexOf(k); return i < 0 ? d : argv[i + 1]; };
const html = path.resolve(opt("--html", "deck.html"));
const pdf = path.resolve(opt("--pdf", html.replace(/\.html$/, ".pdf")));
const pngDir = argv.includes("--png") ? path.resolve(opt("--png", "preview")) : null;

let puppeteer;
for (const d of [path.dirname(html), process.cwd(), path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..")]) {
  try { puppeteer = createRequire(path.join(d, "package.json"))("puppeteer-core"); break; } catch { /* 下一個 */ }
}
if (!puppeteer) throw new Error("找不到 puppeteer-core：在 skill 目錄執行 npm install");
const chrome = [process.env.CHROME_PATH, "C:/Program Files/Google/Chrome/Application/chrome.exe",
  "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome", "/usr/bin/google-chrome", "/usr/bin/chromium"].filter(Boolean).find((p) => fs.existsSync(p));

const b = await puppeteer.launch({ executablePath: chrome, headless: "new", args: ["--no-sandbox", "--allow-file-access-from-files"] });
const p = await b.newPage();
await p.setViewport({ width: 1600, height: 900, deviceScaleFactor: 1 });
await p.goto(pathToFileURL(html).href, { waitUntil: "networkidle0", timeout: 120000 });
await p.evaluate(async () => {
  await document.fonts.ready;
  await Promise.all([...document.images].map((i) => (i.complete ? 0 : new Promise((r) => { i.onload = i.onerror = r; }))));
});
const broken = await p.evaluate(() => [...document.images].filter((i) => !i.naturalWidth).map((i) => i.getAttribute("src")));
if (broken.length) console.log("圖片載入失敗：", broken.join("、"));

const over = await p.evaluate(() => [...document.querySelectorAll(".slide")].map((s, i) => {
  const c = s.querySelector(".content"); if (!c) return null;
  const sr = s.getBoundingClientRect(); const bottom = sr.bottom - 44, right = sr.right - 50;
  const els = [...c.querySelectorAll("*")].filter((e) => e.getClientRects().length);
  const bad = els.filter((e) => e.getBoundingClientRect().bottom > bottom + 1).length;
  const wide = els.filter((e) => e.getBoundingClientRect().right > right + 1).length;
  // 擠壓：flex 容器被壓得比內容矮 → 內容溢出、和下一塊重疊（下緣檢查抓不到）
  const squeezed = [c, ...c.querySelectorAll(".row, .grow, .content > *")].filter((e) => e.scrollHeight > e.clientHeight + 3 && getComputedStyle(e).overflow === "visible").length;
  return bad || wide || squeezed ? `第 ${i + 1} 頁：超出下緣 ${bad}、超出右緣 ${wide}、擠壓重疊 ${squeezed}` : null;
}).filter(Boolean));
console.log(over.length ? over.join("\n") : "版面檢查：沒有超出");

await p.pdf({ path: pdf, width: "1600px", height: "900px", printBackground: true, preferCSSPageSize: true });
console.log("PDF", pdf, Math.round(fs.statSync(pdf).size / 1024) + " KB");
if (pngDir) {
  fs.mkdirSync(pngDir, { recursive: true });
  const n = await p.evaluate(() => document.querySelectorAll(".slide").length);
  await p.setViewport({ width: 1600, height: 900 * n, deviceScaleFactor: 1 });
  for (let i = 0; i < n; i++) {
    await p.screenshot({ path: path.join(pngDir, `p${String(i + 1).padStart(2, "0")}.png`), clip: { x: 0, y: 900 * i, width: 1600, height: 900 } });
  }
  console.log("preview", n, "→", pngDir);
}
await b.close();
process.exit(over.length || broken.length ? 1 : 0);
