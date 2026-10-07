/**
 * ai-go-app-present：整合測試的判定規則（不依賴瀏覽器，tests/itest_core.test.mjs 測這裡）。
 *
 * - 一個「發現」（finding）＝{ level, kind, text, mark? }；level：fail 未通過｜doubt 疑慮｜info 只記錄不影響判定
 * - 案例判定：有 fail → 未通過；否則有 doubt → 疑慮；否則通過（classify）
 * - 自動偵測來源：瀏覽器事件（JS 例外、console 錯誤、API 4xx／5xx、連線失敗、原生對話框）＋畫面掃描
 *   （undefined／NaN／堆疊等技術字樣、錯誤提示框、空白頁、卡在載入中、橫向捲軸）
 * - UI 巡檢只點「不會改資料」的元素：DANGER 命中的一律略過，改由端到端案例在測試資料上測
 *
 * page* 開頭的函式會被序列化丟進瀏覽器執行（puppeteer page.evaluate），裡面不能引用外部變數。
 */

export const STATUS = { pass: "通過", fail: "未通過", doubt: "疑慮", skip: "略過" };

/** UI 巡檢不點的字：會改資料、對外送出、下載、登出、付款。命中的元素改由端到端案例（測試資料）測 */
export const DANGER = new RegExp([
  "刪除", "删除", "移除", "清空", "清除", "送出", "提交", "發送", "傳送", "寄出", "推播", "群發", "廣播", "發布", "發佈",
  "上架", "下架", "付款", "結帳", "購買", "下單", "退款", "扣款", "登出", "停用", "啟用", "封鎖", "解除", "重設", "重置",
  "還原", "匯入", "匯出", "下載", "列印", "同步", "儲存", "保存", "存檔", "確定", "確認", "套用", "封存", "作廢", "核准",
  "駁回", "送審", "審核", "簽核", "邀請", "轉移", "指派", "結束", "轉回", "標為", "全部已讀",
  "delete", "remove", "clear", "send", "submit", "save", "publish", "confirm", "apply", "log ?out", "sign ?out",
  "import", "export", "download", "print", "sync", "approve", "reject", "pay", "checkout", "invite", "archive", "reset",
].join("|"), "i");

/** 畫面上不該出現的技術字樣（使用者看得到＝不合理的訊息）。fail＝一看就是程式錯誤外露 */
export const GARBAGE = [
  { src: "Traceback \\(most recent call last\\)", flags: "", level: "fail", label: "畫面露出程式錯誤堆疊" },
  { src: "\\bat [\\w$.<>]+ \\(\\S+:\\d+:\\d+\\)", flags: "", level: "fail", label: "畫面露出程式錯誤堆疊" },
  { src: "\\b(TypeError|ReferenceError|SyntaxError|RangeError|KeyError|ValueError|AttributeError|NameError)\\b", flags: "", level: "fail", label: "畫面露出程式錯誤名稱" },
  { src: "Internal Server Error|Bad Gateway|Service Unavailable|Gateway Timeout", flags: "i", level: "fail", label: "畫面露出伺服器錯誤原文" },
  { src: "\\[object Object\\]", flags: "", level: "fail", label: "畫面出現 [object Object]" },
  { src: "\\bundefined\\b", flags: "", level: "doubt", label: "畫面出現 undefined" },
  { src: "\\bNaN\\b", flags: "", level: "doubt", label: "畫面出現 NaN" },
  { src: "\\bnull\\b", flags: "", level: "doubt", label: "畫面出現 null" },
  { src: "Invalid Date", flags: "i", level: "doubt", label: "畫面出現 Invalid Date" },
  { src: "\\{\\s*\"(detail|error|message|code|msg)\"\\s*:", flags: "", level: "doubt", label: "畫面露出 JSON 錯誤原文" },
  { src: "\\{\\{\\s*[\\w.]+\\s*\\}\\}|\\$\\{[\\w.]+\\}", flags: "", level: "doubt", label: "畫面出現沒有代換的變數" },
  { src: "Request failed with status code \\d+|Failed to fetch|NetworkError|net::ERR_|\\bHTTP \\d{3}\\b", flags: "i", level: "doubt", label: "畫面露出連線錯誤原文" },
];

