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
    "moviepy.video.fx.all",
    "moviepy.audio",
    "moviepy.audio.fx",
    "moviepy.audio.fx.all",
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
# IMAGEMAGICK_BINARY was removed in moviepy v2; server.py guards with hasattr

# moviepy stubs (used by video_creation.py – v1.x API: imports from moviepy.editor)
class _FakeClip:
    duration = 1.0
    w = 1080
    h = 1920
    audio = None
    def __init__(self, *a, **kw): pass
    # v1 API methods
    def subclip(self, *a, **kw): return self
    def set_audio(self, *a, **kw): return self
    def set_position(self, *a, **kw): return self
    def fl(self, *a, **kw): return self
    def volumex(self, *a, **kw): return self
    def close(self): pass
    def write_videofile(self, *a, **kw): pass

_mpy_editor = sys.modules["moviepy.editor"]
_mpy_editor.ImageClip = _FakeClip  # type: ignore
_mpy_editor.VideoFileClip = _FakeClip  # type: ignore
_mpy_editor.AudioFileClip = _FakeClip  # type: ignore
_mpy_editor.ColorClip = _FakeClip  # type: ignore
_mpy_editor.CompositeVideoClip = _FakeClip  # type: ignore
_mpy_editor.CompositeAudioClip = _FakeClip  # type: ignore
_mpy_editor.concatenate_videoclips = lambda clips, **kw: _FakeClip()  # type: ignore

# moviepy.video.fx.all stubs (loop, fadein, resize) – v1 API
def _fake_vfx_fn(*a, **kw): return _FakeClip()

_mpy_vfx_all = sys.modules["moviepy.video.fx.all"]
_mpy_vfx_all.loop = _fake_vfx_fn  # type: ignore
_mpy_vfx_all.fadein = _fake_vfx_fn  # type: ignore
_mpy_vfx_all.resize = _fake_vfx_fn  # type: ignore

# moviepy.audio.fx.all stubs (audio_loop) – v1 API
_mpy_afx_all = sys.modules["moviepy.audio.fx.all"]
_mpy_afx_all.audio_loop = _fake_vfx_fn  # type: ignore


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


# ─────────────────────────────────────────────────────────────────────────────
# 4. gemini_director – JSON parsing and normalisation (no real Gemini calls)
# ─────────────────────────────────────────────────────────────────────────────

class TestGeminiDirectorHelpers(unittest.TestCase):

    def test_parse_clean_json(self):
        from utils.gemini_director import _parse_gemini_json
        result = _parse_gemini_json('{"type": "video", "duration": 3.5}')
        self.assertEqual(result, {"type": "video", "duration": 3.5})

    def test_parse_json_with_markdown_fence(self):
        from utils.gemini_director import _parse_gemini_json
        text = '```json\n{"type": "image", "effect": null}\n```'
        result = _parse_gemini_json(text)
        self.assertIsNotNone(result)
        self.assertEqual(result["type"], "image")

    def test_parse_json_embedded_in_text(self):
        from utils.gemini_director import _parse_gemini_json
        text = 'Here is my decision: {"type": "video", "mute": true} done.'
        result = _parse_gemini_json(text)
        self.assertIsNotNone(result)
        self.assertEqual(result["type"], "video")

    def test_parse_returns_none_on_garbage(self):
        from utils.gemini_director import _parse_gemini_json
        self.assertIsNone(_parse_gemini_json("no json here at all"))

    def test_normalize_valid_decision(self):
        from utils.gemini_director import _normalize
        raw = {"type": "video", "provider": "bing_scrape", "duration": 4.0,
               "mute": True, "effect": "zoom"}
        result = _normalize(raw, segment_idx=0)
        self.assertEqual(result["type"], "video")
        self.assertEqual(result["provider"], "bing_scrape")
        self.assertAlmostEqual(result["duration"], 4.0)
        self.assertTrue(result["mute"])
        self.assertEqual(result["effect"], "zoom")

    def test_normalize_unknown_type_defaults_to_image(self):
        from utils.gemini_director import _normalize
        raw = {"type": "gif", "provider": "pollinations", "duration": 3.0}
        result = _normalize(raw, segment_idx=1)
        self.assertEqual(result["type"], "image")

    def test_normalize_unknown_provider_defaults_to_pollinations(self):
        from utils.gemini_director import _normalize
        raw = {"type": "image", "provider": "youtube", "duration": 3.0}
        result = _normalize(raw, segment_idx=2)
        self.assertEqual(result["provider"], "pollinations")

    def test_normalize_duration_clamped(self):
        from utils.gemini_director import _normalize
        raw = {"type": "image", "provider": "pollinations", "duration": 99.0}
        result = _normalize(raw, segment_idx=3)
        self.assertLessEqual(result["duration"], 15.0)

    def test_normalize_duration_minimum(self):
        from utils.gemini_director import _normalize
        raw = {"type": "image", "provider": "pollinations", "duration": 0.1}
        result = _normalize(raw, segment_idx=4)
        self.assertGreaterEqual(result["duration"], 1.0)

    def test_normalize_unknown_effect_becomes_none(self):
        from utils.gemini_director import _normalize
        raw = {"type": "image", "provider": "pollinations", "effect": "warp"}
        result = _normalize(raw, segment_idx=5)
        self.assertIsNone(result["effect"])

    def test_decide_segment_uses_default_on_gemini_error(self):
        """decide_segment falls back to defaults when Gemini query fails."""
        from unittest.mock import patch
        from utils.gemini_director import decide_segment, _DEFAULT_DECISION
        with patch("utils.gemini_director.query", side_effect=RuntimeError("API down")):
            result = decide_segment("some segment", "some context", segment_idx=0)
        self.assertEqual(result, _DEFAULT_DECISION)

    def test_decide_all_segments_returns_one_per_segment(self):
        """decide_all_segments returns a list of length == len(segments)."""
        from unittest.mock import patch
        from utils.gemini_director import decide_all_segments, _DEFAULT_DECISION
        import tempfile, json

        segments = ["line one", "line two", "line three"]
        with patch("utils.gemini_director.query", side_effect=RuntimeError("no key")):
            with tempfile.TemporaryDirectory() as tmp:
                orig_cwd = os.getcwd()
                os.chdir(tmp)
                os.makedirs("outputs", exist_ok=True)
                try:
                    decisions = decide_all_segments(segments, script_context="ctx")
                finally:
                    os.chdir(orig_cwd)
        self.assertEqual(len(decisions), len(segments))
        for d in decisions:
            self.assertIn("type", d)
            self.assertIn("provider", d)
            self.assertIn("duration", d)
            self.assertIn("mute", d)
            self.assertIn("effect", d)


