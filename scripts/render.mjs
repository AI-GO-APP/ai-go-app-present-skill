/**
 * deck.html → PDF（＋每頁預覽 PNG），並做版面、目錄、獨立性檢查；PDF 超過上限自動整份壓縮。
 * 用法：node scripts/render.mjs --html deck.html [--pdf 手冊.pdf] [--png preview] [--max-mb 20] [--no-compress] [--pdf-timeout 600]
 *
 * 檢查（任一項不過 exit 1）：
 *   - 版面：只看 .content 內的元素（封面、分隔頁、頁尾不算），超出下緣／右緣／擠壓重疊的頁會列出來
 *   - 目錄：一定要有目錄頁（deck_kit 會自動產生）；每一列的頁碼要和它連到的頁一致
 *   - 獨立性：圖片一律是本機檔案（會內嵌進 PDF），不能引用網路上的圖；不能有 iframe／video／object
 * PDF 大小：超過 --max-mb（預設 20）→ 呼叫 compress_pdf.py 整份壓縮（Ghostscript 或 pypdf），原檔搬到 disc/。
 *   壓到畫質底線仍超過 → exit 2：正式檔名已是最小版、可以交付，但要先問使用者（references/workflow.md P7）。
 * 檢查通過不代表好看：一定要再用 contact_sheet.py 拼總表「看過」每一頁。
 */
import fs from "node:fs";
import path from "node:path";
import { spawnSync } from "node:child_process";
import { pathToFileURL, fileURLToPath } from "node:url";
import { createRequire } from "node:module";

const HERE = path.dirname(fileURLToPath(import.meta.url));
const argv = process.argv.slice(2);
const opt = (k, d) => { const i = argv.indexOf(k); return i < 0 ? d : argv[i + 1]; };
const html = path.resolve(opt("--html", "deck.html"));
const pdf = path.resolve(opt("--pdf", html.replace(/\.html$/, ".pdf")));
const pngDir = argv.includes("--png") ? path.resolve(opt("--png", "preview")) : null;
const maxMb = Number(opt("--max-mb", 20));
const compress = !argv.includes("--no-compress");
// 產 PDF 的時間上限（秒）。puppeteer 預設 30 秒，頁多、全頁截圖多時不夠（52 頁約 1 分鐘）
const pdfTimeout = Number(opt("--pdf-timeout", 600)) * 1000;

let puppeteer;
for (const d of [path.dirname(html), process.cwd(), path.resolve(HERE, "..")]) {
  try { puppeteer = createRequire(path.join(d, "package.json"))("puppeteer-core"); break; } catch { /* 下一個 */ }
}
if (!puppeteer) throw new Error("找不到 puppeteer-core：在 skill 目錄執行 npm install");
const chrome = [process.env.CHROME_PATH, "C:/Program Files/Google/Chrome/Application/chrome.exe",
  "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome", "/usr/bin/google-chrome", "/usr/bin/chromium"].filter(Boolean).find((p) => fs.existsSync(p));

const b = await puppeteer.launch({ executablePath: chrome, headless: "new", args: ["--no-sandbox", "--allow-file-access-from-files"],
  protocolTimeout: Math.max(pdfTimeout, 180000) }); // CDP 指令上限（預設 180 秒）也要蓋過 PDF 時間
const p = await b.newPage();
await p.setViewport({ width: 1600, height: 900, deviceScaleFactor: 1 });
await p.goto(pathToFileURL(html).href, { waitUntil: "networkidle0", timeout: 120000 });
await p.evaluate(async () => {
  await document.fonts.ready;
  await Promise.all([...document.images].map((i) => (i.complete ? 0 : new Promise((r) => { i.onload = i.onerror = r; }))));
});
const broken = await p.evaluate(() => [...document.images].filter((i) => !i.naturalWidth).map((i) => i.getAttribute("src")));
if (broken.length) console.log("圖片載入失敗：", broken.join("、"));

