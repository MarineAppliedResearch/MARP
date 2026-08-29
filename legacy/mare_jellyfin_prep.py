#This script helps prep videos for the mare Jellyfin Server. 
#!/usr/bin/env python3
"""
mare_fellyfin_prep.py

Author: Isaac Travers

Prepare MARE ROV FWD camera videos for a Jellyfin working server.

This script treats the source drive as read-only. It discovers FWD camera videos
inside DiveXX folders, transcodes them to smaller working-server copies, writes
Jellyfin poster/thumb images beside each transcoded output, and records per-dive
metadata into dive-line-data.csv.

Expected source structure:

    D:\\Video\\Dive13\\FWD\\20251016_144904 Fwd.mp4

Expected output structure:

    C:\\Users\\isaac\\Videos\\Transcoding\\CAMPA2025\\Dive13\\20251016_144904_Fwd.mp4
    C:\\Users\\isaac\\Videos\\Transcoding\\CAMPA2025\\Dive13\\20251016_144904_Fwd-poster.jpg
    C:\\Users\\isaac\\Videos\\Transcoding\\CAMPA2025\\Dive13\\20251016_144904_Fwd-thumb.jpg
    C:\\Users\\isaac\\Videos\\Transcoding\\CAMPA2025\\Dive13\\dive-line-data.csv
"""

from __future__ import annotations

import argparse                 # Builds the command-line interface and --help text.
import csv                      # Reads and writes the per-dive metadata CSV files.
import json                     # Parses ffprobe JSON output.
import re                       # Parses timestamps and sanitizes filenames.
import shutil                   # Checks whether ffmpeg and ffprobe are available.
import subprocess               # Runs ffmpeg and ffprobe as external commands.
import sys                      # Exits cleanly when safety checks fail.
import tempfile                  # Creates safe temporary OCR frame folders under the output root.
import time                     # Tracks wall-clock transcode speed for ETA estimates.

from dataclasses import dataclass       # Creates simple structured job/info containers.
from datetime import datetime           # Parses filename timestamps and writes processed_at values.
from pathlib import Path                # Handles Windows paths safely.
from typing import Dict                 # Type hint for dictionaries.
from typing import Iterable             # Type hint for row collections.
from typing import List                 # Type hint for lists.
from typing import Optional             # Type hint for optional values.
from typing import Tuple                # Type hint for multi-value returns.


# Video extensions we will reformat to mp4.
VIDEO_EXTENSIONS = {
    ".mp4",
    ".mkv",
    ".mov",
    ".avi",
    ".m4v",
}


# Name of the metadata CSV written inside each output DiveXX folder.
CSV_FILENAME = "dive-line-data.csv"


# Default poster width used when no output-root poster.png template exists.
DEFAULT_DIVE_POSTER_WIDTH = 1024


# Default poster height used when no output-root poster.png template exists.
DEFAULT_DIVE_POSTER_HEIGHT = 1536


# Default width ratio for the inserted dive-identifying poster image.
DEFAULT_DIVE_POSTER_IMAGE_WIDTH_RATIO = 1.30


# Default black border size around the inserted dive-identifying image.
DEFAULT_DIVE_POSTER_BORDER_PX = 4


# Used to store the dive/line cross-reference data for each output video.
# This CSV is intentionally not a transcode log.
CSV_COLUMNS = [
    "filename",
    "date_time_from_filename",
    "video_length",
    "ocr_dive",
    "ocr_date",
    "ocr_line",
    "notes",
]


# Used to explain to the user what each CSV column means.
# This row is written as the first data row for later reference.
CSV_COLUMN_DESCRIPTIONS = {
    "filename": "Output video filename.",
    "date_time_from_filename": "Recording start date and time parsed from the original filename.",
    "video_length": "Video duration reported by ffprobe.",
    "ocr_dive": "Dive value read from the video title card.",
    "ocr_date": "Date value read from the video title card.",
    "ocr_line": "Start Line or location value read from the video title card.",
    "notes": "Manual notes or corrections.",
}


# Stores all path and naming details needed to process one source video.
# The source path is never used as a write target.
# The output paths always point under the configured output root.
@dataclass
class VideoJob:
    source_path: Path
    output_path: Path
    output_dir: Path
    dive_folder: str
    camera: str
    source_filename: str
    output_filename: str
    poster_path: Path
    thumb_path: Path
    filename_timestamp_raw: str
    filename_date: str
    filename_time: str
    filename_datetime: str


# Stores source media values reported by ffprobe.
# Empty strings are used when a value is unavailable.
# CSV writing stays simple because values are already strings.
@dataclass
class SourceMediaInfo:
    duration_seconds: str = ""
    width: str = ""
    height: str = ""
    fps: str = ""
    video_bitrate_kbps: str = ""
    audio_bitrate_kbps: str = ""


# Stores title-card OCR values for one video.
# Empty strings are used when OCR does not find a value.
# error is recorded into the CSV error column when OCR fails.
@dataclass
class OcrResult:
    dive: str = ""
    date: str = ""
    start_line: str = ""
    location: str = ""
    raw_text: str = ""
    error: str = ""


