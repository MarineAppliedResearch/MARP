from __future__ import annotations

import json
import math
import shlex
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any
import textwrap


PROJECT_FOLDER = Path(r"C:\Users\isaac\Videos\lofi\Califnia_MPA_lofi_outreach")

MUSIC_FOLDER = PROJECT_FOLDER / "music"
VIDEO_FOLDER = PROJECT_FOLDER / "video"
SLIDES_FILE = PROJECT_FOLDER / "slides.json"

OUTPUT_FOLDER = PROJECT_FOLDER / "output"
WORKING_FOLDER = OUTPUT_FOLDER / "_working"
OUTPUT_FILE = OUTPUT_FOLDER / "ouptut.mp4"

SONGS_PER_VIDEO = 1
INTRO_GLIMPSE_SECONDS = 0.0
MAIN_START_SECONDS = 30.0

OUTPUT_WIDTH = 1920
OUTPUT_HEIGHT = 1080

TEXT_FADE_SECONDS = 1.0
TEXT_FONT_SIZE = 56
TEXT_BOX_OPACITY = 0.48
TEXT_BOX_BORDER = 36


START_IMAGE_FILE = VIDEO_FOLDER / "start.png"

START_IMAGE_HOLD_SECONDS = 3.0
END_IMAGE_HOLD_SECONDS = 2.0
START_END_FADE_SECONDS = 1.0
AUDIO_FADE_IN_SECONDS = 1.0
AUDIO_FADE_OUT_SECONDS = 2.0

# This should match your normalized ROV footage.
# Your current footage is 25 fps, so the still image stream is generated at 25 fps.
START_IMAGE_FPS = 25

# Set this to a short duration while testing slide placement and wrapping.
#
# Use None for the full render. Use something like 90 or 180 for test renders. None = 90
PREVIEW_SECONDS: float | None = None

VIDEO_EXTENSIONS = {".mp4", ".mov", ".m4v"}
MUSIC_EXTENSIONS = {".mp3", ".m4a", ".aac", ".wav", ".flac"}


@dataclass
class MediaItem:
    path: Path
    duration: float


@dataclass
class SongTiming:
    index: int
    number: int
    path: Path
    duration: float
    start: float
    end: float

@dataclass
class VideoPiece:
    source_video: MediaItem
    source_start: float
    duration: float


@dataclass
class VideoBlock:
    index: int
    number: int
    source_video: MediaItem
    start: float
    end: float
    duration: float
    song_start_index: int
    song_end_index: int
    pieces: list[VideoPiece]


@dataclass
class Slide:
    start: float
    duration: float
    text: str
    font_size: int = TEXT_FONT_SIZE


# Prints the setup expected by this script and stops before FFmpeg work starts.
def fail_with_setup_message(message: str) -> None:
    print()
    print(f"ERROR: {message}")
    print()
    print("Expected folder layout:")
    print("  ./music/       MP3 or other audio files, sorted by filename")
    print("  ./video/       normalized ROV MP4 files, sorted by filename")
    print("  ./slides.json  optional timed slide script")
    print()
    print("Example:")
    print("  lofi_project/")
    print("    mare_lofi_builder.py")
    print("    music/")
    print("      001_track.mp3")
    print("      002_track.mp3")
    print("    video/")
    print("      Dive01.mp4")
    print("      Dive02.mp4")
    print("    slides.json")
    print()
    sys.exit(1)


# Runs a command and gives a readable error if the external tool fails.
def run_command(command: list[str]) -> None:
    print()
    print("Running:")
    print(" ".join(shlex.quote(part) for part in command))
    print()

    result = subprocess.run(command)

    if result.returncode != 0:
        print()
        print(f"ERROR: command failed with exit code {result.returncode}.")
        sys.exit(result.returncode)


# Returns the media duration in seconds using ffprobe.
def probe_duration(path: Path) -> float:
    command = [
        "ffprobe",
        "-v", "error",
        "-show_entries", "format=duration",
        "-of", "default=nokey=1:noprint_wrappers=1",
        str(path),
    ]

    result = subprocess.run(command, capture_output=True, text=True)

    if result.returncode != 0:
        print(f"ERROR: ffprobe failed while reading: {path}")
        print(result.stderr.strip())
        sys.exit(result.returncode)

    try:
        return float(result.stdout.strip())
    except ValueError:
        print(f"ERROR: could not read duration from: {path}")
        sys.exit(1)