/** 錯誤提示框：這些元素裡出現 ALERT_TEXT 的字 → 疑慮（案例自己預期的錯誤訊息用 allow／expectText 放行） */
export const ALERT_SEL = "[role=alert],[role=alertdialog],[aria-live=assertive],.toast,.error,.alert,.snackbar,.notice,"
  + "[class*=toast],[class*=Toast],[class*=error],[class*=Error],[class*=alert],[class*=danger],[class*=notification]";
export const ALERT_TEXT = { src: "失敗|錯誤|異常|無法|請稍後|發生問題|出了點問題|error|failed|exception|denied|forbidden", flags: "i" };
export const LOADING_TEXT = { src: "^(載入中|讀取中|處理中|請稍候|Loading)[.…。]*$", flags: "i" };
export const DIALOG_SEL = "dialog[open],[role=dialog],[role=alertdialog],.modal,[class*=modal],[class*=Modal],[class*=drawer],[class*=Drawer]";

const DEFAULT_IGNORE_URL = ["favicon", "/sockjs-node", "hot-update", "google-analytics", "googletagmanager", "doubleclick", "/__vite_ping"];
const IGNORE_NET = /net::ERR_ABORTED|net::ERR_BLOCKED_BY_CLIENT/;

export function classify(findings) {
  if (findings.some((f) => f.level === "fail")) return "fail";
  if (findings.some((f) => f.level === "doubt")) return "doubt";
  return "pass";
}

/** 案例編號 → 檔名安全（截圖名 it-<id>） */
export const safeId = (id) => String(id).replace(/[^\w.-]+/g, "_");

/** allow 清單：字串或 RegExp → 可序列化的形式（丟進瀏覽器用） */
export const packAllow = (allow = []) => allow.filter((a) => typeof a === "string" || a instanceof RegExp)
  .map((a) => (a instanceof RegExp ? { re: true, src: a.source, flags: a.flags } : { src: a }));
const allowed = (text, allow = []) => allow.some((a) => (a instanceof RegExp ? a.test(text) : typeof a === "string" && text.includes(a)));

export function isDangerous(label, extra = []) {
  const t = String(label || "");
  return DANGER.test(t) || extra.some((x) => (x instanceof RegExp ? x.test(t) : t.includes(x)));
}

const shortUrl = (u) => { try { const x = new URL(u); return x.pathname + (x.search.length > 1 ? x.search.slice(0, 40) : ""); } catch { return String(u).slice(0, 80); } };

/**
 * 把瀏覽器事件變成發現。events：[{ type: pageerror|console|http|network|dialog, … }]
 * opts：{ ignoreUrls, ignoreConsole, allowStatus:[422], allow:[文字] }
 */
export function eventFindings(events, opts = {}) {
  const ignoreUrls = [...DEFAULT_IGNORE_URL, ...(opts.ignoreUrls || [])];
  const skipUrl = (u) => !u || /^(data|blob|chrome-extension):/.test(u) || ignoreUrls.some((x) => u.includes(x));
  const ignoreConsole = opts.ignoreConsole || [];
  const allowStatus = new Set(opts.allowStatus || []);
  const out = [], seen = new Set();
  const push = (f) => { const k = f.kind + "|" + f.text; if (!seen.has(k)) { seen.add(k); out.push(f); } };
  for (const e of events) {
    if (e.type === "pageerror") push({ level: "fail", kind: "pageerror", text: "程式錯誤（未攔截的例外）：" + firstLine(e.text) });
    else if (e.type === "console") {
      const t = firstLine(e.text);
      if (/^Failed to load resource/.test(t)) continue;            // 同一件事 http 事件已經記了
      if (ignoreConsole.some((x) => t.includes(x)) || allowed(t, opts.allow)) continue;
      push({ level: "doubt", kind: "console", text: "瀏覽器 console 錯誤：" + t });
    } else if (e.type === "http") {
      if (skipUrl(e.url) || allowStatus.has(e.status) || e.status === 304) continue;
      push({ level: e.status >= 500 ? "fail" : "doubt", kind: "http", text: `API 回應 ${e.status}：${e.method || "GET"} ${shortUrl(e.url)}` });
    } else if (e.type === "network") {
      if (skipUrl(e.url) || IGNORE_NET.test(e.error || "")) continue;
      push({ level: "doubt", kind: "network", text: `連線失敗（${e.error}）：${shortUrl(e.url)}` });
    } else if (e.type === "dialog") {
      push({ level: "info", kind: "dialog", text: `跳出瀏覽器原生對話框「${firstLine(e.text).slice(0, 60)}」（${e.accepted ? "已按確定" : "已按取消"}）` });
    }
  }
  return out;
}