# Parses command-line arguments and prints detailed --help text.
# Defaults are set for the CAMPA2025 FWD camera workflow.
# argparse provides the help option automatically with -h or --help.
# Returns the parsed argument namespace used by main().
def parse_arguments() -> argparse.Namespace:

    parser = argparse.ArgumentParser(
        prog="mare_jellyfin_prep.py",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        description=(
            "Transcode MARE ROV FWD camera videos into a Jellyfin working-server folder.\n"
            "The source drive is treated as read-only. All outputs, CSV files, and\n"
            "thumbnails are written under the output root."
        ),
        epilog=(
            "Examples:\n"
            "\n"
            "  Dry-run three files from Dive13:\n"
            "    python mare_jellyfin_prep.py --dry-run --only-dive Dive13 --limit 3\n"
            "\n"
            "  Process one Dive13 file for testing:\n"
            "    python mare_jellyfin_prep.py --only-dive Dive13 --limit 1\n"
            "\n"
            "  Resume a larger run and skip existing transcoded videos:\n"
            "    python mare_jellyfin_prep.py --skip-existing\n"
            "\n"
            "  Use a different video bitrate:\n"
            "    python mare_jellyfin_prep.py --video-bitrate 10M --only-dive Dive13 --limit 1\n"
        ),
    )

    # Allows the user to choose the read-only source video root.
    parser.add_argument(
        "--input-root",
        default=r"E:\Oceana 2016",
        help=r"Read-only source video root. Default: E:\Oceana 2016",
    )

    # Allows the user to choose where all derived files are written.
    parser.add_argument(
        "--output-root",
        default=r"C:\Users\isaac\Videos\Transcoding\Oceana 2016",
        help=r"Output root for transcoded videos, thumbnails, and CSV files.",
    )

    # Allows the user to set the project name written into metadata and CSV rows.
    parser.add_argument(
        "--project",
        default="Oceana 2016",
        help="Project name written into metadata and CSV rows. Default: Oceana 2016",
    )

    # Allows the user to process a specific camera folder inside each dive folder.
    parser.add_argument(
        "--camera",
        default=r"Video_With_Overlay",
        help=r"Camera folder to process inside each DiveXX folder. Default: Video_With_Overlay",
    )

    # Allows the user to limit processing to one dive folder.
    parser.add_argument(
        "--only-dive",
        default=None,
        help="Optional dive folder filter, for example Dive13. If omitted, all Dive* folders are scanned.",
    )

    # Allows the user to process only a small number of videos for testing.
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Optional maximum number of videos to process. Useful for testing.",
    )

    # Allows the user to preview the planned work without writing files.
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be processed without writing output files.",
    )

    # Allows the script to resume without re-transcoding existing output videos.
    parser.add_argument(
        "--skip-existing",
        action="store_true",
        help="Skip transcoding when the output video already exists.",
    )

    # Allows the user to intentionally rebuild existing outputs.
    parser.add_argument(
        "--overwrite",
        action="store_true",
        help="Overwrite existing output videos and thumbnails. Use carefully.",
    )

    # Allows the user to choose where Jellyfin poster/thumb frames are sampled.
    parser.add_argument(
        "--thumbnail-offset",
        type=float,
        default=2.0,
        help="Seconds from video start to extract Jellyfin poster/thumb frames. Default: 2.0",
    )


    # Allows the user to keep OCR crop images for debugging.
    parser.add_argument(
        "--keep-ocr-crops",
        action="store_true",
        help="Keep OCR crop images beside the output dive folder for debugging.",
    )

     # Allows the user to disable title-card OCR while keeping the video pipeline active.
    parser.add_argument(
        "--no-ocr",
        action="store_false",
        dest="enable_ocr",
        help="Disable title-card OCR extraction.",
    )

    # Allows the user to point at a specific Tesseract executable.
    parser.add_argument(
        "--tesseract",
        default="tesseract",
        help="Tesseract executable name or full path. Default: tesseract",
    )

    # Allows the user to choose which early video frames are OCR scanned.
    parser.add_argument(
        "--ocr-offsets",
        default="0.25,0.5,1,2",
        help="Comma-separated seconds used for OCR frame extraction. Default: 0.25,0.5,1,2",
    )

    # Allows the user to keep extracted OCR frames for debugging.
    parser.add_argument(
        "--keep-ocr-frames",
        action="store_true",
        help="Keep temporary OCR frame images beside the output dive folder for debugging.",
    )

    # Allows the user to label the transcode settings used for this run.
    parser.add_argument(
        "--profile",
        default="h264_nvenc_8m",
        help="Profile label written to the CSV. Default: h264_nvenc_8m",
    )

    # Allows the user to change the target video bitrate.
    parser.add_argument(
        "--video-bitrate",
        default="8M",
        help="Target video bitrate passed to ffmpeg. Default: 8M",
    )

    # Allows the user to change the low-priority audio bitrate.
    parser.add_argument(
        "--audio-bitrate",
        default="48k",
        help="Target audio bitrate passed to ffmpeg. Default: 48k",
    )

    # Allows the user to point at a specific ffmpeg executable.
    parser.add_argument(
        "--ffmpeg",
        default="ffmpeg",
        help="ffmpeg executable name or full path. Default: ffmpeg",
    )

    # Allows the user to point at a specific ffprobe executable.
    parser.add_argument(
        "--ffprobe",
        default="ffprobe",
        help="ffprobe executable name or full path. Default: ffprobe",
    )

    # Allows the user to choose the NVENC speed/quality preset.
    parser.add_argument(
        "--nvenc-preset",
        default="medium",
        help="NVENC preset passed to ffmpeg. Default: medium",
    )

      # Allows the user to run image generation from existing transcoded videos.
    parser.add_argument(
        "--images-only",
        action="store_true",
        help="Skip video encoding and only create poster/thumb images and dive poster images.",
    )

    # Allows the user to skip creating per-dive poster.png images.
    parser.add_argument(
        "--skip-dive-posters",
        action="store_true",
        help="Do not create poster.png files inside each dive folder.",
    )

    # Allows the user to choose the root poster template filename.
    parser.add_argument(
        "--dive-poster-template",
        default="poster.png",
        help="Poster template filename inside the output root. Default: poster.png",
    )

    # Allows the user to choose the fallback poster width when no template exists.
    parser.add_argument(
        "--dive-poster-width",
        type=int,
        default=DEFAULT_DIVE_POSTER_WIDTH,
        help="Fallback poster width used when no template exists. Default: 1024",
    )

    # Allows the user to choose the fallback poster height when no template exists.
    parser.add_argument(
        "--dive-poster-height",
        type=int,
        default=DEFAULT_DIVE_POSTER_HEIGHT,
        help="Fallback poster height used when no template exists. Default: 1536",
    )

    # Allows the user to choose how wide the inserted image should be.
    parser.add_argument(
        "--dive-poster-image-width-ratio",
        type=float,
        default=DEFAULT_DIVE_POSTER_IMAGE_WIDTH_RATIO,
        help="Inserted image width as a fraction of poster width. Default: 0.90",
    )

  

    parser.set_defaults(enable_ocr=True)

    return parser.parse_args()


# Finds the first generated -poster.jpg in a dive folder.
# The earliest file is chosen using normal filename sort order.
# Returns the Path when found, otherwise returns None.
def find_first_dive_poster_image(dive_output_dir: Path) -> Optional[Path]:

    poster_paths = sorted(dive_output_dir.glob("*-poster.jpg"))

    if not poster_paths:
        return None

    return poster_paths[0]


# Creates one poster.png for a dive folder.
# The first -poster.jpg in the dive folder is pasted onto the poster template.
# If the root poster.png template does not exist, a black background is used.
# The output file is written as poster.png inside the dive folder.
def create_dive_folder_poster(
    args: argparse.Namespace,
    output_root: Path,
    dive_output_dir: Path,
) -> Tuple[bool, str]:

    first_poster_path = find_first_dive_poster_image(dive_output_dir)

    if first_poster_path is None:
        return False, "No -poster.jpg files were found in the dive folder."

    template_path = output_root / args.dive_poster_template
    output_path = dive_output_dir / "poster.png"

    if template_path.exists():
        template_width, template_height = get_image_dimensions(args.ffprobe, template_path)

        if template_width <= 0 or template_height <= 0:
            return False, f"Could not read poster template dimensions: {template_path}"

        background_input = [
            "-i",
            str(template_path),
        ]
    else:
        template_width = args.dive_poster_width
        template_height = args.dive_poster_height

        # Create a black poster canvas when no poster template exists.
        background_input = [
            "-f",
            "lavfi",
            "-i",
            f"color=c=black:s={template_width}x{template_height}",
        ]

    image_width_ratio = args.dive_poster_image_width_ratio

    if image_width_ratio <= 0:
        return False, "--dive-poster-image-width-ratio must be greater than 0."

    
    target_image_width = int(template_width * image_width_ratio)

    # Center horizontally and vertically within the full poster.
    overlay_x_expr = "(W-w)/2"
    overlay_y_expr = "(H*0.38)-(h/2)"

    filter_complex = (
        f"[1:v]scale={target_image_width}:-1"
        f"[framed];"
        f"[0:v][framed]overlay={overlay_x_expr}:{overlay_y_expr}"
    )

    overwrite_flag = "-y" if args.overwrite else "-n"

    command = [
        args.ffmpeg,
        "-hide_banner",
        "-loglevel",
        "error",
        overwrite_flag,
        *background_input,
        "-i",
        str(first_poster_path),
        "-filter_complex",
        filter_complex,
        "-frames:v",
        "1",
        str(output_path),
    ]

    result = run_command(command)

    if result.returncode != 0:
        stdout_text = result.stdout or ""
        stderr_text = result.stderr or ""

        error_text = stderr_text.strip() or stdout_text.strip() or "Dive poster creation failed"
        return False, error_text[-4000:]

    return True, ""


# Creates poster.png in each processed dive folder.
# One poster is generated per dive using the first -poster.jpg in that folder.
# output_root may contain a poster.png template used as the background.
# Errors are printed but do not stop the script.
def create_all_dive_folder_posters(
    args: argparse.Namespace,
    output_root: Path,
    jobs: List[VideoJob],
) -> None:

    if args.skip_dive_posters:
        print()
        print("Skipping dive poster.png generation.")
        return

    dive_dirs: List[Path] = []
    seen_dirs = set()

    for job in jobs:
        if job.output_dir not in seen_dirs:
            seen_dirs.add(job.output_dir)
            dive_dirs.append(job.output_dir)

    for dive_output_dir in sorted(dive_dirs):
        print()
        print(f"Creating dive poster: {dive_output_dir / 'poster.png'}")

        ok, error = create_dive_folder_poster(
            args=args,
            output_root=output_root,
            dive_output_dir=dive_output_dir,
        )

        if ok:
            print("Dive poster created.")
        else:
            print(f"Dive poster skipped: {error}")


# Prints an error message and exits the script.
# message is shown on stderr so normal output remains clean.
# Used for safety checks and invalid argument combinations.
def fail(message: str) -> None:

    print(f"ERROR: {message}", file=sys.stderr)
    sys.exit(1)


