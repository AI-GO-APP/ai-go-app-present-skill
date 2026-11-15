/**
 * 錄影用的游標運動：沿三次貝茲曲線（Bézier curve）走弧線，速度用 cubic-bezier 緩動（慢 → 快 → 慢）。
 * 純函式，record.mjs 用；tests/motion.test.mjs 測。
 */

/** CSS 的 cubic-bezier(x1, y1, x2, y2)：回傳「時間進度 0～1 → 動畫進度 0～1」的函式。 */
export function bezierEase(x1, y1, x2, y2) {
  const bx = (t) => 3 * (1 - t) * (1 - t) * t * x1 + 3 * (1 - t) * t * t * x2 + t * t * t;
  const by = (t) => 3 * (1 - t) * (1 - t) * t * y1 + 3 * (1 - t) * t * t * y2 + t * t * t;
  return (p) => {
    if (p <= 0) return 0;
    if (p >= 1) return 1;
    let lo = 0, hi = 1;
    for (let i = 0; i < 40; i++) {           // x(t) 單調遞增：二分法解 t
      const mid = (lo + hi) / 2;
      if (bx(mid) < p) lo = mid; else hi = mid;
    }
    return by((lo + hi) / 2);
  };
}

export const EASE = bezierEase(0.45, 0, 0.25, 1);

/** 三次貝茲曲線上 t（0～1）那一點。 */
export function cubicPoint(p0, p1, p2, p3, t) {
  const u = 1 - t;
  const a = u * u * u, b = 3 * u * u * t, c = 3 * u * t * t, d = t * t * t;
  return { x: a * p0.x + b * p1.x + c * p2.x + d * p3.x, y: a * p0.y + b * p1.y + c * p2.y + d * p3.y };
}

/**
 * 從 a 到 b 的游標路徑控制點：往上（或往右）拱的不對稱弧線——出發時甩出去、接近目標時收直，像手在移滑鼠。
 * 拱的幅度隨距離變大（上限 140px）；bounds {w, h} 有給就把控制點夾在畫面內。
 */
export function cursorPath(a, b, bounds) {
  const dx = b.x - a.x, dy = b.y - a.y, d = Math.hypot(dx, dy);
  if (d < 1) return [a, a, b, b];
  let nx = -dy / d, ny = dx / d;
  if (ny > 0 || (ny === 0 && nx < 0)) { nx = -nx; ny = -ny; }
  const off = Math.min(140, d * 0.22);
  const clamp = (p) => (bounds ? { x: Math.min(bounds.w, Math.max(0, p.x)), y: Math.min(bounds.h, Math.max(0, p.y)) } : p);
  const c1 = clamp({ x: a.x + dx * 0.25 + nx * off, y: a.y + dy * 0.25 + ny * off });
  const c2 = clamp({ x: a.x + dx * 0.75 + nx * off * 0.35, y: a.y + dy * 0.75 + ny * off * 0.35 });
  return [a, c1, c2, b];
}

/** 移動時間（毫秒）：近的快、遠的慢，上限 1.1 秒。 */
export function cursorDuration(a, b) {
  return Math.round(Math.min(1100, 350 + Math.hypot(b.x - a.x, b.y - a.y) * 0.7));
}

/** 路徑取樣 n+1 點（含起點與終點），時間等距、位置已套緩動：直接當動畫關鍵格或逐點移動滑鼠。 */
export function sampleCursor(a, b, n = 24, bounds) {
  const [p0, p1, p2, p3] = cursorPath(a, b, bounds);
  const pts = [];
  for (let i = 0; i <= n; i++) {
    const q = cubicPoint(p0, p1, p2, p3, EASE(i / n));
    pts.push([Math.round(q.x * 10) / 10, Math.round(q.y * 10) / 10]);
  }
  pts[0] = [a.x, a.y];
  pts[n] = [b.x, b.y];
  return pts;
}
