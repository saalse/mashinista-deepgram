---
name: transcribe-deepgram
description: Transcribe a local audio or video file (mp4, mov, m4a, mp3, wav and more, up to several hours) to text with Deepgram nova-3, with speaker labels and timestamps, mixed languages supported, privacy mode (model-training opt-out) on by default. Use when the user asks to transcribe, make a transcript of, or turn into text a recording, lecture, interview, meeting, call, voice note or doctor visit, or to update mashinista-deepgram.
license: MIT
compatibility: macOS, designed for Claude Code (the Code tab of the Claude desktop app). Needs uv, ffmpeg and internet access to api.deepgram.com, plus a Deepgram API key; install.sh sets all of this up.
metadata:
  author: Alex Samson (https://www.saalse.com/)
  repository: https://github.com/saalse/mashinista-deepgram
  version: "1.0"
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

## The one command

```bash
uv run ~/.claude/skills/transcribe-deepgram/scripts/transcribe.py "/path/to/file.mp4"
```

- If this skill was loaded from another folder, use `scripts/transcribe.py`
  inside that folder instead.
- Quote the recording's path: names often have spaces.
- A long file takes a few minutes (local audio extraction, upload, then
  Deepgram). Run it with a 10 minute Bash timeout, or in the background, and
  tell the user it is working.
- If `uv` is not found, use `/opt/homebrew/bin/uv` (Apple silicon) or
  `/usr/local/bin/uv` (Intel Mac) instead.
- Video is fine. The script cuts out a mono audio track on the Mac with ffmpeg
  and uploads only that, so the picture never leaves the computer.

Defaults: model nova-3, `--lang multi` (handles a mix of languages), speaker
labels on, no keyterms.

## Options worth knowing

- `--speakers "Name1,Name2"` puts names on Speaker 0, Speaker 1 and so on, in
  the order people first speak. If the user names the speakers, run once
  without it, look at who speaks first in the transcript, then rerun with
  names only if they want them in the file. Otherwise just tell them which
  speaker is who.
- `--keyterms "Word one,Word two"` helps with names, brands or jargon the
  user expects in the recording. Ask for them only if the first result gets
  names wrong.
- `--lang ru` or `--lang en` forces one language when the recording has only
  that one and `multi` makes mistakes.
- `--medical` for a doctor visit, test results or any healthcare talk. It
  switches to the nova-3-medical model with a medical word list and English.
  If the visit is in another language, do not use `--medical`; use the default
  model with `--lang` instead.
- `--no-diarize` for a single speaker (a voice note), to get timestamped
  paragraphs instead of speaker blocks.

Add `--help` to the command for the rest.

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
small Mac dialog asks the user to paste it; tell them to look for it. If
Homebrew is missing, a Terminal window opens: tell the user to type their Mac
password there and wait for "All set".

## When something goes wrong

- `no Deepgram API key found`: the key was never saved. Run the installer.
- `status 401` or `403`: the key is wrong or was deleted. The user makes a new
  one at console.deepgram.com. Move
  `~/Library/Application Support/Mashinista/deepgram/.env` to the Trash with
  `trash`, then run the installer; it asks for the new key.
- `status 402` or a message about credit or balance: the Deepgram account is
  out of credit. The user tops it up at console.deepgram.com.
- `ffmpeg is not installed`: run the installer.
- `ffmpeg could not read the audio`: the file may be damaged or have no sound.
