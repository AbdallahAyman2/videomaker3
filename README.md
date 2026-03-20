---
title: AI Video Generator
emoji: 🎬
colorFrom: blue
colorTo: purple
sdk: docker
pinned: false
---

# AI Video Generator

🎥 An AI Video Generator tool developed by the "Arabian AI School" YouTube channel

🎬 YouTube: https://www.youtube.com/@ArabianAiSchool  
📸 Instagram: https://www.instagram.com/arabianaischool  
👍 Facebook: https://www.facebook.com/arabianaischool  
🐦 Twitter: https://twitter.com/arabianaischool  
✉️ Email: arabianaischool@gmail.com  

▶️ Tutorial Video & More Info on the channel

---

## 🚀 Project Overview

**AI Video Generator** is a FastAPI-based pipeline that:

1. Uses **Google Gemini** to write a video script.
2. Splits the script into lines and generates AI images (Pollinations.ai – free).
3. Translates prompts via `googletrans` if needed.
4. Generates voice-overs with **ElevenLabs TTS**.
5. Assembles images, audio and captions into a vertical short video with **MoviePy** + **FFmpeg**.
6. Streams real-time progress via Server-Sent Events (SSE).
7. **Uploads the finished video to a Telegram bot** automatically.

Anyone with the server URL can open the web UI or call the HTTP API to generate a video.

---

## 📋 Features

- **Automated Script Writing** with Google Gemini  
- **AI Image Generation** for each caption segment (Pollinations.ai, free)  
- **High-Quality TTS** from ElevenLabs  
- **Dynamic Video Composition** (MoviePy + FFmpeg)  
- **Live Progress Updates** through SSE endpoint (`/stream`)  
- **Download endpoint** (`/download`) for the generated MP4  
- **Telegram upload** – finished video is sent to your bot automatically  
- **n8n / HTTP integration** – trigger generation via GET `/generate?topic=…&voice_name=…`  

---

## 🔑 Required Secrets

Set the following environment variables / secrets before running:

| Secret name            | Description                                      |
|------------------------|--------------------------------------------------|
| `GEMINI_API_KEY`       | Google Gemini API key                            |
| `ELEVENLABS_API_KEY`   | ElevenLabs text-to-speech API key                |
| `TELEGRAM_BOT_TOKEN`   | Telegram Bot token (from @BotFather)             |
| `TELEGRAM_CHAT_ID`     | Telegram chat / channel ID where videos are sent |

---

## ☁️ Deploying to Hugging Face Spaces (recommended – free)

1. Create a new Space at https://huggingface.co/new-space  
   - **SDK**: Docker  
   - **Visibility**: Public (so anyone with the link can access it)
2. Push this repository to the Space.
3. In the Space **Settings → Secrets**, add all four secrets listed above.
4. The app starts automatically on port **7860**.

---

## 🐙 Deploying to GitHub Codespaces (free tier)

1. Open the repository in a Codespace.
2. Install system dependencies once:
   ```bash
   sudo apt update && sudo apt install -y ffmpeg imagemagick
   ```
3. Install Python dependencies:
   ```bash
   pip install -r requirements.txt
   ```
4. Set secrets as environment variables or in a `.env` file (never commit it):
   ```bash
   export GEMINI_API_KEY="your_key"
   export ELEVENLABS_API_KEY="your_key"
   export TELEGRAM_BOT_TOKEN="your_token"
   export TELEGRAM_CHAT_ID="your_chat_id"
   ```
5. Start the server:
   ```bash
   python server.py
   ```
6. Forward port **7860** in the Ports tab to make it publicly accessible.

---

## 🖥️ Running Locally (Windows / Linux / macOS)

### System Dependencies

- **FFmpeg** – https://ffmpeg.org/download.html (add to PATH)
- **ImageMagick** – https://imagemagick.org (add to PATH)

### Setup

```bash
git clone https://github.com/AbdallahAyman2/videomaker3.git
cd videomaker3
python -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

Set the required environment variables, then run:

```bash
python server.py
```

Open http://localhost:7860 in your browser.

---

## 🔗 HTTP API (n8n integration)

| Method | Endpoint                                      | Description                             |
|--------|-----------------------------------------------|-----------------------------------------|
| GET    | `/`                                           | Web UI                                  |
| GET    | `/generate?topic=…&voice_name=…`              | Start video generation; returns `{"status":"started"}` |
| GET    | `/stream`                                     | SSE stream of progress messages         |
| GET    | `/download`                                   | Download the last generated MP4         |

**Example n8n HTTP Request node**:

```
GET https://your-space.hf.space/generate?topic=الذكاء الاصطناعي&voice_name=هيثم
```

---

## 📂 Project Structure

```
videomaker3/
├── .gitignore
├── LICENSE
├── README.md
├── requirements.txt
├── server.py
├── utils/
│   ├── gemini.py          # Gemini API wrapper
│   ├── write_script.py    # Script generation helpers
│   ├── image_gen.py       # Image download from Pollinations.ai
│   ├── voice_gen.py       # ElevenLabs TTS
│   └── video_creation.py  # MoviePy video assembly
├── static/                # Front-end assets (CSS, images)
├── templates/             # Jinja2 HTML templates
└── outputs/               # (gitignored) generated images / audio / video
    └── font.ttf
```

---

## ✍️ Customization

- **Modify prompts**: edit `utils/write_script.py`.
- **Tweak video styles**: adjust MoviePy composition in `utils/video_creation.py`.
- **Add new voices**: update the `voice_options` dict in `server.py`.
- **Template changes**: update files under `templates/`.