# Checks whether an external command is available without exiting.
# tool_name may be a command name like tesseract or a full path.
# Returns True when the tool can be found.
def external_tool_available(tool_name: str) -> bool:

    tool_on_path = shutil.which(tool_name)
    explicit_path_exists = Path(tool_name).exists()

    return tool_on_path is not None or explicit_path_exists


# Checks whether an external command is available.
# tool_name may be a command name like ffmpeg or a full path.
# The script fails early if the required tool cannot be found.
def check_external_tool(tool_name: str) -> None:

    # shutil.which handles command names available on PATH.
    tool_on_path = shutil.which(tool_name)

    # Path.exists handles explicit executable paths.
    explicit_path_exists = Path(tool_name).exists()

    if tool_on_path is None and not explicit_path_exists:
        fail(f"Could not find required tool: {tool_name}")


# Converts user-provided path text into an absolute Path.
# path_text may include user-relative or normal Windows paths.
# The resolved path is used by safety checks and file operations.
def resolved_path(path_text: str) -> Path:

    return Path(path_text).expanduser().resolve()


# Verifies the input and output paths are safe for this workflow.
# input_root must exist and must be absolute.
# output_root must be absolute and must not be on the source drive.
# This prevents accidental writes to the archived source media.
def assert_safe_paths(input_root: Path, output_root: Path) -> None:

    input_drive = input_root.drive.upper()
    output_drive = output_root.drive.upper()

    if not input_root.exists():
        fail(f"Input root does not exist: {input_root}")

    if input_drive == "":
        fail(f"Input root must be an absolute Windows path: {input_root}")

    if output_drive == "":
        fail(f"Output root must be an absolute Windows path: {output_root}")

    # D: is the source drive for this workflow, so outputs are rejected there.
    if output_drive == "D:":
        fail(f"Output root is on D:. Refusing to write derived files there: {output_root}")

    try:
        output_root.relative_to(input_root)
        fail(f"Output root is inside input root. Refusing unsafe layout: {output_root}")
    except ValueError:
        pass

    try:
        input_root.relative_to(output_root)
        fail(f"Input root is inside output root. Refusing unsafe layout: {input_root}")
    except ValueError:
        pass


# Creates a safe output filename from a source filename.
# Spaces are replaced with underscores.
# Unsafe Windows filename characters are replaced.
# Output videos are always written as mp4.
def sanitize_filename_for_output(source_name: str) -> str:

    stem = Path(source_name).stem
    extension = ".mp4"

    # Replace source filename spaces so later scripts are easier to write.
    cleaned = stem.replace(" ", "_")

    # Replace characters that are invalid or troublesome in Windows filenames.
    cleaned = re.sub(r'[<>:"/\\|?*]+', "_", cleaned)

    # Collapse repeated underscores so names stay stable and readable.
    cleaned = re.sub(r"_+", "_", cleaned).strip("_")

    if not cleaned:
        cleaned = "unnamed_video"

    return f"{cleaned}{extension}"


# Parses the recording timestamp from a source filename.
# source_name should contain a value like 20251016_144904.
# Returns raw timestamp, date, time, and combined datetime strings.
# Empty strings are returned when no valid timestamp is found.
def parse_filename_timestamp(source_name: str) -> Tuple[str, str, str, str]:

    match = re.search(r"(?P<date>\d{8})[_-](?P<time>\d{6})", source_name)

    if not match:
        return "", "", "", ""

    raw_timestamp = f"{match.group('date')}_{match.group('time')}"

    try:
        parsed_timestamp = datetime.strptime(raw_timestamp, "%Y%m%d_%H%M%S")
    except ValueError:
        return raw_timestamp, "", "", ""

    date_text = parsed_timestamp.strftime("%Y-%m-%d")
    time_text = parsed_timestamp.strftime("%H:%M:%S")
    datetime_text = parsed_timestamp.strftime("%Y-%m-%d %H:%M:%S")

    return raw_timestamp, date_text, time_text, datetime_text


# Finds video files that match supported project folder layouts.
# Supports DiveXX/camera, camera/DiveXX, and direct DiveXX folders.
# camera chooses the folder name to process, normally FWD or Forward.
# Returns VideoJob objects with source and output paths.
def discover_video_jobs(
    input_root: Path,
    output_root: Path,
    camera: str,
    only_dive: Optional[str],
    limit: Optional[int],
) -> List[VideoJob]:

    jobs: List[VideoJob] = []
    search_dirs: List[Tuple[Path, str]] = []

    # Old layout:
    # F:\Video\Dive 3\FWD\*.mp4
    for dive_dir in sorted([path for path in input_root.glob("Dive*") if path.is_dir()]):
        dive_folder = dive_dir.name

        if only_dive and dive_folder.lower() != only_dive.lower():
            continue

        camera_dir = dive_dir / camera

        if camera_dir.exists() and camera_dir.is_dir():
            search_dirs.append((camera_dir, dive_folder))

    # New layout:
    # F:\Video\FWD\Dive 3\*.mp4
    camera_root = input_root / camera

    if camera_root.exists() and camera_root.is_dir():
        for dive_dir in sorted([path for path in camera_root.glob("Dive*") if path.is_dir()]):
            dive_folder = dive_dir.name

            if only_dive and dive_folder.lower() != only_dive.lower():
                continue

            search_dirs.append((dive_dir, dive_folder))

    # Direct camera-root layout:
    # input_root is already F:\Video\FWD, with Dive folders inside it.
    for dive_dir in sorted([path for path in input_root.glob("Dive*") if path.is_dir()]):
        dive_folder = dive_dir.name

        if only_dive and dive_folder.lower() != only_dive.lower():
            continue

        # Only add this direct Dive folder if it actually contains videos.
        has_video_files = False

        for source_path in dive_dir.iterdir():
            if source_path.is_file() and source_path.suffix.lower() in VIDEO_EXTENSIONS:
                has_video_files = True
                break

        if has_video_files:
            search_dirs.append((dive_dir, dive_folder))

    # Remove duplicate search folders while preserving order.
    unique_search_dirs: List[Tuple[Path, str]] = []
    seen_dirs = set()

    for search_dir, dive_folder in search_dirs:
        resolved_search_dir = search_dir.resolve()

        if resolved_search_dir in seen_dirs:
            continue

        seen_dirs.add(resolved_search_dir)
        unique_search_dirs.append((search_dir, dive_folder))

    for video_dir, dive_folder in unique_search_dirs:
        for source_path in sorted(video_dir.iterdir()):
            if not source_path.is_file():
                continue

            if source_path.suffix.lower() not in VIDEO_EXTENSIONS:
                continue

            output_dir = output_root / dive_folder
            output_filename = sanitize_filename_for_output(source_path.name)
            output_path = output_dir / output_filename

            output_stem = output_path.stem
            poster_path = output_dir / f"{output_stem}-poster.jpg"
            thumb_path = output_dir / f"{output_stem}-thumb.jpg"

            raw_ts, date_text, time_text, datetime_text = parse_filename_timestamp(source_path.name)

            jobs.append(
                VideoJob(
                    source_path=source_path,
                    output_path=output_path,
                    output_dir=output_dir,
                    dive_folder=dive_folder,
                    camera=camera,
                    source_filename=source_path.name,
                    output_filename=output_filename,
                    poster_path=poster_path,
                    thumb_path=thumb_path,
                    filename_timestamp_raw=raw_ts,
                    filename_date=date_text,
                    filename_time=time_text,
                    filename_datetime=datetime_text,
                )
            )

            if limit is not None and len(jobs) >= limit:
                return jobs

    return jobs


# Runs one external command and returns the completed process.
# command is the full argv list, not a shell string.
# stdout and stderr are captured so errors can be recorded in the CSV.
# Invalid text bytes are replaced instead of crashing on Windows.
def run_command(command: List[str]) -> subprocess.CompletedProcess:

    # shell=False is used by passing a list. This is safer for paths with spaces.
    return subprocess.run(
        command,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )


