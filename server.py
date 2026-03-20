# server.py

# -------------------------------------------------------------------------------
# تم إنشاء هذا المشروع تلقائيًا بواسطة أداة من تطوير قناة "مدرسة الذكاء الاصطناعي"
# يوتيوب  : https://www.youtube.com/@ArabianAiSchool
# إنستغرام: https://www.instagram.com/arabianaischool
# فيسبوك  : https://www.facebook.com/arabianaischool
# تويتر   : https://twitter.com/arabianaischool
# ايميل القناة : arabianaischool@gmail.com
# -------------------------------------------------------------------------------

import sys
import os
import shutil

# ───────────────────────────────────────────────────────────────────────────────
# 1) Detect and configure ffmpeg / ImageMagick paths
#    On Linux servers (HF Spaces, GitHub Codespaces) the tools are in PATH.
#    On Windows (local dev) fall back to the bundled / installed locations.
# ───────────────────────────────────────────────────────────────────────────────
if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
    # PyInstaller bundle
    _base = sys._MEIPASS
    ffmpeg_path = os.path.join(_base, "ffmpeg", "ffmpeg.exe")
    imagemagick_path = os.path.join(_base, "ImageMagick", "magick.exe")
elif sys.platform.startswith("win"):
    ffmpeg_path = shutil.which("ffmpeg") or r"ffmpeg.exe"
    imagemagick_path = shutil.which("magick") or r"C:\Program Files\ImageMagick\magick.exe"
else:
    # Linux / macOS server — expect tools in PATH (installed via apt / brew)
    ffmpeg_path = shutil.which("ffmpeg") or "ffmpeg"
    imagemagick_path = shutil.which("magick") or shutil.which("convert") or "convert"

os.environ["FFMPEG_BINARY"] = ffmpeg_path
os.environ["IMAGEMAGICK_BINARY"] = imagemagick_path

import moviepy.config as mpy_config
mpy_config.FFMPEG_BINARY = ffmpeg_path
mpy_config.IMAGEMAGICK_BINARY = imagemagick_path

print("Using ffmpeg:", ffmpeg_path)
print("Using ImageMagick:", imagemagick_path)

# ───────────────────────────────────────────────────────────────────────────────
# 2) Ensure output sub-folders exist
# ───────────────────────────────────────────────────────────────────────────────
out_base = os.path.join(os.getcwd(), "outputs")
os.makedirs(out_base, exist_ok=True)
for sub in ("images", "audio", "media"):
    os.makedirs(os.path.join(out_base, sub), exist_ok=True)

import threading
import asyncio
import requests

from fastapi import FastAPI, Request, HTTPException, Query
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.responses import FileResponse
from starlette.responses import StreamingResponse

from utils.gemini import query
from utils.write_script import write_content, split_text_to_lines
from utils.gemini_director import decide_all_segments
from utils.media_fetch import fetch_media_main
from utils.voice_gen import voice_main
from utils.video_creation import video_main

# ───────────────────────────────────────────────────────────────────────────────
# 3) Telegram helper — credentials come from environment variables
#    Set TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID as secrets.
# ───────────────────────────────────────────────────────────────────────────────
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID   = os.environ.get("TELEGRAM_CHAT_ID", "")


def send_video_to_telegram(video_path: str, caption: str = "") -> bool:
    """Upload a video file to the configured Telegram chat.

    Returns True on success, False on failure (errors are printed but not raised
    so they never break the main pipeline).
    """
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        print("Telegram credentials not set - skipping upload.")
        return False
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendVideo"
    try:
        with open(video_path, "rb") as vf:
            resp = requests.post(
                url,
                data={"chat_id": TELEGRAM_CHAT_ID, "caption": caption},
                files={"video": vf},
                timeout=120,
            )
        if resp.ok:
            print("Video sent to Telegram successfully.")
            return True
        else:
            print(f"Telegram upload failed: {resp.status_code} {resp.text}")
            return False
    except Exception as exc:
        print(f"Telegram upload error: {exc}")
        return False


# ───────────────────────────────────────────────────────────────────────────────
# 4) FastAPI app
# ───────────────────────────────────────────────────────────────────────────────
BASE = getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))

app = FastAPI(title="ARABIAN AI SCHOOL Video Generator")

app.mount(
    "/static",
    StaticFiles(directory=os.path.join(BASE, "static")),
    name="static",
)
templates = Jinja2Templates(directory=os.path.join(BASE, "templates"))

# Available ElevenLabs voice IDs
voice_options = {
    "هيثم": "UR972wNGq3zluze0LoIp",
    "يحيى": "QRq5hPRAKf5ZhSlTBH6r",
    "سارة": "jAAHNNqlbAX9iWjJPEtE",
    "مازن": "rPNcQ53R703tTmtue1AT",
    "أسماء": "qi4PkV9c01kb869Vh7Su",
}

VALID_MEDIA_MODES = {"pollinations", "bing_scrape", "search_apis"}

# Per-connection SSE queues
listeners: list[asyncio.Queue] = []


# ───────────────────────────────────────────────────────────────────────────────
# SSE endpoint
# ───────────────────────────────────────────────────────────────────────────────
@app.get("/stream")
def stream():
    async def event_generator():
        q: asyncio.Queue = asyncio.Queue()
        listeners.append(q)
        try:
            while True:
                msg = await q.get()
                yield f"data: {msg}\n\n"
        except asyncio.CancelledError:
            pass
        finally:
            try:
                listeners.remove(q)
            except ValueError:
                pass

    return StreamingResponse(event_generator(), media_type="text/event-stream")


