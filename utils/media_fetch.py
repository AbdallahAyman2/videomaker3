"""utils/media_fetch.py
Media fetching module supporting three modes:
  1. pollinations - AI-generated images via Pollinations.ai (default)
  2. bing_scrape   - Bing web scraping (no API key required)
  3. search_apis  - Fallback chain: Brave → Tavily → Serper → SerpApi → DuckDuckGo

When a list of per-segment Gemini decisions is supplied (via *decisions*),
the provider and preferred media type from each decision is respected instead
of applying the same *mode* to every segment.

File outputs (per part index):
  outputs/media/part{i}.mp4  — downloaded video clip
  outputs/media/part{i}.jpg  — downloaded / generated image
"""

import json
import os
import time

import requests
from io import BytesIO
from urllib.parse import quote_plus

from PIL import Image
from tqdm import tqdm
from googletrans import Translator

# ─────────────────────────────────────────────
# API keys (only needed for search_apis mode)
# ─────────────────────────────────────────────
BRAVE_API_KEY   = os.environ.get("BRAVE_API_KEY", "")
TAVILY_API_KEY  = os.environ.get("TAVILY_API_KEY", "")
SERPER_API_KEY  = os.environ.get("SERPER_API_KEY", "")
SERPAPI_API_KEY = os.environ.get("SERPAPI_API_KEY", "")

_BROWSER_UA = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)

_translator = None


def _get_translator() -> Translator:
    global _translator
    if _translator is None:
        _translator = Translator()
    return _translator


def _translate_to_english(text: str) -> str:
    try:
        result = _get_translator().translate(text, src="ar", dest="en")
        return result.text
    except Exception as exc:
        print(f"    Translation failed, using original text: {exc}")
        return text


def _download_file(url: str, dest_path: str, timeout: int = 20) -> bool:
    """Download *url* to *dest_path*. Returns True if size > 1 KB."""
    try:
        headers = {"User-Agent": _BROWSER_UA}
        resp = requests.get(url, headers=headers, timeout=timeout, stream=True)
        resp.raise_for_status()
        with open(dest_path, "wb") as fh:
            for chunk in resp.iter_content(chunk_size=8192):
                if chunk:
                    fh.write(chunk)
        if os.path.getsize(dest_path) > 1024:
            return True
        os.remove(dest_path)
        return False
    except Exception as exc:
        print(f"    Download failed ({url}): {exc}")
        if os.path.exists(dest_path):
            os.remove(dest_path)
        return False


def _save_image_from_bytes(data: bytes, dest_path: str) -> bool:
    """Decode *data* as an image and save as JPEG. Returns True on success."""
    try:
        img = Image.open(BytesIO(data)).convert("RGB")
        img.save(dest_path, format="JPEG")
        return True
    except Exception as exc:
        print(f"    Image save failed: {exc}")
        return False


# ─────────────────────────────────────────────────────────────────────────────
# MODE 1: Pollinations
# ─────────────────────────────────────────────────────────────────────────────

def _fetch_pollinations(prompt_en: str, dest_path: str) -> bool:
    """Fetch an AI-generated image from Pollinations.ai."""
    encoded = quote_plus(prompt_en)
    url = f"https://image.pollinations.ai/prompt/{encoded}"
    try:
        resp = requests.get(url, timeout=30)
        resp.raise_for_status()
        return _save_image_from_bytes(resp.content, dest_path)
    except Exception as exc:
        print(f"    Pollinations error: {exc}")
        return False


# ─────────────────────────────────────────────────────────────────────────────
# MODE 2: Bing Scraping
# ─────────────────────────────────────────────────────────────────────────────

def _bing_search_videos(query: str) -> list:
    """Scrape Bing video search and return candidate MP4/video URLs."""
    try:
        from bs4 import BeautifulSoup
    except ImportError:
        print("    beautifulsoup4 not installed; skipping Bing video scrape.")
        return []

    search_url = (
        f"https://www.bing.com/videos/search?q={quote_plus(query)}&FORM=HDRSC3"
    )
    headers = {"User-Agent": _BROWSER_UA, "Accept-Language": "en-US,en;q=0.9"}
    try:
        resp = requests.get(search_url, headers=headers, timeout=15)
        soup = BeautifulSoup(resp.text, "lxml")

        urls = []
        # Direct href links that look like video files
        for tag in soup.find_all("a", href=True):
            href = tag["href"]
            if any(ext in href.lower() for ext in (".mp4", ".webm")):
                urls.append(href)

        # data-src attributes
        for tag in soup.find_all(attrs={"data-src": True}):
            src = tag["data-src"]
            if any(ext in src.lower() for ext in (".mp4", ".webm")):
                urls.append(src)

        return urls[:5]
    except Exception as exc:
        print(f"    Bing video scrape error: {exc}")
        return []