# Runs ffprobe and returns parsed JSON.
# ffprobe is the executable name or full path.
# source_path is read only.
# None is returned if ffprobe fails or returns invalid JSON.
def ffprobe_json(ffprobe: str, source_path: Path) -> Optional[dict]:

    command = [
        ffprobe,
        "-v",
        "error",
        "-print_format",
        "json",
        "-show_format",
        "-show_streams",
        str(source_path),
    ]

    result = run_command(command)

    if result.returncode != 0:
        return None

    try:
        return json.loads(result.stdout)
    except json.JSONDecodeError:
        return None


# Converts ffprobe rational frame rates into decimal text.
# value may look like 25/1 or 30000/1001.
# Returns the original value if it is not a rational number.
# Returns an empty string if the denominator is zero.
def rational_to_decimal(value: str) -> str:

    if not value:
        return ""

    if "/" not in value:
        return value

    numerator_text, denominator_text = value.split("/", 1)

    try:
        numerator = float(numerator_text)
        denominator = float(denominator_text)
    except ValueError:
        return value

    if denominator == 0:
        return ""

    decimal_value = numerator / denominator

    return f"{decimal_value:.3f}".rstrip("0").rstrip(".")


# Converts a bitrate string from bits/sec to kbps text.
# bit_rate_text usually comes from ffprobe.
# Returns an empty string if the value is unavailable.
def bitrate_to_kbps(bit_rate_text: str) -> str:

    if not bit_rate_text:
        return ""

    try:
        return str(round(int(bit_rate_text) / 1000))
    except ValueError:
        return ""


# Reads source media information with ffprobe.
# ffprobe is the executable name or full path.
# source_path is read only.
# Missing values are returned as empty strings.
def read_source_media_info(ffprobe: str, source_path: Path) -> SourceMediaInfo:

    data = ffprobe_json(ffprobe, source_path)

    if not data:
        return SourceMediaInfo()

    info = SourceMediaInfo()

    format_data = data.get("format", {})
    duration_text = format_data.get("duration", "")

    if duration_text:
        try:
            info.duration_seconds = f"{float(duration_text):.3f}"
        except ValueError:
            info.duration_seconds = duration_text

    streams = data.get("streams", [])

    video_stream = None
    audio_stream = None

    # Pick the first video stream and first audio stream reported by ffprobe.
    for stream in streams:
        if stream.get("codec_type") == "video" and video_stream is None:
            video_stream = stream

        if stream.get("codec_type") == "audio" and audio_stream is None:
            audio_stream = stream

    if video_stream:
        info.width = str(video_stream.get("width", "") or "")
        info.height = str(video_stream.get("height", "") or "")
        info.fps = rational_to_decimal(video_stream.get("avg_frame_rate", "") or "")
        info.video_bitrate_kbps = bitrate_to_kbps(video_stream.get("bit_rate", "") or "")

    if audio_stream:
        info.audio_bitrate_kbps = bitrate_to_kbps(audio_stream.get("bit_rate", "") or "")

    return info


# Builds a readable video title for MP4 metadata.
# project is the survey/project name.
# job provides dive, camera, and filename timestamp values.
# The title is written into the transcoded output file.
def build_video_title(project: str, job: VideoJob) -> str:

    parts = [
        project,
        job.dive_folder,
        job.camera,
    ]

    if job.filename_datetime:
        parts.append(job.filename_datetime)

    return " ".join(parts)


# Parses a positive seconds value from text.
# Returns None when the value is missing, invalid, or non-positive.
def parse_positive_seconds(seconds_text: str) -> Optional[float]:

    if not seconds_text:
        return None

    try:
        seconds_value = float(seconds_text)
    except ValueError:
        return None

    if seconds_value <= 0:
        return None

    return seconds_value


# Formats an ETA duration in HH:MM:SS.
def format_eta_hh_mm_ss(total_seconds: int) -> str:

    safe_seconds = max(0, total_seconds)
    hours = safe_seconds // 3600
    minutes = (safe_seconds % 3600) // 60
    seconds = safe_seconds % 60

    return f"{hours:02d}:{minutes:02d}:{seconds:02d}"


# Transcodes one source video into the working-server output folder.
# ffmpeg is the executable name or full path.
# job contains the read-only source path and output path.
# Returns success flag and error text.
def transcode_video(
    ffmpeg: str,
    project: str,
    job: VideoJob,
    job_index: int,
    total_jobs: int,
    video_bitrate: str,
    audio_bitrate: str,
    nvenc_preset: str,
    overwrite: bool,
    source_duration_seconds: str,
    total_source_seconds_all_jobs: float,
    completed_source_seconds_before_job: float,
) -> Tuple[bool, str]:

    overwrite_flag = "-y" if overwrite else "-n"
    title = build_video_title(project, job)

    expected_duration_seconds = parse_positive_seconds(source_duration_seconds)

    command = [
        ffmpeg,
        "-hide_banner",
        overwrite_flag,
        "-progress",
        "pipe:1",
        "-nostats",

        # Source media is only used as input.
        "-i",
        str(job.source_path),

        # Keep first video stream and first audio stream if audio exists.
        "-map",
        "0:v:0",
        "-map",
        "0:a:0?",

        # Drop subtitle and data streams to keep output simple for Jellyfin.
        "-sn",
        "-dn",

        # Use GPU H.264 encoding for broad Jellyfin/client compatibility.
        "-c:v",
        "h264_nvenc",
        "-preset",
        nvenc_preset,
        "-b:v",
        video_bitrate,
        "-maxrate",
        video_bitrate,
        "-bufsize",
        "16M",
        "-pix_fmt",
        "yuv420p",

        # Keep audio, but compress it because audio is low priority here.
        "-c:a",
        "aac",
        "-b:a",
        audio_bitrate,
        "-ac",
        "2",
        "-ar",
        "48000",

        # Move MP4 metadata to the front for better streaming behavior.
        "-movflags",
        "+faststart",

        # Write common metadata fields that tools tend to recognize.
        "-metadata",
        f"title={title}",
        "-metadata",
        "artist=Marine Applied Research and Exploration",
        "-metadata",
        "album_artist=Marine Applied Research and Exploration",
        "-metadata",
        "author=Marine Applied Research and Exploration",
        "-metadata",
        "publisher=Marine Applied Research and Exploration",
        "-metadata",
        "copyright=Marine Applied Research and Exploration",
        "-metadata",
        "encoded_by=Isaac Assegai Travers",
        "-metadata",
        f"keywords=ROV-VIDEO; {project}; {job.camera}; {job.dive_folder}",
        "-metadata",
        "comment=ROV-VIDEO; https://mareresearch.org",
        "-metadata",
        f"description={project} ROV {job.camera} camera video. Source recording timestamp derived from filename.",

        str(job.output_path),
    ]

    progress_prefix = f"Transcoding Video[{job_index} of {total_jobs}]..."

    process = subprocess.Popen(
        command,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
        errors="replace",
    )

    last_progress_value = -1
    latest_speed_multiplier: Optional[float] = None
    transcode_start_time = time.monotonic()

    if process.stdout is not None:
        for raw_line in process.stdout:
            line = raw_line.strip()

            if not line or "=" not in line:
                continue

            key, value = line.split("=", 1)

            if key == "speed":
                clean_speed_value = value.strip().lower().rstrip("x")

                try:
                    parsed_speed = float(clean_speed_value)

                    if parsed_speed > 0:
                        latest_speed_multiplier = parsed_speed
                except ValueError:
                    pass

                continue

            if key != "out_time_ms":
                continue

            try:
                output_seconds = int(value) / 1_000_000
            except ValueError:
                continue

            if expected_duration_seconds is not None:
                percent_done = int(min(100, (output_seconds / expected_duration_seconds) * 100))

                if percent_done == last_progress_value:
                    continue

                bar_width = 30
                filled_width = int((percent_done / 100) * bar_width)
                empty_width = bar_width - filled_width
                bar_text = ("#" * filled_width) + ("-" * empty_width)

                remaining_source_seconds = max(0.0, expected_duration_seconds - output_seconds)

                effective_speed = latest_speed_multiplier

                if effective_speed is None or effective_speed <= 0:
                    elapsed_wall_seconds = max(time.monotonic() - transcode_start_time, 0.001)
                    derived_speed = output_seconds / elapsed_wall_seconds

                    if derived_speed > 0:
                        effective_speed = derived_speed

                eta_text = "ETA --:--:--"
                job_eta_text = " - JOB ETA --:--:--"
                speed_text = "speed --"

                if effective_speed is not None and effective_speed > 0:
                    eta_seconds = int(remaining_source_seconds / effective_speed)
                    eta_text = f"ETA {format_eta_hh_mm_ss(eta_seconds)}"
                    speed_text = f"speed {effective_speed:.2f}x"

                    if total_source_seconds_all_jobs > 0:
                        processed_source_seconds = completed_source_seconds_before_job + output_seconds
                        remaining_job_source_seconds = max(
                            0.0,
                            total_source_seconds_all_jobs - processed_source_seconds,
                        )
                        job_eta_seconds = int(remaining_job_source_seconds / effective_speed)
                        job_eta_text = f"JOB ETA {format_eta_hh_mm_ss(job_eta_seconds)}"

                print(
                    f"\r{progress_prefix} [{bar_text}] {percent_done:3d}% "
                    f"({int(output_seconds)}s/{int(expected_duration_seconds)}s) "
                    f"{speed_text} {eta_text} {job_eta_text}",
                    end="",
                    flush=True,
                )

                last_progress_value = percent_done
            else:
                elapsed_seconds = int(output_seconds)

                if elapsed_seconds == last_progress_value:
                    continue

                print(
                    f"\r{progress_prefix} {elapsed_seconds}s processed",
                    end="",
                    flush=True,
                )

                last_progress_value = elapsed_seconds

    return_code = process.wait()

    stderr_text = ""

    if process.stderr is not None:
        stderr_text = process.stderr.read() or ""

    if last_progress_value >= 0:
        if expected_duration_seconds is not None and return_code == 0 and last_progress_value < 100:
            bar_width = 30
            bar_text = ("#" * bar_width)

            print(
                f"\r{progress_prefix} [{bar_text}] 100% "
                f"({int(expected_duration_seconds)}s/{int(expected_duration_seconds)}s) "
                "speed done ETA 00:00:00 JOB ETA 00:00:00",
                end="",
                flush=True,
            )

        print()

    if return_code != 0:
        error_text = stderr_text.strip() or "ffmpeg transcode failed"
        return False, error_text[-4000:]

    return True, ""


