"""
transcribe_helpers.py: small helpers for transcribe.py.

Homebrew tools and ffmpeg, lengths and language names, the settings line,
the Trash, and the transcript of an ordinary recording.
"""
from __future__ import annotations

import json
import shutil
import subprocess
import sys
from datetime import datetime
from pathlib import Path

# --- Small helpers --------------------------------------------------------

def die(msg: str, code: int = 1) -> "None":
    print(msg, file=sys.stderr)
    raise SystemExit(code)


def find_tool(name: str) -> str | None:
    """Find a Homebrew tool even when PATH lacks the Homebrew folder."""
    found = shutil.which(name)
    if found:
        return found
    for folder in ("/opt/homebrew/bin", "/usr/local/bin"):
        candidate = Path(folder) / name
        if candidate.is_file():
            return str(candidate)
    return None


def extract_audio(source: Path, workdir: Path, channel: int | None = None) -> Path:
    """Cut the first audio track out as mono Opus, locally, for upload.

    channel: take only that channel (0 = left) instead of mixing them all.
    """
    ffmpeg = find_tool("ffmpeg")
    if not ffmpeg:
        die("ERROR: ffmpeg is not installed, and this file needs it.\n"
            "  Rerun install.sh, or run: brew install ffmpeg")
    out = workdir / (source.stem + ".ogg")
    print(f"Extracting a mono audio track locally from {source.name} ...",
          file=sys.stderr)
    mono = (["-ac", "1"] if channel is None
            else ["-af", f"pan=mono|c0=c{channel}"])
    result = subprocess.run(
        [ffmpeg, "-nostdin", "-hide_banner", "-loglevel", "error", "-y",
         "-i", str(source), "-map", "0:a:0", "-vn", "-sn", "-dn", *mono,
         "-c:a", "libopus", "-b:a", "48k", "-application", "voip",
         str(out)],
        capture_output=True, text=True,
    )
    if result.returncode != 0 or not out.is_file() or out.stat().st_size == 0:
        detail = (result.stderr or "").strip().splitlines()[-3:]
        hint = ("  The file may have no audio track."
                if "matches no streams" in (result.stderr or "") else "")
        die(f"ERROR: ffmpeg could not read the audio in {source.name}.\n"
            + "".join(f"  {d}\n" for d in detail) + hint)
    return out


def media_duration(source: Path) -> float | None:
    """Length in seconds from ffprobe, or None if it cannot tell."""
    ffprobe = find_tool("ffprobe")
    if not ffprobe:
        return None
    result = subprocess.run(
        [ffprobe, "-v", "error", "-show_entries", "format=duration",
         "-of", "default=noprint_wrappers=1:nokey=1", str(source)],
        capture_output=True, text=True,
    )
    try:
        return float(result.stdout.strip())
    except ValueError:
        return None


def fmt_length(seconds: float) -> str:
    """'1 h 52 min', '14 min', '45 s', rounded to the nearest minute from 1 min."""
    if seconds < 59.5:
        return f"{int(round(seconds))} s"
    h, m = divmod(int(round(seconds / 60)), 60)
    if h:
        return f"{h} h {m} min"
    return f"{m} min"


# Names for the settings line; any other code is shown as it is.
LANGUAGE_NAMES = {
    "multi": "a mix of languages", "en": "English", "en-US": "English (US)",
    "en-GB": "English (UK)", "de": "German", "es": "Spanish",
    "es-419": "Spanish (Latin America)", "fr": "French", "fr-CA": "French (Canada)",
    "it": "Italian", "pt": "Portuguese", "pt-BR": "Portuguese (Brazil)",
    "nl": "Dutch", "ru": "Russian", "uk": "Ukrainian", "pl": "Polish",
    "tr": "Turkish", "ja": "Japanese", "ko": "Korean", "zh": "Chinese",
    "zh-TW": "Chinese (Taiwan)", "hi": "Hindi", "sv": "Swedish", "da": "Danish",
    "no": "Norwegian", "fi": "Finnish", "id": "Indonesian", "vi": "Vietnamese",
    "th": "Thai",
}


def language_name(code: str) -> str:
    return LANGUAGE_NAMES.get(code, f"language {code}")


def settings_line(*, language: str, call_mode: bool, diarize: bool,
                  keyterms: list[str], mip_opt_out: bool,
                  labels: list[str] = ()) -> str:
    """The run's settings in plain words, said before anything is paid for.

    labels: call_labels() on a call, the transcript's own labels.
    """
    parts = [language_name(language)]
    if call_mode:
        me = labels[0] if labels else "Me"
        if diarize:
            parts.append(f"your voice on its own channel, labelled {me}")
            parts.append("the others split by voice as Speaker 1, 2, ...")
        else:
            far = labels[1] if len(labels) > 1 else "Speaker 1"
            parts.append(f"you and the other person on separate channels, "
                         f"labelled {me} and {far}")
            parts.append("nobody guessed by voice")
    else:
        parts.append("speaker labels " + ("on" if diarize else "off"))
    parts.append(f"{len(keyterms)} keyterms" if keyterms else "no keyterms")
    parts.append("privacy mode on" if mip_opt_out else "PRIVACY MODE OFF")
    return "Settings: " + ", ".join(parts)


