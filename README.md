# video-merger

Merge all the videos in a folder (for example clips recorded with your phone) into a single `merged.mp4`, with a black title card ("March 2024") at the start of every month and a chapter for each month.

- Vertical or horizontal: the merged video is vertical (1080x1920) when most of your clips are vertical, otherwise horizontal (1920x1080). Detected automatically, including phone videos that are stored as landscape with a rotation flag.
- Works with mp4, mov, m4v, mkv, avi, 3gp, webm and more.
- Clips are joined in chronological order, using the recording date stored in each video's metadata: **the video shot first comes first**. This also works with videos from several phones.
- Monthly chapters: the video contains one chapter per month, so you can jump from month to month in players that show chapters (VLC, QuickTime on Mac and most desktop players; phone players vary). A `chapters.txt` is also written, ready to paste into a YouTube description.
- Incremental: keep `merged.mp4`, delete the clips you already used, paste new ones, run again. The new clips are appended after the existing merged video, which is not re-encoded (no quality loss).
- Self-contained: a local virtual environment (`.venv`) holds everything, including ffmpeg (via the `imageio-ffmpeg` package). Nothing is installed on your system and no existing Python packages are used.

## Project layout

Put the project folder and your videos in the **same directory**:

```
my-videos/
├── merge_videos.py
├── requirements.txt
├── README.md
├── .gitignore        # keeps .venv and video files out of Git
├── .venv/            # created by you (step 1 below)
├── clip1.mp4         # your videos
├── clip2.mov
├── merged.mp4        # created by the script
└── chapters.txt      # created by the script (for YouTube)
```

## 1. Set up the virtual environment (once)

Requires Python 3.9 or newer.

**macOS / Linux**

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

**Windows (PowerShell)**

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

**Windows (cmd)**

```bat
python -m venv .venv
.venv\Scripts\activate.bat
pip install -r requirements.txt
```

## 2. Activate the environment (every new terminal)

```bash
source .venv/bin/activate        # macOS / Linux
.venv\Scripts\Activate.ps1       # Windows PowerShell
```

Leave it with `deactivate`.

## 3. Merge the videos

Copy your videos into the project folder, then run:

```bash
python merge_videos.py
```

The result is `merged.mp4` in the same folder, plus `chapters.txt`.

Before encoding, the script lists the clips with their month, in the order it will use.

### Adding more videos later

1. Delete the original clips you already merged (keep `merged.mp4`).
2. Paste the new clips into the folder.
3. Run `python merge_videos.py` again.

The new clips are appended after `merged.mp4`, in chronological order, and the existing chapters are kept. If the first new clip is from the same month as the last chapter, no new title card is added. `merged.mp4` always stays first, so new clips should be more recent than the ones already merged. If you leave the old clips in the folder, they will be merged again.

## Options

| Option | Default | Description |
| --- | --- | --- |
| `directory` | folder of the script | Folder containing the videos |
| `--gap SECONDS` | `0.5` | Black screen between clips of the same month; `0` for no break |
| `--title-duration SECONDS` | `2` | How long the month title card is shown |
| `--no-chapters` | off | No title cards and no chapters, only the gap between clips |
| `--timezone NAME` | this computer's time zone | Time zone used to decide which month a clip belongs to, e.g. `Europe/Brussels` |
| `--sort recorded\|added\|modified\|name` | `recorded` | Order of the clips (see below) |
| `--reverse` | off | Newest first instead of oldest first |
| `--orientation auto\|vertical\|horizontal` | `auto` | Video format: vertical is 1080x1920, horizontal is 1920x1080. `auto` picks the format of the majority of the clips |
| `--width`, `--height` | from orientation | Custom output resolution (give both). Clips are scaled to fit, with black bars |
| `--fps` | `30` | Output frame rate |

Examples:

```bash
python merge_videos.py --orientation vertical    # force a vertical video
python merge_videos.py --gap 1.5                 # longer break
python merge_videos.py --gap 0                   # no break
python merge_videos.py --title-duration 3        # longer month title
python merge_videos.py --timezone Europe/Brussels
python merge_videos.py --sort added              # order by when files were pasted
python merge_videos.py /path/to/other/folder     # use another folder
```

### How the order is decided

- `recorded` (default): the recording date stored in the video metadata (`creation_time`), oldest first. Phones normally write it in UTC, so videos from different phones and time zones line up correctly. If a video has no usable date (for example it was re-saved by a messaging app that strips metadata), its file modified time is used instead.
- `added`: when the file was pasted into the folder (creation time on macOS and Windows; closest equivalent on Linux).
- `modified`: the file modified time.
- `name`: alphabetical.

The script lists the clips in the order it will use before it starts encoding, so you can check it. Press Ctrl+C to stop if the order looks wrong.

## Chapters and YouTube

`chapters.txt` looks like this:

```
0:00 January 2024
12:41 February 2024
25:03 April 2024
```

When you upload `merged.mp4` to YouTube (for example as a private video), paste this text into the video description. YouTube then shows the chapters on the progress bar with previews, and you can jump between months. YouTube requires the first chapter at `0:00`, at least three chapters, and at least 10 seconds per chapter. The script warns you if this is not met. Uploading is done manually.

The chapters are also stored inside `merged.mp4` itself, so they work offline in players that support chapters. If merged.mp4 was created with an older version of this script (no chapters), the existing part becomes a chapter called "Earlier videos".

## Notes

- Every new clip is re-encoded to H.264 / AAC at the chosen resolution and frame rate, so clips from different phones or orientations (portrait/landscape) can be joined. Clips without audio get silent audio.
- The format is decided the first time. Later runs keep the size of the existing `merged.mp4`, even if you add clips of the other orientation (they get black bars). To change the format, delete `merged.mp4` and merge your clips again. Changing `--fps` later has the same limitation.
- Clips with a different orientation than the video (for example a horizontal clip in a vertical video) are shown fully, with black bars above and below.
- A clip is assigned to a month using the time zone above, so a clip shot late on the last day of a month is not moved to the wrong month.
- Month names are in English.
- Encoding takes time for long videos.

## Put it on GitHub

```bash
git init
git add .
git commit -m "Initial commit: video merger"
git branch -M main
git remote add origin https://github.com/<your-user>/video-merger.git
git push -u origin main
```

`.gitignore` excludes `.venv/` and all video files, so only the code and documentation are uploaded.
