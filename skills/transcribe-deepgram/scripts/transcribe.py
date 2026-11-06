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

Calls: a stereo recording whose left channel is the user's mic and right
channel everyone else, as Nistka records them into ~/Documents/Nistka. A
two-channel file in that folder is a call by default; --call makes any stereo
file one, --no-call turns it off. Both channels are checked
locally for sound, then go up unmixed with multichannel=true, so the speaker
comes from the channel, not from guessing. Multichannel is billed per
channel: about 2x. If one channel is silent, the other is transcribed alone
as an ordinary recording. --check prints the settings, the length and the
price, and uploads nothing.

The key comes from the DEEPGRAM_API_KEY environment variable, else from a
.env file next to this script, else from .env at the top of the install
folder, three levels up (install.sh writes it there).

Outputs, written next to the input file, or as --output "<dir>/<stem>":
  <name>.transcript.txt   readable text, with speaker labels and timestamps
  <name>.response.json    the raw Deepgram JSON response

The rest of the code sits next to this file: transcribe_helpers.py (small
helpers and the ordinary transcript), transcribe_call.py (the call parts of a
run) and call_lines.py (a call's transcript lines).
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
from pathlib import Path

from transcribe_call import (CALL_CHANNELS, audio_channels, build_call_transcript,
                             call_labels, channel_levels, encode_call_audio,
                             in_nistka_folder, leaked, levels_text, repeat_text,
                             resolve_diarize, silent_channels, with_names)
from transcribe_helpers import (build_transcript_text, die, extract_audio,
                                fmt_length, make_room, media_duration,
                                response_to_json, settings_line, split_list)

# --- Configuration --------------------------------------------------------

DEFAULT_MODEL = "nova-3"
MEDICAL_MODEL = "nova-3-medical"
_HERE = Path(__file__).resolve().parent  # <install>/skills/transcribe-deepgram/scripts
ENV_FILES = [_HERE / ".env"] + [p / ".env" for p in _HERE.parents[2:3]]

# Audio Deepgram takes as is. Anything else (video, other audio formats) and
# anything bigger than EXTRACT_ABOVE_MB is converted locally with ffmpeg.
# A call in one of these formats always goes up as it is, whatever its size:
# re-encoding would cost quality and gain nothing but upload time.
DIRECT_AUDIO = {".wav", ".mp3", ".m4a", ".ogg", ".opus", ".flac", ".aac"}
EXTRACT_ABOVE_MB = 100
MAX_UPLOAD_MB = 2048  # Deepgram's upload limit as third-party pages give it

# Pay as you go prices per minute, from deepgram.com/pricing on 2026-10-26.
# Speaker labels and smart formatting are included; keyterms are an add-on.
PRICE_PER_MIN = {"multi": 0.0052, "other": 0.0043, "keyterms": 0.0013}

OUTPUT_SUFFIXES = (".transcript.txt", ".response.json")

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


def estimate_cost(seconds: float, *, model: str, language: str,
                  keyterms: list[str], channels: int = 1) -> float | None:
    """Pay as you go estimate in dollars, or None for models not priced here.

    Multichannel audio is billed per channel.
    """
    if model != DEFAULT_MODEL:
        return None
    rate = PRICE_PER_MIN["multi" if language == "multi" else "other"]
    if keyterms:
        rate += PRICE_PER_MIN["keyterms"]
    return seconds / 60 * rate * channels


def output_stem(arg: str | None, source: Path) -> Path:
    """Where the outputs go: <stem>.transcript.txt and <stem>.response.json.

    Default: next to the input, named after it. --output "<dir>/<stem>"
    puts them elsewhere; the folder must exist.
    """
    if not arg:
        return source.with_name(source.stem)
    out = Path(arg).expanduser()
    if not out.name or out.name.endswith(OUTPUT_SUFFIXES):
        die(f"ERROR: --output takes a folder and a name without an ending, like "
            f"\"~/Desktop/call\", not {arg}")
    if not out.parent.is_dir():
        die(f"ERROR: --output points into a folder that does not exist: {out.parent}")
    return out


def with_suffix(stem: Path, suffix: str) -> Path:
    """stem + suffix, keeping any dots already in the stem's name."""
    return stem.parent / (stem.name + suffix)


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
    p.add_argument("--diarize", dest="diarize", default=None,
                   action=argparse.BooleanOptionalAction,
                   help="Label speakers (default: on). Use --no-diarize to disable. "
                        "On a call it applies to the others only, and is off "
                        "unless --speakers names two or more people.")
    p.add_argument("--keyterms", dest="keyterms", default=None,
                   help='Words to recognise better, comma separated: '
                        '--keyterms "Name One,Product,Term". '
                        "With --medical they are added to the medical set.")
    p.add_argument("--no-keyterms", dest="no_keyterms", action="store_true",
                   help="Send no keyterms at all, not even the medical set.")
    p.add_argument("--speakers", dest="speakers", default=None,
                   help='Speaker names in the order they first speak, e.g. '
                        '"Host,Guest". Maps to Speaker 0, Speaker 1, ... '
                        "On a call: the other people only, never you. One name "
                        "labels the others' channel; two or more split it by "
                        "voice as Speaker 1, 2, ... Either way the names are "
                        "added to the keyterms.")
    p.add_argument("--me", dest="me", default=None,
                   help='On a call: your label (default "Me"), also added to '
                        "the keyterms.")
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
    p.add_argument("--call", dest="call", default=None,
                   action=argparse.BooleanOptionalAction,
                   help="A call: left channel you, right channel the others, "
                        "transcribed as two channels (about 2x the price). On by "
                        "default for a two-channel file in ~/Documents/Nistka; "
                        "--call for any other stereo file, "
                        "--no-call to transcribe it the ordinary way.")
    p.add_argument("--output", dest="output", default=None, metavar="DIR/NAME",
                   help="Write NAME.transcript.txt and NAME.response.json into "
                        "DIR instead of next to the input. The transcript header "
                        "names NAME.")
    p.add_argument("--check", dest="check", action="store_true",
                   help="Free: print the settings, the length and the price (and "
                        "on a call the channel check), then stop. Uploads "
                        "nothing, writes nothing, needs no key.")
    p.add_argument("--keep-all-lines", dest="keep_all_lines", action="store_true",
                   help="On a call: keep short lines in an unexpected language "
                        "or script, and pure fillers, which are dropped by "
                        "default.")
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

    # 1) Input file checks, and where the outputs go.
    source = Path(args.media).expanduser()
    if not source.exists():
        die(f"ERROR: file not found: {source}")
    if not source.is_file():
        die(f"ERROR: not a file: {source}")
    stem = output_stem(args.output, source)
    shown = stem if args.output else source  # what the transcript header names

    # 2) A call? Two channels in the Nistka folder, or --call.
    call_mode = False
    if args.call or (args.call is None and in_nistka_folder(source)):
        channels = audio_channels(source)
        if args.call and channels != CALL_CHANNELS:
            die(f"ERROR: --call needs a two-channel recording; {source.name} has "
                f"{channels or 'no readable'} audio channel(s).\n"
                "  Leave out --call to transcribe it the ordinary way.")
        call_mode = channels == CALL_CHANNELS

    # 3) On a call, both channels are checked locally, before anything else.
    only_channel = None  # set when one channel is silent: transcribe the other
    details: list[str] = []
    if call_mode:
        print(f"Checking both channels of {source.name} locally ...", file=sys.stderr)
        levels = channel_levels(source)
        if not levels:
            die(f"ERROR: could not read the sound in {source.name}.\n"
                "  The file may be empty or damaged (a recording that failed to "
                "start leaves a tiny file like that).")
        details = levels_text(levels)
        silent = silent_channels(levels)
        if len(silent) >= CALL_CHANNELS:
            die(f"ERROR: both channels of {source.name} are silent: there is "
                "nothing to transcribe.")
        if silent == [1]:
            only_channel = 0
            print("Note: the others' channel (right) is silent: nothing played "
                  "through the computer, so everyone in the call, if anyone, is "
                  "on your mic. Transcribing your mic channel alone, with "
                  "speakers told apart by voice (half the price of a call).",
                  file=sys.stderr)
        elif silent == [0]:
            only_channel = 1
            print("WARNING: your mic channel (left) is silent. The recording app "
                  "may have had no microphone access. Transcribing the others' "
                  "channel alone, with speakers told apart by voice.",
                  file=sys.stderr)
        else:
            print("Both channels have sound: your mic on the left, the others on "
                  "the right.", file=sys.stderr)
        if not args.no_keyterms:
            keyterms = with_names(keyterms, ([args.me] if args.me else []) + speaker_names)
        if only_channel is not None:
            call_mode = False
            if speaker_names:
                print("  The names you gave help as keyterms only; the "
                      "transcript says Speaker 0, Speaker 1, ...", file=sys.stderr)
            speaker_names = []
    preview = args.check  # nothing is uploaded or paid for

    # 4) API key, before any slow upload work. A check needs none.
    api_key = None if preview else read_api_key()

    # 5) Loud warning if privacy mode is off.
    if args.allow_training and not preview:
        banner = "!" * 60
        print(banner, file=sys.stderr)
        print("!! WARNING: privacy mode is OFF (--allow-training).", file=sys.stderr)
        print(f"!! '{source.name}' MAY BE KEPT AND USED TO TRAIN", file=sys.stderr)
        print("!! DEEPGRAM MODELS. Do NOT use this for private audio.", file=sys.stderr)
        print(banner, file=sys.stderr)

    diarize = resolve_diarize(args.diarize, call_mode=call_mode,
                              speaker_names=speaker_names)

    opts: dict = dict(
        model=model,
        language=language,
        smart_format=True,
        punctuate=True,
        utterances=True,
        utt_split=0.8,
        diarize=diarize,
        mip_opt_out=mip_opt_out,
    )
    if call_mode:
        opts["multichannel"] = True  # billed per channel: about 2x
    if keyterms:
        opts["keyterm"] = keyterms  # the SDK accepts a list of strings

    # 6) Settings, length and price, said before any upload.
    labels = call_labels(args.me, speaker_names) if call_mode else []
    print(settings_line(language=language, call_mode=call_mode, diarize=diarize,
                        keyterms=keyterms, mip_opt_out=mip_opt_out, labels=labels),
          file=sys.stderr)
    duration = media_duration(source)
    if duration:
        cost = estimate_cost(duration, model=model, language=language,
                             keyterms=keyterms,
                             channels=CALL_CHANNELS if call_mode else 1)
        price = ("" if cost is None else
                 ", under $0.01" if cost < 0.01 else f", about ${cost:.2f}")
        price += " at pay as you go prices" if price else ""
        if call_mode:
            price = (f", two channels billed separately{price}"
                     " (about 2x a normal run, keyterms included)")
        print(f"Length: {fmt_length(duration)}{price}", file=sys.stderr)
    if preview:
        print("Nothing was uploaded or charged.", file=sys.stderr)
        return 0

    from deepgram import DeepgramClient
    from deepgram.core.api_error import ApiError

    with tempfile.TemporaryDirectory(prefix="mashinista-") as tmp:
        # 7) What goes up. A call: the file as it is when Deepgram takes the
        #    format, else both channels as lossless FLAC; never mixed. One
        #    silent channel: the other alone. Otherwise video, unusual formats
        #    and big audio: a local mono extract.
        size_mb = source.stat().st_size / (1024 * 1024)
        direct = source.suffix.lower() in DIRECT_AUDIO
        upload = source
        if call_mode:
            if not direct:
                upload = encode_call_audio(source, Path(tmp))
        elif only_channel is not None:
            upload = extract_audio(source, Path(tmp), channel=only_channel)
        elif not direct or size_mb > EXTRACT_ABOVE_MB:
            upload = extract_audio(source, Path(tmp))
        upload_mb = upload.stat().st_size / (1024 * 1024)
        if upload_mb > MAX_UPLOAD_MB:
            die(f"ERROR: the sound to upload is {upload_mb / 1024:.1f} GB, over "
                "Deepgram's 2 GB limit.\n"
                "  Split the recording into shorter parts and transcribe each one.")
        audio_bytes = upload.read_bytes()

        print(f"Transcribing {source.name}: uploading {upload_mb:.1f} MB to "
              f"Deepgram ({model}) ...", file=sys.stderr)

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

    # 8) Write the outputs.
    json_path, txt_path = make_room([with_suffix(stem, s) for s in
                                     (".response.json", ".transcript.txt")])
    data = response_to_json(response)
    json_path.write_text(json.dumps(data, ensure_ascii=False, indent=2),
                         encoding="utf-8")
    counts = None
    if call_mode:
        text, counts = build_call_transcript(
            data, source=shown, language=language, far_diarized=diarize,
            keyterms=keyterms, mip_opt_out=mip_opt_out,
            speaker_names=labels, model=model, details=details,
            keep_all_lines=args.keep_all_lines)
    else:
        text = build_transcript_text(
            response, source=shown, language=language, diarize=diarize,
            keyterms=keyterms, mip_opt_out=mip_opt_out,
            speaker_names=speaker_names, model=model)
    txt_path.write_text(text, encoding="utf-8")

    # 9) Confirmations.
    print(f"\nSaved transcript → {txt_path}", file=sys.stderr)
    print(f"Saved raw JSON   → {json_path}", file=sys.stderr)
    if counts is not None:
        if not args.keep_all_lines:
            detail = ", ".join(f"{v} {k}" for k, v in sorted(counts["dropped_detail"].items()))
            print(f"Cleanup: dropped {counts['dropped']} short lines"
                  + (f" ({detail})" if detail else ""), file=sys.stderr)
        rep_n, total = counts["repeated"], counts["me_lines"]
        line = repeat_text(rep_n, total)
        if leaked(rep_n, total):
            print(f"WARNING: {line}. The others' voices probably reached your "
                  "mic; check the transcript before trusting the labels.",
                  file=sys.stderr)
        else:
            print(f"Repeats: {line}.", file=sys.stderr)
    if mip_opt_out:
        print("Privacy: MIP opt-out ON (audio not used for training).", file=sys.stderr)
    else:
        print("Privacy: MIP opt-out OFF, this file MAY be used to train Deepgram models.",
              file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
