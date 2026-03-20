"""utils/gemini_director.py

Per-segment Gemini media/cut decision engine.

For every segment of the video script Gemini is asked to decide:
  - type    : "video" or "image"
  - provider: which source to use (pollinations / bing_scrape / search_apis)
  - duration: how many seconds to show the clip  (1.0 – 15.0)
  - mute    : (video only) whether to silence the original clip audio
  - effect  : optional visual effect (zoom / pan / fade) or null

Unknown or invalid Gemini responses are logged and replaced with safe defaults.
All decisions are also saved to outputs/segment_decisions.json for debugging.
"""
from __future__ import annotations

import json
import os
import re

from utils.gemini import query

# ─────────────────────────────────────────────────────────────────────────────
# Constants
# ─────────────────────────────────────────────────────────────────────────────

_VALID_TYPES     = {"video", "image"}
_VALID_PROVIDERS = {"pollinations", "bing_scrape", "search_apis"}
_VALID_EFFECTS   = {"zoom", "pan", "fade", None}
_MIN_DURATION    = 1.0
_MAX_DURATION    = 15.0
_GEMINI_CONTEXT_CHARS = 800   # max chars of script context sent to Gemini per segment

_DEFAULT_DECISION: dict = {
    "type": "image",
    "provider": "pollinations",
    "duration": 5.0,
    "mute": True,
    "effect": None,
}


def _default_decision() -> dict:
    return dict(_DEFAULT_DECISION)


# ─────────────────────────────────────────────────────────────────────────────
# JSON extraction / normalisation helpers
# ─────────────────────────────────────────────────────────────────────────────

def _parse_gemini_json(text: str) -> dict | None:
    """Extract and parse the first JSON object found in *text*.

    Returns None if no valid JSON object can be found.
    """
    # Direct parse first (Gemini sometimes returns clean JSON)
    try:
        return json.loads(text.strip())
    except Exception:
        pass

    # Markdown code-fence: ```json { … } ```
    m = re.search(r"```(?:json)?\s*(\{[^`]+\})\s*```", text, re.DOTALL)
    if m:
        try:
            return json.loads(m.group(1))
        except Exception:
            pass

    # Bare JSON object anywhere in the text
    m = re.search(r"\{[^{}]+\}", text, re.DOTALL)
    if m:
        try:
            return json.loads(m.group())
        except Exception:
            pass

    return None


def _normalize(raw: dict, segment_idx: int) -> dict:
    """Validate and normalise a raw Gemini response dict.

    Unknown values are replaced with safe defaults and logged.
    """
    decision = _default_decision()

    media_type = raw.get("type", "image")
    if media_type not in _VALID_TYPES:
        print(
            f"[gemini_director] Segment {segment_idx}: unknown type {media_type!r}; "
            "defaulting to 'image'."
        )
        media_type = "image"
    decision["type"] = media_type

    provider = raw.get("provider", "pollinations")
    if provider not in _VALID_PROVIDERS:
        print(
            f"[gemini_director] Segment {segment_idx}: unknown provider {provider!r}; "
            "defaulting to 'pollinations'."
        )
        provider = "pollinations"
    decision["provider"] = provider

    try:
        duration = float(raw.get("duration", _DEFAULT_DECISION["duration"]))
        duration = max(_MIN_DURATION, min(_MAX_DURATION, duration))
    except (TypeError, ValueError):
        duration = _DEFAULT_DECISION["duration"]
    decision["duration"] = duration

    decision["mute"] = bool(raw.get("mute", True))

    effect = raw.get("effect") or None
    if effect not in _VALID_EFFECTS:
        print(
            f"[gemini_director] Segment {segment_idx}: unknown effect {effect!r}; "
            "ignoring."
        )
        effect = None
    decision["effect"] = effect

    return decision


# ─────────────────────────────────────────────────────────────────────────────
# Public API
# ─────────────────────────────────────────────────────────────────────────────

def decide_segment(
    segment_text: str,
    script_context: str,
    segment_idx: int,
    available_providers: list[str] | None = None,
) -> dict:
    """Query Gemini to decide media/cut settings for a single segment.

    Returns a normalised decision dict with keys:
        type, provider, duration, mute, effect
    """
    providers = available_providers or sorted(_VALID_PROVIDERS)

    prompt = (
        "You are an AI video editing director.\n"
        "You are making a short vertical YouTube video (YouTube Shorts) about:\n"
        f"\"\"\"\n{script_context[:_GEMINI_CONTEXT_CHARS]}\n\"\"\"\n\n"
        "Decide how to visually render the following segment:\n"
        f"\"\"\"\n{segment_text}\n\"\"\"\n\n"
        "Available options:\n"
        f"  type      : \"video\" or \"image\"\n"
        f"  provider  : one of {providers}\n"
        f"  duration  : seconds to display (1.0 – 15.0)\n"
        f"  mute      : true or false  (true = replace source audio with AI narration)\n"
        f"  effect    : null or one of [\"zoom\", \"pan\", \"fade\"]\n\n"
        "Rules:\n"
        "  - Prefer a short real video clip when it would be more engaging.\n"
        "  - Set mute=true when AI narration should replace the original audio (recommended).\n"
        "  - Use an effect only when it strongly enhances the message.\n"
        "  - duration should roughly match the expected speaking time for the segment.\n"
        "  - \"pollinations\" can only supply images, not videos.\n\n"
        "Reply with ONLY valid JSON — no markdown, no explanation. Example:\n"
        "{\"type\": \"video\", \"provider\": \"bing_scrape\", \"duration\": 3.5, "
        "\"mute\": true, \"effect\": null}"
    )

    try:
        data = query(prompt)
        raw_text = data["candidates"][0]["content"]["parts"][0]["text"]
        raw_dict = _parse_gemini_json(raw_text)
        if raw_dict is None:
            print(
                f"[gemini_director] Segment {segment_idx}: "
                "could not parse JSON from Gemini response – using defaults.\n"
                f"  Raw response: {raw_text[:200]}"
            )
            return _default_decision()
        return _normalize(raw_dict, segment_idx)
    except Exception as exc:
        print(
            f"[gemini_director] Segment {segment_idx}: Gemini error: {exc} – "
            "using defaults."
        )
        return _default_decision()


def decide_all_segments(
    segments: list[str],
    script_context: str,
    available_providers: list[str] | None = None,
) -> list[dict]:
    """Query Gemini for every segment and return a list of decision dicts.

    The list is also persisted to outputs/segment_decisions.json for debugging.
    """
    decisions: list[dict] = []
    for idx, segment in enumerate(segments):
        print(
            f"  [gemini_director] Deciding segment {idx}: "
            f"{segment[:60]}{'...' if len(segment) > 60 else ''}"
        )
        decision = decide_segment(
            segment_text=segment,
            script_context=script_context,
            segment_idx=idx,
            available_providers=available_providers,
        )
        print(f"  [gemini_director] → {decision}")
        decisions.append(decision)

    # Persist for debugging / re-use
    out_path = os.path.join(os.getcwd(), "outputs", "segment_decisions.json")
    try:
        os.makedirs(os.path.dirname(out_path), exist_ok=True)
        with open(out_path, "w", encoding="utf-8") as fh:
            json.dump(decisions, fh, ensure_ascii=False, indent=2)
        print(f"[gemini_director] Decisions saved to {out_path}")
    except Exception as exc:
        print(f"[gemini_director] Could not save decisions: {exc}")

    return decisions