function firstLine(t) { return String(t || "").split(/\r?\n/)[0].trim().slice(0, 200); }

/** 畫面掃描結果（pageScan 回傳）→ 發現 */
export function scanFindings(scan, { loadingSec = 0 } = {}) {
  const out = [];
  for (const it of scan.items || []) out.push({ level: it.level, kind: "text", text: `${it.label}：「${it.snippet}」`, markSel: `[data-itest-mark="${it.mark}"]`, ...(it.rect ? { markRect: it.rect } : {}) });
  if (scan.blank) out.push({ level: "fail", kind: "blank", text: "畫面空白（沒有任何文字或圖片）" });
  if (scan.loading) out.push({ level: "doubt", kind: "loading", text: `停在載入中超過 ${loadingSec} 秒`, markSel: scan.loadingMark ? `[data-itest-mark="${scan.loadingMark}"]` : undefined });
  if (scan.overflow) out.push({ level: "doubt", kind: "overflow", text: `畫面出現橫向捲軸（內容寬 ${scan.overflow}px，超出視窗）` });
  return out;
}

/** UI 巡檢：點擊前後的快照比對 → 反應類型；null＝沒反應 */
export function reaction(before, after, requests, href = "") {
  if (before.url !== after.url) return "換頁";
  if (href && href === before.url) return "已在此頁";       // 導覽列連到目前這頁：沒變化是正常的
  if (after.dialogs > before.dialogs) return "開啟視窗";
  if (before.h !== after.h) return "畫面更新";
  if (requests > 0) return "送出讀取請求";
  return null;
}

/** 巡檢摘要的一句話：「點了 23 個：分頁「全部」（畫面更新）、…等 23 個」 */
export function describeSweep(clicked, skipped, max = 8) {
  const names = clicked.slice(0, max).map((c) => `「${c.label}」（${c.reaction}）`).join("、");
  let s = clicked.length ? `點了 ${clicked.length} 個可點元素都有反應、沒有錯誤：${names}${clicked.length > max ? ` 等 ${clicked.length} 個` : ""}` : "沒有可點的元素";
  if (skipped.length) s += `；略過 ${skipped.length} 個會改資料或離開 App 的元素（${skipped.slice(0, 5).map((x) => `「${x.label}」`).join("、")}${skipped.length > 5 ? "…" : ""}），改由端到端案例測`;
  return s;
}

/** 合併結果：這次跑的群組整組取代，沒跑的群組保留上次的 */
export function mergeResults(old, fresh, groupsRun) {
  const run = new Set(groupsRun);
  const kept = (old?.cases || []).filter((c) => !run.has(c.group));
  const ids = new Set(fresh.map((c) => c.id));
  const dup = fresh.map((c) => c.id).filter((id, i, a) => a.indexOf(id) !== i);
  if (dup.length) throw new Error("案例編號重複：" + [...new Set(dup)].join("、"));
  return [...kept.filter((c) => !ids.has(c.id)), ...fresh];
}

/**
 * 判讀檔骨架（GT2）：未通過／疑慮、且還沒判讀（或重跑過）的案例補一筆空白判讀；
 * 判讀過但這次通過的案例，舊判讀移到 previous_judgement，留 fixed 欄給你寫「修正後重測通過」。
 * run＝案例執行時間（results 的 at），跟案例對不上＝判讀過期。回傳 { review, todo:[id…] }
 */
