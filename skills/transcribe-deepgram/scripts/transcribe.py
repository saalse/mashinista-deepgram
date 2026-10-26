#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.10"
# dependencies = ["deepgram-sdk==5.3.4"]
# ///
"""
transcribe.py: private cloud transcription with Deepgram nova-3.

Run it from any folder:

  uv run ~/.claude/skills/transcribe-deepgram/scripts/transcribe.py ~/Movies/lecture.mp4

uv installs the one dependency on the first run. The script uploads the audio
to Deepgram, which transcribes it and, in privacy mode (mip_opt_out=true, the
default), does not use it to train its models. --allow-training turns privacy
mode off for that one run, for non-sensitive audio, and warns loudly first.

Video, and audio over EXTRACT_ABOVE_MB, goes through ffmpeg first: a mono
speech track (48 kbps Opus, about 22 MB per hour) is cut out locally and only
that is uploaded. The picture never leaves the Mac, so the video's own size
does not matter; 2 GB of extracted sound would be about 90 hours.

The key comes from the DEEPGRAM_API_KEY environment variable, else from a
.env file next to this script, else from .env at the top of the install
folder, three levels up (install.sh writes it there).

Outputs, written next to the input file:
  <name>.transcript.txt   readable text, with speaker labels and timestamps
  <name>.response.json    the raw Deepgram JSON response
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
from datetime import datetime
from pathlib import Path

# --- Configuration --------------------------------------------------------

DEFAULT_MODEL = "nova-3"
MEDICAL_MODEL = "nova-3-medical"
_HERE = Path(__file__).resolve().parent  # <install>/skills/transcribe-deepgram/scripts
ENV_FILES = [_HERE / ".env"] + [p / ".env" for p in _HERE.parents[2:3]]

# Audio Deepgram takes as is. Anything else (video, other audio formats) and
# anything bigger than EXTRACT_ABOVE_MB is converted locally with ffmpeg.
DIRECT_AUDIO = {".wav", ".mp3", ".m4a", ".ogg", ".opus", ".flac", ".aac"}
EXTRACT_ABOVE_MB = 100
MAX_UPLOAD_MB = 2048  # Deepgram's upload limit as third-party pages give it

# Pay as you go prices per minute, from deepgram.com/pricing on 2026-10-26.
# Speaker labels and smart formatting are included; keyterms are an add-on.
PRICE_PER_MIN = {"multi": 0.0052, "other": 0.0043, "keyterms": 0.0013}

# General medical vocabulary for --medical (Nova-3 keyterm prompting).
MEDICAL_KEYTERMS = [
    "diagnosis", "prognosis", "prescription", "medication", "dosage",
    "ultrasound", "MRI", "CT scan", "X-ray", "biopsy", "pathology",
    "blood test", "CBC", "hemoglobin", "cholesterol", "glucose",
    "blood pressure", "TSH", "vitamin D", "antibiotic", "anesthesia",
    "dermatology", "cardiology", "endocrinology", "gastroenterology",
    "gynecology", "neurology", "oncology", "orthopedics", "pediatrics",
    "milligrams", "milliliters", "IU", "mmHg",
]


# --- Small helpers --------------------------------------------------------

def die(msg: str, code: int = 1) -> "None":
    print(msg, file=sys.stderr)
    raise SystemExit(code)


def read_api_key() -> str:
    """DEEPGRAM_API_KEY from the environment, else from the first ENV_FILES hit."""
    key = os.environ.get("DEEPGRAM_API_KEY", "").strip()
    if key:
        return key
    for env_file in ENV_FILES:
        if not env_file.is_file():
            continue
        for line in env_file.read_text(encoding="utf-8").splitlines():
            name, sep, value = line.strip().partition("=")
            if sep and name.strip().removeprefix("export ").strip() == "DEEPGRAM_API_KEY":
                key = value.strip().strip("'\"")
                if key:
                    return key
    die("ERROR: no Deepgram API key found.\n"
        f"  Rerun install.sh, or put DEEPGRAM_API_KEY=<your key> in {ENV_FILES[-1]}\n"
        "  Get a key at https://console.deepgram.com (API Keys).")


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


def extract_audio(source: Path, workdir: Path) -> Path:
    """Cut the first audio track out as mono Opus, locally, for upload."""
    ffmpeg = find_tool("ffmpeg")
    if not ffmpeg:
        die("ERROR: ffmpeg is not installed, and this file needs it.\n"
            "  Rerun install.sh, or run: brew install ffmpeg")
    out = workdir / (source.stem + ".ogg")
    print(f"Extracting a mono audio track locally from {source.name} ...",
          file=sys.stderr)
    result = subprocess.run(
        [ffmpeg, "-nostdin", "-hide_banner", "-loglevel", "error", "-y",
         "-i", str(source), "-map", "0:a:0", "-vn", "-sn", "-dn",
         "-ac", "1", "-c:a", "libopus", "-b:a", "48k", "-application", "voip",
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
    """'1 h 52 min', '14 min', '45 s'."""
    total = int(round(seconds))
    h, rem = divmod(total, 3600)
    m, s = divmod(rem, 60)
    if h:
        return f"{h} h {m} min"
    if m:
        return f"{m} min"
    return f"{s} s"


def estimate_cost(seconds: float, *, model: str, language: str,
                  keyterms: list[str]) -> float | None:
    """Pay as you go estimate in dollars, or None for models not priced here."""
    if model != DEFAULT_MODEL:
        return None
    rate = PRICE_PER_MIN["multi" if language == "multi" else "other"]
    if keyterms:
        rate += PRICE_PER_MIN["keyterms"]
    return seconds / 60 * rate


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


# --- Main -----------------------------------------------------------------

def parse_args(argv=None):
    p = argparse.ArgumentParser(
        prog="transcribe.py",
        description="Private cloud transcription with Deepgram nova-3.",
    )
    p.add_argument("media", help="Path to a local audio or video file.")
    p.add_argument("--lang", dest="lang", default=None,
                   help="Language code: multi (mixed languages, default), "
                        "en, de, es, ... With --medical the default is en.")
    p.add_argument("--diarize", dest="diarize", default=True,
                   action=argparse.BooleanOptionalAction,
                   help="Label speakers (default: on). Use --no-diarize to disable.")
    p.add_argument("--keyterms", dest="keyterms", default=None,
                   help='Words to recognise better, comma separated: '
                        '--keyterms "Name One,Product,Term". '
                        "With --medical they are added to the medical set.")
    p.add_argument("--no-keyterms", dest="no_keyterms", action="store_true",
                   help="Send no keyterms at all, not even the medical set.")
    p.add_argument("--speakers", dest="speakers", default=None,
                   help='Speaker names in the order they first speak, e.g. '
                        '"Host,Guest". Maps to Speaker 0, Speaker 1, ...')
    p.add_argument("--medical", dest="medical", action="store_true",
                   help=f"Healthcare audio: model {MEDICAL_MODEL}, the medical "
                        "keyterm set, and English unless --lang is given "
                        "(the medical model also takes --lang multi).")
    p.add_argument("--model", dest="model", default=None,
                   help=f"Deepgram model name (default: {DEFAULT_MODEL}).")
    p.add_argument("--allow-training", dest="allow_training", action="store_true",
                   help="Turn privacy mode OFF for this run: Deepgram may keep "
                        "the audio and use it to train its models "
                        "(mip_opt_out=false). Only for non-sensitive audio.")
    p.add_argument("--timeout", dest="timeout", type=int, default=1200,
                   help="Request timeout in seconds (default 1200 = 20 min).")
    return p.parse_args(argv)


def main(argv=None) -> int:
    args = parse_args(argv)

    # 0) --medical sets defaults; an explicit --model or --lang still wins.
    model = args.model or (MEDICAL_MODEL if args.medical else DEFAULT_MODEL)
    language = args.lang or ("en" if args.medical else "multi")
    if args.no_keyterms:
        keyterms = []
    else:
        keyterms = (list(MEDICAL_KEYTERMS) if args.medical else []) + split_list(args.keyterms)
    speaker_names = split_list(args.speakers)
    mip_opt_out = not args.allow_training  # privacy mode is the default

    # 1) Input file checks.
    source = Path(args.media).expanduser()
    if not source.exists():
        die(f"ERROR: file not found: {source}")
    if not source.is_file():
        die(f"ERROR: not a file: {source}")

    # 2) API key, before any slow local work.
    api_key = read_api_key()

    # 3) Loud warning if privacy mode is off.
    if args.allow_training:
        banner = "!" * 60
        print(banner, file=sys.stderr)
        print("!! WARNING: privacy mode is OFF (--allow-training).", file=sys.stderr)
        print(f"!! '{source.name}' MAY BE KEPT AND USED TO TRAIN", file=sys.stderr)
        print("!! DEEPGRAM MODELS. Do NOT use this for private audio.", file=sys.stderr)
        print(banner, file=sys.stderr)

    from deepgram import DeepgramClient
    from deepgram.core.api_error import ApiError

    opts: dict = dict(
        model=model,
        language=language,
        smart_format=True,
        punctuate=True,
        utterances=True,
        utt_split=0.8,
        diarize=args.diarize,
        mip_opt_out=mip_opt_out,
    )
    if keyterms:
        opts["keyterm"] = keyterms  # the SDK accepts a list of strings

    # 4) Length and price, said before any upload.
    duration = media_duration(source)
    if duration:
        cost = estimate_cost(duration, model=model, language=language,
                             keyterms=keyterms)
        price = ("" if cost is None else
                 ", under $0.01" if cost < 0.01 else f", about ${cost:.2f}")
        price += " at pay as you go prices" if price else ""
        print(f"Length: {fmt_length(duration)}{price}", file=sys.stderr)

    with tempfile.TemporaryDirectory(prefix="mashinista-") as tmp:
        # 5) Video, unusual formats and big audio: upload a local mono extract.
        size_mb = source.stat().st_size / (1024 * 1024)
        upload = source
        if source.suffix.lower() not in DIRECT_AUDIO or size_mb > EXTRACT_ABOVE_MB:
            upload = extract_audio(source, Path(tmp))
        upload_mb = upload.stat().st_size / (1024 * 1024)
        if upload_mb > MAX_UPLOAD_MB:
            die(f"ERROR: the sound to upload is {upload_mb / 1024:.1f} GB, over "
                "Deepgram's 2 GB limit.\n"
                "  Split the recording into shorter parts and transcribe each one.")
        audio_bytes = upload.read_bytes()

        print(f"Transcribing: {source.name}  (uploading "
              f"{upload_mb:.1f} MB)  lang={language} "
              f"diarize={'on' if args.diarize else 'off'} model={model}",
              file=sys.stderr)

        client = DeepgramClient(api_key=api_key)
        try:
            response = client.listen.v1.media.transcribe_file(
                request=audio_bytes,
                request_options={"timeout_in_seconds": args.timeout, "max_retries": 2},
                **opts,
            )
        except ApiError as e:
            detail = getattr(e, "body", None)
            die(f"ERROR: Deepgram API error (status {getattr(e, 'status_code', '?')}).\n"
                f"  Details: {detail}\n"
                f"  If status is 401 or 403, the API key is missing or invalid.\n"
                f"  If 400, an option may be unsupported for language '{language}'.")
        except Exception as e:  # network, timeout, etc.
            die(f"ERROR: transcription failed: {type(e).__name__}: {e}")

    # 6) Write outputs next to the input file.
    json_path, txt_path = make_room([
        source.with_name(source.stem + ".response.json"),
        source.with_name(source.stem + ".transcript.txt"),
    ])
    json_path.write_text(
        json.dumps(response_to_json(response), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    txt_path.write_text(
        build_transcript_text(response, source=source, language=language,
                              diarize=args.diarize, keyterms=keyterms,
                              mip_opt_out=mip_opt_out, speaker_names=speaker_names,
                              model=model),
        encoding="utf-8",
    )

    # 7) Confirmations.
    print(f"\nSaved transcript → {txt_path}", file=sys.stderr)
    print(f"Saved raw JSON   → {json_path}", file=sys.stderr)
    if mip_opt_out:
        print("Privacy: MIP opt-out ON (audio not used for training).", file=sys.stderr)
    else:
        print("Privacy: MIP opt-out OFF, this file MAY be used to train Deepgram models.",
              file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