# Creates one still image from a video file.
# video_path should be the transcoded output video.
# image_path is the poster or thumb output path.
# Returns success flag and error text.
def create_thumbnail(
    ffmpeg: str,
    video_path: Path,
    image_path: Path,
    offset_seconds: float,
    overwrite: bool,
) -> Tuple[bool, str]:

    overwrite_flag = "-y" if overwrite else "-n"

    command = [
        ffmpeg,
        "-hide_banner",
        "-loglevel",
        "error",
        overwrite_flag,
        "-ss",
        str(offset_seconds),
        "-i",
        str(video_path),
        "-frames:v",
        "1",
        "-q:v",
        "2",
        str(image_path),
    ]

    result = run_command(command)

    if result.returncode != 0:
        stdout_text = result.stdout or ""
        stderr_text = result.stderr or ""

        error_text = stderr_text.strip() or stdout_text.strip() or "ffmpeg thumbnail extraction failed"
        return False, error_text[-4000:]

    return True, ""


# Parses the comma-separated OCR offset argument.
# offsets_text should look like 1,2,3,5.
# Invalid or negative values are ignored.
# Returns a default list if no valid values are found.
def parse_ocr_offsets(offsets_text: str) -> List[float]:

    offsets: List[float] = []

    for offset_part in offsets_text.split(","):
        clean_part = offset_part.strip()

        if not clean_part:
            continue

        try:
            offset_value = float(clean_part)
        except ValueError:
            continue

        if offset_value < 0:
            continue

        offsets.append(offset_value)

    if not offsets:
        return [0.25, 0.5, 1.0, 2.0]

    return offsets


# Extracts one frame from the transcoded video for OCR.
# video_path is the output video, not the source video.
# image_path is written under the output folder only.
# Returns success flag and error text.
def extract_ocr_frame(
    ffmpeg: str,
    video_path: Path,
    image_path: Path,
    offset_seconds: float,
) -> Tuple[bool, str]:

    image_path.parent.mkdir(parents=True, exist_ok=True)

    command = [
        ffmpeg,
        "-hide_banner",
        "-loglevel",
        "error",
        "-y",
        "-ss",
        str(offset_seconds),
        "-i",
        str(video_path),
        "-frames:v",
        "1",

        # PNG avoids JPEG artifacts before OCR.
        str(image_path),
    ]

    result = run_command(command)

    if result.returncode != 0:
        stdout_text = result.stdout or ""
        stderr_text = result.stderr or ""

        error_text = stderr_text.strip() or stdout_text.strip() or "OCR Frame extraction error"
        return False, error_text[-4000:]

    return True, ""


# Runs Tesseract OCR against one extracted frame.
# tesseract is the executable name or full path.
# image_path is the frame image to scan.
# Returns OCR text and error text.
def run_tesseract_ocr(tesseract: str, image_path: Path) -> Tuple[str, str]:

    command = [
        tesseract,
        str(image_path),
        "stdout",
        "--psm",
        "6",
    ]

    result = run_command(command)

    stdout_text = result.stdout or ""
    stderr_text = result.stderr or ""

    if result.returncode != 0:
        error_text = stderr_text.strip() or stdout_text.strip() or "Tesseract OCR failed"
        return "", error_text[-4000:]

    return stdout_text.strip(), ""


# Normalizes OCR text for easier parsing.
# Raw text is preserved separately in the CSV.
# This function only cleans spacing and obvious separator issues.
def normalize_ocr_text(raw_text: str) -> str:

    text = raw_text.replace("\r\n", "\n").replace("\r", "\n")

    # Collapse repeated spaces inside each OCR line.
    clean_lines: List[str] = []

    for line in text.split("\n"):
        clean_line = re.sub(r"\s+", " ", line).strip()

        if clean_line:
            clean_lines.append(clean_line)

    return "\n".join(clean_lines)


# Extracts a dive value from normalized OCR text.
# Looks for values like Dive13, Dive 13, or DIVE: 13.
# Returns an empty string when no dive value is found.
def parse_ocr_dive(normalized_text: str) -> str:

    match = re.search(r"\bDIVE\s*[:#-]?\s*0*(\d{1,3})\b", normalized_text, re.IGNORECASE)

    if not match:
        return ""

    return f"Dive{int(match.group(1)):02d}"


# Extracts a date value from normalized OCR text.
# Supports YYYY-MM-DD, YYYY/MM/DD, MM/DD/YYYY, and YYYYMMDD.
# Returns a normalized YYYY-MM-DD string when possible.
def parse_ocr_date(normalized_text: str) -> str:

    yyyy_mm_dd = re.search(
        r"\b(?P<year>20\d{2})[-/](?P<month>\d{1,2})[-/](?P<day>\d{1,2})\b",
        normalized_text,
    )

    if yyyy_mm_dd:
        year = int(yyyy_mm_dd.group("year"))
        month = int(yyyy_mm_dd.group("month"))
        day = int(yyyy_mm_dd.group("day"))

        try:
            parsed_date = datetime(year, month, day)
            return parsed_date.strftime("%Y-%m-%d")
        except ValueError:
            return ""

    mm_dd_yyyy = re.search(
        r"\b(?P<month>\d{1,2})[-/](?P<day>\d{1,2})[-/](?P<year>20\d{2})\b",
        normalized_text,
    )

    if mm_dd_yyyy:
        year = int(mm_dd_yyyy.group("year"))
        month = int(mm_dd_yyyy.group("month"))
        day = int(mm_dd_yyyy.group("day"))

        try:
            parsed_date = datetime(year, month, day)
            return parsed_date.strftime("%Y-%m-%d")
        except ValueError:
            return ""

    compact_date = re.search(r"\b(?P<date>20\d{6})\b", normalized_text)

    if compact_date:
        try:
            parsed_date = datetime.strptime(compact_date.group("date"), "%Y%m%d")
            return parsed_date.strftime("%Y-%m-%d")
        except ValueError:
            return ""

    return ""