def _bing_search_images(query: str) -> list:
    """Scrape Bing image search and return candidate image URLs."""
    try:
        from bs4 import BeautifulSoup
    except ImportError:
        print("    beautifulsoup4 not installed; skipping Bing image scrape.")
        return []

    search_url = (
        f"https://www.bing.com/images/search?q={quote_plus(query)}&FORM=HDRSC2"
    )
    headers = {"User-Agent": _BROWSER_UA, "Accept-Language": "en-US,en;q=0.9"}
    try:
        resp = requests.get(search_url, headers=headers, timeout=15)
        soup = BeautifulSoup(resp.text, "lxml")

        urls = []
        # Bing encodes image metadata in the "m" attribute of <a class="iusc">
        for tag in soup.find_all("a", class_="iusc"):
            raw = tag.get("m", "")
            if raw:
                try:
                    data = json.loads(raw)
                    murl = data.get("murl", "")
                    if murl:
                        urls.append(murl)
                except Exception:
                    pass

        # Generic fallback: img src from external domains
        for tag in soup.find_all("img", attrs={"src": True}):
            src = tag["src"]
            if src.startswith("http") and "bing.com" not in src:
                urls.append(src)

        return urls[:10]
    except Exception as exc:
        print(f"    Bing image scrape error: {exc}")
        return []


def _fetch_bing_video_only(prompt_en: str, part_idx: int, media_dir: str):
    """Try Bing video scrape only. Returns saved path or None."""
    print(f"    [bing_scrape] Searching videos for: {prompt_en[:60]}")
    for vurl in _bing_search_videos(prompt_en):
        dest = os.path.join(media_dir, f"part{part_idx}.mp4")
        if _download_file(vurl, dest, timeout=30):
            print(f"    [bing_scrape] Video downloaded: {vurl[:80]}")
            return dest
    return None


def _fetch_bing_image_only(prompt_en: str, part_idx: int, media_dir: str):
    """Try Bing image scrape only. Returns saved path or None."""
    print(f"    [bing_scrape] Searching images for: {prompt_en[:60]}")
    for iurl in _bing_search_images(prompt_en):
        try:
            resp = requests.get(
                iurl, timeout=15, headers={"User-Agent": _BROWSER_UA}
            )
            resp.raise_for_status()
            dest = os.path.join(media_dir, f"part{part_idx}.jpg")
            if _save_image_from_bytes(resp.content, dest):
                print(f"    [bing_scrape] Image downloaded: {iurl[:80]}")
                return dest
        except Exception as exc:
            print(f"    Image download error: {exc}")
            continue
    return None


def _fetch_bing_scrape(prompt_en: str, part_idx: int, media_dir: str):
    """Try video first (Bing video search), then fallback to Bing image search.

    Returns the saved file path (str) or None.
    """
    saved = _fetch_bing_video_only(prompt_en, part_idx, media_dir)
    if saved:
        return saved
    print(f"    [bing_scrape] No video found – trying images...")
    return _fetch_bing_image_only(prompt_en, part_idx, media_dir)


# ─────────────────────────────────────────────────────────────────────────────
# MODE 3: Search API fallback chain
# ─────────────────────────────────────────────────────────────────────────────

def _brave_search_videos(query: str) -> list:
    if not BRAVE_API_KEY:
        raise RuntimeError("BRAVE_API_KEY not set")
    resp = requests.get(
        "https://api.search.brave.com/res/v1/videos/search",
        params={"q": query, "count": 5},
        headers={"Accept": "application/json", "X-Subscription-Token": BRAVE_API_KEY},
        timeout=15,
    )
    if resp.status_code in (402, 429):
        raise RuntimeError(f"Brave credits exhausted ({resp.status_code})")
    resp.raise_for_status()
    urls = []
    for item in resp.json().get("results", []):
        src = item.get("video", {}).get("src") or item.get("url", "")
        if src:
            urls.append(src)
    return urls