# ─────────────────────────────────────────────────────────────────────────────
# 5. media_fetch – per-segment decision dispatcher
# ─────────────────────────────────────────────────────────────────────────────

class TestMediaFetchDecisionDispatch(unittest.TestCase):

    def test_fetch_segment_pollinations_type_image_uses_pollinations(self):
        """When decision has type=image and provider=pollinations, _fetch_pollinations is called."""
        from unittest.mock import patch
        from utils.media_fetch import _fetch_segment_with_decision
        import tempfile

        decision = {"type": "image", "provider": "pollinations", "duration": 3.0,
                    "mute": True, "effect": None}
        with tempfile.TemporaryDirectory() as tmp:
            with patch("utils.media_fetch._fetch_pollinations", return_value=True) as mock_poll:
                result = _fetch_segment_with_decision(
                    part_idx=0,
                    prompt_en="test prompt",
                    media_dir=tmp,
                    fallback_mode="pollinations",
                    decision=decision,
                )
            self.assertTrue(mock_poll.called)

    def test_fetch_segment_video_provider_pollinations_downgrades_to_image(self):
        """When type=video but provider=pollinations, must fetch image (pollinations can't do video)."""
        from unittest.mock import patch
        from utils.media_fetch import _fetch_segment_with_decision
        import tempfile

        decision = {"type": "video", "provider": "pollinations", "duration": 3.0,
                    "mute": True, "effect": None}
        with tempfile.TemporaryDirectory() as tmp:
            with patch("utils.media_fetch._fetch_pollinations", return_value=True) as mock_poll:
                _fetch_segment_with_decision(
                    part_idx=0,
                    prompt_en="test prompt",
                    media_dir=tmp,
                    fallback_mode="pollinations",
                    decision=decision,
                )
            # Should fall through to pollinations image fetch (not video)
            self.assertTrue(mock_poll.called)

    def test_fetch_segment_none_decision_uses_mode(self):
        """When decision is None, the global mode is used."""
        from unittest.mock import patch
        from utils.media_fetch import _fetch_segment_with_decision
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            with patch("utils.media_fetch._fetch_pollinations", return_value=True) as mock_poll:
                _fetch_segment_with_decision(
                    part_idx=0,
                    prompt_en="test prompt",
                    media_dir=tmp,
                    fallback_mode="pollinations",
                    decision=None,
                )
            self.assertTrue(mock_poll.called)

    def test_fetch_media_main_passes_decisions(self):
        """fetch_media_main calls _fetch_segment_with_decision for each line."""
        from unittest.mock import patch
        from utils import media_fetch
        import tempfile

        decisions = [{"type": "image", "provider": "pollinations", "duration": 3.0,
                      "mute": True, "effect": None}]
        with tempfile.TemporaryDirectory() as tmp:
            orig_cwd = os.getcwd()
            os.chdir(tmp)
            os.makedirs("outputs/media", exist_ok=True)
            try:
                with open("outputs/line_by_line.txt", "w") as fh:
                    fh.write("line one\n")
                with patch.object(media_fetch, "_fetch_segment_with_decision",
                                  return_value=None) as mock_dispatch:
                    with patch.object(media_fetch, "_fetch_pollinations", return_value=False):
                        media_fetch.fetch_media_main(mode="pollinations", decisions=decisions)
                self.assertTrue(mock_dispatch.called)
                call_kwargs = mock_dispatch.call_args
                self.assertEqual(call_kwargs.kwargs.get("decision") or
                                 call_kwargs[1].get("decision") or
                                 call_kwargs[0][4],  # positional arg index
                                 decisions[0])
            finally:
                os.chdir(orig_cwd)


if __name__ == "__main__":
    unittest.main(verbosity=2)