# Extracts a Start Line value from normalized OCR text.
# Looks for values like Start Line 42 or START LINE: 042.
# Returns the original line identifier with common cleanup applied.
def parse_ocr_start_line(normalized_text: str) -> str:

    match = re.search(
        r"\bSTART\s+LINE\s*[:#-]?\s*(?P<line>[A-Za-z0-9_.-]+)\b",
        normalized_text,
        re.IGNORECASE,
    )

    if not match:
        return ""

    line_value = match.group("line").strip(" .,:;")

    if not line_value:
        return ""

    return f"Start Line {line_value}"


# Chooses a likely location line when no Start Line is present.
# Known metadata-looking lines are ignored.
# The longest remaining useful line is returned.
def parse_ocr_location(normalized_text: str) -> str:

    candidate_lines: List[str] = []

    for line in normalized_text.split("\n"):
        clean_line = line.strip()

        if len(clean_line) < 4:
            continue

        if re.search(r"\bDIVE\b", clean_line, re.IGNORECASE):
            continue

        if re.search(r"\bSTART\s+LINE\b", clean_line, re.IGNORECASE):
            continue

        if re.search(r"\b20\d{2}[-/]?\d{0,2}[-/]?\d{0,2}\b", clean_line):
            continue

        if re.search(r"\b\d{1,2}[-/]\d{1,2}[-/]20\d{2}\b", clean_line):
            continue

        candidate_lines.append(clean_line)

    if not candidate_lines:
        return ""

    best_line = ""

    for candidate_line in candidate_lines:
        if len(candidate_line) > len(best_line):
            best_line = candidate_line

    return best_line


# Scores OCR text so the best early frame can be selected.
# Higher scores mean the text contains more useful title-card fields.
# The score is only used to choose among extracted frames.
def score_ocr_text(normalized_text: str) -> int:

    score = 0

    if parse_ocr_dive(normalized_text):
        score += 10

    if parse_ocr_date(normalized_text):
        score += 10

    if parse_ocr_start_line(normalized_text):
        score += 15

    if parse_ocr_location(normalized_text):
        score += 5

    # A small length score helps choose fuller OCR reads.
    score += min(len(normalized_text), 200) // 20

    return score


# Parses OCR text into CSV-ready fields.
# raw_text is preserved in the OCR result.
# Location is only used when Start Line is not found.
def parse_ocr_result(raw_text: str) -> OcrResult:

    normalized_text = normalize_ocr_text(raw_text)

    result = OcrResult()
    result.raw_text = normalized_text
    result.dive = parse_ocr_dive(normalized_text)
    result.date = parse_ocr_date(normalized_text)
    result.start_line = parse_ocr_start_line(normalized_text)

    if not result.start_line:
        result.location = parse_ocr_location(normalized_text)

    return result


# Removes a temporary OCR frame folder when debugging is disabled.
# work_dir must be under the output folder.
# Errors are ignored because OCR cleanup should not fail the video job.
def cleanup_ocr_work_dir(work_dir: Path) -> None:

    if not work_dir.exists():
        return

    for child_path in work_dir.iterdir():
        try:
            if child_path.is_file():
                child_path.unlink()
        except OSError:
            pass

    try:
        work_dir.rmdir()
    except OSError:
        pass



# Gets image dimensions using ffprobe.
# image_path is a generated OCR frame or crop.
# Returns width and height as integers.
# Returns zeroes when dimensions cannot be read.
def get_image_dimensions(ffprobe: str, image_path: Path) -> Tuple[int, int]:

    command = [
        ffprobe,
        "-v",
        "error",
        "-select_streams",
        "v:0",
        "-show_entries",
        "stream=width,height",
        "-of",
        "json",
        str(image_path),
    ]

    result = run_command(command)

    if result.returncode != 0:
        return 0, 0

    try:
        data = json.loads(result.stdout or "")
    except json.JSONDecodeError:
        return 0, 0

    streams = data.get("streams", [])

    if not streams:
        return 0, 0

    width = int(streams[0].get("width", 0) or 0)
    height = int(streams[0].get("height", 0) or 0)

    return width, height


# Converts proportional crop values into an ffmpeg crop filter.
# crop_box values are left, top, right, bottom percentages from 0.0 to 1.0.
# width and height are the input image dimensions.
# Returns an ffmpeg crop filter string.
def build_crop_filter(
    width: int,
    height: int,
    crop_box: Tuple[float, float, float, float],
) -> str:

    left_pct, top_pct, right_pct, bottom_pct = crop_box

    crop_x = int(width * left_pct)
    crop_y = int(height * top_pct)
    crop_w = int(width * (right_pct - left_pct))
    crop_h = int(height * (bottom_pct - top_pct))

    return f"crop={crop_w}:{crop_h}:{crop_x}:{crop_y}"


# Extracts a cropped OCR region from a full OCR frame.
# frame_path is the full video frame extracted from the output video.
# crop_path is written under the output folder only.
# crop_box uses proportional coordinates.
def extract_ocr_crop(
    ffmpeg: str,
    ffprobe: str,
    frame_path: Path,
    crop_path: Path,
    crop_box: Tuple[float, float, float, float],
) -> Tuple[bool, str]:

    width, height = get_image_dimensions(ffprobe, frame_path)

    if width <= 0 or height <= 0:
        return False, "Could not read OCR frame dimensions."

    crop_filter = build_crop_filter(width, height, crop_box)

    crop_path.parent.mkdir(parents=True, exist_ok=True)

    command = [
        ffmpeg,
        "-hide_banner",
        "-loglevel",
        "error",
        "-y",
        "-i",
        str(frame_path),

        # Crop to the title text, enlarge it, remove color noise, and sharpen edges.
        "-vf",
        f"{crop_filter},scale=iw*3:ih*3,format=gray,eq=contrast=2.2:brightness=0.05,unsharp=5:5:1.2",

        str(crop_path),
    ]

    result = run_command(command)

    if result.returncode != 0:
        stdout_text = result.stdout or ""
        stderr_text = result.stderr or ""
        error_text = stderr_text.strip() or stdout_text.strip() or "OCR crop extraction failed"
        return False, error_text[-4000:]

    return True, ""


# Runs Tesseract against one crop using single-line title text settings.
# psm 7 tells Tesseract each crop should be treated as one text line.
# whitelist limits OCR to characters expected in title cards.
# Returns OCR text and error text.
def run_tesseract_crop_ocr(
    tesseract: str,
    image_path: Path,
) -> Tuple[str, str]:

    command = [
        tesseract,
        str(image_path),
        "stdout",
        "--psm",
        "7",
        "-c",
        "tessedit_char_whitelist=ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789 /:-",
    ]

    result = run_command(command)

    stdout_text = result.stdout or ""
    stderr_text = result.stderr or ""

    if result.returncode != 0:
        error_text = stderr_text.strip() or stdout_text.strip() or "Tesseract OCR failed"
        return "", error_text[-4000:]

    return stdout_text.strip(), ""


# Cleans a single OCR field into one line.
# OCR often includes line breaks or repeated spaces.
# The cleaned value is easier to parse and store in the CSV.
def clean_ocr_field(raw_text: str) -> str:

    text = raw_text.replace("\r\n", "\n").replace("\r", "\n")
    text = text.replace("|", "I")

    clean_parts: List[str] = []

    for line in text.split("\n"):
        clean_line = re.sub(r"\s+", " ", line).strip()

        if clean_line:
            clean_parts.append(clean_line)

    return " ".join(clean_parts).strip()


# Parses the cropped dive OCR text.
# Expected text looks like Dive 13.
# Returns DiveXX when a dive number is found.
def parse_dive_crop_text(text: str) -> str:

    match = re.search(r"\bDIVE\s*[:#-]?\s*0*(\d{1,3})\b", text, re.IGNORECASE)

    if not match:
        return ""

    return f"Dive{int(match.group(1)):02d}"