def _brave_search_images(query: str) -> list:
    if not BRAVE_API_KEY:
        raise RuntimeError("BRAVE_API_KEY not set")
    resp = requests.get(
        "https://api.search.brave.com/res/v1/images/search",
        params={"q": query, "count": 10},
        headers={"Accept": "application/json", "X-Subscription-Token": BRAVE_API_KEY},
        timeout=15,
    )
    if resp.status_code in (402, 429):
        raise RuntimeError(f"Brave credits exhausted ({resp.status_code})")
    resp.raise_for_status()
    return [
        item["properties"]["url"]
        for item in resp.json().get("results", [])
        if item.get("properties", {}).get("url")
    ]


def _tavily_search_videos(query: str) -> list:
    if not TAVILY_API_KEY:
        raise RuntimeError("TAVILY_API_KEY not set")
    resp = requests.post(
        "https://api.tavily.com/search",
        json={
            "api_key": TAVILY_API_KEY,
            "query": query + " short video clip mp4",
            "search_depth": "basic",
            "include_images": False,
            "max_results": 5,
        },
        timeout=15,
    )
    if resp.status_code in (402, 429):
        raise RuntimeError(f"Tavily credits exhausted ({resp.status_code})")
    resp.raise_for_status()
    return [
        item.get("url", "")
        for item in resp.json().get("results", [])
        if any(ext in item.get("url", "").lower() for ext in (".mp4", ".webm"))
    ]


def _tavily_search_images(query: str) -> list:
    if not TAVILY_API_KEY:
        raise RuntimeError("TAVILY_API_KEY not set")
    resp = requests.post(
        "https://api.tavily.com/search",
        json={
            "api_key": TAVILY_API_KEY,
            "query": query,
            "search_depth": "basic",
            "include_images": True,
            "max_results": 5,
        },
        timeout=15,
    )
    if resp.status_code in (402, 429):
        raise RuntimeError(f"Tavily credits exhausted ({resp.status_code})")
    resp.raise_for_status()
    return resp.json().get("images", [])


def _serper_search_videos(query: str) -> list:
    if not SERPER_API_KEY:
        raise RuntimeError("SERPER_API_KEY not set")
    resp = requests.post(
        "https://google.serper.dev/videos",
        json={"q": query},
        headers={"X-API-KEY": SERPER_API_KEY, "Content-Type": "application/json"},
        timeout=15,
    )
    if resp.status_code in (402, 429):
        raise RuntimeError(f"Serper credits exhausted ({resp.status_code})")
    resp.raise_for_status()
    return [
        item.get("link", "")
        for item in resp.json().get("videos", [])
        if item.get("link")
    ]


def _serper_search_images(query: str) -> list:
    if not SERPER_API_KEY:
        raise RuntimeError("SERPER_API_KEY not set")
    resp = requests.post(
        "https://google.serper.dev/images",
        json={"q": query},
        headers={"X-API-KEY": SERPER_API_KEY, "Content-Type": "application/json"},
        timeout=15,
    )
    if resp.status_code in (402, 429):
        raise RuntimeError(f"Serper credits exhausted ({resp.status_code})")
    resp.raise_for_status()
    return [
        item.get("imageUrl", "")
        for item in resp.json().get("images", [])
        if item.get("imageUrl")
    ]


def _serpapi_search_videos(query: str) -> list:
    if not SERPAPI_API_KEY:
        raise RuntimeError("SERPAPI_API_KEY not set")
    resp = requests.get(
        "https://serpapi.com/search",
        params={"engine": "bing_videos", "q": query, "api_key": SERPAPI_API_KEY},
        timeout=15,
    )
    if resp.status_code in (402, 429):
        raise RuntimeError(f"SerpApi credits exhausted ({resp.status_code})")
    resp.raise_for_status()
    return [
        item.get("link", "")
        for item in resp.json().get("video_results", [])
        if item.get("link")
    ]


def _serpapi_search_images(query: str) -> list:
    if not SERPAPI_API_KEY:
        raise RuntimeError("SERPAPI_API_KEY not set")
    resp = requests.get(
        "https://serpapi.com/search",
        params={"engine": "bing_images", "q": query, "api_key": SERPAPI_API_KEY},
        timeout=15,
    )
    if resp.status_code in (402, 429):
        raise RuntimeError(f"SerpApi credits exhausted ({resp.status_code})")
    resp.raise_for_status()
    return [
        item.get("original", "")
        for item in resp.json().get("images_results", [])
        if item.get("original")
    ]