export function reviewSkeleton(cases, review = {}) {
  const out = { ...review }, todo = [];
  for (const c of cases) {
    const r = out[c.id];
    const fresh = r && r.run === c.at;
    if (c.status === "fail" || c.status === "doubt") {
      if (!fresh) {
        out[c.id] = { run: c.at, auto: c.status, status: c.status, severity: "", judgement: "", suggest: "",
          ...(r?.judgement ? { previous_judgement: r.judgement } : {}) };
      }
      if (!out[c.id].judgement) todo.push(c.id);
    } else if (r && !fresh && (r.status === "fail" || r.status === "doubt")) {
      out[c.id] = { run: c.at, auto: c.status, status: c.status, fixed: "", previous_judgement: r.judgement || "" };
    }
  }
  return { review: out, todo };
}

// ─────────────── 以下在瀏覽器裡執行 ───────────────

/** 畫面掃描：技術字樣、錯誤提示框、空白、載入中、橫向捲軸。命中的元素加 data-itest-mark 供截圖標框 */
export function pageScan(o) {
  const h = [...document.querySelectorAll("div")].find((x) => x.shadowRoot);
  const root = h ? h.shadowRoot : document;
  const top = root === document ? document.body : root;
  const vis = (e) => { if (!e || !e.getClientRects || !e.getClientRects().length) return false; const cs = getComputedStyle(e); return cs.visibility !== "hidden" && cs.display !== "none" && Number(cs.opacity) !== 0; };
  const allow = (o.allow || []).map((a) => (a.re ? new RegExp(a.src, a.flags) : a.src));
  const allowed = (t) => allow.some((a) => (typeof a === "string" ? t.includes(a) : a.test(t)));
  root.querySelectorAll("[data-itest-mark]").forEach((e) => e.removeAttribute("data-itest-mark"));
  let seq = 0;
  const mark = (el) => { if (!el.getAttribute("data-itest-mark")) el.setAttribute("data-itest-mark", String(++seq)); return el.getAttribute("data-itest-mark"); };
  const pats = (o.patterns || []).map((p) => ({ ...p, re: new RegExp(p.src, p.flags) }));
  const loadRe = new RegExp(o.loading.src, o.loading.flags);
  const items = [], seen = new Set(), baseline = new Set(o.baseline || []);
  let textLen = 0, loadingMark = null;
  const w = document.createTreeWalker(top, NodeFilter.SHOW_TEXT);
  for (let n = w.nextNode(); n; n = w.nextNode()) {
    const el = n.parentElement;
    if (!el || /^(SCRIPT|STYLE|NOSCRIPT|TEMPLATE)$/.test(el.tagName) || !vis(el)) continue;
    const t = n.textContent.replace(/\s+/g, " ").trim();
    if (!t) continue;
    textLen += t.length;
    if (!loadingMark && t.length <= 20 && loadRe.test(t)) loadingMark = mark(el);
    if (allowed(t)) continue;
    for (const p of pats) {
      const m = t.match(p.re);
      if (!m) continue;
      const key = p.label + "|" + t.slice(0, 80);
      if (seen.has(p.label) || baseline.has(key)) continue;
      seen.add(p.label);
      const rg = document.createRange(); rg.selectNodeContents(n);   // 只框這段字，不框整個區塊
      const b = rg.getBoundingClientRect();
      items.push({ level: p.level, label: p.label, snippet: t.slice(0, 80), key, mark: mark(el),
        rect: b.width ? { x: b.x - 4, y: b.y - 3, w: b.width + 8, h: b.height + 6 } : null });
    }
  }
  const alertRe = new RegExp(o.alert.src, o.alert.flags);
  const alerts = new Set();
  for (const el of root.querySelectorAll(o.alertSel)) {
    if (!vis(el)) continue;
    const t = (el.innerText || el.textContent || "").replace(/\s+/g, " ").trim().slice(0, 120);
    if (!t || !alertRe.test(t) || allowed(t) || alerts.has(t) || [...alerts].some((x) => x.includes(t) || t.includes(x))) continue;
    const key = "錯誤提示|" + t.slice(0, 80);
    if (baseline.has(key)) continue;
    alerts.add(t);
    items.push({ level: "doubt", label: "出現錯誤提示", snippet: t.slice(0, 80), key, mark: mark(el) });
  }
  if (!loadingMark) {
    const sp = [...root.querySelectorAll("[aria-busy=true],[class*=spinner],[class*=Spinner],[class*=skeleton],[class*=Skeleton]")].find(vis);
    if (sp) loadingMark = mark(sp);
  }
  const media = [...root.querySelectorAll("img,svg,canvas,video")].some(vis);
  const sw = document.documentElement.scrollWidth;
  return { items, textLen, blank: textLen < 2 && !media, loading: !!loadingMark, loadingMark,
    overflow: sw > window.innerWidth + 4 ? sw : 0 };
}