# Parses the cropped date OCR text.
# Expected text looks like 10/16/2025.
# Returns a normalized YYYY-MM-DD date string.
def parse_date_crop_text(text: str) -> str:

    match = re.search(
        r"\b(?P<month>\d{1,2})[-/](?P<day>\d{1,2})[-/](?P<year>20\d{2})\b",
        text,
    )

    if not match:
        return parse_ocr_date(text)

    year = int(match.group("year"))
    month = int(match.group("month"))
    day = int(match.group("day"))

    try:
        parsed_date = datetime(year, month, day)
    except ValueError:
        return ""

    return parsed_date.strftime("%Y-%m-%d")


# Parses the cropped bottom OCR text.
# Expected text looks like Start Line 810 or Point Arena.
# Returns either a Start Line value or a location string.
# Very noisy OCR strings are rejected.
def parse_line_crop_text(text: str) -> Tuple[str, str]:

    start_line = parse_ocr_start_line(text)

    if start_line:
        return start_line, ""

    # Keep normal location characters and remove OCR punctuation noise.
    location = re.sub(r"[^A-Za-z0-9 /:-]+", "", text)
    location = re.sub(r"\s+", " ", location).strip()

    if len(location) < 3:
        return "", ""

    letter_count = len(re.findall(r"[A-Za-z]", location))
    total_count = len(location)

    if total_count == 0:
        return "", ""

    # Reject strings that are mostly OCR garbage.
    if letter_count / total_count < 0.55:
        return "", ""

    # Reject very long OCR hallucinations from background texture.
    if len(location) > 40:
        return "", ""

    return "", location


# Writes a Jellyfin .ignore file in the output dive folder.
# This keeps sidecar poster/thumb JPG files from appearing as media items.
# The actual JPG files still remain beside the videos for local artwork use.
def write_jellyfin_ignore_file(dive_output_dir: Path) -> None:

    ignore_path = dive_output_dir / ".ignore"

    ignore_text = (
        "*-poster.jpg\n"
        "*-thumb.jpg\n"
    )

    ignore_path.write_text(ignore_text, encoding="utf-8")


# Runs OCR against known title-card regions.
# The full frame is extracted from the output video, then cropped.
# Top-left is parsed as dive, top-right as date, bottom as line/location.
# Returns parsed OCR fields and any non-fatal OCR errors.
def run_video_ocr(args: argparse.Namespace, job: VideoJob) -> OcrResult:

    offsets = parse_ocr_offsets(args.ocr_offsets)
    work_dir = job.output_dir / "_ocr_temp" / job.output_path.stem

    best_result = OcrResult()
    best_score = -1
    errors: List[str] = []

    for offset_seconds in offsets:
        offset_label = str(offset_seconds).replace(".", "_")
        frame_path = work_dir / f"{job.output_path.stem}_frame_{offset_label}s.png"

        ok, error = extract_ocr_frame(
            ffmpeg=args.ffmpeg,
            video_path=job.output_path,
            image_path=frame_path,
            offset_seconds=offset_seconds,
        )

        if not ok:
            errors.append(error)
            continue

        crop_definitions = {
            "dive": (0.00, 0.00, 0.48, 0.18),
            "date": (0.42, 0.00, 1.00, 0.18),
            "line": (0.12, 0.72, 0.88, 0.98),
        }

        crop_texts: Dict[str, str] = {}

        for crop_name, crop_box in crop_definitions.items():
            crop_path = work_dir / f"{job.output_path.stem}_{crop_name}_{offset_label}s.png"

            ok, error = extract_ocr_crop(
                ffmpeg=args.ffmpeg,
                ffprobe=args.ffprobe,
                frame_path=frame_path,
                crop_path=crop_path,
                crop_box=crop_box,
            )

            if not ok:
                errors.append(error)
                continue

            print(f"OCR crop: {crop_path}")

            raw_text, error = run_tesseract_crop_ocr(args.tesseract, crop_path)

            if error:
                errors.append(error)
                continue

            crop_texts[crop_name] = clean_ocr_field(raw_text)

        current_result = OcrResult()

        dive_text = crop_texts.get("dive", "")
        date_text = crop_texts.get("date", "")
        line_text = crop_texts.get("line", "")

        current_result.dive = parse_dive_crop_text(dive_text)
        current_result.date = parse_date_crop_text(date_text)

        start_line, location = parse_line_crop_text(line_text)
        current_result.start_line = start_line
        current_result.location = location

        current_result.raw_text = (
            f"DIVE_CROP: {dive_text}\n"
            f"DATE_CROP: {date_text}\n"
            f"LINE_CROP: {line_text}"
        )

        current_score = 0

        if current_result.dive:
            current_score += 10

        if current_result.date:
            current_score += 10

        if current_result.start_line:
            current_score += 15

        if current_result.location:
            current_score += 10

        if current_score > best_score:
            best_score = current_score
            best_result = current_result

    if not args.keep_ocr_frames and not args.keep_ocr_crops:
        cleanup_ocr_work_dir(work_dir)

    if not best_result.raw_text:
        best_result.error = "OCR did not read usable title-card text."

        if errors:
            best_result.error = " | ".join(errors)

        return best_result

    if errors:
        best_result.error = " | ".join(errors)

    return best_result


# Builds the SCHEMA row written into each dive CSV file.
# Each column receives a human-readable description.
# Future data rows use record_type VIDEO.
def make_schema_row() -> Dict[str, str]:

    row = {}

    for column in CSV_COLUMNS:
        row[column] = CSV_COLUMN_DESCRIPTIONS.get(column, "")

    row["notes"] = "COLUMN DESCRIPTIONS"

    return row


# Reads existing video rows from a dive CSV file.
# Rows are keyed by filename because output filenames are stable.
# The header-description row is ignored.
def read_existing_video_rows(csv_path: Path) -> Dict[str, Dict[str, str]]:

    if not csv_path.exists():
        return {}

    rows_by_filename: Dict[str, Dict[str, str]] = {}

    with csv_path.open("r", newline="", encoding="utf-8-sig") as handle:
        reader = csv.DictReader(handle)

        for row in reader:
            if row.get("notes") == "COLUMN DESCRIPTIONS":
                continue

            filename = row.get("filename", "")

            if filename:
                rows_by_filename[filename] = row

    return rows_by_filename


# Writes a complete per-dive CSV file.
# csv_path is created under the output dive folder.
# video_rows should contain actual video rows only.
# A column-description row is written after the header.
def write_dive_csv(csv_path: Path, video_rows: Iterable[Dict[str, str]]) -> None:

    csv_path.parent.mkdir(parents=True, exist_ok=True)

    sorted_rows = list(video_rows)

    # Sort rows explicitly without lambda expressions.
    def row_sort_key(row: Dict[str, str]) -> Tuple[str, str]:

        return (
            row.get("date_time_from_filename", ""),
            row.get("filename", ""),
        )

    sorted_rows.sort(key=row_sort_key)

    with csv_path.open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.DictWriter(handle, fieldnames=CSV_COLUMNS)
        writer.writeheader()
        writer.writerow(make_schema_row())

        for row in sorted_rows:
            writer.writerow(row)


# Builds one row for the per-dive line lookup CSV.
# The CSV relates each output video to a dive, date, line, or location.
# Processing details are intentionally left out.
def build_video_row(
    job: VideoJob,
    media_info: SourceMediaInfo,
    ocr_result: OcrResult,
) -> Dict[str, str]:

    ocr_line = ""

    if ocr_result.start_line:
        ocr_line = ocr_result.start_line
    elif ocr_result.location:
        ocr_line = ocr_result.location

    return {
        "filename": job.output_filename,
        "date_time_from_filename": job.filename_datetime,
        "video_length": media_info.duration_seconds,
        "ocr_dive": ocr_result.dive,
        "ocr_date": ocr_result.date,
        "ocr_line": ocr_line,
        "notes": "",
    }


# Inserts or updates one row in the per-dive CSV.
# csv_path points to the dive-line-data.csv file.
# Existing rows are preserved unless they match the same filename.
# The CSV is rewritten after each processed video for resumability.
def upsert_video_row(csv_path: Path, row: Dict[str, str]) -> None:

    existing_rows = read_existing_video_rows(csv_path)

    # Output filename is stable after source filename sanitization.
    existing_rows[row["filename"]] = row

    write_dive_csv(csv_path, existing_rows.values())


