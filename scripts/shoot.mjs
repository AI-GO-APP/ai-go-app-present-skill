/**
 * 依截圖計畫拍照。
 * 用法：node scripts/shoot.mjs --config present.config.json --plan shots.plan.mjs [群組 ...]
 * 計畫檔 export default { 群組名: async (s) => { ... } }，s 是 lib.mjs 的 session（go/click/shot/step…）。
 * 不給群組＝全部跑；同名截圖重拍會覆蓋，shots.json 只更新該筆。
 */
import path from "node:path";
import { pathToFileURL } from "node:url";
import { loadConfig, createSession } from "./lib.mjs";

const argv = process.argv.slice(2);
const opt = (k, d) => { const i = argv.indexOf(k); if (i < 0) return d; const v = argv[i + 1]; argv.splice(i, 2); return v; };
const cfg = loadConfig(opt("--config", "present.config.json"));
const planFile = path.resolve(opt("--plan", path.join(cfg._dir, "shots.plan.mjs")));
const plan = (await import(pathToFileURL(planFile).href)).default;
const want = argv.length ? argv : Object.keys(plan);
const unknown = want.filter((k) => !plan[k]);
if (unknown.length) { console.error("計畫裡沒有這些群組：", unknown.join("、"), "\n可用：", Object.keys(plan).join("、")); process.exit(2); }

const s = await createSession(cfg);
try {
  for (const k of want) { console.log("── " + k); await plan[k](s); }
} finally {
  await s.close();
}
console.log("done");
