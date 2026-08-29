from __future__ import annotations

"""
dvd_video_ts_to_mp4.py

Batch converts old DVD VIDEO_TS folders into normal MP4 files for Jellyfin.

DVD folders are not normal folders of video files. A VIDEO_TS folder contains
DVD playback structure, menus, and one or more playable "titles." Each title
may be a real dive video, a menu loop, a short clip, or other DVD content.

This script uses HandBrakeCLI to:
    1. Find every VIDEO_TS folder under an input directory.
    2. Scan each DVD folder for playable titles.
    3. Export every detected title as an MP4 file.
    4. Preserve the source DVD resolution instead of upscaling.
    5. Use H.264 video and AAC audio for Jellyfin compatibility.

The script intentionally does not skip short titles by default because some
real survey clips may only be one or two minutes long.
"""

import argparse
import re
import subprocess
from pathlib import Path


HANDBRAKE_CLI = r"C:\tools\HandBrakeCLI-1.11.2-win-x86_64\HandBrakeCLI.exe"


# Cleans a string so it can safely be used as part of a Windows filename.
def sanitize_name(name: str) -> str:
    # Replace characters that Windows does not allow in filenames.
    safe_name = re.sub(r'[<>:"/\\|?*]+', "_", name)

    # Remove accidental leading/trailing spaces after cleanup.
    return safe_name.strip()


# Runs an external command and captures the text output for later parsing.
def run_command(command: list[str]) -> subprocess.CompletedProcess:
    # HandBrakeCLI writes useful scan information to stderr as well as stdout,
    # so both streams are captured instead of printing directly to the console.
    return subprocess.run(
        command,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        encoding="utf-8",
        errors="replace",
    )


# Finds every DVD video folder under the requested input root.
def find_video_ts_folders(input_root: Path) -> list[Path]:
    folders: list[Path] = []

    # Normalize the input root folder name once so we can support:
    #   VIDEO_TS
    #   VIDEO_TS1
    #   VIDEO_TS2
    #   VIDEO_TS_DISC_01
    # without caring about case.
    input_root_name = input_root.name.upper()

    # Support the case where the user passes a DVD video folder directly.
    if input_root.is_dir() and input_root_name.startswith("VIDEO_TS"):
        folders.append(input_root)

    # Support the more common case where the user passes a parent folder that
    # contains one or more DVD video folders somewhere underneath it.
    for path in input_root.rglob("*"):
        if not path.is_dir():
            continue

        # Accept any folder whose name starts with VIDEO_TS.
        # This catches copied DVD folders named VIDEO_TS, VIDEO_TS1, VIDEO_TS2,
        # etc., while ignoring unrelated folders.
        if path.name.upper().startswith("VIDEO_TS"):
            folders.append(path)

    # Remove duplicates while preserving the original search order.
    # This matters when input_root itself was a VIDEO_TS-style folder and rglob
    # also encounters the same folder during traversal.
    seen: set[Path] = set()
    unique_folders: list[Path] = []

    for folder in folders:
        resolved_folder = folder.resolve()

        if resolved_folder in seen:
            continue

        seen.add(resolved_folder)
        unique_folders.append(folder)

    return unique_folders

# Scans a VIDEO_TS folder and returns the DVD title numbers detected by HandBrakeCLI.
def scan_titles(video_ts_folder: Path, min_duration_seconds: int) -> list[int]:
    # In HandBrakeCLI, title 0 means "scan all titles."
    # min-duration is set low so very short real clips are not hidden.
    command = [
        HANDBRAKE_CLI,
        "--input", str(video_ts_folder),
        "--title", "0",
        "--scan",
        "--min-duration", str(min_duration_seconds),
    ]

    result = run_command(command)

    # HandBrakeCLI may report scan details in either stdout or stderr,
    # so combine both before looking for title numbers.
    combined_output = result.stdout + "\n" + result.stderr

    title_numbers: list[int] = []

    # Common HandBrake scan format:
    #   + title 1:
    #   + title 2:
    for line in combined_output.splitlines():
        match = re.search(r"\+ title (\d+):", line)

        if match:
            title_numbers.append(int(match.group(1)))

    # Fallback for alternate HandBrake scan text.
    # This makes the script less fragile across HandBrake versions.
    if not title_numbers:
        for line in combined_output.splitlines():
            match = re.search(r"Scanning title (\d+)", line, re.IGNORECASE)

            if match:
                title_numbers.append(int(match.group(1)))

    # Sort and deduplicate the titles so each one is exported once.
    return sorted(set(title_numbers))


