#!/usr/bin/env python3
"""Merge all videos in a folder into one file (merged.mp4), with monthly chapters.

- Clips are ordered by the date they were recorded (read from the video metadata),
  oldest first. Works across several phones. Falls back to the file's modified
  time when a video has no recording date.
- The video is vertical (1080x1920) if most clips are vertical, otherwise
  horizontal (1920x1080). Clips with a different orientation get black bars.
  When merged.mp4 already exists, its size is kept.
- Whenever the month changes, a black title card ("March 2024") is inserted and a
  chapter is created, so you can jump from month to month in most video players.
  Between clips of the same month, a short black screen is inserted instead.
- A chapters.txt is written next to merged.mp4, ready to paste into a YouTube
  video description (YouTube then shows the chapters on the progress bar).
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
from PIL import Image, ImageDraw, ImageFont

FFMPEG = imageio_ffmpeg.get_ffmpeg_exe()
VIDEO_EXTS = {".mp4", ".mov", ".m4v", ".mkv", ".avi", ".3gp", ".webm",
              ".mts", ".m2ts", ".wmv"}
MERGED_NAME = "merged.mp4"
CHAPTERS_NAME = "chapters.txt"
MONTHS = ["January", "February", "March", "April", "May", "June", "July",
          "August", "September", "October", "November", "December"]

# Encoding settings shared by clips, gaps and title cards so they can be joined
# without re-encoding.
ENCODE_OPTS = ["-c:v", "libx264", "-preset", "medium", "-crf", "18",
               "-pix_fmt", "yuv420p",
               "-c:a", "aac", "-b:a", "192k", "-ar", "48000", "-ac", "2"]


# ----------------------------------------------------------------- ffmpeg info
def ffmpeg_info(path: Path) -> str:
    """Text printed by `ffmpeg -i` (metadata, streams, duration, chapters)."""
    return subprocess.run([FFMPEG, "-hide_banner", "-i", str(path)],
                          capture_output=True, text=True).stderr


def has_audio(path: Path) -> bool:
    return re.search(r"Stream #.*Audio:", ffmpeg_info(path)) is not None


def duration(path: Path) -> float:
    m = re.search(r"Duration:\s*(\d+):(\d+):(\d+(?:\.\d+)?)", ffmpeg_info(path))
    if not m:
        raise RuntimeError(f"Cannot read the duration of {path}")
    h, mi, s = m.groups()
    return int(h) * 3600 + int(mi) * 60 + float(s)


def read_chapters(path: Path):
    """Chapters already stored in a video, as a list of (start_seconds, title)."""
    pattern = (r"Chapter #\d+:\d+: start ([\d.]+), end [\d.]+\s*\n"
               r"\s*Metadata:\s*\n\s*title\s*:\s*(.+)")
    return [(float(s), t.strip()) for s, t in re.findall(pattern, ffmpeg_info(path))]


def video_size(path: Path):
    """(width, height) of the first video stream as it is displayed, or None.

    Phones often store vertical videos as landscape plus a rotation flag, so the
    rotation is taken into account.
    """
    info = ffmpeg_info(path)
    line = re.search(r"Stream #.*Video:.*", info)
    if not line:
        return None
    m = re.search(r"[,\s](\d{2,5})x(\d{2,5})[,\s\[]", line.group(0) + " ")
    if not m:
        return None
    w, h = int(m.group(1)), int(m.group(2))
    r = (re.search(r"rotation of (-?[\d.]+) degrees", info)
         or re.search(r"rotate\s*:\s*(-?\d+)", info))
    if r and int(abs(float(r.group(1)))) % 180 == 90:
        w, h = h, w
    return w, h


def choose_size(args, merged: Path, clips):
    """Output size: existing merged.mp4 > --width/--height > --orientation."""
    if merged.exists():
        size = video_size(merged)
        if size:
            if args.width and args.height and (args.width, args.height) != size:
                print(f"Note: merged.mp4 is {size[0]}x{size[1]}, so that size is kept "
                      f"(delete merged.mp4 to start over with another size).")
            return size
    if args.width or args.height:
        if not (args.width and args.height):
            sys.exit("Please give both --width and --height.")
        return args.width, args.height
    if args.orientation == "auto":
        sizes = [video_size(c) for c in clips]
        vertical = sum(1 for z in sizes if z and z[1] > z[0])
        horizontal = sum(1 for z in sizes if z and z[1] <= z[0])
        orientation = "vertical" if vertical > horizontal else "horizontal"
        print(f"Orientation: {orientation} ({vertical} vertical, "
              f"{horizontal} horizontal clip(s))")
    else:
        orientation = args.orientation
    return (1080, 1920) if orientation == "vertical" else (1920, 1080)


# ------------------------------------------------------------------- ordering
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
    m = re.search(r"creation_time\s*:\s*(\S+)", ffmpeg_info(path))  # first = container
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


def sort_key(mode: str, recorded: dict):
    if mode == "added":      # when pasted into the folder
        return added_time
    if mode == "modified":   # file modified time
        return lambda p: p.stat().st_mtime
    if mode == "name":
        return lambda p: p.name.lower()
    return lambda p: recorded[p]  # default: when the video was shot


# --------------------------------------------------------------------- months
def get_timezone(name):
    if not name:
        return None  # local time zone of this computer
    from zoneinfo import ZoneInfo
    return ZoneInfo(name)


def month_of(timestamp: float, tz):
    dt = datetime.fromtimestamp(timestamp, tz)
    return (dt.year, dt.month)


def month_label(ym) -> str:
    return f"{MONTHS[ym[1] - 1]} {ym[0]}"


def parse_month_label(title: str):
    parts = title.split()
    if len(parts) == 2 and parts[0] in MONTHS and parts[1].isdigit():
        return (int(parts[1]), MONTHS.index(parts[0]) + 1)
    return None


# ------------------------------------------------------------------- encoding
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


def load_font(size: int):
    for name in ("DejaVuSans.ttf", "Arial.ttf", "arial.ttf", "Helvetica.ttc"):
        try:
            return ImageFont.truetype(name, size)
        except OSError:
            pass
    return ImageFont.load_default(size=size)


def make_title_card(dst: Path, label: str, seconds: float,
                    width: int, height: int, fps: int):
    """Black screen with the month and year written in white, silent audio."""
    png = dst.with_suffix(".png")
    img = Image.new("RGB", (width, height), "black")
    draw = ImageDraw.Draw(img)
    size = max(12, min(height // 8, width // 8))
    font = load_font(size)
    while size > 12 and draw.textlength(label, font=font) > width * 0.85:
        size -= 4
        font = load_font(size)
    draw.text((width / 2, height / 2), label, fill="white", font=font, anchor="mm")
    img.save(png)
    subprocess.run([
        FFMPEG, "-y", "-hide_banner", "-loglevel", "error",
        "-loop", "1", "-framerate", str(fps), "-i", str(png),
        "-f", "lavfi", "-i", "anullsrc=r=48000:cl=stereo",
        "-t", str(seconds), "-r", str(fps), *ENCODE_OPTS, str(dst)], check=True)


# ------------------------------------------------------------------- chapters
def fmt_time(seconds: float) -> str:
    s = int(seconds)
    h, rem = divmod(s, 3600)
    m, sec = divmod(rem, 60)
    return f"{h}:{m:02d}:{sec:02d}" if h else f"{m}:{sec:02d}"


def write_ffmetadata(path: Path, chapters, total: float):
    lines = [";FFMETADATA1"]
    for i, (start, title) in enumerate(chapters):
        end = chapters[i + 1][0] if i + 1 < len(chapters) else total
        lines += ["[CHAPTER]", "TIMEBASE=1/1000",
                  f"START={int(round(start * 1000))}",
                  f"END={int(round(end * 1000))}", f"title={title}"]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def write_chapters_txt(path: Path, chapters, total: float):
    path.write_text("".join(f"{fmt_time(s)} {t}\n" for s, t in chapters),
                    encoding="utf-8")
    print(f"\nChapters (saved to {path.name}, paste into the YouTube description):")
    for s, t in chapters:
        print(f"  {fmt_time(s)} {t}")
    ends = [c[0] for c in chapters[1:]] + [total]
    if len(chapters) < 3 or any(e - c[0] < 10 for c, e in zip(chapters, ends)):
        print("  Note: YouTube only shows chapters if there are at least 3, "
              "each at least 10 seconds long.")


# ----------------------------------------------------------------------- main
def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("directory", type=Path, nargs="?",
                    default=Path(__file__).resolve().parent,
                    help="folder with the videos (default: folder of this script)")
    ap.add_argument("--gap", type=float, default=0.5,
                    help="seconds of black screen between clips of the same month "
                         "(default: 0.5, 0 = none)")
    ap.add_argument("--title-duration", type=float, default=2.0,
                    help="seconds the month title card is shown (default: 2)")
    ap.add_argument("--no-chapters", action="store_true",
                    help="no month title cards and no chapters, only the gap")
    ap.add_argument("--timezone", default=None,
                    help="time zone used to decide the month of a clip, e.g. "
                         "Europe/Brussels (default: this computer's time zone)")
    ap.add_argument("--sort", choices=["recorded", "added", "modified", "name"],
                    default="recorded",
                    help="clip order (default: recorded = date in the video metadata, "
                         "oldest first)")
    ap.add_argument("--reverse", action="store_true", help="newest first instead")
    ap.add_argument("--orientation", choices=["auto", "vertical", "horizontal"],
                    default="auto",
                    help="video format (default: auto = vertical 1080x1920 if most "
                         "clips are vertical, otherwise horizontal 1920x1080)")
    ap.add_argument("--width", type=int, default=None,
                    help="custom output width (use together with --height)")
    ap.add_argument("--height", type=int, default=None,
                    help="custom output height (use together with --width)")
    ap.add_argument("--fps", type=int, default=30)
    args = ap.parse_args()

    tz = get_timezone(args.timezone)
    folder = args.directory.resolve()
    merged = folder / MERGED_NAME
    candidates = [p for p in folder.iterdir()
                  if p.is_file() and p.suffix.lower() in VIDEO_EXTS and p != merged
                  and not p.name.startswith(".")]
    if not candidates:
        print("No new videos found. Nothing to do.")
        return

    print("Reading video dates ...")
    recorded = {p: recorded_time(p) for p in candidates}
    clips = sorted(candidates, key=sort_key(args.sort, recorded), reverse=args.reverse)

    print(f"Merging {len(clips)} clip(s)"
          + (" after the existing merged.mp4" if merged.exists() else "") + ":")
    for c in clips:
        print(f"  - {c.name}  ({month_label(month_of(recorded[c], tz))})")

    use_chapters = not args.no_chapters
    width, height = choose_size(args, merged, clips)
    print(f"Output size: {width}x{height}")

    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        gap_clip = None
        if args.gap > 0:
            gap_clip = tmp / "gap.mp4"
            make_gap(gap_clip, args.gap, width, height, args.fps)

        encoded = []
        for i, clip in enumerate(clips):
            out = tmp / f"part_{i:04d}.mp4"
            print(f"Encoding {clip.name} ...")
            normalize(clip, out, width, height, args.fps)
            encoded.append(out)

        # Existing merged.mp4 goes first, untouched; keep its chapters.
        playlist, chapters, prev_month, t = [], [], None, 0.0
        if merged.exists():
            playlist.append(merged)
            t = duration(merged)
            if use_chapters:
                chapters = read_chapters(merged)
                if chapters:
                    prev_month = parse_month_label(chapters[-1][1])
                else:
                    chapters = [(0.0, "Earlier videos")]

        cards = {}
        for clip, enc in zip(clips, encoded):
            ym = month_of(recorded[clip], tz)
            separator = None
            if use_chapters and ym != prev_month:
                label = month_label(ym)
                if label not in cards:
                    cards[label] = tmp / f"card_{len(cards):03d}.mp4"
                    make_title_card(cards[label], label, args.title_duration,
                                    width, height, args.fps)
                separator = cards[label]
                chapters.append((t, label))
            elif playlist and gap_clip:
                separator = gap_clip
            if separator:
                playlist.append(separator)
                t += duration(separator)
            playlist.append(enc)
            t += duration(enc)
            prev_month = ym

        listfile = tmp / "list.txt"
        listfile.write_text("".join(
            "file '{}'\n".format(p.as_posix().replace("'", r"'\''"))
            for p in playlist))

        cmd = [FFMPEG, "-y", "-hide_banner", "-loglevel", "error",
               "-f", "concat", "-safe", "0", "-i", str(listfile)]
        if chapters:
            metafile = tmp / "chapters.ffmeta"
            write_ffmetadata(metafile, chapters, t)
            cmd += ["-i", str(metafile), "-map", "0",
                    "-map_metadata", "1", "-map_chapters", "1"]
        result = tmp / "result.mp4"
        cmd += ["-c", "copy", "-movflags", "+faststart", str(result)]
        subprocess.run(cmd, check=True)
        total = duration(result)
        shutil.move(str(result), str(merged))

    print(f"\nDone: {merged}")
    if chapters:
        write_chapters_txt(folder / CHAPTERS_NAME, chapters, total)
    print("\nYou can now delete the original clips; new ones will be appended "
          "after merged.mp4 next time.")


if __name__ == "__main__":
    try:
        main()
    except subprocess.CalledProcessError as e:
        sys.exit(f"ffmpeg failed: {e}")
