# utils/video_creation.py

import os
import glob
import re

from moviepy.editor import (
    ImageClip,
    AudioFileClip,
    concatenate_videoclips,
)

# Target dimensions for YouTube Shorts (9:16 vertical)
TARGET_W = 1080
TARGET_H = 1920


def _resize_clip(clip):
    """Resize an ImageClip to fit within TARGET_W x TARGET_H, adding black bars if needed."""
    clip = clip.resize(height=TARGET_H)
    if clip.w > TARGET_W:
        clip = clip.resize(width=TARGET_W)
    # Center the clip on a black background of exact dimensions
    from moviepy.editor import ColorClip, CompositeVideoClip
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


def video_main() -> str:
    """
    Combine per-sentence images and audio into a vertical MP4 (YouTube Shorts).

    Reads from:
        outputs/images/part{i}.jpg
        outputs/audio/part{i}.mp3

    Writes to:
        outputs/youtube_short.mp4

    Returns the path to the output file.
    """
    outputs_dir = os.path.join(os.getcwd(), "outputs")
    images_dir = os.path.join(outputs_dir, "images")
    audio_dir = os.path.join(outputs_dir, "audio")

    image_files = sorted(
        glob.glob(os.path.join(images_dir, "part*.jpg")), key=_sort_key
    )
    audio_files = sorted(
        glob.glob(os.path.join(audio_dir, "part*.mp3")), key=_sort_key
    )

    if not image_files or not audio_files:
        raise RuntimeError(
            f"Missing media files.\n"
            f"  Images found: {len(image_files)}\n"
            f"  Audio  found: {len(audio_files)}"
        )

    clips = []
    for i, (img_path, aud_path) in enumerate(zip(image_files, audio_files)):
        try:
            audio = AudioFileClip(aud_path)
            image = ImageClip(img_path, duration=audio.duration).set_audio(audio)
            image = _resize_clip(image)
            clips.append(image)
        except Exception as e:
            print(f"Warning: skipping part {i} due to error: {e}")

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

    # Clean up clip resources
    final.close()
    for c in clips:
        c.close()

    return out_path


if __name__ == "__main__":
    path = video_main()
    print(f"Video saved to: {path}")