def broadcast(message: str):
    """Send a message to every active SSE listener."""
    for q in listeners:
        q.put_nowait(message)


# ───────────────────────────────────────────────────────────────────────────────
# Home page
# ───────────────────────────────────────────────────────────────────────────────
@app.get("/")
async def get_form(request: Request):
    return templates.TemplateResponse(
        request,
        "index.html",
        {"voice_options": list(voice_options.keys())},
    )


# ───────────────────────────────────────────────────────────────────────────────
# Download the generated video
# ───────────────────────────────────────────────────────────────────────────────
@app.get("/download")
async def download_video():
    video_path = os.path.join(out_base, "youtube_short.mp4")
    if not os.path.exists(video_path):
        raise HTTPException(status_code=404, detail="Video not ready yet.")
    return FileResponse(
        video_path,
        media_type="video/mp4",
        filename="youtube_short.mp4",
    )


# ───────────────────────────────────────────────────────────────────────────────
# Generate endpoint (supports GET for browser/n8n HTTP requests)
# ───────────────────────────────────────────────────────────────────────────────
@app.get("/generate")
async def generate_shorts(
    topic: str = Query(..., description="Video topic"),
    voice_name: str = Query(..., description="Voice name"),
    media_mode: str = Query("pollinations", description="Media sourcing mode: pollinations | bing_scrape | search_apis"),
):
    topic = topic.strip()
    if not topic:
        raise HTTPException(status_code=400, detail="topic cannot be empty")
    if voice_name not in voice_options:
        raise HTTPException(status_code=400, detail="invalid voice_name")
    if media_mode not in VALID_MEDIA_MODES:
        raise HTTPException(
            status_code=400,
            detail=f"invalid media_mode; allowed values: {sorted(VALID_MEDIA_MODES)}",
        )

    voice_id = voice_options[voice_name]
    threading.Thread(
        target=run_pipeline,
        args=(topic, voice_id, media_mode),
        daemon=True,
    ).start()

    broadcast(f"▶️ بدأ إنشاء الفيديو للموضوع: «{topic}» بصوت «{voice_name}» (مصدر الوسائط: {media_mode}).")
    return {"status": "started", "topic": topic, "voice": voice_name, "media_mode": media_mode}


# ───────────────────────────────────────────────────────────────────────────────
# Full pipeline
# ───────────────────────────────────────────────────────────────────────────────
def run_pipeline(topic: str, voice_id: str, media_mode: str = "pollinations"):
    try:
        broadcast("1) توليد العنوان...")
        data = query(
            f"أعطِ 5 عناوين لفيديوهات يوتيوب شورتس تتعلق بالموضوع '{topic}' مفصولة بفواصل"
        )
        raw = data["candidates"][0]["content"]["parts"][0]["text"]
        titles = [t.strip() for t in raw.replace("،", ",").split(",") if t.strip()]
        if not titles:
            raise ValueError("Gemini returned no titles for the given topic.")
        title = titles[0]
        broadcast(f"2) العنوان: {title}")

        broadcast("3) توليد المحتوى...")
        data2 = query(
            f"اشرح عن هذا الموضوع {title} بإيجاز مدته دقيقة واحدة بدون تعليمات."
        )
        content = data2["candidates"][0]["content"]["parts"][0]["text"]
        broadcast("4) المحتوى مُنشأ.")

        broadcast("5) حفظ المحتوى وتقسيمه إلى سطور...")
        write_content(content)
        split_text_to_lines()
        broadcast("6) حفظ line_by_line.txt.")

        broadcast("7) استشارة Gemini لقرار الوسائط لكل جزء...")
        line_file = os.path.join(os.getcwd(), "outputs", "line_by_line.txt")
        with open(line_file, "r", encoding="utf-8") as _fh:
            lines = [l.strip() for l in _fh if l.strip()]
        decisions = decide_all_segments(
            segments=lines,
            script_context=content,
        )
        broadcast(f"8) تم توليد {len(decisions)} قرار وسائط من Gemini.")

        broadcast(f"9) جلب الوسائط (mode={media_mode})...")
        fetch_media_main(mode=media_mode, decisions=decisions)
        broadcast("10) الوسائط جاهزة.")

        broadcast("11) توليد الصوت...")
        voice_main(voice_id=voice_id)
        broadcast("12) الصوت جاهز.")

        broadcast("13) إنشاء الفيديو...")
        video_path = video_main(decisions=decisions)
        broadcast("14) ✅ انتهى! يمكن تحميل الفيديو من /download")

        broadcast("15) إرسال الفيديو إلى تيليغرام...")
        ok = send_video_to_telegram(video_path, caption=f"🎬 {title}")
        if ok:
            broadcast("16) ✅ تم إرسال الفيديو إلى تيليغرام.")
        else:
            broadcast("16) ⚠️ لم يتم إرسال الفيديو إلى تيليغرام (تحقق من الإعدادات).")
    except Exception as e:
        broadcast(f"❌ خطأ أثناء المعالجة: {e}")


# ───────────────────────────────────────────────────────────────────────────────
# Entry point
# ───────────────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    import uvicorn

    # HF Spaces uses port 7860; fall back to 7860 on other servers too.
    port = int(os.environ.get("PORT", 7860))
    uvicorn.run(app, host="0.0.0.0", port=port)
