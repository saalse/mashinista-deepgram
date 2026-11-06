# Call recordings (Nistka)

Read this when the file is a call recording, or the user asks for one.
Everything in SKILL.md still applies unless this file says otherwise.

## Contents

- What a call recording is
- Finding the call
- What the script does with it
- Ask about the call
- Check the price, then ask
- What the run prints, and what to tell the user

## What a call recording is

One stereo file: the left channel is the user's microphone, the right
channel is everyone else (the sound the computer played). Nistka, a Mac menu
bar recorder, records calls this way, as `<date> <time>.m4a` (for example
`2026-11-03 23-30-00.m4a`) in `~/Documents/Nistka`. The user may rename
files there.

A two-channel file in that folder is treated as a call on its own. For a
stereo file from anywhere else whose channels are split the same way, add
`--call`. `--no-call` transcribes a file in that folder the ordinary way.

While Nistka records, it writes `<date> <time> source.caf` next to it, and
replaces it with the `.m4a` when the recording stops. A `source.caf` with no
`.m4a` of the same date and time is what a crash left: it is a complete
recording and can be transcribed like any other. A tiny one (a few KB) is a
recording that never started; the script says it cannot read it.

## Finding the call

When the user names a call without a path ("my last call", "this morning's
call"), list the `.m4a` files (and any lone `source.caf`) in
`~/Documents/Nistka`, newest first by the date and time in the name, and
confirm the one you picked by its date, time and length before the
questions. Ignore `.txt` and `.json` files: those are
transcripts from earlier runs.

## What the script does with it

Locally on the Mac, before anything is uploaded, it checks both channels
for sound (about 10 seconds per hour of audio). Then:

- Both channels have sound: the file goes up as it is, with the two
  channels kept apart, and the speaker comes from the channel. So the
  user's own lines are labelled exactly. It costs about twice a normal run:
  each channel is billed.
- The right channel is silent: nothing played through the computer, so
  anyone in the conversation was in the room, on the mic. Only the left
  channel goes up, as an ordinary recording with speakers told apart by
  voice, at the normal price.
- The left channel is silent: the recorder probably had no microphone
  access. Only the right channel goes up, the same way.
- Both silent: it stops and nothing is uploaded.

## Ask about the call

A call gets one click question and one typed message, instead of the three
questions in SKILL.md. The user's own lines are always labelled `Me` from
their own channel, so ask only about the others. (`--me "Name"` puts the
user's name there instead, if they ask for it.)

1. The language, alone in one AskUserQuestion call, worded and handled as
   the language question in SKILL.md.
2. Then one normal chat message, so the user can type the names. Ask roughly
   this:

   > Who else was on the call? Name everyone except yourself. For someone
   > whose name you don't know, write Speaker A, Speaker B and so on, so I
   > know how many people there were.
   >
   > And what was it about, in a sentence or two? Which names came up:
   > people who were talked about, places, brands, products, technical
   > terms? Rare names come out much better when I know them. Say skip to go
   > without this part.

   Wait for the answer. Turn the people into `--speakers`, the context into
   `--keyterms` as SKILL.md describes. On a call keyterms cost about $0.16
   per hour, because both channels are billed.

- One person, by name or as Speaker A: `--speakers "Dana"`. Their lines carry
  that label. No guessing by voice at all: both labels come from the
  channels.
- Two or more: `--speakers "Dana,Lee,Speaker A"`, everything the user
  typed. The user's lines stay exact; only the others are split by voice, as
  `Speaker 1`, `Speaker 2` and so on (nobody knows who spoke first, so names
  are not matched by order).
- Not sure how many, or no answer about the people: `--diarize` and no
  `--speakers`.

Real names go into the keyterms on their own; do not list them again.
`Speaker A` and the like do not.

After a run with two or more people, read the transcript and tell the user
who seems to be who, from what they say and how others address them. Rerun
only if the user wants the names in the file: a rerun of a call costs the
full price again.

## Check the price, then ask

Before the paid run, always run the same command with `--check` added:

```bash
PATH="/opt/homebrew/bin:/usr/local/bin:$PATH" uv run ~/.claude/skills/transcribe-deepgram/scripts/transcribe.py "$HOME/Documents/Nistka/2026-11-03 23-30-00.m4a" --lang en --speakers "Dana" --check
```

It checks both channels on the Mac, uploads nothing, writes nothing and
needs no key. It prints the channel check, the settings and the price
exactly as the paid run will. Pass them on, then ask in one AskUserQuestion
call:

**"Start the paid transcription for about $0.62?"**

- "Yes, go": run the command again without `--check`.
- "Not now": stop.

If the check said a channel is silent, say so first, in plain words, and
what that means for the labels and the price.

## What the run prints, and what to tell the user

- `Both channels have sound`: the normal case.
- `the others' channel (right) is silent` or `your mic channel (left) is
  silent`: see "What the script does with it". The names the user gave
  then only help as keyterms, and the transcript says Speaker 0, Speaker 1.
  If the left channel was silent, suggest checking the recorder's
  microphone permission in System Settings, Privacy & Security, before the
  next call.
- `Settings:` and `Length:` before the upload: check them (the labels in
  the settings are the ones the transcript will use), and pass the price on.
  It already counts both channels and the keyterms.
- After the run, `Repeats: ... the channels stayed apart` is the normal
  result, with 0 or a few repeats (short words both people said at the same
  moment). `WARNING: ... lines of yours also appear on the others' channel`
  means the others' voices reached the user's mic, for example from
  speakers without echo cancellation: tell the user the labels may be off
  in places, and offer `--no-call` (one mixed recording with speakers told
  apart by voice).
- `Cleanup: dropped N short lines`: short lines that came out in an odd
  language or script (Deepgram's mix model does that to short "yes" and "mm"
  sounds) and pure fillers. Add `--keep-all-lines` to keep them.
- The channel levels sit at the very end of the transcript file, in a short
  block of technical details, so the user can ignore them.

Also tell the user, when it applies:

- Anyone in the room with the user is heard by their mic, so they are
  labelled as the user. Exact labels hold only for people on the call.
- With several people, one person can get two Speaker numbers when their
  audio changes mid-call (another device, a car, a reconnect). Check that
  before you say who is who.
