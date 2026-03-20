# utils/video_creation.py

import os
import glob
import re

from moviepy.editor import (
    ImageClip,
    VideoFileClip,
    AudioFileClip,
    ColorClip,
    CompositeVideoClip,
    concatenate_videoclips,
)
from moviepy.video.fx.loop import loop as vfx_loop

# Target dimensions for YouTube Shorts (9:16 vertical)
TARGET_W = 1080
TARGET_H = 1920


def _resize_clip(clip):
    """Resize a clip to fit within TARGET_W x TARGET_H, adding black bars if needed."""
    clip = clip.resize(height=TARGET_H)
    if clip.w > TARGET_W:
        clip = clip.resize(width=TARGET_W)
    bg = ColorClip(size=(TARGET_W, TARGET_H), color=[0, 0, 0], duration=clip.duration)
    return CompositeVideoClip(
        [bg, clip.set_position("center")],
        size=(TARGET_W, TARGET_H),
    )


def _sort_key(path):
    """Extract the numeric index from filenames like part0.jpg / part12.mp3."""
    name = os.path.splitext(os.path.basename(path))[0]
    m = re.search(r"(\d+)$", name)
    return int(m.group(1)) if m else 0


def _find_media_files(outputs_dir: str) -> list:
    """
    Collect media files for each part index in priority order:
      1. outputs/media/part{i}.mp4  (video preferred)
      2. outputs/media/part{i}.jpg  (image in new media dir)
      3. outputs/images/part{i}.jpg (legacy location)

    Returns a sorted list of (index, file_path) pairs.
    """
    media_dir  = os.path.join(outputs_dir, "media")
    images_dir = os.path.join(outputs_dir, "images")

    # Collect all candidates grouped by part index
    candidates = {}  # idx -> best_path

    def _add(path):
        idx = _sort_key(path)
        ext = os.path.splitext(path)[1].lower()
        existing = candidates.get(idx)
        if existing is None:
            candidates[idx] = path
        else:
            existing_ext = os.path.splitext(existing)[1].lower()
            # mp4 beats jpg; media_dir jpg beats images_dir jpg
            if ext == ".mp4" and existing_ext != ".mp4":
                candidates[idx] = path
            elif ext == ".jpg" and existing_ext == ".jpg":
                if media_dir in path and media_dir not in existing:
                    candidates[idx] = path

    for pattern in (
        os.path.join(media_dir,  "part*.mp4"),
        os.path.join(media_dir,  "part*.jpg"),
        os.path.join(images_dir, "part*.jpg"),
    ):
        for p in glob.glob(pattern):
            _add(p)

    return [candidates[k] for k in sorted(candidates.keys())]


def video_main() -> str:
    """
    Combine per-sentence media (video clips or still images) and audio into a
    vertical MP4 (YouTube Shorts, 1080×1920 @ 24 fps).

    Reads from:
        outputs/media/part{i}.mp4   — video clip (preferred)
        outputs/media/part{i}.jpg   — still image
        outputs/images/part{i}.jpg  — still image (legacy fallback)
        outputs/audio/part{i}.mp3   — audio narration

    Writes to:
        outputs/youtube_short.mp4

    Returns the path to the output file.
    """
    outputs_dir = os.path.join(os.getcwd(), "outputs")
    audio_dir   = os.path.join(outputs_dir, "audio")

    media_files = _find_media_files(outputs_dir)
    audio_files = sorted(
        glob.glob(os.path.join(audio_dir, "part*.mp3")), key=_sort_key
    )

    if not media_files or not audio_files:
        raise RuntimeError(
            f"Missing media files.\n"
            f"  Media found: {len(media_files)}\n"
            f"  Audio found: {len(audio_files)}"
        )

    clips = []
    for i, (media_path, aud_path) in enumerate(zip(media_files, audio_files)):
        try:
            audio = AudioFileClip(aud_path)
            ext   = os.path.splitext(media_path)[1].lower()

            if ext == ".mp4":
                vc = VideoFileClip(media_path, audio=False)
                if vc.duration >= audio.duration:
                    vc = vc.subclip(0, audio.duration)
                else:
                    # Loop the video to fill the audio duration
                    vc = vc.fx(vfx_loop, duration=audio.duration)
                vc = vc.set_audio(audio)
            else:
                # Still image (.jpg / .png)
                vc = ImageClip(media_path, duration=audio.duration).set_audio(audio)

            vc = _resize_clip(vc)
            clips.append(vc)
        except Exception as exc:
            print(f"Warning: skipping part {i} ({media_path}): {exc}")

    if not clips:
        raise RuntimeError("No clips could be created from the available media files.")

    final = concatenate_videoclips(clips, method="compose")

    out_path = os.path.join(outputs_dir, "youtube_short.mp4")
    final.write_videofile(
        out_path,
        fps=24,
        codec="libx264",
        audio_codec="aac",
        threads=4,
        preset="ultrafast",
        logger=None,
    )

    # Release resources
    final.close()
    for c in clips:
        c.close()

    return out_path


if __name__ == "__main__":
    path = video_main()
    print(f"Video saved to: {path}")
