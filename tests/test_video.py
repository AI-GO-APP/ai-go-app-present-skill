"""
scripts/video_post.py 的單元測試（標準函式庫 unittest＋Pillow）。

執行：python -m unittest discover -s tests -v

只測純函式：檔名、錨點、靜止偵測、剪輯表。找得到 ffmpeg 時另外跑一個 3 秒的合成影片 probe，找不到就跳過。
"""

from __future__ import annotations
import datetime as dt
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


vp = load("video_post")
MADE = dt.date(2026, 11, 15)


class Filename(unittest.TestCase):
    def test_manual(self):
        self.assertEqual(vp.video_filename("展示公司", "訂單中心", MADE, "操作說明"),
                         "AI GO 展示公司 訂單中心 操作說明 20261115.mp4")

    def test_showcase(self):
        self.assertTrue(vp.video_filename("展示公司", "訂單中心", MADE, "功能展示").endswith("功能展示 20261115.mp4"))

    def test_part_sanitized(self):
        self.assertEqual(vp.video_filename("展示公司", "訂單中心", MADE, "操作說明", "1 新增/查詢"),
                         "AI GO 展示公司 訂單中心 操作說明 20261115 1 新增_查詢.mp4")

    def test_other_purpose_rejected(self):
        with self.assertRaises(ValueError):
            vp.video_filename("展示公司", "訂單中心", MADE, "測試報告")


class Anchor(unittest.TestCase):
    def test_at_is_exact(self):
        self.assertEqual(vp.anchor({"t": 2.0, "when": "at"}, [(1.0, 3.0)], 10), 2.0)

    def test_at_clamped(self):
        self.assertEqual(vp.anchor({"t": 12.0}, [], 10), 10)

    def test_before_snaps_to_end_of_static_span(self):
        self.assertAlmostEqual(vp.anchor({"t": 1.5, "when": "before"}, [(1.0, 3.0)], 10), 2.85)

    def test_before_outside_span_keeps_time(self):
        self.assertEqual(vp.anchor({"t": 3.5, "when": "before"}, [(1.0, 3.0)], 10), 3.5)

    def test_after_skips_short_toast_gap(self):
        # 思考 0–4 秒 → 動作 → toast 出現（4.5–5.0 短暫靜止）→ toast 消失 → 6 秒才記 did
        fz = [(0.0, 4.0), (4.5, 5.0)]
        self.assertAlmostEqual(vp.anchor({"t": 6.0, "when": "after"}, fz, 10), 3.85)

    def test_after_without_prior_span(self):
        self.assertEqual(vp.anchor({"t": 6.0, "when": "after"}, [], 10), 6.0)


class Activity(unittest.TestCase):
    def frames(self, *paints):
        from PIL import Image, ImageDraw
        out = []
        for box in paints:
            im = Image.new("L", (80, 80), 0)
            if box:
                ImageDraw.Draw(im).rectangle(box, fill=255)
            out.append(im)
        return out

    def test_detects_block_ignores_noise_and_caret(self):
        act, boxes = vp.activity(self.frames(
            None,
            None,                 # 沒變
            (5, 5, 5, 5),         # 1 個像素：雜訊
            (5, 5, 5, 5),
            None,                 # 1 個像素消失：雜訊
            (40, 10, 41, 40),     # 細直線：閃爍的輸入游標
            None,
            (10, 10, 20, 20),     # 一塊：真的在變
        ))
        self.assertEqual(act, [False, False, False, False, False, False, False, True])
        self.assertIsNotNone(boxes[-1])


class IdleSpans(unittest.TestCase):
    def test_all_static(self):
        self.assertEqual(vp.idle_spans([False] * 30, [None] * 30, 10, 3.0, 1.2, 10000), [(0.0, 3.0)])

    def test_short_tail_not_idle(self):
        act = [False] * 20 + [True] * 5 + [False] * 5
        boxes = [None] * 20 + [(0, 0, 50, 50)] * 5 + [None] * 5
        self.assertEqual(vp.idle_spans(act, boxes, 10, 3.0, 1.2, 10000), [(0.0, 2.0)])

    def test_spinner_counts_as_waiting(self):
        act = [True] * 50
        boxes = [(10, 10, 14, 14)] * 50            # 一直在轉、但只佔一小塊
        spans = vp.idle_spans(act, boxes, 10, 5.0, 1.2, 100 * 100)
        self.assertEqual(spans, [(0.5, 5.0)])

    def test_large_long_change_is_not_spinner(self):
        act = [True] * 50
        boxes = [(0, 0, 90, 90)] * 50
        self.assertEqual(vp.idle_spans(act, boxes, 10, 5.0, 1.2, 100 * 100), [])


