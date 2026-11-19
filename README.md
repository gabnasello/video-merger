# video-merger

Merge all the videos in a folder (for example clips recorded with your phone) into a single `merged.mp4`, with a short black screen between clips.

- Works with mp4, mov, m4v, mkv, avi, 3gp, webm and more.
- Clips are joined in chronological order, using the recording date stored in each video's metadata: **the video shot first comes first**. This also works with videos from several phones.
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
└── merged.mp4        # created by the script
```

## 1. Set up the virtual environment (once)

Requires Python 3.8 or newer.

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

The result is `merged.mp4` in the same folder.

### Adding more videos later

1. Delete the original clips you already merged (keep `merged.mp4`).
2. Paste the new clips into the folder.
3. Run `python merge_videos.py` again.

The new clips are appended after `merged.mp4`, in chronological order. `merged.mp4` always stays first, so new clips should be more recent than the ones already merged. If you leave the old clips in the folder, they will be merged again.

## Options

| Option | Default | Description |
| --- | --- | --- |
| `directory` | folder of the script | Folder containing the videos |
| `--gap SECONDS` | `0.5` | Black screen between clips; `0` for no break |
| `--sort recorded\|added\|modified\|name` | `recorded` | Order of the clips (see below) |
| `--reverse` | off | Newest first instead of oldest first |
| `--width`, `--height` | `1920`, `1080` | Output resolution (clips are scaled to fit, with black bars) |
| `--fps` | `30` | Output frame rate |

Examples:

```bash
python merge_videos.py --gap 1.5                 # longer break
python merge_videos.py --gap 0                   # no break
python merge_videos.py --sort added              # order by when files were pasted
python merge_videos.py /path/to/other/folder     # use another folder
```

### How the order is decided

- `recorded` (default): the recording date stored in the video metadata (`creation_time`), oldest first. Phones normally write it in UTC, so videos from different phones and time zones line up correctly. If a video has no usable date (for example it was re-saved by a messaging app that strips metadata), its file modified time is used instead.
- `added`: when the file was pasted into the folder (creation time on macOS and Windows; closest equivalent on Linux).
- `modified`: the file modified time.
- `name`: alphabetical.

The script lists the clips in the order it will use before it starts encoding, so you can check it. Press Ctrl+C to stop if the order looks wrong.

## Notes

- Every new clip is re-encoded to H.264 / AAC at the chosen resolution and frame rate, so clips from different phones or orientations (portrait/landscape) can be joined. Clips without audio get silent audio.
- If you change `--width`, `--height` or `--fps` after creating `merged.mp4`, the existing part keeps its old settings.
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
