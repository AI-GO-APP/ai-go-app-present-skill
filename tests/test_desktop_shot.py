"""
scripts/desktop_shot.py 與 deck_kit 新元件的單元測試（標準函式庫 unittest）。

執行：python -m unittest discover -s tests -v

不碰真實螢幕：只測純函式（PNG 編碼、參數解析、manifest 併寫）與 deck_kit 的 HTML 產生。
Windows 上另外測 win_list_windows／win_capture 能跑（抓 4×4 的小區域），其他平台跳過。
"""

from __future__ import annotations
import contextlib
import importlib.util
import io
import json
import platform
import shutil
import struct
import tempfile
import unittest
import zlib
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent.parent / "scripts"


def load(name: str):
    spec = importlib.util.spec_from_file_location(name, SCRIPTS / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


ds = load("desktop_shot")
dk = load("deck_kit")


def decode_png_rgb(data: bytes) -> tuple[int, int, bytes]:
    """最小 PNG 解碼（只支援本模組產出的 8-bit RGB、filter 0），用來驗證編碼器。"""
    assert data[:8] == b"\x89PNG\r\n\x1a\n"
    pos, idat, w = 8, b"", 0
    while pos < len(data):
        (n,) = struct.unpack(">I", data[pos:pos + 4])
        tag, body = data[pos + 4:pos + 8], data[pos + 8:pos + 8 + n]
        if tag == b"IHDR":
            w, h, depth, ctype = struct.unpack(">IIBB", body[:10])
            assert (depth, ctype) == (8, 2)
        elif tag == b"IDAT":
            idat += body
        pos += 12 + n
    raw = zlib.decompress(idat)
    stride = w * 3 + 1
    rows = [raw[i * stride + 1:(i + 1) * stride] for i in range(h)]
    assert all(raw[i * stride] == 0 for i in range(h))
    return w, h, b"".join(rows)


class PngTests(unittest.TestCase):
    def test_encode_roundtrip_channel_order(self):
        # 2×2，BGRA：紅、綠 ／ 藍、白
        px = [(0, 0, 255, 255), (0, 255, 0, 255), (255, 0, 0, 255), (255, 255, 255, 255)]
        bgra = bytes(c for p in px for c in p)
        w, h, rgb = decode_png_rgb(ds.encode_png(2, 2, bgra))
        self.assertEqual((w, h), (2, 2))
        self.assertEqual(rgb, bytes([255, 0, 0, 0, 255, 0, 0, 0, 255, 255, 255, 255]))

    def test_png_size_reads_header(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "x.png"
            p.write_bytes(ds.encode_png(3, 5, bytes(3 * 5 * 4)))
            self.assertEqual(ds.png_size(p), (3, 5))


class ArgParsingTests(unittest.TestCase):
    def test_region(self):
        self.assertEqual(ds.parse_region("10, 20,300,400"), (10, 20, 300, 400))
        for bad in ("1,2,3", "1,2,0,4", "a,b,c,d"):
            with self.assertRaises(ValueError):
                ds.parse_region(bad)

    def test_mark(self):
        self.assertEqual(ds.parse_mark("2:5,6,70,80"), {"n": 2, "x": 5, "y": 6, "w": 70, "h": 80})
        self.assertEqual(ds.parse_mark("·:1,1,1,1")["n"], "·")
        with self.assertRaises(ValueError):
            ds.parse_mark("1,2,3,4")


class ManifestTests(unittest.TestCase):
    def test_merge_keeps_existing_entries(self):
        with tempfile.TemporaryDirectory() as d:
            mf = Path(d) / "shots.json"
            mf.write_text(json.dumps({"browser-shot": {"w": 1600, "h": 900, "full": True, "marks": []}}), encoding="utf-8")
            ds.merge_manifest(mf, "desk", {"w": 800, "h": 600, "kind": "desktop", "marks": [], "full": False, "note": ""})
            man = json.loads(mf.read_text(encoding="utf-8"))
            self.assertEqual(set(man), {"browser-shot", "desk"})
            self.assertEqual(man["desk"]["kind"], "desktop")

    def test_merge_tolerates_bom_and_garbage(self):
        with tempfile.TemporaryDirectory() as d:
            mf = Path(d) / "shots.json"
            mf.write_bytes("﻿{}".encode("utf-8"))
            ds.merge_manifest(mf, "a", {"w": 1, "h": 1})
            mf.write_text("not json", encoding="utf-8")
            ds.merge_manifest(mf, "b", {"w": 1, "h": 1})
            self.assertEqual(list(json.loads(mf.read_text(encoding="utf-8"))), ["b"])


@unittest.skipUnless(platform.system() == "Windows", "只在 Windows 測真實擷取")
class WindowsCaptureTests(unittest.TestCase):
    def test_capture_small_region_is_valid_png(self):
        ds._win_dpi_aware()
        data = ds.win_capture((0, 0, 4, 4))
        w, h, rgb = decode_png_rgb(data)
        self.assertEqual((w, h, len(rgb)), (4, 4, 48))

    def test_list_windows_returns_rects(self):
        ds._win_dpi_aware()
        wins = ds.win_list_windows()
        self.assertTrue(wins)
        hwnd, title, (x, y, w, h) = wins[0]
        self.assertTrue(title and w > 0 and h > 0)

    def test_cli_screen_writes_png_and_manifest(self):
        with tempfile.TemporaryDirectory() as d, contextlib.redirect_stdout(io.StringIO()):
            rc = ds.main(["--name", "s", "--region", "0,0,8,6", "--out", d, "--delay", "0", "--mark", "1:1,1,2,2"])
            self.assertEqual(rc, 0)
            self.assertEqual(ds.png_size(Path(d) / "s.png"), (8, 6))
            man = json.loads((Path(d) / "shots.json").read_text(encoding="utf-8"))
            self.assertEqual(man["s"]["kind"], "desktop")
            self.assertFalse(man["s"]["full"])  # --region 裁的局部不包框
            self.assertEqual(man["s"]["marks"][0]["n"], 1)


class DeckKitTests(unittest.TestCase):
    def deck(self, man: dict) -> "dk.Deck":
        d = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, d, ignore_errors=True)
        (Path(d) / "shots.json").write_text(json.dumps(man), encoding="utf-8")
        return dk.Deck(tenant="租戶", app="App", purposes=["操作說明"], shots=d)

    def test_whole_desktop_window_gets_window_frame_with_title(self):
        d = self.deck({"win": {"w": 1000, "h": 500, "full": True, "kind": "desktop", "title": "LINE <測試>", "marks": []}})
        html = d.shot("win", 800)
        self.assertIn('class="shot framed window', html)
        self.assertIn("LINE &lt;測試&gt;", html)

    def test_desktop_crop_gets_no_frame(self):
        d = self.deck({"part": {"w": 640, "h": 360, "full": False, "kind": "desktop", "marks": []}})
        self.assertNotIn("framed", d.shot("part", 600))
        self.assertNotIn("framed", d.fig("part", 600))
        self.assertIn("framed window", d.fig("part", 600, frame="window"))

    def test_browser_full_shot_unchanged(self):
        d = self.deck({"full": {"w": 1600, "h": 900, "full": True, "marks": []}})
        self.assertIn('class="shot framed browser', d.shot("full", 800))
        self.assertNotIn("<span>", d.shot("full", 800))

    def test_frame_override(self):
        d = self.deck({"win": {"w": 1000, "h": 500, "full": True, "kind": "desktop", "marks": []}})
        self.assertNotIn("framed", d.shot("win", 800, frame=False))
        self.assertIn("framed browser", d.shot("win", 800, frame="browser"))

    def test_term_escapes_and_redacts(self):
        html = dk.Deck.term([("npm install <pkg>", "added 1 package"), ("export TOKEN=abc123", "")],
                            title="skill 目錄", redact=["abc123"])
        self.assertIn("npm install &lt;pkg&gt;", html)
        self.assertIn("<pre>added 1 package</pre>", html)
        self.assertIn("TOKEN=••••", html)
        self.assertNotIn("abc123", html)
        self.assertIn("<span>skill 目錄</span>", html)
        self.assertEqual(html.count('class="cmd"'), 2)

    def test_term_single_string(self):
        html = dk.Deck.term("git pull")
        self.assertEqual(html.count('class="cmd"'), 1)
        self.assertNotIn("<pre>", html)


if __name__ == "__main__":
    unittest.main()
