/**
 * 探勘：逐頁截一張小圖，並列出分頁、按鈕、標題、設定欄位標籤 → disc/ui.json。
 * 用法：node scripts/discover.mjs --config present.config.json
 * 產物給大綱規劃用：先看「每頁有哪些分頁與操作」，再決定哪些是大功能（全頁圖解）、哪些是流程（一頁一個）。
 */
import fs from "node:fs";
import path from "node:path";
import { loadConfig, createSession } from "./lib.mjs";

const arg = (k, d) => { const i = process.argv.indexOf(k); return i > 0 ? process.argv[i + 1] : d; };
const cfg = loadConfig(arg("--config", "present.config.json"));
const OUT = path.resolve(cfg._dir, "disc");
fs.mkdirSync(OUT, { recursive: true });
const s = await createSession(cfg, { dsf: 1 });
const out = {};
for (const [route, name] of cfg.routes || [["/", "home"]]) {
  await s.go(route, 3000);
  await s.p.screenshot({ path: path.join(OUT, `${name}.png`) });
  out[name] = await s.run(`
    const t = (q) => [...new Set([...root.querySelectorAll(q)].map((e) => e.textContent.replace(/\\s+/g, " ").trim()).filter((x) => x && x.length < 60))];
    return { route: ${JSON.stringify(route)},
      tabs: t(".tab,[role=tab],.tabs button,.pill-tab"),
      heads: t("h1,h2,h3,h4,.card-title,.section-title,.pf-title,.bx-title"),
      fields: t(".field > label, .field label:first-of-type"),
      buttons: t("button").slice(0, 80),
      titles: [...new Set([...root.querySelectorAll("[title],[aria-label]")].map((e) => e.getAttribute("title") || e.getAttribute("aria-label")).filter(Boolean))].slice(0, 60),
      placeholders: [...new Set([...root.querySelectorAll("input,textarea")].map((e) => e.placeholder).filter(Boolean))].slice(0, 40) };`);
  console.log("OK", name, route);
}
fs.writeFileSync(path.join(OUT, "ui.json"), JSON.stringify(out, null, 1));
const meta = await s.meta();
meta.made = new Date(Date.now() + 8 * 3600e3).toISOString().slice(0, 10);   // 台灣日期
fs.writeFileSync(path.join(OUT, "meta.json"), JSON.stringify(meta, null, 1));
console.log("租戶：" + (meta.tenant || "（取不到，請在設定檔填 tenant）") + "　App：" + meta.app);
await s.close();
console.log("→", path.join(OUT, "ui.json"));
