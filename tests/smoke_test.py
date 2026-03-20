#!/usr/bin/env python3
"""
tests/smoke_test.py
Minimal smoke-test for the videomaker3 pipeline.

Tests:
  1. media_fetch.py – path/fallback logic (no real network calls)
  2. video_creation.py – _find_media_files priority ordering
  3. server.py – /generate endpoint accepts media_mode; invalid values rejected

Run with:
  python -m pytest tests/smoke_test.py -v
or:
  python tests/smoke_test.py
"""

import os
import sys
import types
import unittest
import tempfile

# ── ensure repo root is on path ──────────────────────────────────────────────
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)


# ─────────────────────────────────────────────────────────────────────────────
# Stub heavy modules so the tests don't need ffmpeg / MoviePy / network
# ─────────────────────────────────────────────────────────────────────────────

def _make_stub(name):
    """Return a minimal module stub."""
    mod = types.ModuleType(name)
    sys.modules[name] = mod
    return mod


for _name in (
    "moviepy",
    "moviepy.config",
    "moviepy.editor",
    "moviepy.video",
    "moviepy.video.fx",
    "moviepy.video.fx.loop",
    "googletrans",
    "tqdm",
    "PIL",
    "PIL.Image",
):
    if _name not in sys.modules:
        _make_stub(_name)

# tqdm.tqdm passthrough
sys.modules["tqdm"].tqdm = lambda it, **kw: it  # type: ignore

# PIL.Image stub
class _FakeImage:
    @staticmethod
    def open(*a, **kw):
        return _FakeImage()
    def convert(self, *a):
        return self
    def save(self, *a, **kw):
        pass

sys.modules["PIL"].Image = _FakeImage  # type: ignore
sys.modules["PIL.Image"].open = _FakeImage.open  # type: ignore

# googletrans stub
class _FakeTranslation:
    text = "test prompt in english"

class _FakeTranslator:
    def translate(self, text, **kw):
        return _FakeTranslation()

sys.modules["googletrans"].Translator = _FakeTranslator  # type: ignore

# moviepy.config stub (used by server.py)
_mpy_config = sys.modules["moviepy.config"]
_mpy_config.FFMPEG_BINARY = "ffmpeg"  # type: ignore
_mpy_config.IMAGEMAGICK_BINARY = "convert"  # type: ignore

# moviepy.editor stubs (used by video_creation.py)
class _FakeClip:
    duration = 1.0
    w = 1080
    h = 1920
    def __init__(self, *a, **kw): pass
    def resize(self, *a, **kw): return self
    def set_audio(self, *a, **kw): return self
    def set_position(self, *a, **kw): return self
    def subclip(self, *a, **kw): return self
    def fx(self, *a, **kw): return self
    def close(self): pass

_mpy_editor = sys.modules["moviepy.editor"]
_mpy_editor.ImageClip = _FakeClip  # type: ignore
_mpy_editor.VideoFileClip = _FakeClip  # type: ignore
_mpy_editor.AudioFileClip = _FakeClip  # type: ignore
_mpy_editor.ColorClip = _FakeClip  # type: ignore
_mpy_editor.CompositeVideoClip = _FakeClip  # type: ignore
_mpy_editor.concatenate_videoclips = lambda clips, **kw: _FakeClip()  # type: ignore

# moviepy.video.fx.loop stub
sys.modules["moviepy.video.fx.loop"].loop = lambda clip, **kw: clip  # type: ignore


# ─────────────────────────────────────────────────────────────────────────────
# 1. media_fetch – _translate_to_english / save_image helpers
# ─────────────────────────────────────────────────────────────────────────────

class TestMediaFetchHelpers(unittest.TestCase):

    def test_translate_returns_string(self):
        from utils.media_fetch import _translate_to_english
        result = _translate_to_english("الذكاء الاصطناعي")
        self.assertIsInstance(result, str)
        self.assertTrue(len(result) > 0)

    def test_allowed_modes_constant(self):
        # fetch_media_main should accept these modes without raising
        from utils import media_fetch
        allowed = {"pollinations", "bing_scrape", "search_apis"}
        # Just verify the function exists and the module loads
        self.assertTrue(callable(media_fetch.fetch_media_main))

    def test_save_image_from_bytes_bad_data(self):
        from utils.media_fetch import _save_image_from_bytes
        with tempfile.TemporaryDirectory() as tmp:
            dest = os.path.join(tmp, "test.jpg")
            # _FakeImage.save always succeeds, so just check it returns bool
            result = _save_image_from_bytes(b"not real image data", dest)
            self.assertIsInstance(result, bool)