# Processes one video job from source to output.
# args contains command-line settings.
# job contains source, output, thumbnail, and dive paths.
# Errors are written into the per-dive CSV and do not stop the batch.
def process_job(
    args: argparse.Namespace,
    job: VideoJob,
    job_index: int,
    total_jobs: int,
    media_info: SourceMediaInfo,
    total_source_seconds_all_jobs: float,
    completed_source_seconds_before_job: float,
) -> None:

    csv_path = job.output_dir / CSV_FILENAME

    print()
    print(f"Source: {job.source_path}")
    print(f"Output: {job.output_path}")

    if args.dry_run:
        print("DRY RUN: no files written")
        return

    # Create only the output directory, never the source directory.
    job.output_dir.mkdir(parents=True, exist_ok=True)

    write_jellyfin_ignore_file(job.output_dir)

    status_parts: List[str] = []
    errors: List[str] = []

    output_exists = job.output_path.exists()

    if args.images_only:
        print("Images-only mode. Skipping transcode.")

        if not output_exists:
            print("Skipping image generation because output video does not exist.")
            return

        status_parts.append("IMAGES_ONLY")
    elif output_exists and args.skip_existing and not args.overwrite:
        print("Skipping transcode because output exists.")
        status_parts.append("SKIPPED_EXISTING")
    else:
        ok, error = transcode_video(
            ffmpeg=args.ffmpeg,
            project=args.project,
            job=job,
            job_index=job_index,
            total_jobs=total_jobs,
            video_bitrate=args.video_bitrate,
            audio_bitrate=args.audio_bitrate,
            nvenc_preset=args.nvenc_preset,
            overwrite=args.overwrite,
            source_duration_seconds=media_info.duration_seconds,
            total_source_seconds_all_jobs=total_source_seconds_all_jobs,
            completed_source_seconds_before_job=completed_source_seconds_before_job,
        )

        if ok:
            status_parts.append("TRANSCODED")
        else:
            status_parts.append("TRANSCODE_FAILED")
            errors.append(error)

            print(f"FAILED: {error}")
            return

    if not job.output_path.exists():
        status_parts.append("OUTPUT_MISSING")
        errors.append("Output video does not exist after transcode/skip step.")
    else:
        if job.poster_path.exists() and not args.overwrite:
            print("Poster already exists.")
        else:
            print("Creating Jellyfin poster...")

            ok, error = create_thumbnail(
                ffmpeg=args.ffmpeg,
                video_path=job.output_path,
                image_path=job.poster_path,
                offset_seconds=args.thumbnail_offset,
                overwrite=args.overwrite,
            )

            if not ok:
                status_parts.append("POSTER_FAILED")
                errors.append(error)

        if job.thumb_path.exists() and not args.overwrite:
            print("Thumb already exists.")
        else:
            print("Creating Jellyfin thumb...")

            ok, error = create_thumbnail(
                ffmpeg=args.ffmpeg,
                video_path=job.output_path,
                image_path=job.thumb_path,
                offset_seconds=args.thumbnail_offset,
                overwrite=args.overwrite,
            )

            if not ok:
                status_parts.append("THUMB_FAILED")
                errors.append(error)

        ocr_result = OcrResult()

        if args.enable_ocr and not args.images_only:
            print("Reading title-card text with OCR...")

            ocr_result = run_video_ocr(args, job)

            if ocr_result.dive:
                print(f"OCR dive: {ocr_result.dive}")
            else:
                print("OCR dive: not found")

            if ocr_result.date:
                print(f"OCR date: {ocr_result.date}")
            else:
                print("OCR date: not found")

            if ocr_result.start_line:
                print(f"OCR line: {ocr_result.start_line}")
            elif ocr_result.location:
                print(f"OCR location: {ocr_result.location}")
            else:
                print("OCR line/location: not found")

            if ocr_result.raw_text:
                print("OCR raw text:")
                print(ocr_result.raw_text)

            if ocr_result.error:
                status_parts.append("OCR_WARNING")
                errors.append(ocr_result.error)
            else:
                status_parts.append("OCR_DONE")

    if not errors:
        status_parts.append("DONE")
    else:
        status_parts.append("DONE_WITH_WARNINGS")

    row = build_video_row(
        job=job,
        media_info=media_info,
        ocr_result=ocr_result,
    )

    upsert_video_row(csv_path, row)

    if errors:
        print(f"DONE WITH WARNINGS: {' | '.join(errors)}")
    else:
        print("DONE")


# Prints a summary of the current run settings.
# args contains user command-line settings.
# input_root and output_root are resolved absolute paths.
# jobs_found is the number of discovered source videos.
def print_run_summary(
    args: argparse.Namespace,
    input_root: Path,
    output_root: Path,
    jobs_found: int,
) -> None:

    print(f"Input root:  {input_root}")
    print(f"Output root: {output_root}")
    print(f"Project:     {args.project}")
    print(f"Camera:      {args.camera}")
    print(f"Profile:     {args.profile}")
    print(f"Video rate:  {args.video_bitrate}")
    print(f"Audio rate:  {args.audio_bitrate}")
    print(f"OCR enabled: {args.enable_ocr}")
    print(f"Jobs found:  {jobs_found}")


# Handles one unexpected exception during job processing.
# The error is printed so the batch can continue.
# dive-line-data.csv is not updated because it only tracks usable videos.
def record_unexpected_job_error(
    args: argparse.Namespace,
    job: VideoJob,
    exception: Exception,
) -> None:

    print(f"UNEXPECTED ERROR processing {job.source_path}: {exception}", file=sys.stderr)


# Coordinates argument parsing, safety checks, discovery, and processing.
# This is the main entry point for the script.
# Each video is processed independently so one failure does not stop the batch.
def main() -> None:

    args = parse_arguments()

    input_root = resolved_path(args.input_root)
    output_root = resolved_path(args.output_root)

    assert_safe_paths(input_root, output_root)

    check_external_tool(args.ffmpeg)
    check_external_tool(args.ffprobe)

    if args.enable_ocr and not external_tool_available(args.tesseract):
        print(f"OCR disabled because Tesseract was not found: {args.tesseract}")
        args.enable_ocr = False

    if args.overwrite and args.skip_existing:
        fail("--overwrite and --skip-existing conflict. Choose one behavior.")

    jobs = discover_video_jobs(
        input_root=input_root,
        output_root=output_root,
        camera=args.camera,
        only_dive=args.only_dive,
        limit=args.limit,
    )

    print_run_summary(
        args=args,
        input_root=input_root,
        output_root=output_root,
        jobs_found=len(jobs),
    )

    if not jobs:
        print("No matching videos found.")
        return

    print("Reading source media info for ETA calculations...")

    media_infos_by_source: Dict[Path, SourceMediaInfo] = {}

    for job in jobs:
        media_infos_by_source[job.source_path] = read_source_media_info(args.ffprobe, job.source_path)

    total_jobs = len(jobs)
    total_source_seconds_all_jobs = 0.0

    for job in jobs:
        info = media_infos_by_source.get(job.source_path, SourceMediaInfo())
        duration_seconds = parse_positive_seconds(info.duration_seconds)

        if duration_seconds is not None:
            total_source_seconds_all_jobs += duration_seconds

    completed_source_seconds_before_job = 0.0

    for job_index, job in enumerate(jobs, start=1):
        media_info = media_infos_by_source.get(job.source_path, SourceMediaInfo())

        try:
            process_job(
                args,
                job,
                job_index,
                total_jobs,
                media_info,
                total_source_seconds_all_jobs,
                completed_source_seconds_before_job,
            )
        except KeyboardInterrupt:
            print("\nInterrupted by user.")
            raise
        except Exception as ex:
            record_unexpected_job_error(args, job, ex)

        job_duration_seconds = parse_positive_seconds(media_info.duration_seconds)

        if job_duration_seconds is not None:
            completed_source_seconds_before_job += job_duration_seconds

    create_all_dive_folder_posters(
        args=args,
        output_root=output_root,
        jobs=jobs,
    )

    


if __name__ == "__main__":
    main()