# Converts one DVD title from a VIDEO_TS folder into one MP4 file.
def convert_title(
    video_ts_folder: Path,
    output_file: Path,
    title_number: int,
    quality: int,
    deinterlace: bool,
) -> bool:
    # These settings are intentionally conservative for old DVD footage:
    #   - x264 creates a Jellyfin-friendly H.264 MP4.
    #   - AAC audio is broadly compatible.
    #   - rate same avoids changing the source frame rate.
    #   - crop 0:0:0:0 prevents HandBrake from trimming edges automatically.
    #   - optimize makes the MP4 start more cleanly when served over a network.
    command = [
        HANDBRAKE_CLI,
        "--input", str(video_ts_folder),
        "--output", str(output_file),
        "--title", str(title_number),
        "--format", "av_mp4",
        "--encoder", "x264",
        "--quality", str(quality),
        "--aencoder", "av_aac",
        "--ab", "160",
        "--crop", "0:0:0:0",
        "--optimize",
    ]

    # Old DVD video is commonly interlaced. Decomb is safer than blindly
    # deinterlacing everything because it only processes frames that need it.
    if deinterlace:
        command.append("--decomb")

    print()
    print(f"Converting title {title_number}:")
    print(f"  Source: {video_ts_folder}")
    print(f"  Output: {output_file}")

    # This conversion can take a while, so do not capture output here.
    # Let HandBrakeCLI print progress directly to the terminal.
    result = subprocess.run(command)

    # Return success/failure so the caller can report failed titles.
    return result.returncode == 0


# Parses command-line arguments and runs the batch conversion workflow.
def main() -> None:
    parser = argparse.ArgumentParser(
        description="Convert DVD VIDEO_TS folders into one MP4 per DVD title."
    )

    # Root folder containing one VIDEO_TS folder or many copied DVD folders.
    parser.add_argument(
        "--input-root",
        required=True,
        help="Folder containing one or more DVD VIDEO_TS folders.",
    )

    # Root folder where all converted MP4 files should be written.
    parser.add_argument(
        "--output-root",
        required=True,
        help="Folder where MP4 files should be written.",
    )

    # Keep this default low because some real dive clips may be very short.
    parser.add_argument(
        "--min-duration",
        type=int,
        default=1,
        help="Minimum title duration in seconds. Use 1 to keep very short clips.",
    )

    # H.264 CRF-like quality value used by HandBrake.
    # Lower values mean larger files and better quality.
    parser.add_argument(
        "--quality",
        type=int,
        default=20,
        help="H.264 quality value. Lower is larger/better. 18-22 is typical.",
    )

    # Allow deinterlacing to be disabled if a specific DVD is already progressive.
    parser.add_argument(
        "--no-deinterlace",
        action="store_true",
        help="Disable DVD deinterlacing/decomb.",
    )

    # Useful for confirming detected VIDEO_TS folders and titles before encoding.
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Only scan and show what would be converted.",
    )

    args = parser.parse_args()

    input_root = Path(args.input_root)
    output_root = Path(args.output_root)

    # Make sure the output folder exists before starting any scans/conversions.
    output_root.mkdir(parents=True, exist_ok=True)

    # Locate all DVD folders to process.
    video_ts_folders = find_video_ts_folders(input_root)

    if not video_ts_folders:
        print("No VIDEO_TS folders found.")
        return

    print(f"Found {len(video_ts_folders)} VIDEO_TS folder(s).")

    # Process each DVD independently.
    for video_ts_folder in video_ts_folders:
        # Use the parent folder name as the disc name.
        # Example: D:/Raw_DVDs/CAMPA_2004_DVD01/VIDEO_TS
        # becomes: CAMPA_2004_DVD01_Title01.mp4
        # Use the parent folder name as the disc name when VIDEO_TS is inside a named
        # folder, such as D:/Raw_DVDs/CAMPA_2004_DVD01/VIDEO_TS.
        disc_folder = video_ts_folder.parent
        disc_name = sanitize_name(disc_folder.name)

        # If VIDEO_TS is directly at the root of a drive, such as D:/VIDEO_TS, Windows
        # does not provide a useful parent folder name. In that case, use the output
        # folder name so the generated files still get a meaningful prefix.
        if not disc_name:
            disc_name = sanitize_name(output_root.name)

        print()
        print("=" * 80)
        print(f"Scanning DVD folder: {video_ts_folder}")
        print(f"Disc name: {disc_name}")

        # Ask HandBrakeCLI which playable titles exist in this DVD structure.
        title_numbers = scan_titles(video_ts_folder, args.min_duration)

        if not title_numbers:
            print("No titles found.")
            continue

        print(f"Detected titles: {', '.join(str(title) for title in title_numbers)}")

        # Export every detected title.
        # We are not filtering menus yet because short real survey clips matter.
        for title_number in title_numbers:
            # Include the VIDEO_TS-style folder name when it has a suffix, such as
            # VIDEO_TS1 or VIDEO_TS2. This prevents multiple DVDs from the same dive folder
            # from overwriting each other.
            video_ts_name = sanitize_name(video_ts_folder.name)

            if video_ts_name.upper() == "VIDEO_TS":
                output_file = output_root / f"{disc_name}_Title{title_number:02d}.mp4"
            else:
                output_file = output_root / f"{disc_name}_{video_ts_name}_Title{title_number:02d}.mp4"

            # Skip already-created files so an interrupted run can be restarted.
            if output_file.exists():
                print(f"Skipping existing file: {output_file}")
                continue

            # Dry run reports what would happen without encoding anything.
            if args.dry_run:
                print(f"Would convert title {title_number} -> {output_file}")
                continue

            ok = convert_title(
                video_ts_folder=video_ts_folder,
                output_file=output_file,
                title_number=title_number,
                quality=args.quality,
                deinterlace=not args.no_deinterlace,
            )

            if not ok:
                print(f"FAILED: title {title_number} from {video_ts_folder}")


# Standard Python entry point.
# Keeps the script importable without immediately running conversions.
if __name__ == "__main__":
    main()