def _ddg_search_videos(query: str) -> list:
    try:
        from duckduckgo_search import DDGS
        with DDGS() as ddgs:
            results = list(ddgs.videos(query, max_results=5))
        return [
            r.get("content", "") or r.get("embed_url", "")
            for r in results
            if r.get("content") or r.get("embed_url")
        ]
    except Exception as exc:
        raise RuntimeError(f"DuckDuckGo error: {exc}")


def _ddg_search_images(query: str) -> list:
    try:
        from duckduckgo_search import DDGS
        with DDGS() as ddgs:
            results = list(ddgs.images(query, max_results=10))
        return [r.get("image", "") for r in results if r.get("image")]
    except Exception as exc:
        raise RuntimeError(f"DuckDuckGo error: {exc}")


# Provider chain in order (best → worst)
_PROVIDER_CHAIN = [
    (_brave_search_videos,   _brave_search_images,   "Brave"),
    (_tavily_search_videos,  _tavily_search_images,  "Tavily"),
    (_serper_search_videos,  _serper_search_images,  "Serper"),
    (_serpapi_search_videos, _serpapi_search_images, "SerpApi"),
    (_ddg_search_videos,     _ddg_search_images,     "DuckDuckGo"),
]


def _fetch_search_apis_video_only(prompt_en: str, part_idx: int, media_dir: str):
    """Try each API provider for a video only. Returns saved path or None."""
    for video_fn, _, name in _PROVIDER_CHAIN:
        try:
            print(f"    [search_apis] Trying video via {name}...")
            for vurl in video_fn(prompt_en):
                if not vurl:
                    continue
                dest = os.path.join(media_dir, f"part{part_idx}.mp4")
                if _download_file(vurl, dest, timeout=30):
                    print(f"    [search_apis] Video downloaded via {name}: {vurl[:80]}")
                    return dest
        except RuntimeError as exc:
            print(f"    [search_apis] {name} video unavailable: {exc}")
        except Exception as exc:
            print(f"    [search_apis] {name} video error: {exc}")
    return None


def _fetch_search_apis_image_only(prompt_en: str, part_idx: int, media_dir: str):
    """Try each API provider for an image only. Returns saved path or None."""
    for _, image_fn, name in _PROVIDER_CHAIN:
        try:
            print(f"    [search_apis] Trying image via {name}...")
            for iurl in image_fn(prompt_en):
                if not iurl:
                    continue
                try:
                    resp = requests.get(
                        iurl, timeout=15, headers={"User-Agent": _BROWSER_UA}
                    )
                    resp.raise_for_status()
                    dest = os.path.join(media_dir, f"part{part_idx}.jpg")
                    if _save_image_from_bytes(resp.content, dest):
                        print(f"    [search_apis] Image downloaded via {name}: {iurl[:80]}")
                        return dest
                except Exception as exc:
                    print(f"    Image fetch error: {exc}")
        except RuntimeError as exc:
            print(f"    [search_apis] {name} image unavailable: {exc}")
        except Exception as exc:
            print(f"    [search_apis] {name} image error: {exc}")
    return None


def _fetch_search_apis(prompt_en: str, part_idx: int, media_dir: str):
    """Try each provider for videos first, then images.

    Returns the saved file path or None.
    """
    saved = _fetch_search_apis_video_only(prompt_en, part_idx, media_dir)
    if saved:
        return saved
    return _fetch_search_apis_image_only(prompt_en, part_idx, media_dir)


# ─────────────────────────────────────────────────────────────────────────────
# Per-segment dispatcher (Gemini-directed)
# ─────────────────────────────────────────────────────────────────────────────