# Collects media files from a folder in filename order.
def scan_media_folder(folder: Path, extensions: set[str], label: str) -> list[MediaItem]:
    if not folder.exists():
        fail_with_setup_message(f"Missing required {label} folder: {folder}")

    files = [
        path
        for path in sorted(folder.iterdir(), key=lambda p: p.name.lower())
        if path.is_file() and path.suffix.lower() in extensions
    ]

    if not files:
        fail_with_setup_message(f"No usable {label} files found in: {folder}")

    print(f"Scanning {label} files...")

    return [MediaItem(path=path, duration=probe_duration(path)) for path in files]


# Converts seconds to a compact HH:MM:SS display string.
def format_seconds(seconds: float) -> str:
    total = int(round(seconds))
    hours = total // 3600
    minutes = (total % 3600) // 60
    secs = total % 60

    if hours:
        return f"{hours:02d}:{minutes:02d}:{secs:02d}"

    return f"{minutes:02d}:{secs:02d}"


# Parses HH:MM:SS, MM:SS, or numeric seconds into seconds.
def parse_time(value: Any) -> float:
    if isinstance(value, (int, float)):
        return float(value)

    if not isinstance(value, str):
        raise ValueError(f"Unsupported time value: {value!r}")

    parts = value.strip().split(":")

    if len(parts) == 1:
        return float(parts[0])

    if len(parts) == 2:
        minutes, seconds = parts
        return int(minutes) * 60 + float(seconds)

    if len(parts) == 3:
        hours, minutes, seconds = parts
        return int(hours) * 3600 + int(minutes) * 60 + float(seconds)

    raise ValueError(f"Unsupported time format: {value!r}")


# Builds the start and end time for each song in the final audio bed.
def build_song_timing(music: list[MediaItem]) -> list[SongTiming]:
    timings: list[SongTiming] = []
    cursor = 0.0

    for index, item in enumerate(music):
        start = cursor
        end = start + item.duration

        timings.append(
            SongTiming(
                index=index,
                number=index + 1,
                path=item.path,
                duration=item.duration,
                start=start,
                end=end,
            )
        )

        cursor = end

    return timings


# Groups the song timeline into ROV video blocks.
#
# Each block starts with the assigned video's opening glimpse, then uses footage
# after MAIN_START_SECONDS. If that assigned video is short, the block borrows
# filler footage from later videos so the final visual block still matches the
# assigned song group duration.
def build_video_blocks(songs: list[SongTiming], videos: list[MediaItem]) -> list[VideoBlock]:
    blocks: list[VideoBlock] = []
    block_count = math.ceil(len(songs) / SONGS_PER_VIDEO)

    if not videos:
        fail_with_setup_message("No ROV videos found.")

    for block_index in range(block_count):
        first_song_index = block_index * SONGS_PER_VIDEO
        last_song_index = min(first_song_index + SONGS_PER_VIDEO - 1, len(songs) - 1)

        block_start = songs[first_song_index].start
        block_end = songs[last_song_index].end
        block_duration = block_end - block_start

        assigned_video = videos[block_index % len(videos)]
        pieces: list[VideoPiece] = []

        remaining_duration = block_duration

        # Start each block with the first few seconds of the assigned video.
        intro_duration = min(INTRO_GLIMPSE_SECONDS, remaining_duration, assigned_video.duration)

        if intro_duration > 0:
            pieces.append(
                VideoPiece(
                    source_video=assigned_video,
                    source_start=0.0,
                    duration=intro_duration,
                )
            )

            remaining_duration -= intro_duration

        # Then use the assigned video's main footage after the baked-in intro.
        assigned_main_available = max(0.0, assigned_video.duration - MAIN_START_SECONDS)
        assigned_main_duration = min(remaining_duration, assigned_main_available)

        if assigned_main_duration > 0:
            pieces.append(
                VideoPiece(
                    source_video=assigned_video,
                    source_start=MAIN_START_SECONDS,
                    duration=assigned_main_duration,
                )
            )

            remaining_duration -= assigned_main_duration

        # If the assigned video is short, borrow filler from other videos.
        filler_video_index = block_index + 1

        while remaining_duration > 0.01:
            if filler_video_index >= len(videos) + block_index + 1:
                print()
                print("ERROR: Not enough ROV footage to fill the music timeline.")
                print(f"  Video block: {block_index + 1}")
                print(f"  Missing:     {remaining_duration:.1f} seconds")
                print()
                sys.exit(1)

            filler_video = videos[filler_video_index % len(videos)]
            filler_available = max(0.0, filler_video.duration - MAIN_START_SECONDS)

            if filler_available <= 0:
                filler_video_index += 1
                continue

            filler_duration = min(remaining_duration, filler_available)

            pieces.append(
                VideoPiece(
                    source_video=filler_video,
                    source_start=MAIN_START_SECONDS,
                    duration=filler_duration,
                )
            )

            remaining_duration -= filler_duration
            filler_video_index += 1

        blocks.append(
            VideoBlock(
                index=block_index,
                number=block_index + 1,
                source_video=assigned_video,
                start=block_start,
                end=block_end,
                duration=block_duration,
                song_start_index=first_song_index,
                song_end_index=last_song_index,
                pieces=pieces,
            )
        )

    return blocks


