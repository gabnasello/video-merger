#!/usr/bin/env python3
"""Merge all videos in a folder into one file (merged.mp4).

- Clips are ordered by the date they were recorded (read from the video metadata),
  oldest first. Works across several phones. Falls back to the file's modified
  time when a video has no recording date.
- A short black screen (default 0.5 s) is inserted between clips.
- If merged.mp4 already exists, it is always placed first and is NOT re-encoded,
  so you can delete the source clips and keep adding new ones over time.
- Uses the ffmpeg binary bundled with the `imageio-ffmpeg` package, so nothing
  needs to be installed system-wide.

By default the folder is the one that contains this script.
"""
import argparse
import re
import shutil
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

import imageio_ffmpeg

FFMPEG = imageio_ffmpeg.get_ffmpeg_exe()
VIDEO_EXTS = {".mp4", ".mov", ".m4v", ".mkv", ".avi", ".3gp", ".webm",
              ".mts", ".m2ts", ".wmv"}
MERGED_NAME = "merged.mp4"

# Encoding settings shared by clips and gaps so they can be joined without re-encoding.
ENCODE_OPTS = ["-c:v", "libx264", "-preset", "medium", "-crf", "18",
               "-pix_fmt", "yuv420p",
               "-c:a", "aac", "-b:a", "192k", "-ar", "48000", "-ac", "2"]


def added_time(path: Path) -> float:
    """Approximate when the file was pasted into the folder."""
    st = path.stat()
    # macOS/Windows: creation time of the copy. Linux: inode change time.
    return getattr(st, "st_birthtime", None) or st.st_ctime


def recorded_time(path: Path) -> float:
    """Recording date from the video metadata (UTC timestamp).

    Falls back to the file's modified time if the metadata is missing or invalid
    (for example videos re-saved by a messaging app).
    """
    out = subprocess.run([FFMPEG, "-hide_banner", "-i", str(path)],
                         capture_output=True, text=True).stderr
    m = re.search(r"creation_time\s*:\s*(\S+)", out)  # first match = container level
    if m:
        try:
            dt = datetime.fromisoformat(m.group(1).replace("Z", "+00:00"))
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            if dt.year >= 1990:  # ignore placeholder dates such as 1970 or 1904
                return dt.timestamp()
        except ValueError:
            pass
    return path.stat().st_mtime


def sort_key(mode: str):
    if mode == "added":      # when pasted into the folder
        return added_time
    if mode == "modified":   # file modified time
        return lambda p: p.stat().st_mtime
    if mode == "name":
        return lambda p: p.name.lower()
    return recorded_time     # default: when the video was shot


def has_audio(path: Path) -> bool:
    out = subprocess.run([FFMPEG, "-hide_banner", "-i", str(path)],
                         capture_output=True, text=True).stderr
    return re.search(r"Stream #.*Audio:", out) is not None


def normalize(src: Path, dst: Path, width: int, height: int, fps: int):
    """Re-encode a clip to a common format so clips can be joined safely."""
    audio = has_audio(src)
    vf = (f"scale={width}:{height}:force_original_aspect_ratio=decrease,"
          f"pad={width}:{height}:(ow-iw)/2:(oh-ih)/2,setsar=1,fps={fps}")
    cmd = [FFMPEG, "-y", "-hide_banner", "-loglevel", "error", "-i", str(src)]
    if not audio:  # add silent audio so every clip has the same streams
        cmd += ["-f", "lavfi", "-i", "anullsrc=r=48000:cl=stereo"]
    cmd += ["-map", "0:v:0", "-map", "0:a:0" if audio else "1:a:0"]
    if not audio:
        cmd += ["-shortest"]
    cmd += ["-vf", vf, *ENCODE_OPTS, str(dst)]
    subprocess.run(cmd, check=True)


def make_gap(dst: Path, seconds: float, width: int, height: int, fps: int):
    """Create a black, silent clip of the given length."""
    subprocess.run([
        FFMPEG, "-y", "-hide_banner", "-loglevel", "error",
        "-f", "lavfi", "-i", f"color=c=black:s={width}x{height}:r={fps}",
        "-f", "lavfi", "-i", "anullsrc=r=48000:cl=stereo",
        "-t", str(seconds), *ENCODE_OPTS, str(dst)], check=True)


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("directory", type=Path, nargs="?",
                    default=Path(__file__).resolve().parent,
                    help="folder with the videos (default: folder of this script)")
    ap.add_argument("--gap", type=float, default=0.5,
                    help="seconds of black screen between clips (default: 0.5, 0 = none)")
    ap.add_argument("--sort", choices=["recorded", "added", "modified", "name"],
                    default="recorded",
                    help="clip order (default: recorded = date in the video metadata, "
                         "oldest first)")
    ap.add_argument("--reverse", action="store_true", help="newest first instead")
    ap.add_argument("--width", type=int, default=1920)
    ap.add_argument("--height", type=int, default=1080)
    ap.add_argument("--fps", type=int, default=30)
    args = ap.parse_args()

    folder = args.directory.resolve()
    merged = folder / MERGED_NAME
    clips = sorted(
        (p for p in folder.iterdir()
         if p.is_file() and p.suffix.lower() in VIDEO_EXTS and p != merged
         and not p.name.startswith(".")),
        key=sort_key(args.sort), reverse=args.reverse)

    if not clips:
        print("No new videos found. Nothing to do.")
        return

    print(f"Merging {len(clips)} clip(s)"
          + (" after the existing merged.mp4" if merged.exists() else "") + ":")
    for c in clips:
        print("  -", c.name)

    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        gap_clip = None
        if args.gap > 0:
            gap_clip = tmp / "gap.mp4"
            make_gap(gap_clip, args.gap, args.width, args.height, args.fps)

        encoded = []
        for i, clip in enumerate(clips):
            out = tmp / f"part_{i:04d}.mp4"
            print(f"Encoding {clip.name} ...")
            normalize(clip, out, args.width, args.height, args.fps)
            encoded.append(out)

        # merged.mp4 (if any) first, already encoded; gap between every pair.
        parts = ([merged] if merged.exists() else []) + encoded
        playlist = []
        for i, part in enumerate(parts):
            if i > 0 and gap_clip:
                playlist.append(gap_clip)
            playlist.append(part)

        listfile = tmp / "list.txt"
        listfile.write_text("".join(
            "file '{}'\n".format(p.as_posix().replace("'", r"'\''"))
            for p in playlist))

        result = tmp / "result.mp4"
        subprocess.run([FFMPEG, "-y", "-hide_banner", "-loglevel", "error",
                        "-f", "concat", "-safe", "0", "-i", str(listfile),
                        "-c", "copy", "-movflags", "+faststart", str(result)],
                       check=True)
        shutil.move(str(result), str(merged))

    print(f"\nDone: {merged}")
    print("You can now delete the original clips; new ones will be appended "
          "after merged.mp4 next time.")


if __name__ == "__main__":
    try:
        main()
    except subprocess.CalledProcessError as e:
        sys.exit(f"ffmpeg failed: {e}")