/** 快照：網址、畫面雜湊、開著的視窗數（UI 巡檢判斷「點了有沒有反應」） */
export function pageSnap(dialogSel) {
  const h = [...document.querySelectorAll("div")].find((x) => x.shadowRoot);
  const root = h ? h.shadowRoot : document;
  const html = (root === document ? document.body : root).innerHTML;
  let x = 5381;
  for (let i = 0; i < html.length; i++) x = ((x << 5) + x + html.charCodeAt(i)) | 0;
  const vis = (e) => e.getClientRects().length && getComputedStyle(e).visibility !== "hidden";
  return { url: location.href, h: x, len: html.length, dialogs: [...root.querySelectorAll(dialogSel)].filter(vis).length };
}

/**
 * 可點元素：不給 key＝列出全部 [{ key, n, label, tag, href, target, type }]；
 * 給 key＋n＝找到第 n 個同 key 的元素、捲到畫面中間並加 data-itest-cur，回傳中心座標（找不到回 null）。
 */
export function pageCandidates(o) {
  const h = [...document.querySelectorAll("div")].find((x) => x.shadowRoot);
  const root = h ? h.shadowRoot : document;
  const vis = (e) => { if (!e.getClientRects().length) return false; const cs = getComputedStyle(e); return cs.visibility !== "hidden" && cs.display !== "none" && cs.pointerEvents !== "none"; };
  const norm = (t) => (t || "").replace(/\s+/g, " ").trim();
  const sel = "button,[role=button],[role=tab],[role=menuitem],a[href],summary,.tab,[onclick]";
  const els = [...root.querySelectorAll(sel)].filter((e) => vis(e) && !e.disabled && e.getAttribute("aria-disabled") !== "true"
    && !/^(switch|checkbox|radio|menuitemcheckbox|menuitemradio)$/.test(e.getAttribute("role") || "")   // 開關、勾選會改設定
    && !e.closest("[data-itest-skip]") && !(e.parentElement && e.parentElement.closest(sel)));
  const count = {}, list = [];
  for (const e of els) {
    const txt = norm(e.innerText || e.textContent).slice(0, 40);
    const label = txt || norm(e.getAttribute("aria-label") || e.getAttribute("title")) || `無文字的${e.tagName === "A" ? "連結" : "按鈕"}`;
    const key = e.tagName.toLowerCase() + "|" + label;
    const n = count[key] = (count[key] || 0) + 1;
    list.push({ key, n, label, tag: e.tagName.toLowerCase(), href: e.getAttribute("href") || "", abs: e.href || "", target: e.getAttribute("target") || "",
      type: e.getAttribute("type") || "", download: e.hasAttribute("download"), el: e });
  }
  root.querySelectorAll("[data-itest-cur]").forEach((e) => e.removeAttribute("data-itest-cur"));
  if (!o || !o.key) return list.map(({ el, ...x }) => x);
  const hit = list.find((x) => x.key === o.key && x.n === o.n);
  if (!hit) return null;
  hit.el.setAttribute("data-itest-cur", "1");
  hit.el.scrollIntoView({ block: "center", inline: "center" });
  const r = hit.el.getBoundingClientRect();
  return { x: r.x + r.width / 2, y: r.y + r.height / 2, rect: { x: r.x, y: r.y, w: r.width, h: r.height } };
}