# Checks that each video block has enough planned pieces to fill its song group.
#
# The actual borrowing logic happens in build_video_blocks(). This validation is
# kept as a sanity check so timeline mistakes fail before FFmpeg rendering.
def validate_video_coverage(blocks: list[VideoBlock]) -> None:
    for block in blocks:
        planned_duration = sum(piece.duration for piece in block.pieces)
        shortfall = block.duration - planned_duration

        if shortfall <= 0.01:
            continue

        print()
        print("ERROR: Video block does not have enough planned footage.")
        print(f"  Video block: {block.number}")
        print(f"  Needed:      {format_seconds(block.duration)}")
        print(f"  Planned:     {format_seconds(planned_duration)}")
        print(f"  Shortfall:   {shortfall:.1f} seconds")
        print()
        sys.exit(1)


# Escapes a file path for FFmpeg drawtext textfile usage.
#
# Windows paths contain backslashes and colons, both of which can confuse FFmpeg
# filter syntax, so this converts to forward slashes and escapes the colon.
def escape_filter_path(path: Path) -> str:
    safe_path = path.resolve().as_posix()
    safe_path = safe_path.replace(":", "\\:")
    safe_path = safe_path.replace("'", "\\'")
    return safe_path


# Writes one wrapped slide text file for FFmpeg drawtext.
#
# Using textfile is more reliable than embedding multi-line text directly in the
# filter graph because FFmpeg does not consistently handle escaped newlines in
# drawtext text strings.
def write_slide_text_file(slide: Slide, slide_index: int) -> Path:
    slide_text_folder = WORKING_FOLDER / "slide_text"
    slide_text_folder.mkdir(exist_ok=True)

    text_path = slide_text_folder / f"slide_{slide_index:03d}.txt"

    # Wrap before writing so drawtext receives real line breaks from the file.
    wrapped_text = wrap_slide_text(slide.text)

    text_path.write_text(wrapped_text, encoding="utf-8")

    return text_path

# Wraps slide text before it is rendered onto a centered card.
#
# FFmpeg drawtext does not automatically wrap long lines, so Python inserts line
# breaks before each line is drawn separately.
def wrap_slide_text(text: str, max_line_length: int = 38) -> str:
    paragraphs = text.splitlines()
    wrapped_paragraphs: list[str] = []

    for paragraph in paragraphs:
        if not paragraph.strip():
            wrapped_paragraphs.append("")
            continue

        wrapped_paragraphs.append(
            textwrap.fill(
                paragraph,
                width=max_line_length,
                break_long_words=False,
                break_on_hyphens=False,
            )
        )

    return "\n".join(wrapped_paragraphs)


