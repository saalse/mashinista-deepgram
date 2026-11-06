"""
transcribe_call.py: the two-channel call parts of a transcribe.py run.

A call recording here is one stereo file: the left channel is the user's mic,
the right channel is everyone else (the sound the computer played). Nistka
records calls this way, into NISTKA_DIR. This module decides when a file is
such a call, checks locally that both channels carry sound, prepares the
upload without ever mixing the channels, and builds the call's transcript.
"""
from __future__ import annotations

import re
import subprocess
import sys
from datetime import datetime
from pathlib import Path

from transcribe_helpers import die, find_tool, fmt_ts

# Nistka saves every call here, as "<date> <time>.m4a" (stereo AAC).
NISTKA_DIR = Path.home() / "Documents" / "Nistka"

CALL_CHANNELS = 2         # channel 0 (left) is you, channel 1 (right) the others
SILENT_PEAK_DB = -60.0    # a channel that never gets louder than this is silent
UPLOAD_RATE = 16000       # Hz, for the lossless upload of formats Deepgram lacks
REPEAT_WARN_MIN = 5       # warn when more of your lines than this, and
REPEAT_WARN_SHARE = 0.02  # more than this share, repeat on the others' channel


# --- Is it a call? ----------------------------------------------------------

def audio_channels(source: Path) -> int | None:
    """Channels of the first audio stream, from ffprobe, or None."""
    ffprobe = find_tool("ffprobe")
    if not ffprobe:
        return None
    result = subprocess.run(
        [ffprobe, "-v", "error", "-select_streams", "a:0",
         "-show_entries", "stream=channels", "-of", "csv=p=0", str(source)],
        capture_output=True, text=True,
    )
    try:
        return int(result.stdout.strip().splitlines()[0])
    except (ValueError, IndexError):
        return None


def in_nistka_folder(source: Path) -> bool:
    """True for a file anywhere inside NISTKA_DIR."""
    path = source.resolve()
    return path.is_relative_to(NISTKA_DIR.resolve())


# --- Both channels, checked locally -----------------------------------------

_STAT = re.compile(r"(Channel|Peak level dB|RMS level dB):\s*(\S+)")


def channel_levels(source: Path) -> list[tuple[float, float]] | None:
    """(peak dB, RMS dB) per channel of the first audio stream, or None.

    Decodes the whole file locally with ffmpeg's astats filter: about
    10 seconds per hour of audio. Nothing is uploaded.
    """
    ffmpeg = find_tool("ffmpeg")
    if not ffmpeg:
        die("ERROR: ffmpeg is not installed, and a call recording needs it.\n"
            "  Rerun install.sh, or run: brew install ffmpeg")
    result = subprocess.run(
        [ffmpeg, "-nostdin", "-hide_banner", "-nostats", "-i", str(source),
         "-map", "0:a:0", "-af",
         "astats=measure_overall=none:measure_perchannel=Peak_level+RMS_level",
         "-f", "null", "-"],
        capture_output=True, text=True,
    )
    levels: dict[int, dict[str, float]] = {}
    current = None
    for key, value in _STAT.findall(result.stderr or ""):
        if key == "Channel":
            current = int(value)
            levels[current] = {}
        elif current is not None:
            try:
                levels[current][key] = float(value)
            except ValueError:
                continue
    out = [(v.get("Peak level dB"), v.get("RMS level dB")) for _, v in sorted(levels.items())]
    if result.returncode != 0 or not out or any(p is None for p, _ in out):
        return None
    return [(p, r if r is not None else float("-inf")) for p, r in out]


def silent_channels(levels: list[tuple[float, float]]) -> list[int]:
    """Indexes of the channels that never rise above SILENT_PEAK_DB."""
    return [i for i, (peak, _) in enumerate(levels) if peak < SILENT_PEAK_DB]


def _db(x: float) -> str:
    return "silent" if x == float("-inf") else f"{x:.0f} dB"


def levels_text(levels: list[tuple[float, float]]) -> list[str]:
    """The measured levels, for the technical details."""
    names = ["you (left)", "the others (right)"]
    return [f"{names[i] if i < len(names) else f'channel {i + 1}'}: "
            f"peak {_db(p)}, average {_db(r)}" for i, (p, r) in enumerate(levels)]


# --- Who is labelled how ----------------------------------------------------

def leaked(repeated: int, me_lines: int) -> bool:
    """Too many of your lines repeat on the others' channel."""
    return repeated > max(REPEAT_WARN_MIN, REPEAT_WARN_SHARE * me_lines)


def repeat_text(repeated: int, me_lines: int, *, short: bool = False) -> str:
    """The repeats count, and what it means, in plain words."""
    line = (f"{repeated} of {me_lines} lines of yours also "
            f"{'on' if short else 'appear on'} the others' channel within ±1 s")
    if leaked(repeated, me_lines):
        return line
    if repeated:
        return (line + ": the channels stayed apart (a few are normal: short "
                "words you both said at the same moment)")
    return line + ": the channels stayed apart"


def resolve_diarize(flag: bool | None, *, call_mode: bool,
                    speaker_names: list[str]) -> bool:
    """Diarization on unless turned off; on a call, for the others only.

    On a call the speaker comes from the channel, so a call with one other
    person needs no diarization at all. It is on when --speakers names two
    or more people, or when --diarize asks for it, and then only the right
    channel's labels are used.
    """
    if flag is not None:
        return flag
    return len(speaker_names) >= 2 if call_mode else True


def call_labels(me: str | None, far_names: list[str]) -> list[str]:
    """Labels for label_lines: you first, then the others if it is one person.

    Two or more names cannot be matched to diarized voices by order (nobody
    knows who spoke first), so those stay Speaker 1, 2, ... and the names
    only help as keyterms.
    """
    return [me or "Me"] + (far_names if len(far_names) == 1 else [])


