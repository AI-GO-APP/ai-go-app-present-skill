// scripts/motion.mjs（錄影游標的貝茲弧線與緩動）的單元測試：node --test tests/*.test.mjs
import test from "node:test";
import assert from "node:assert/strict";
import { bezierEase, EASE, cubicPoint, cursorPath, cursorDuration, sampleCursor } from "../scripts/motion.mjs";

test("緩動：頭尾固定、單調遞增、慢 → 快 → 慢", () => {
  assert.equal(EASE(0), 0);
  assert.equal(EASE(1), 1);
  let prev = 0;
  for (let i = 1; i <= 50; i++) { const v = EASE(i / 50); assert.ok(v >= prev); prev = v; }
  assert.ok(EASE(0.1) < 0.1);
  assert.ok(EASE(0.9) > 0.9);
  const lin = bezierEase(1 / 3, 1 / 3, 2 / 3, 2 / 3);
  assert.ok(Math.abs(lin(0.3) - 0.3) < 1e-6);
});

test("貝茲曲線：t=0 在起點、t=1 在終點", () => {
  const [a, c1, c2, b] = cursorPath({ x: 100, y: 500 }, { x: 900, y: 300 });
  assert.deepEqual(cubicPoint(a, c1, c2, b, 0), { x: 100, y: 500 });
  assert.deepEqual(cubicPoint(a, c1, c2, b, 1), { x: 900, y: 300 });
});

test("游標路徑是弧線：中段離開直線、往上拱，幅度有上限", () => {
  const a = { x: 100, y: 500 }, b = { x: 1100, y: 500 };
  const pts = sampleCursor(a, b, 24);
  assert.deepEqual(pts[0], [100, 500]);
  assert.deepEqual(pts[24], [1100, 500]);
  const top = Math.min(...pts.map((q) => q[1]));
  assert.ok(top < 480, "水平移動要往上拱");
  assert.ok(top > 500 - 140, "拱的幅度不超過 140px");
  for (let i = 1; i < pts.length; i++) assert.ok(pts[i][0] >= pts[i - 1][0], "不回頭");
});

test("很短的移動幾乎是直線；原地不動不出錯", () => {
  const pts = sampleCursor({ x: 300, y: 300 }, { x: 320, y: 300 }, 12);
  assert.ok(Math.min(...pts.map((q) => q[1])) > 300 - 6);
  const same = sampleCursor({ x: 5, y: 5 }, { x: 5, y: 5 }, 6);
  assert.ok(same.every((q) => q[0] === 5 && q[1] === 5));
});

test("控制點夾在畫面內", () => {
  const [, c1, c2] = cursorPath({ x: 10, y: 5 }, { x: 1500, y: 8 }, { w: 1600, h: 900 });
  assert.ok(c1.y >= 0 && c2.y >= 0);
  for (const q of sampleCursor({ x: 10, y: 5 }, { x: 1500, y: 8 }, 24, { w: 1600, h: 900 })) assert.ok(q[1] >= 0);
});

test("移動時間：近的快、遠的慢、有上限", () => {
  const near = cursorDuration({ x: 0, y: 0 }, { x: 50, y: 0 });
  const far = cursorDuration({ x: 0, y: 0 }, { x: 800, y: 0 });
  assert.ok(near < far);
  assert.equal(cursorDuration({ x: 0, y: 0 }, { x: 5000, y: 0 }), 1100);
});