# Escapes strings for FFmpeg filter text values.
def escape_filter_text(text: str) -> str:
    replacements = {
        "\\": "\\\\",
        ":": "\\:",
        "'": "\\'",
        "%": "\\%",
        "\n": "\\n",
        "\r": "",
    }

    escaped = text

    for old, new in replacements.items():
        escaped = escaped.replace(old, new)

    return escaped


# Resolves one slide's start time from absolute, song-relative, or video-relative timing.
def resolve_slide_start(raw_slide: dict[str, Any], songs: list[SongTiming], blocks: list[VideoBlock]) -> float:
    offset = parse_time(raw_slide.get("offset", 0))

    if "at" in raw_slide:
        return parse_time(raw_slide["at"])

    if "song_number" in raw_slide:
        song_index = int(raw_slide["song_number"]) - 1

        if song_index < 0 or song_index >= len(songs):
            raise ValueError(f"song_number out of range: {raw_slide['song_number']}")

        return songs[song_index].start + offset

    if "song_index" in raw_slide:
        song_index = int(raw_slide["song_index"])

        if song_index < 0 or song_index >= len(songs):
            raise ValueError(f"song_index out of range: {raw_slide['song_index']}")

        return songs[song_index].start + offset

    if "video_number" in raw_slide:
        block_index = int(raw_slide["video_number"]) - 1

        if block_index < 0 or block_index >= len(blocks):
            raise ValueError(f"video_number out of range: {raw_slide['video_number']}")

        return blocks[block_index].start + offset

    if "video_index" in raw_slide:
        block_index = int(raw_slide["video_index"])

        if block_index < 0 or block_index >= len(blocks):
            raise ValueError(f"video_index out of range: {raw_slide['video_index']}")

        return blocks[block_index].start + offset

    raise ValueError("Slide must include at, song_number, song_index, video_number, or video_index.")