def is_placeholder(name: str) -> bool:
    """'Speaker A', 'Speaker 2': stands in for an unknown name, so no keyterm."""
    return re.fullmatch(r"speaker\s*\w{1,2}", name.strip(), re.IGNORECASE) is not None


def with_names(keyterms: list[str], names: list[str]) -> list[str]:
    """Keyterms plus people's names, once each: on a call they are said aloud."""
    seen = {k.casefold() for k in keyterms}
    out = list(keyterms)
    for n in names:
        if n.casefold() not in seen and not is_placeholder(n):
            out.append(n)
            seen.add(n.casefold())
    return out


# --- Upload -----------------------------------------------------------------

def encode_call_audio(source: Path, workdir: Path) -> Path:
    """Both channels as independent lossless FLAC at UPLOAD_RATE.

    Only for formats Deepgram does not take as they are (CAF, video). FLAC's
    independent channel mode keeps the two channels apart; lossy stereo
    codecs at low bitrates code mid and side, which can bleed one channel
    into the other.
    """
    ffmpeg = find_tool("ffmpeg")
    if not ffmpeg:
        die("ERROR: ffmpeg is not installed, and this file needs it.\n"
            "  Rerun install.sh, or run: brew install ffmpeg")
    out = workdir / (source.stem + ".flac")
    print(f"Preparing both channels locally from {source.name} ...", file=sys.stderr)
    result = subprocess.run(
        [ffmpeg, "-nostdin", "-hide_banner", "-loglevel", "error", "-y",
         "-i", str(source), "-map", "0:a:0", "-vn", "-sn", "-dn",
         "-ac", str(CALL_CHANNELS), "-ar", str(UPLOAD_RATE),
         "-c:a", "flac", "-ch_mode", "indep", str(out)],
        capture_output=True, text=True,
    )
    if result.returncode != 0 or not out.is_file() or out.stat().st_size == 0:
        die(f"ERROR: ffmpeg could not read the audio in {source.name}.\n"
            + "".join(f"  {d}\n" for d in (result.stderr or "").strip().splitlines()[-3:]))
    return out


# --- Transcript -------------------------------------------------------------

def build_call_transcript(data: dict, *, source: Path, language: str,
                          far_diarized: bool, keyterms: list[str],
                          mip_opt_out: bool, speaker_names: list[str],
                          model: str, keep_all_lines: bool,
                          details: list[str] = ()) -> tuple[str, dict]:
    """Transcript text for a two-channel call, plus the counts worth printing.

    source is what the header names: the recording, or the --output stem.
    """
    from call_lines import call_lines, count_repeats, drop_noise_lines, label_lines

    lines = call_lines(data, far_diarized=far_diarized)
    repeated, me_lines = count_repeats(lines)
    dropped = {}
    if not keep_all_lines:
        lines, dropped = drop_noise_lines(lines)
    label_lines(lines, speaker_names)

    metadata = data.get("metadata") or {}
    privacy = ("MIP opt-out ON (audio not used for training)"
               if mip_opt_out else
               "MIP opt-out OFF, THIS FILE MAY BE USED TO TRAIN DEEPGRAM MODELS")
    out: list[str] = []
    out.append(f"Transcript: {source.name}")
    out.append(f"Source:     {source}")
    out.append(f"Date:       {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    out.append(f"Engine:     Deepgram {model} (cloud), call, 2 channels")
    out.append(f"Language:   {language}")
    out.append("Speakers:   " + (
        "you from your own channel; the others split by voice" if far_diarized else
        "you and one other person, each from their own channel"))
    out.append("            Anyone in the room with you is on your mic, "
               "so they are labelled as you.")
    if far_diarized:
        out.append("            Someone whose audio changed (another device, a "
                   "reconnect) can get a second Speaker number.")
    out.append(f"Keyterms:   {', '.join(keyterms) if keyterms else '(none)'}")
    out.append(f"Privacy:    {privacy}")
    if keep_all_lines:
        out.append("Cleanup:    off (--keep-all-lines)")
    else:
        detail = ", ".join(f"{v} {k}" for k, v in sorted(dropped.items()))
        out.append(f"Cleanup:    dropped {sum(dropped.values())} short lines"
                   + (f" ({detail})" if detail else ""))
    out.append(f"Repeats:    {repeat_text(repeated, me_lines, short=True)}")
    if metadata.get("duration") is not None:
        out.append(f"Length:     {fmt_ts(metadata['duration'])}")
    out.append("-" * 60)
    out.append("")

    # Merge consecutive lines by the same speaker into one block.
    blocks: list[dict] = []
    for line in lines:
        if blocks and blocks[-1]["label"] == line["label"]:
            blocks[-1]["end"] = line["end"]
            blocks[-1]["text"] += " " + line["text"]
        else:
            blocks.append({"label": line["label"], "start": line["start"],
                           "end": line["end"], "text": line["text"]})
    for b in blocks:
        out.append(f"{b['label']}  [{fmt_ts(b['start'])}–{fmt_ts(b['end'])}]")
        out.append(f"  {b['text']}")
        out.append("")
    if not blocks:
        out.append("(empty transcript)")
        out.append("")

    # Measurements at the end: only for troubleshooting.
    out.append("-" * 60)
    out.append("Technical details, only needed if something looks wrong:")
    out.extend(f"  {info}" for info in details)
    if metadata.get("request_id"):
        out.append(f"  Deepgram request_id {metadata['request_id']}")

    counts = {"repeated": repeated, "me_lines": me_lines,
              "dropped": sum(dropped.values()), "dropped_detail": dropped}
    return "\n".join(out).rstrip() + "\n", counts
