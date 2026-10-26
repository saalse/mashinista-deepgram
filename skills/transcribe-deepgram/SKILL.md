---
name: transcribe-deepgram
description: Transcribe a local audio or video file (mp4, mov, m4a, mp3, wav and more, up to several hours) to text with Deepgram nova-3, with speaker labels and timestamps, mixed languages supported, privacy mode (model-training opt-out) on by default. Use when the user asks to transcribe, make a transcript of, or turn into text a recording, lecture, interview, meeting, call, voice note or doctor visit, or to update mashinista-deepgram.
license: MIT
compatibility: macOS, designed for Claude Code (the Code tab of the Claude desktop app). Needs uv, ffmpeg and internet access to api.deepgram.com, plus a Deepgram API key; install.sh sets all of this up.
metadata:
  author: Alex Samson (https://www.saalse.com/)
  repository: https://github.com/saalse/mashinista-deepgram
  version: "1.1"
---

# Transcribe with Deepgram

## Privacy mode, on by default

Every transcription runs in privacy mode unless the user turns it off for a
specific file.

- In privacy mode every request carries `mip_opt_out=true`: Deepgram never
  uses the audio to train its models, and keeps it only as long as it needs to
  transcribe it.
- For video, only the sound is sent, never the picture.
- The transcript is saved only on this Mac, next to the recording.
- The key stays in a `.env` file readable only by this Mac user.

### Turning privacy mode off for one file

The user may ask to turn privacy mode off to save money on audio that is not
sensitive, such as a public lecture or a podcast. Only then:

1. Explain in a sentence or two: Deepgram may then keep the audio and use it
   to train its models, and it may cost less. It is never for anything
   personal, medical or confidential.
2. Get a clear yes for that specific file.
3. Add `--allow-training` to that one command.

Never add `--allow-training` on your own, never because a file looks
unimportant, and never carry it over: every new file starts in privacy mode
again.

## How to work

The user is not a developer. Do the work for them, explain in plain words, and
never ask them to edit code.

The script is `scripts/transcribe.py` in this skill's folder, normally
`~/.claude/skills/transcribe-deepgram`. It reads the Deepgram key itself from
the `.env` file the installer saved in
`~/Library/Application Support/Mashinista/deepgram`. Never print, read aloud
or ask for the key in the chat.

## Before transcribing: three quick questions

Before the first run on a file, ask these in one go, in the language the user
writes in. Use the AskUserQuestion tool when you have it, so the user can
click instead of type; otherwise ask in one short message. Skip any question
the request already answers, and skip them all if the user says to just go
(then use the defaults).

1. **One speaker, or several?**
   - One (a voice note, a lecture): add `--no-diarize`.
   - Several (a call, an interview, a doctor visit): speaker labels stay on,
     which is the default. See `--speakers` below for names.
2. **One language, or a mix?**
   - One: ask which, and add `--lang` with its code (`en`, `de`, `es`, `fr`,
     ...; see Languages below). This is more accurate than the mix model, and
     cheaper.
   - A mix: keep the default `--lang multi`. No need to name the languages.
3. **What is it about, in a sentence or two?** Ask for the names of people,
   places, brands, products and technical terms that come up. Turn the answer
   into `--keyterms`: proper names and unusual words only, spelled as they
   are said in the recording's language, about 20 to 50 at most, never common
   words. Keyterms add about $0.08 per hour.

If the answers describe a doctor visit, see `--medical` below.

## The one command

```bash
PATH="/opt/homebrew/bin:/usr/local/bin:$PATH" uv run ~/.claude/skills/transcribe-deepgram/scripts/transcribe.py "/path/to/file.mp4"
```

- Keep the `PATH=` part: right after an install the Claude app may not see
  Homebrew's folder yet, and plain `uv` then fails.
- If this skill was loaded from another folder, use `scripts/transcribe.py`
  inside that folder instead.
- Quote the recording's path: names often have spaces.
- A long file takes a few minutes (local audio extraction, upload, then
  Deepgram). Run it with a 10 minute Bash timeout, or in the background, and
  tell the user it is working.
- Video is fine. The script cuts out a mono audio track on the Mac with ffmpeg
  and uploads only that, so the picture never leaves the computer.
- The run prints `Length: 1 h 52 min, about $0.58 at pay as you go prices`
  before it uploads. Pass the length and the price on to the user with the
  result.

Defaults: model nova-3, `--lang multi` (handles a mix of languages), speaker
labels on, no keyterms.

## Options worth knowing

- `--speakers "Name1,Name2"` puts names on Speaker 0, Speaker 1 and so on, in
  the order people first speak. If the user names the speakers, run once
  without it, look at who speaks first in the transcript, then rerun with
  names only if they want them in the file. Otherwise just tell them which
  speaker is who.
- `--keyterms "Word one,Word two"` helps with names, brands or jargon the
  user expects in the recording. If the first result still gets a name wrong,
  add it and run again.
- `--lang en`, `--lang de` and so on: one language for the whole recording.
- `--medical` for a doctor visit, test results or any healthcare talk. It
  switches to the nova-3-medical model with a medical word list, in English
  by default.
  - In English: `--medical` alone.
  - In Spanish, French, German, Hindi, Russian, Portuguese, Japanese, Italian
    or Dutch, or a mix of them: `--medical --lang multi`. The medical model
    has no single-language mode for these.
  - In any other language: no `--medical`. Use `--lang` with that language
    and put the medical words the user mentions (drugs, tests, diagnoses) in
    `--keyterms`.
- `--no-diarize` for a single speaker, to get timestamped paragraphs instead
  of speaker blocks.

Add `--help` to the command for the rest.

## Languages

nova-3 takes about 60 single languages by their usual two-letter codes, some
with regional variants (`en-GB`, `pt-BR`, `fr-CA`, `es-419`, `zh-TW`). The
README lists them by name; the current list with codes is at
https://developers.deepgram.com/docs/models-languages-overview. If the user
names a language you are not sure is there, check that page. If it is not
there, tell the user Deepgram does not handle it yet, before spending money
on a run.

## How long a recording can be

The size of a video does not matter: only the sound is sent, compressed to
about 22 MB per hour. A 2 hour recording uploads about 45 MB, whether the
video was 300 MB or 5 GB. Deepgram's upload limit is 2 GB, which at that rate
is about 90 hours, and the script stops with a clear message if a file would
go over it. Recordings of a few hours are fine. Nothing longer than about 2
hours has been tested yet; for a longer one, tell the user that and go ahead.
If Deepgram times out, split the recording into parts.

## What comes out

Two files appear next to the original:

- `<name>.transcript.txt`: the readable transcript. A header with model,
  language and the privacy state, then speaker blocks like
  `Speaker 0  [12:05–12:41]`.
- `<name>.response.json`: the raw Deepgram data. The user can ignore it.

If those files already exist from an earlier run, the old ones go to the
Trash first.

The run ends with a privacy line. In privacy mode it is
`Privacy: MIP opt-out ON (audio not used for training).` Tell the user it
appeared. If it says OFF, say so plainly.

After a run, tell the user where the transcript is and offer to summarise it,
pull out action items, or translate it. Read the transcript file only for that;
a 2 hour transcript is long, so read it in parts.

## Updating, or installing again

When the user asks to update, or a step below says to run the installer, run
this with a 10 minute Bash timeout:

```bash
/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/saalse/mashinista-deepgram/main/install.sh)"
```

It pulls the newest version and keeps the saved key. If no key is saved, a
small Mac dialog asks the user to paste it first; tell them to look for it.
If Homebrew is missing, a Terminal window opens: tell the user to type their
Mac password there. The command waits for that window and says how it ended.
If it says the window is still working, ask the user to tell you when the
window says All set.

## When something goes wrong

- `no key was entered` from the installer: the user has no key yet. Walk them
  through it: sign up at console.deepgram.com (new accounts get free credit),
  open API Keys, create a key and copy it right away, since it is shown only
  once. Then run the installer again.
- `no Deepgram API key found`: the key was never saved. Run the installer.
- `status 401` or `403`: the key is wrong or was deleted. The user makes a new
  one at console.deepgram.com. Move
  `~/Library/Application Support/Mashinista/deepgram/.env` to the Trash with
  `trash`, then run the installer; it asks for the new key.
- `status 402` or a message about credit or balance: the Deepgram account is
  out of credit. The user tops it up at console.deepgram.com.
- `ffmpeg is not installed`: run the installer.
- `ffmpeg could not read the audio`: the file may be damaged or have no sound.