class PlanClips(unittest.TestCase):
    EVS = [
        {"A": 1.0, "kind": "chapter", "text": "新增一張訂單", "sub": ""},
        {"A": 2.0, "kind": "step", "text": "點右上角「＋ 新增訂單」"},
    ]

    def test_structure_and_hold(self):
        clips, total = vp.plan_clips(self.EVS, [], 5.0, idle=1.2, cps=5, fps=30)
        kinds = [c.get("card") or "video" for c in clips]
        self.assertEqual(kinds, ["intro", "chapter", "video", "video", "outro"])
        first, second = clips[2], clips[3]
        self.assertEqual((first["s"], first["e"]), (1.0, 2.0))
        self.assertIs(second["from_prev"], first)
        need = 0.8 + vp.text_len(self.EVS[1]["text"]) / 5
        self.assertGreaterEqual(first["hold"] + 3.0, need)        # 凍結＋播放 ≥ 讀完字幕
        self.assertGreaterEqual(first["hold"], 1.0)
        self.assertAlmostEqual(second["hold"], 1.5)               # 結尾停住
        self.assertAlmostEqual(total, clips[-1]["end"])
        self.assertAlmostEqual(total, 3.2 + 2.4 + 1.0 + first["hold"] + 3.0 + 1.5 + 3.0)

    def test_head_trimmed_unless_keep_head(self):
        clips, _ = vp.plan_clips(self.EVS, [], 5.0, idle=1.2, cps=5, fps=30, intro=False, outro=False)
        self.assertEqual(clips[1]["s"], 1.0)
        clips, _ = vp.plan_clips(self.EVS, [], 5.0, idle=1.2, cps=5, fps=30, intro=False, outro=False, keep_head=True)
        self.assertEqual(clips[0]["s"], 0.0)

    def test_fast_forward_pieces(self):
        evs = [{"A": 0.0, "kind": "step", "text": "按「查詢」"}]
        clips, _ = vp.plan_clips(evs, [(1.0, 7.0), (8.0, 9.0)], 10.0, idle=1.2, cps=5, fps=30, intro=False, outro=False)
        pieces = clips[0]["pieces"]
        self.assertEqual(pieces[0], (0.0, 1.0, 1.0, 0))
        self.assertEqual(pieces[1], (1.0, 7.0, 6.0 / 1.2, 6.0))   # ≥ 4 秒：壓成 1.2 秒、標略過 6 秒
        self.assertEqual(pieces[2], (7.0, 10.0, 1.0, 0))           # 1 秒的靜止 < idle：照常播


class Times(unittest.TestCase):
    def test_formats(self):
        self.assertEqual(vp.ass_time(3725.456), "1:02:05.46")
        self.assertEqual(vp.srt_time(3725.456), "01:02:05,456")
        self.assertEqual(vp.srt_time(-1), "00:00:00,000")


def _ffmpeg():
    try:
        return vp.ffmpeg_bin()
    except SystemExit:
        return None


@unittest.skipUnless(_ffmpeg(), "找不到 ffmpeg")
class FfmpegSmoke(unittest.TestCase):
    def test_probe_and_freezes(self):
        with tempfile.TemporaryDirectory() as d:
            out = Path(d) / "t.mkv"
            # 前 1 秒在動（testsrc），後 2 秒純色靜止
            vp.run(["-f", "lavfi", "-i", "testsrc=size=320x180:rate=30:duration=1",
                    "-f", "lavfi", "-i", "color=c=gray:size=320x180:rate=30:duration=2",
                    "-filter_complex", "[0:v][1:v]concat=n=2:v=1[v]", "-map", "[v]",
                    "-c:v", "libx264", "-pix_fmt", "yuv420p", str(out)])
            dur, w, h = vp.probe(out)
            self.assertAlmostEqual(dur, 3.0, delta=0.15)   # time= 是最後一格的開始
            self.assertEqual((w, h), (320, 180))
            fz = vp.freezes(out, 1.2, dur, w, h)
            self.assertEqual(len(fz), 1)
            self.assertAlmostEqual(fz[0][0], 1.0, delta=0.15)


if __name__ == "__main__":
    unittest.main()
