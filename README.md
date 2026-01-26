# AI Video Generator

🎥 An AI Video Generator tool developed by the “Arabian AI School” YouTube channel

🎬 YouTube: https://www.youtube.com/@ArabianAiSchool

📸 Instagram: https://www.instagram.com/arabianaischool

👍 Facebook: https://www.facebook.com/arabianaischool

🐦 Twitter: https://twitter.com/arabianaischool

✉️ Email: arabianaischool@gmail.com

▶️ Tutorial Video & More Info on the channel
---

## 🚀 Project Overview

**AI Video Generator** is a FastAPI-based pipeline that:
1. Uses **Google Gemini** (via `gemini_secret.txt`) to write a video script.
2. Splits the script into lines and generates AI images (Pollinations).( you can use any other image or video generation api )
3. Translates prompts via `googletrans` if needed.
4. Generates voice-overs with **ElevenLabs TTS** (`voice_secret.txt`).
5. Assembles images or videos, audio, and captions into a short video with **MoviePy**, **FFmpeg**, and **ImageMagick**.
6. Streams real-time progress via Server-Sent Events (SSE).

Ideal for automating quick YouTube Shorts,videos or social media clips on any topic.

---

## 📋 Features

- **Automated Script Writing** with Google Gemini  
- **Image and video Generation** for each caption segment  
- **High-Quality TTS** from ElevenLabs  
- **Dynamic Video Composition** (MoviePy + FFmpeg + ImageMagick)  
- **Live Progress Updates** through SSE endpoint  
- **Modular Codebase** for easy customization  

---

## ⚙️ Prerequisites

### 1. System Dependencies

- **FFmpeg**  
  - **Windows**: Download installer from [ffmpeg.org](https://ffmpeg.org/download.html) → Add `ffmpeg.exe` to your `PATH`.  
  - **macOS**:  
    ```bash
    brew install ffmpeg
    ```
  - **Ubuntu/Debian Linux**:  
    ```bash
    sudo apt update
    sudo apt install ffmpeg
    ```

- **ImageMagick**  
  - **Windows**: Download from https://imagemagick.org → Add `magick.exe` to your `PATH`.  
  - **macOS**:  
    ```bash
    brew install imagemagick
    ```
  - **Ubuntu/Debian Linux**:  
    ```bash
    sudo apt update
    sudo apt install imagemagick
    ```

### 2. Python 3.9+

Ensure you have **Python 3.9** or newer installed.

### 3. API Keys

Create two text files in the project root (they are ignored by `.gitignore`):

- `gemini_secret.txt`  
  - Your Google Gemini API key.

- `voice_secret.txt`  
  - Your ElevenLabs API key.

---

## 🛠️ Installation & Setup

1. **Clone the repository**  
   ```bash
   git clone https://github.com/Arabianaischool/AIVIDEOGEN.git
   cd AIVIDEOGEN
````

2. **Create & activate a virtual environment**

   ```bash
   python3 -m venv .venv
   source .venv/bin/activate      # macOS/Linux
   .venv\Scripts\activate         # Windows PowerShell
   ```

3. **Install Python dependencies**

   ```bash
   pip install --upgrade pip
   pip install -r requirements.txt
   ```

---

## ▶️ Running the Server

Start the FastAPI application:

```bash
uvicorn server:app --reload --host 127.0.0.1 --port 8000
```

* Open your browser to **[http://127.0.0.1:8000](http://127.0.0.1:8000)**.
* Enter a **topic** and select a **voice**.
* Watch real-time progress and download your generated video when it completes.

---

## 📂 Project Structure

```
AIVIDEOGEN/
├── .gitignore
├── LICENSE
├── README.md
├── gemini_secret.txt         # (ignored) Google Gemini key
├── voice_secret.txt          # (ignored) ElevenLabs key
├── requirements.txt
├── server.py
├── utils/
│   ├── gemini.py
│   ├── write_script.py
│   ├── image_gen.py
│   ├── voice_gen.py
│   └── video_creation.py
├── static/                   # Front-end assets (CSS, JS, images)
├── templates/                # Jinja2 HTML templates
└── outputs/                  # (ignored) generated images/audio/video
```

---

## ✍️ Customization

* **Modify prompts**: edit `utils/write_script.py`.
* **Tweak video styles**: adjust MoviePy composition in `utils/video_creation.py`.
* **Add new voices**: update the voice list in `server.py`.
* **Template changes**: update files under `templates/`.

---