# Loads optional user-authored slides from slides.json.
def load_slides(songs: list[SongTiming], blocks: list[VideoBlock], total_duration: float) -> list[Slide]:
    if not SLIDES_FILE.exists():
        print("No slides.json found. Continuing without text slides.")
        return []

    try:
        raw_data = json.loads(SLIDES_FILE.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        print(f"ERROR: slides.json is not valid JSON: {exc}")
        sys.exit(1)

    if isinstance(raw_data, dict):
        raw_slides = raw_data.get("slides", [])
    elif isinstance(raw_data, list):
        raw_slides = raw_data
    else:
        print("ERROR: slides.json must contain either a list or an object with a 'slides' list.")
        sys.exit(1)

    slides: list[Slide] = []

    for raw_slide in raw_slides:
        if not isinstance(raw_slide, dict):
            print("ERROR: every slide entry must be a JSON object.")
            sys.exit(1)

        try:
            text = str(raw_slide["text"])
            start = resolve_slide_start(raw_slide, songs, blocks)
            duration = parse_time(raw_slide.get("duration", 7))
            font_size = int(raw_slide.get("font_size", TEXT_FONT_SIZE))
        except (KeyError, ValueError, TypeError) as exc:
            print(f"ERROR: invalid slide entry: {raw_slide}")
            print(exc)
            sys.exit(1)

        if duration <= 0:
            print(f"ERROR: slide duration must be positive: {raw_slide}")
            sys.exit(1)

        if start >= total_duration:
            print(f"WARNING: skipping slide after end of audio: {raw_slide}")
            continue

        slides.append(
            Slide(
                start=max(0.0, start),
                duration=min(duration, total_duration - start),
                text=text,
                font_size=font_size,
            )
        )

    print(f"Loaded {len(slides)} slide(s).")
    return slides


# Writes a concat list for the audio files so FFmpeg can assemble the music bed.
def write_audio_concat_list(music: list[MediaItem], path: Path) -> None:
    lines = []

    for item in music:
        absolute_path = item.path.resolve().as_posix()
        safe_path = absolute_path.replace("'", "'\\''")
        lines.append(f"file '{safe_path}'")

    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


# Builds the audio bed as one AAC file and applies basic loudness normalization.
def render_music_bed(music: list[MediaItem], working_folder: Path) -> Path:
    concat_list = working_folder / "music_concat.txt"
    music_bed = working_folder / "music_bed.m4a"

    write_audio_concat_list(music, concat_list)

    command = [
        "ffmpeg",
        "-y",
        "-f", "concat",
        "-safe", "0",
        "-i", str(concat_list),
        "-af", "loudnorm=I=-16:TP=-1.5:LRA=11",
        "-c:a", "aac",
        "-b:a", "192k",
        str(music_bed),
    ]

    run_command(command)
    return music_bed


# Adds FFmpeg trim filters for one ROV visual block.
#
# A block is now a list of planned video pieces. Normally that is the opening
# glimpse plus main footage from the assigned video. If the assigned video was
# short, this list may also include filler pieces from other ROV videos.
def add_video_block_filters(
    filters: list[str],
    input_lookup: dict[Path, int],
    block: VideoBlock,
) -> str:
    piece_labels: list[str] = []

    for piece_index, piece in enumerate(block.pieces):
        input_index = input_lookup[piece.source_video.path]
        piece_label = f"block{block.index}_piece{piece_index}"

        filters.append(
            f"[{input_index}:v]"
            f"trim=start={piece.source_start}:duration={piece.duration},"
            f"setpts=PTS-STARTPTS,"
            f"format=yuv420p"
            f"[{piece_label}]"
        )

        piece_labels.append(piece_label)

    output_label = f"video_block{block.index}"

    filters.append(
        "".join(f"[{label}]" for label in piece_labels)
        + f"concat=n={len(piece_labels)}:v=1:a=0"
        + f"[{output_label}]"
    )

    return output_label


# Builds the FFmpeg alpha expression used to fade a slide in and out.
#
# The expression returns 0 before the slide, ramps to 1, holds, then ramps back
# to 0. FFmpeg evaluates this once per frame while drawtext is enabled.
def build_slide_alpha_expression(start: float, duration: float) -> str:
    end = start + duration
    fade = min(TEXT_FADE_SECONDS, duration / 2.0)

    return (
        f"if(lt(t\\,{start})\\,0\\,"
        f"if(lt(t\\,{start + fade})\\,(t-{start})/{fade}\\,"
        f"if(lt(t\\,{end - fade})\\,1\\,"
        f"if(lt(t\\,{end})\\,({end}-t)/{fade}\\,0))))"
    )

# Adds all resolved text slides to the assembled ROV video stream.
#
# Slides are applied through a generated ASS subtitle file. This avoids the
# fragile drawbox/drawtext filter chains and keeps the card layout predictable.
def add_slide_filters(
    filters: list[str],
    input_label: str,
    slides: list[Slide],
) -> str:
    if not slides:
        return input_label

    subtitle_path = write_ass_subtitles(slides)

    # FFmpeg subtitles filter works best with forward slashes on Windows.
    safe_subtitle_path = subtitle_path.resolve().as_posix().replace(":", "\\:")

    output_label = "video_with_slides"

    filters.append(
        f"[{input_label}]"
        f"subtitles='{safe_subtitle_path}'"
        f"[{output_label}]"
    )

    return output_label


# Escapes text for ASS subtitle dialogue lines.
#
# ASS uses braces and backslashes for override tags, so user text needs to be
# cleaned before it is written into the generated subtitle file.
def escape_ass_text(text: str) -> str:
    escaped = text
    escaped = escaped.replace("\\", "\\\\")
    escaped = escaped.replace("{", "\\{")
    escaped = escaped.replace("}", "\\}")
    return escaped


# Formats seconds as ASS subtitle time: H:MM:SS.cc.
#
# ASS subtitles use centiseconds instead of milliseconds, so this rounds to two
# decimal places.
def format_ass_time(seconds: float) -> str:
    centiseconds_total = int(round(seconds * 100))

    hours = centiseconds_total // 360000
    minutes = (centiseconds_total % 360000) // 6000
    secs = (centiseconds_total % 6000) // 100
    centiseconds = centiseconds_total % 100

    return f"{hours}:{minutes:02d}:{secs:02d}.{centiseconds:02d}"


# Writes the resolved slides to an ASS subtitle file.
#
# ASS handles centered text, line breaks, background boxes, and fade tags more
# reliably than FFmpeg drawtext for this use case.
def write_ass_subtitles(slides: list[Slide]) -> Path:
    subtitle_path = WORKING_FOLDER / "slides.ass"

    lines: list[str] = [
        "[Script Info]",
        "ScriptType: v4.00+",
        "PlayResX: 1920",
        "PlayResY: 1080",
        "",
        "[V4+ Styles]",
        "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, "
        "Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, "
        "Shadow, Alignment, MarginL, MarginR, MarginV, Encoding",
        "Style: Card,Arial,54,&H00FFFFFF,&H000000FF,&H00000000,&H88000000,"
        "0,0,0,0,100,100,0,0,3,0,0,5,180,180,80,1",
        "",
        "[Events]",
        "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text",
    ]

    for slide in slides:
        start_time = format_ass_time(slide.start)
        end_time = format_ass_time(slide.start + slide.duration)

        # Wrap in Python so ASS receives deliberate centered line breaks.
        wrapped_text = wrap_slide_text(slide.text, max_line_length=38)
        escaped_text = escape_ass_text(wrapped_text).replace("\n", "\\N")

        fade_ms = int(min(TEXT_FADE_SECONDS, slide.duration / 2.0) * 1000)

        # an5 and pos put the subtitle block at the exact center of 1920x1080.
        override_tags = f"{{\\fad({fade_ms},{fade_ms})\\an5\\pos(960,540)\\q2}}"

        lines.append(
            f"Dialogue: 0,{start_time},{end_time},Card,,0,0,0,,"
            f"{override_tags}{escaped_text}"
        )

    subtitle_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return subtitle_path

# Builds the complete FFmpeg video filter graph.
# Builds the complete FFmpeg video filter graph.
#
# The graph trims each planned video piece, concatenates pieces into visual
# blocks, applies slides, and optionally wraps the whole video with start.png.
def build_video_filter_graph(
    blocks: list[VideoBlock],
    slides: list[Slide],
    input_lookup: dict[Path, int],
    start_image_input_index: int | None,
) -> tuple[str, str]:
    filters: list[str] = []
    block_labels: list[str] = []

    for block in blocks:
        # Each block may contain pieces from more than one source video.
        block_labels.append(add_video_block_filters(filters, input_lookup, block))

    assembled_label = "assembled_video"

    # Join all visual blocks into the full final video timeline.
    filters.append(
        "".join(f"[{label}]" for label in block_labels)
        + f"concat=n={len(block_labels)}:v=1:a=0"
        + f"[{assembled_label}]"
    )

    # Slides are applied before the start/end wrapper so slide timing still
    # matches the music/video story timeline, not the extra title-card seconds.
    main_video_label = add_slide_filters(filters, assembled_label, slides)

    if start_image_input_index is None:
        return ";".join(filters), main_video_label

    main_duration = sum(block.duration for block in blocks)

    start_still_duration = START_IMAGE_HOLD_SECONDS + START_END_FADE_SECONDS
    end_still_duration = END_IMAGE_HOLD_SECONDS + START_END_FADE_SECONDS

    xfade_ready_main_label = "xfade_ready_main_video"
    start_image_label = "start_image_prepared"
    end_image_label = "end_image_prepared"
    intro_wrapped_label = "intro_wrapped_video"
    final_wrapped_label = "final_wrapped_video"

    # Normalize the assembled ROV stream before using xfade.
    #
    # xfade requires both inputs to have the same frame rate and timebase. This
    # keeps the source timing explicit instead of letting FFmpeg infer it.
    filters.append(
        f"[{main_video_label}]"
        f"fps={START_IMAGE_FPS},"
        f"settb=AVTB,"
        f"setpts=PTS-STARTPTS,"
        f"format=yuv420p"
        f"[{xfade_ready_main_label}]"
    )

    main_video_label = xfade_ready_main_label

    # Prepare the start image as a short video stream matching the ROV stream.
    filters.append(
        f"[{start_image_input_index}:v]"
        f"scale={OUTPUT_WIDTH}:{OUTPUT_HEIGHT}:force_original_aspect_ratio=increase,"
        f"crop={OUTPUT_WIDTH}:{OUTPUT_HEIGHT},"
        f"fps={START_IMAGE_FPS},"
        f"settb=AVTB,"
        f"setpts=PTS-STARTPTS,"
        f"format=yuv420p,"
        f"trim=start=0:duration={start_still_duration},"
        f"setpts=PTS-STARTPTS"
        f"[{start_image_label}]"
    )

    # Prepare a second copy of the same image for the ending hold.
    filters.append(
        f"[{start_image_input_index}:v]"
        f"scale={OUTPUT_WIDTH}:{OUTPUT_HEIGHT}:force_original_aspect_ratio=increase,"
        f"crop={OUTPUT_WIDTH}:{OUTPUT_HEIGHT},"
        f"fps={START_IMAGE_FPS},"
        f"settb=AVTB,"
        f"setpts=PTS-STARTPTS,"
        f"format=yuv420p,"
        f"trim=start=0:duration={end_still_duration},"
        f"setpts=PTS-STARTPTS"
        f"[{end_image_label}]"
    )

    # Hold start.png, then crossfade into the assembled ROV video.
    filters.append(
        f"[{start_image_label}][{main_video_label}]"
        f"xfade="
        f"transition=fade:"
        f"duration={START_END_FADE_SECONDS}:"
        f"offset={START_IMAGE_HOLD_SECONDS}"
        f"[{intro_wrapped_label}]"
    )

    # After the ROV video, crossfade back to start.png and hold it at the end.
    filters.append(
        f"[{intro_wrapped_label}][{end_image_label}]"
        f"xfade="
        f"transition=fade:"
        f"duration={START_END_FADE_SECONDS}:"
        f"offset={START_IMAGE_HOLD_SECONDS + main_duration - START_END_FADE_SECONDS}"
        f"[{final_wrapped_label}]"
    )

    return ";".join(filters), final_wrapped_label


# Renders the final MP4 from planned ROV video pieces and the prepared music bed.
#
# Each unique source video is added once as an FFmpeg input. If video/start.png
# exists, it is added as a looped still-image input and used as the opening and
# closing visual wrapper. The music bed is trimmed to the same final visual
# duration and faded out at the end.
def render_final_video(blocks: list[VideoBlock], slides: list[Slide], music_bed: Path) -> None:
    unique_videos: list[MediaItem] = []
    seen_paths: set[Path] = set()

    for block in blocks:
        for piece in block.pieces:
            if piece.source_video.path in seen_paths:
                continue

            # Preserve first-use order so FFmpeg input indexes stay predictable.
            seen_paths.add(piece.source_video.path)
            unique_videos.append(piece.source_video)

    input_lookup = {
        video.path: input_index
        for input_index, video in enumerate(unique_videos)
    }

    command = ["ffmpeg", "-y"]

    for video in unique_videos:
        command.extend(["-i", str(video.path)])

    main_duration = sum(block.duration for block in blocks)
    final_visual_duration = main_duration

    start_image_input_index: int | None = None

    if START_IMAGE_FILE.exists():
        start_image_input_index = len(unique_videos)

        # The wrapper adds a start hold before the ROV footage and an end hold
        # after it. The crossfades overlap, so their durations are not added.
        final_visual_duration = (
            START_IMAGE_HOLD_SECONDS
            + main_duration
            + END_IMAGE_HOLD_SECONDS
        )

        # Loop the still image long enough for both the start and end wrappers.
        command.extend(
            [
                "-loop", "1",
                "-t", str(START_IMAGE_HOLD_SECONDS + END_IMAGE_HOLD_SECONDS + (2 * START_END_FADE_SECONDS)),
                "-i", str(START_IMAGE_FILE),
            ]
        )

        print(f"Using start/end image: {START_IMAGE_FILE}")
    else:
        print(f"No start image found at {START_IMAGE_FILE}. Rendering without start/end image wrapper.")

    filter_graph, final_video_label = build_video_filter_graph(
        blocks,
        slides,
        input_lookup,
        start_image_input_index,
    )

    # The music bed is added after all video and image inputs.
    command.extend(["-i", str(music_bed)])

    if start_image_input_index is None:
        audio_input_index = len(unique_videos)
    else:
        audio_input_index = len(unique_videos) + 1

    final_audio_label = "final_audio"
    audio_fade_out_start = max(0.0, final_visual_duration - AUDIO_FADE_OUT_SECONDS)

    # Trim audio to the final visual duration and fade it out at the end.
    filter_graph = (
        filter_graph
        + ";"
        + f"[{audio_input_index}:a]"
        f"atrim=start=0:duration={final_visual_duration},"
        f"asetpts=PTS-STARTPTS,"
        f"afade=t=in:st=0:d={AUDIO_FADE_IN_SECONDS},"
        f"afade=t=out:st={audio_fade_out_start}:d={AUDIO_FADE_OUT_SECONDS}"
        f"[{final_audio_label}]"
    )

    command.extend(
        [
            "-filter_complex", filter_graph,
            "-map", f"[{final_video_label}]",
            "-map", f"[{final_audio_label}]",
        ]
    )

    # Limit the render duration while testing so slide changes do not cost a full render.
    if PREVIEW_SECONDS is not None:
        command.extend(["-t", str(PREVIEW_SECONDS)])

    command.extend(
        [
            "-c:v", "libx264",
            "-preset", "medium",
            "-crf", "20",
            "-c:a", "aac",
            "-b:a", "192k",
            "-pix_fmt", "yuv420p",
            "-movflags", "+faststart",
            "-shortest",
            str(OUTPUT_FILE),
        ]
    )

    run_command(command)


# Prints the plan before rendering so bad folder contents are obvious.
def print_render_summary(music: list[MediaItem], songs: list[SongTiming], videos: list[MediaItem], blocks: list[VideoBlock]) -> None:
    total_music_duration = songs[-1].end

    print()
    print("Render plan")
    print("-----------")
    print(f"Music files:          {len(music)}")
    print(f"ROV video files:      {len(videos)}")
    print(f"Songs per ROV block:  {SONGS_PER_VIDEO}")
    print(f"Video blocks needed:  {len(blocks)}")
    print(f"Total music duration: {format_seconds(total_music_duration)}")
    print(f"Output:               {OUTPUT_FILE}")
    print()

    print("Song timing")
    print("-----------")

    for song in songs:
        print(
            f"{song.number:02d}. "
            f"{song.path.name} "
            f"{format_seconds(song.start)} -> {format_seconds(song.end)}"
        )

    print()
    print("ROV block timing")
    print("----------------")

    for block in blocks:
        first_song = block.song_start_index + 1
        last_song = block.song_end_index + 1

        print(
            f"Video block {block.number:02d}: "
            f"songs {first_song}-{last_song}, "
            f"{format_seconds(block.start)} -> {format_seconds(block.end)}, "
            f"{block.source_video.path.name}"
        )


# Ensures the required external tools are available before doing any probing or rendering.
def verify_tools() -> None:
    missing = [tool for tool in ("ffmpeg", "ffprobe") if shutil.which(tool) is None]

    if missing:
        print()
        print(f"ERROR: missing required tool(s): {', '.join(missing)}")
        print("Install FFmpeg and make sure ffmpeg and ffprobe are available in PATH.")
        print()
        sys.exit(1)


# Runs the full build process.
def main() -> None:
    verify_tools()

    OUTPUT_FOLDER.mkdir(exist_ok=True)
    working_folder = OUTPUT_FOLDER / "_working"
    working_folder.mkdir(exist_ok=True)

    music = scan_media_folder(MUSIC_FOLDER, MUSIC_EXTENSIONS, "music")
    videos = scan_media_folder(VIDEO_FOLDER, VIDEO_EXTENSIONS, "ROV video")

    songs = build_song_timing(music)
    blocks = build_video_blocks(songs, videos)

    validate_video_coverage(blocks)
    slides = load_slides(songs, blocks, songs[-1].end)

    print_render_summary(music, songs, videos, blocks)

    music_bed = WORKING_FOLDER / "music_bed.m4a"

    if not music_bed.exists():
        music_bed = render_music_bed(music, WORKING_FOLDER)
    else:
        print(f"Using existing music bed: {music_bed}")

    render_final_video(blocks, slides, music_bed)

    print()
    print("Done.")
    print(f"Created: {OUTPUT_FILE}")


if __name__ == "__main__":
    main()
