---
title: Transcribing calls recorded with Nistka
sidebarTitle: Calls recorded with Nistka
---

Nistka is a small Mac menu bar recorder for calls. It saves each call as one
stereo file: your microphone on the left channel, everyone else (the sound
your computer played) on the right. mashinista-deepgram uses that to label
every line of yours as you, from your own channel, without guessing by
voice.

Any other recorder that writes the same kind of stereo file works too; see
the end of this page.

## How to use it

Nistka saves calls in `~/Documents/Nistka`, named by date and time, for
example `2026-11-03 23-30-00.m4a`. In the Code tab of the Claude app, say
for example:

> transcribe my last call

Claude finds the newest recording and checks with you that it is the right
one. It asks which language the call was in, who else was on it (write
Speaker A, Speaker B for anyone whose name you don't know), and what it was
about.

Before you pay, Claude runs a free check of both channels and tells you the
price.

## What to expect

- With one other person, there is no guessing at all: both labels come from
  the channels. With more people, your lines stay exact and only the others
  are told apart by voice. One person can get two speaker numbers if their
  audio changes mid-call (another device, a reconnect).
- Anyone sitting next to you is heard by your mic, so they are labelled as
  you.
- If nothing played through your computer (for example a phone on speaker
  in the room), the right channel is silent. Then only your mic channel is
  sent, with speakers told apart by voice, at the normal price.
- The recording is sent as it is, never mixed down to one channel and never
  re-compressed, so nothing is lost on the way.
- It costs about twice a normal run, because each channel is billed.

If Nistka crashes mid-call, it leaves `<date> <time> source.caf` in the same
folder. That file is the complete recording up to the crash, and Claude can
transcribe it the same way.

## Other recorders

For a stereo recording made some other way, with your mic on the left and
the others on the right, ask Claude to transcribe it "as a call". From
Terminal, add `--call` to the command.