def _fetch_segment_with_decision(
    part_idx: int,
    prompt_en: str,
    media_dir: str,
    fallback_mode: str,
    decision: dict | None,
) -> str | None:
    """Fetch media for one segment, honouring the Gemini per-segment decision.

    Args:
        part_idx:      segment index (used in output filename)
        prompt_en:     English search/generation prompt
        media_dir:     directory to save the file in
        fallback_mode: global media mode used when *decision* is None
        decision:      Gemini decision dict, or None for mode-based behaviour

    Returns:
        Saved file path or None.
    """
    if decision is None:
        # Legacy behaviour: apply the global mode
        if fallback_mode == "bing_scrape":
            return _fetch_bing_scrape(prompt_en, part_idx, media_dir)
        if fallback_mode == "search_apis":
            return _fetch_search_apis(prompt_en, part_idx, media_dir)
        # pollinations (default)
        dest = os.path.join(media_dir, f"part{part_idx}.jpg")
        return dest if _fetch_pollinations(prompt_en, dest) else None

    desired_type = decision.get("type", "image")
    provider = decision.get("provider", fallback_mode)

    # Pollinations cannot supply videos
    if desired_type == "video" and provider == "pollinations":
        print(
            f"    [gemini_director] Segment {part_idx}: "
            "pollinations cannot supply videos – fetching image instead."
        )
        desired_type = "image"

    # Validate provider; fall back to mode
    if provider not in {"pollinations", "bing_scrape", "search_apis"}:
        print(
            f"    [gemini_director] Segment {part_idx}: unknown provider "
            f"{provider!r} – falling back to mode={fallback_mode}."
        )
        provider = fallback_mode

    saved = None

    if desired_type == "video":
        # Try video from the chosen provider
        if provider == "bing_scrape":
            saved = _fetch_bing_video_only(prompt_en, part_idx, media_dir)
        elif provider == "search_apis":
            saved = _fetch_search_apis_video_only(prompt_en, part_idx, media_dir)

        if saved:
            return saved
        print(
            f"    [gemini_director] Segment {part_idx}: video fetch failed – "
            "falling back to image from the same provider."
        )

    # Image fetch (either requested directly or video-fallback)
    if provider == "bing_scrape":
        saved = _fetch_bing_image_only(prompt_en, part_idx, media_dir)
    elif provider == "search_apis":
        saved = _fetch_search_apis_image_only(prompt_en, part_idx, media_dir)
    else:  # pollinations
        dest = os.path.join(media_dir, f"part{part_idx}.jpg")
        saved = dest if _fetch_pollinations(prompt_en, dest) else None

    return saved


# ─────────────────────────────────────────────────────────────────────────────
# Main entry point
# ─────────────────────────────────────────────────────────────────────────────

def fetch_media_main(
    mode: str = "pollinations",
    decisions: list[dict] | None = None,
) -> None:
    """Read prompts from outputs/line_by_line.txt and download/generate media.

    For each line the file is saved as outputs/media/part{i}.mp4 or .jpg.

    When *decisions* is supplied (a list of per-segment Gemini decision dicts),
    each segment uses the provider and type from its decision instead of the
    global *mode*.  The global *mode* is still used as a fallback when a
    decision is missing or when the decision's provider fails.

    Falls back to Pollinations image generation for any part where all other
    methods fail.

    Args:
        mode:      "pollinations" | "bing_scrape" | "search_apis"
        decisions: optional per-segment Gemini decisions
    """
    allowed_modes = {"pollinations", "bing_scrape", "search_apis"}
    if mode not in allowed_modes:
        print(f"Unknown media_mode '{mode}'; defaulting to 'pollinations'.")
        mode = "pollinations"

    outputs_dir = os.path.join(os.getcwd(), "outputs")
    media_dir = os.path.join(outputs_dir, "media")
    os.makedirs(media_dir, exist_ok=True)

    line_file = os.path.join(outputs_dir, "line_by_line.txt")
    with open(line_file, "r", encoding="utf-8") as fh:
        prompts = [line.strip() for line in fh if line.strip()]

    for part, prompt in enumerate(tqdm(prompts, desc=f"Fetching media [{mode}]")):
        print(f"\n[Part {part}] {prompt[:70]}...")

        prompt_en = _translate_to_english(prompt)
        decision = decisions[part] if decisions and part < len(decisions) else None

        if decision:
            print(f"    [gemini_director] Using decision: {decision}")

        saved = _fetch_segment_with_decision(
            part_idx=part,
            prompt_en=prompt_en,
            media_dir=media_dir,
            fallback_mode=mode,
            decision=decision,
        )

        # Universal last-resort fallback: Pollinations image
        if not saved:
            print(f"    Primary fetch failed – falling back to Pollinations...")
            dest = os.path.join(media_dir, f"part{part}.jpg")
            if _fetch_pollinations(prompt_en, dest):
                saved = dest
            else:
                print(f"    WARNING: No media could be fetched for part {part}.")

        # Small delay to be kind to servers
        time.sleep(0.5)


if __name__ == "__main__":
    import sys
    mode_arg = sys.argv[1] if len(sys.argv) > 1 else "pollinations"
    fetch_media_main(mode=mode_arg)
