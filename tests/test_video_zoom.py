"""
scripts/video_zoom.py（功能展示影片的鏡頭）與 video_post.src_to_out 的單元測試。

執行：python -m unittest discover -s tests -v

只測純函式：貝茲緩動、推近範圍、鏡頭關鍵格、變化有沒有跑出近景、原始秒 → 成片秒。
找得到 ffmpeg 時另外跑一段合成影片過 zoom_pass，確認輸出尺寸與格數；找不到就跳過。
"""

from __future__ import annotations
import importlib.util
import tempfile
import unittest
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent.parent / "scripts"


def load(name: str):
    spec = importlib.util.spec_from_file_location(name, SCRIPTS / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


vz = load("video_zoom")
vp = load("video_post")
Z = 1 / 1.5


class Ease(unittest.TestCase):
    def test_endpoints_and_monotonic(self):
        e = vz.EASE
        self.assertEqual(e(0), 0.0)
        self.assertEqual(e(1), 1.0)
        self.assertEqual(e(-1), 0.0)
        vals = [e(i / 50) for i in range(51)]
        self.assertEqual(vals, sorted(vals))

    def test_slow_fast_slow(self):
        e = vz.EASE
        self.assertLess(e(0.1), 0.1)             # 起步比等速慢
        self.assertGreater(e(0.9), 0.9)          # 收尾也慢（已經快到了）
        self.assertAlmostEqual(e(0.5), 0.5, places=3)

    def test_linear_curve_is_identity(self):
        lin = vz.bezier_ease(1 / 3, 1 / 3, 2 / 3, 2 / 3)
        for p in (0.2, 0.5, 0.8):
            self.assertAlmostEqual(lin(p), p, places=6)


class FocusBox(unittest.TestCase):
    def test_centered(self):
        x0, y0, s = vz.focus_box(0.5, 0.5, 1.5)
        self.assertAlmostEqual(s, Z)
        self.assertAlmostEqual(x0 + s / 2, 0.5)
        self.assertAlmostEqual(y0 + s / 2, 0.5)

    def test_clamped_to_frame(self):
        self.assertEqual(vz.focus_box(0.02, 0.01, 1.5)[:2], (0.0, 0.0))
        x0, y0, s = vz.focus_box(0.99, 0.98, 1.5)
        self.assertAlmostEqual(x0 + s, 1.0)
        self.assertAlmostEqual(y0 + s, 1.0)

    def test_zoom_below_one_is_full(self):
        self.assertEqual(vz.focus_box(0.3, 0.3, 0.5), vz.FULL)


class Camera(unittest.TestCase):
    def focus(self, frm, x=0.5, y=0.5, hold=1.5, rel=None, limit=None, **kw):
        act = frm + hold
        return {"frm": frm, "act": act, "rel": rel if rel is not None else act + 0.6,
                "limit": limit if limit is not None else act + 10, "x": x, "y": y, **kw}

    def test_single_step_in_and_out(self):
        f = self.focus(5.0, x=0.2, y=0.3)
        keys = vz.plan_camera([f])
        box = vz.focus_box(0.2, 0.3, 1.5)
        self.assertEqual(vz.camera_at(keys, 5.0), vz.FULL)             # 字幕剛出現：還是全景
        self.assertEqual(vz.camera_at(keys, f["act"]), box)            # 動作那一刻：已經推到位
        self.assertEqual(vz.camera_at(keys, f["rel"] - 0.01), box)     # 拉回前都在近景
        self.assertEqual(vz.camera_at(keys, f["rel"] + 0.71), vz.FULL)
        mid = vz.camera_at(keys, 5.15 + 0.35)                          # 推近到一半：介於兩者之間
        self.assertTrue(box[2] < mid[2] < 1.0)
        times = [t for t, _ in keys]
        self.assertEqual(times, sorted(times))

    def test_short_hold_not_zoomed(self):
        keys = vz.plan_camera([self.focus(5.0, hold=0.3)])
        self.assertTrue(all(st == vz.FULL for _, st in keys))

    def test_chain_pans_without_zooming_out(self):
        a = self.focus(5.0, x=0.3, y=0.4, chain=True)
        b = self.focus(8.5, x=0.6, y=0.6)
        keys = vz.plan_camera([a, b])
        for t in (a["act"], 7.0, 8.0, 8.4, b["frm"] + 0.2, b["act"]):   # 兩步之間一直在近景
            self.assertAlmostEqual(vz.camera_at(keys, t)[2], Z)
        self.assertEqual(vz.camera_at(keys, a["act"] + 0.2), vz.focus_box(0.3, 0.4, 1.5))
        self.assertEqual(vz.camera_at(keys, b["frm"] + 0.2), vz.focus_box(0.6, 0.6, 1.5))
        self.assertEqual(vz.camera_at(keys, b["rel"] + 1.0), vz.FULL)

    def test_unchained_steps_return_to_full_between(self):
        a = self.focus(5.0, x=0.3, y=0.4, limit=9.0)
        b = self.focus(9.0, x=0.6, y=0.6)
        keys = vz.plan_camera([a, b])
        self.assertEqual(vz.camera_at(keys, 8.5), vz.FULL)
        self.assertEqual(vz.camera_at(keys, b["act"]), vz.focus_box(0.6, 0.6, 1.5))

    def test_zoom_out_finishes_before_limit(self):
        f = self.focus(5.0, rel=9.0, limit=7.5)                        # 字卡在 7.5 秒：之前要拉回完
        keys = vz.plan_camera([f])
        self.assertEqual(vz.camera_at(keys, 7.5), vz.FULL)

    def test_state_stays_inside_frame(self):
        a = self.focus(5.0, x=0.01, y=0.99, chain=True)
        b = self.focus(8.0, x=0.99, y=0.01)
        keys = vz.plan_camera([a, b])
        for i in range(0, 300):
            x0, y0, s = vz.camera_at(keys, i / 20)
            self.assertGreaterEqual(x0, -1e-9); self.assertGreaterEqual(y0, -1e-9)
            self.assertLessEqual(x0 + s, 1 + 1e-9); self.assertLessEqual(y0 + s, 1 + 1e-9)


class Reveal(unittest.TestCase):
    SIZE = (1000, 500)
    VIEW = (0.2, 0.2, 0.8, 0.8)

    def test_change_inside_view(self):
        boxes = [None] * 10 + [(300, 150, 700, 350)] * 5
        self.assertIsNone(vz.reveal_time(boxes, 10, 0.0, 2.0, self.VIEW, self.SIZE))

    def test_big_change_outside_view(self):
        boxes = [None] * 10 + [(0, 0, 999, 300)] * 5                   # 整頁上半部都變了
        self.assertAlmostEqual(vz.reveal_time(boxes, 10, 0.0, 2.0, self.VIEW, self.SIZE), 1.0)

    def test_small_change_outside_ignored(self):
        boxes = [None] * 10 + [(0, 0, 60, 40)] * 5                     # 角落的小東西（游標、提示）
        self.assertIsNone(vz.reveal_time(boxes, 10, 0.0, 2.0, self.VIEW, self.SIZE))

    def test_only_within_time_range(self):
        boxes = [(0, 0, 999, 300)] + [None] * 30
        self.assertIsNone(vz.reveal_time(boxes, 10, 1.0, 2.0, self.VIEW, self.SIZE))


class SrcToOut(unittest.TestCase):
    def test_follows_fast_forward(self):
        evs = [{"A": 0.0, "kind": "step", "text": "按「查詢」"}]
        clips, _ = vp.plan_clips(evs, [(1.0, 7.0)], 10.0, idle=1.2, cps=5, fps=30, intro=False, outro=False)
        c = clips[0]
        ps = c["play_start"]
        self.assertAlmostEqual(vp.src_to_out(clips, 0.5), ps + 0.5)
        self.assertAlmostEqual(vp.src_to_out(clips, 4.0), ps + 1.0 + 0.6)      # 6 秒壓成 1.2 秒：走到一半
        self.assertAlmostEqual(vp.src_to_out(clips, 8.0), ps + 1.0 + 1.2 + 1.0)

    def test_trimmed_head_is_none(self):
        evs = [{"A": 2.0, "kind": "step", "text": "點"}]
        clips, _ = vp.plan_clips(evs, [], 5.0, idle=1.2, cps=5, fps=30, intro=False, outro=False)
        self.assertIsNone(vp.src_to_out(clips, 1.0))
        self.assertIsNotNone(vp.src_to_out(clips, 3.0))


class CaptionPlace(unittest.TestCase):
    def test_full_view(self):
        self.assertFalse(vp.caption_on_top(0.5, 0.5))
        self.assertTrue(vp.caption_on_top(0.8, 0.95))       # 對話框右下角的「儲存」

    def test_zoomed_view_uses_position_inside_box(self):
        # 近景會夾在畫面邊緣：靠底的按鈕在近景裡還是在底部 → 上移
        self.assertTrue(vp.caption_on_top(0.8, 0.95, 1.5))
        # 全景 y=0.75 不在字幕列；推近後置中，也不在
        self.assertFalse(vp.caption_on_top(0.5, 0.75, 1.5))
        self.assertFalse(vp.caption_on_top(0.5, 0.5, 1.5))


def _ffmpeg():
    try:
        return vp.ffmpeg_bin()
    except SystemExit:
        return None


@unittest.skipUnless(_ffmpeg(), "找不到 ffmpeg")
class ZoomPass(unittest.TestCase):
    def test_master_to_output(self):
        with tempfile.TemporaryDirectory() as d:
            work = Path(d)
            vp.run(["-f", "lavfi", "-i", "testsrc=size=640x360:rate=30:duration=2", "-c:v", "libx264", "-pix_fmt", "yuv420p",
                    str(work / "joined.mp4")])
            keys = vz.plan_camera([{"frm": 0.2, "act": 1.2, "rel": 1.4, "limit": 1.9, "x": 0.25, "y": 0.25}])
            vz.zoom_pass(_ffmpeg(), work, keys, src="joined.mp4", master=(640, 360), out_size=(320, 180), fps=30,
                         pre_vf="null", enc_args=["-c:v", "libx264", "-pix_fmt", "yuv420p"], out_name="out.mp4", jobs=2)
            dur, w, h = vp.probe(work / "out.mp4")
            self.assertEqual((w, h), (320, 180))
            self.assertAlmostEqual(dur, 2.0, delta=0.15)


if __name__ == "__main__":
    unittest.main()