def make_room(paths: list[Path]) -> list[Path]:
    """Move existing outputs to the macOS Trash so nothing is overwritten.

    If trash fails, keep the old files and return timestamped new names instead.
    """
    old = [p for p in paths if p.exists()]
    if not old:
        return paths
    try:
        subprocess.run(["trash", *map(str, old)], check=True,
                       capture_output=True, text=True)
    except (OSError, subprocess.CalledProcessError) as e:
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        print(f"WARNING: could not move old outputs to the Trash ({e}); "
              f"writing new ones with .{stamp} in the name.", file=sys.stderr)
        return [p.with_name(p.name.replace(".", f".{stamp}.", 1)) for p in paths]
    for p in old:
        print(f"Moved previous {p.name} to the Trash.", file=sys.stderr)
    return paths


def fmt_ts(seconds: float | None) -> str:
    """Format seconds as MM:SS or H:MM:SS."""
    if seconds is None:
        return "?:??"
    total = int(round(seconds))
    h, rem = divmod(total, 3600)
    m, s = divmod(rem, 60)
    if h:
        return f"{h}:{m:02d}:{s:02d}"
    return f"{m:02d}:{s:02d}"


def split_list(text: str | None) -> list[str]:
    return [t.strip() for t in (text or "").split(",") if t.strip()]


def speaker_label(index, names: list[str]) -> str:
    """'Speaker 0', or the matching name from --speakers."""
    if index is None:
        return "Speaker ?"
    if 0 <= index < len(names):
        return names[index]
    return f"Speaker {index}"


# --- Transcript rendering -------------------------------------------------

def build_transcript_text(response, *, source: Path, language: str,
                          diarize: bool, keyterms: list[str],
                          mip_opt_out: bool, speaker_names: list[str],
                          model: str) -> str:
    results = getattr(response, "results", None)
    metadata = getattr(response, "metadata", None)
    utterances = list(getattr(results, "utterances", None) or [])

    privacy = ("MIP opt-out ON (audio not used for training)"
               if mip_opt_out else
               "MIP opt-out OFF, THIS FILE MAY BE USED TO TRAIN DEEPGRAM MODELS")
    duration = getattr(metadata, "duration", None) if metadata else None
    request_id = getattr(metadata, "request_id", None) if metadata else None

    lines: list[str] = []
    lines.append(f"Transcript: {source.name}")
    lines.append(f"Source:     {source}")
    lines.append(f"Date:       {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    lines.append(f"Engine:     Deepgram {model} (cloud)")
    lines.append(f"Language:   {language}")
    lines.append(f"Diarization:{'on' if diarize else 'off'}")
    lines.append(f"Keyterms:   {', '.join(keyterms) if keyterms else '(none)'}")
    lines.append(f"Privacy:    {privacy}")
    meta_bits = []
    if duration is not None:
        meta_bits.append(f"duration {fmt_ts(duration)}")
    if request_id:
        meta_bits.append(f"request_id {request_id}")
    if meta_bits:
        lines.append(f"Meta:       {'   '.join(meta_bits)}")
    lines.append("-" * 60)
    lines.append("")

    if utterances:
        if diarize:
            # Merge consecutive utterances by the same speaker into one block.
            blocks: list[dict] = []
            for u in utterances:
                text = (getattr(u, "transcript", "") or "").strip()
                if not text:
                    continue
                spk = getattr(u, "speaker", None)
                spk = int(spk) if spk is not None else None
                if blocks and blocks[-1]["speaker"] == spk:
                    blocks[-1]["end"] = getattr(u, "end", blocks[-1]["end"])
                    blocks[-1]["text"] += " " + text
                else:
                    blocks.append({"speaker": spk, "start": getattr(u, "start", None),
                                   "end": getattr(u, "end", None), "text": text})
            for b in blocks:
                label = speaker_label(b["speaker"], speaker_names)
                lines.append(f"{label}  [{fmt_ts(b['start'])}–{fmt_ts(b['end'])}]")
                lines.append(f"  {b['text']}")
                lines.append("")
        else:
            # One timestamped paragraph per utterance.
            for u in utterances:
                text = (getattr(u, "transcript", "") or "").strip()
                if not text:
                    continue
                lines.append(f"[{fmt_ts(getattr(u, 'start', None))}] {text}")
                lines.append("")
    else:
        # Fallback: no utterances in the response, use the flat transcript.
        transcript = ""
        try:
            transcript = (response.results.channels[0].alternatives[0].transcript
                          or "").strip()
        except Exception:
            pass
        lines.append(transcript or "(empty transcript)")
        lines.append("")

    return "\n".join(lines).rstrip() + "\n"


def response_to_json(response) -> dict:
    """Serialize the SDK response (pydantic v2) to a plain dict for saving."""
    if hasattr(response, "model_dump"):
        return response.model_dump(mode="json")
    if hasattr(response, "dict"):
        return response.dict()
    return json.loads(response.json())  # last resort