// 獨立性：交付的 PDF 要能單獨寄出、離線打開。圖片必須是本機檔案（Chrome 會內嵌），不能是網址
const external = await p.evaluate(() => {
  const local = (u) => !u || /^(file|data|blob):/i.test(u);
  const bad = [...document.images].filter((i) => !local(i.currentSrc || i.src)).map((i) => "圖片 " + i.getAttribute("src"));
  for (const e of document.querySelectorAll("*")) {
    const bg = getComputedStyle(e).backgroundImage;
    for (const m of bg.matchAll(/url\("?([^")]+)"?\)/g)) if (!local(m[1])) bad.push("背景圖 " + m[1]);
  }
  for (const e of document.querySelectorAll("iframe, object, embed, video, audio")) bad.push(e.tagName.toLowerCase() + " 嵌入");
  return [...new Set(bad)];
});
if (external.length) console.log("不是獨立檔案（網路圖片／嵌入物件，PDF 離線會缺圖）：\n  " + external.join("\n  ") +
  "\n  → 下載成本機檔案放進 shots/，用 Deck.shot() 引用");

// 目錄：一定要有；列上的頁碼要等於它連到的頁
const toc = await p.evaluate(() => {
  const slides = [...document.querySelectorAll(".slide")];
  const tocs = slides.filter((s) => s.classList.contains("toc-slide"));
  const wrong = [];
  for (const a of document.querySelectorAll('.toc-slide a.toc-i[href^="#p"]')) {
    const target = document.getElementById(a.getAttribute("href").slice(1));
    const shown = Number(a.querySelector(".pg")?.textContent);
    const real = slides.indexOf(target) + 1;
    if (!target || shown !== real) wrong.push(`「${a.querySelector(".t")?.textContent}」顯示 ${shown}、實際 ${real || "找不到"}`);
  }
  return { count: tocs.length, first: slides.indexOf(tocs[0]) + 1, wrong };
});
const tocBad = !toc.count || toc.wrong.length;
if (!toc.count) console.log("沒有目錄頁：用 deck_kit 的 Deck.write() 產生 HTML（會自動插目錄），不要手刻整份 HTML");
else if (toc.wrong.length) console.log("目錄頁碼不對：\n  " + toc.wrong.join("\n  "));
else console.log(`目錄：第 ${toc.first} 頁起 ${toc.count} 頁，頁碼正確`);

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

// outline：依 h1／h2 產生 PDF 書籤側欄；目錄的 <a href="#pNN"> 在 PDF 裡是可點的內部連結
await p.pdf({ path: pdf, width: "1600px", height: "900px", printBackground: true, preferCSSPageSize: true, outline: true, tagged: true, timeout: pdfTimeout });
console.log("PDF", pdf, (fs.statSync(pdf).size / 1048576).toFixed(1) + " MB");
if (pngDir) {
  fs.mkdirSync(pngDir, { recursive: true });
  const n = await p.evaluate(() => document.querySelectorAll(".slide").length);
  await p.setViewport({ width: 1600, height: 900 * n, deviceScaleFactor: 1 });
  for (let i = 0; i < n; i++) {
    await p.screenshot({ path: path.join(pngDir, `p${String(i + 1).padStart(2, "0")}.png`), clip: { x: 0, y: 900 * i, width: 1600, height: 900 } });
  }
  console.log("preview", n, "→", pngDir, "（原始畫質，G4 目視用）");
}
await b.close();

// 大小：超過上限 → 整份壓縮（預覽 PNG 已用原始畫質產生，不受影響）
let sizeCode = 0;
if (fs.statSync(pdf).size > maxMb * 1048576) {
  if (!compress) {
    console.log(`⚠ PDF 超過 ${maxMb} MB（--no-compress 未壓縮）：交付前要先問使用者`);
    sizeCode = 2;
  } else {
    const py = process.env.PYTHON || (process.platform === "win32" ? "python" : "python3");
    const r = spawnSync(py, [path.join(HERE, "compress_pdf.py"), pdf, "--max-mb", String(maxMb),
      "--keep-original", path.join(path.dirname(pdf), "disc")], { stdio: "inherit" });
    if (r.error) console.log("壓縮腳本無法執行：", r.error.message, "（pip install pypdf pillow；或設 PYTHON）");
    sizeCode = r.error ? 1 : r.status === 2 ? 2 : r.status ? 1 : 0;
  }
}
process.exit(over.length || broken.length || external.length || tocBad || sizeCode === 1 ? 1 : sizeCode);