# ─────────────────────────────────────────────────────────────────────────────
# 2. video_creation – _find_media_files priority logic
# ─────────────────────────────────────────────────────────────────────────────

class TestFindMediaFiles(unittest.TestCase):

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.media_dir  = os.path.join(self.tmp, "media")
        self.images_dir = os.path.join(self.tmp, "images")
        os.makedirs(self.media_dir)
        os.makedirs(self.images_dir)

    def _touch(self, path):
        open(path, "w").close()

    def test_mp4_preferred_over_jpg(self):
        from utils.video_creation import _find_media_files
        self._touch(os.path.join(self.images_dir, "part0.jpg"))
        self._touch(os.path.join(self.media_dir,  "part0.mp4"))
        files = _find_media_files(self.tmp)
        self.assertEqual(len(files), 1)
        self.assertTrue(files[0].endswith(".mp4"))

    def test_media_jpg_preferred_over_legacy_images_jpg(self):
        from utils.video_creation import _find_media_files
        self._touch(os.path.join(self.images_dir, "part0.jpg"))
        self._touch(os.path.join(self.media_dir,  "part0.jpg"))
        files = _find_media_files(self.tmp)
        self.assertEqual(len(files), 1)
        self.assertIn("media", files[0])

    def test_legacy_only_fallback(self):
        from utils.video_creation import _find_media_files
        self._touch(os.path.join(self.images_dir, "part0.jpg"))
        files = _find_media_files(self.tmp)
        self.assertEqual(len(files), 1)
        self.assertIn("images", files[0])

    def test_sorted_order(self):
        from utils.video_creation import _find_media_files
        for i in (2, 0, 1):
            self._touch(os.path.join(self.media_dir, f"part{i}.jpg"))
        files = _find_media_files(self.tmp)
        indices = [
            int(os.path.splitext(os.path.basename(f))[0].replace("part", ""))
            for f in files
        ]
        self.assertEqual(indices, sorted(indices))

    def test_mixed_mp4_and_jpg(self):
        from utils.video_creation import _find_media_files
        self._touch(os.path.join(self.media_dir, "part0.mp4"))
        self._touch(os.path.join(self.media_dir, "part1.jpg"))
        files = _find_media_files(self.tmp)
        self.assertEqual(len(files), 2)
        self.assertTrue(files[0].endswith(".mp4"))
        self.assertTrue(files[1].endswith(".jpg"))


# ─────────────────────────────────────────────────────────────────────────────
# 3. server – FastAPI endpoint validation (no real processing)
# ─────────────────────────────────────────────────────────────────────────────

class TestServerEndpoints(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        # Set required env vars so gemini.py imports without raising
        os.environ.setdefault("GEMINI_API_KEY", "test-key")
        os.environ.setdefault("ELEVENLABS_API_KEY", "test-key")

        from fastapi.testclient import TestClient
        import server
        cls.client = TestClient(server.app)

    def test_home_page_returns_html(self):
        resp = self.client.get("/")
        self.assertEqual(resp.status_code, 200)
        self.assertIn("text/html", resp.headers["content-type"])

    def test_generate_rejects_invalid_media_mode(self):
        resp = self.client.get(
            "/generate",
            params={"topic": "test", "voice_name": "هيثم", "media_mode": "invalid_mode"},
        )
        self.assertEqual(resp.status_code, 400)

    def test_generate_rejects_missing_topic(self):
        resp = self.client.get(
            "/generate",
            params={"topic": "", "voice_name": "هيثم", "media_mode": "pollinations"},
        )
        self.assertEqual(resp.status_code, 400)

    def test_generate_rejects_invalid_voice(self):
        resp = self.client.get(
            "/generate",
            params={"topic": "test", "voice_name": "unknown_voice", "media_mode": "pollinations"},
        )
        self.assertEqual(resp.status_code, 400)

    def test_generate_accepts_all_valid_modes(self):
        """Generate endpoint accepts each valid media_mode without 400."""
        from unittest.mock import patch
        # Patch run_pipeline so no real work is done
        with patch("server.run_pipeline"):
            for mode in ("pollinations", "bing_scrape", "search_apis"):
                resp = self.client.get(
                    "/generate",
                    params={"topic": "test topic", "voice_name": "هيثم", "media_mode": mode},
                )
                self.assertEqual(
                    resp.status_code, 200,
                    msg=f"Expected 200 for media_mode={mode}, got {resp.status_code}",
                )
                body = resp.json()
                self.assertEqual(body["media_mode"], mode)

    def test_download_404_when_no_video(self):
        resp = self.client.get("/download")
        self.assertEqual(resp.status_code, 404)


if __name__ == "__main__":
    unittest.main(verbosity=2)
