# mashinista-deepgram

Private transcription of any audio or video file on a Mac. It is made for
recordings you would not hand to an ordinary transcription service: privacy
mode is on by default, so model training is switched off, Deepgram keeps the
audio only for as long as it takes to transcribe it, and the transcript is
saved only on your Mac. The work runs on Deepgram's nova-3 model, on your own Deepgram account,
and you start it by asking Claude in the Code tab of the Claude desktop app.

- Handles audio and video, one or two hours or more.
- Labels speakers and adds timestamps.
- Handles a mix of languages in one recording.
- Costs about $0.25 to $0.80 for a 1 to 2 hour file at Deepgram's current
  pay as you go price.

It works only in the **Code tab** of the Claude desktop app. Claude Chat
cannot use it: Chat runs commands on a cloud computer, not on your Mac.

## Privacy mode, on by default

Every transcription runs in privacy mode. For audio that is not sensitive,
such as a public lecture, you can ask Claude to turn privacy mode off for
that one file to save money; Claude explains what that means and asks you to
confirm first, and the next file is private again.

- The audio is sent to Deepgram over an encrypted connection and transcribed
  there. Every request carries `mip_opt_out=true`, which opts it out of
  Deepgram's Model Improvement Program. In Deepgram's words, data from
  opted-out requests "is retained only for the duration necessary to process
  the request" ([source](https://developers.deepgram.com/docs/the-deepgram-model-improvement-partnership-program)).
  Turning privacy mode off (`--allow-training`) sends `mip_opt_out=false`, so
  Deepgram may keep that file and use it to train its models; the script
  prints a loud warning first.
- Deepgram still keeps a billing record of each request (its length and
  time), as any paid service does.
- For video, ffmpeg cuts out the sound on your Mac first and only that is
  uploaded. The picture never leaves your computer.
- The transcript is saved next to the original file, on your Mac only.
- Your Deepgram key is kept in a `.env` file in the install folder, readable
  only by your Mac user. It is never sent anywhere except to Deepgram.

## Install

1. Make a Deepgram account at https://console.deepgram.com. New accounts get
   free starting credit.
2. In the Deepgram console, open API Keys, create a key, and copy it.
3. Open the Claude desktop app, go to the **Code tab** (not Chat), pick any
   folder (your Home folder is fine), and send Claude this message:

   ```
   Please install mashinista-deepgram on this Mac by running this command with a 10 minute timeout. It only works in Claude Code (the Code tab), so if you are Claude Chat, tell me to switch to the Code tab instead.
   /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/saalse/mashinista-deepgram/main/install.sh)"
   ```

4. Claude asks before it runs the command. Allow it.
5. A small window asks for the Deepgram key first. Paste it and click Save.
   No key yet? Click Cancel and ask Claude to help you make one.

If Homebrew (the standard tool installer for Macs) is not on your Mac yet, a
Terminal window opens by itself next. Type your Mac password there when
asked (nothing shows while you type, that is on purpose). Homebrew then
prints "Next steps"; ignore them, the installer does them for you. When the
window says All set and "You can close this window now", close it. Claude
waits for that window and tells you when it is done.

You can also paste the same command into the Terminal app yourself; it works
the same way there.

The installer:

- asks for the Deepgram key first and checks it with Deepgram
- installs Homebrew if it is missing, then uv, ffmpeg and git with it
- downloads this project to `~/Library/Application Support/Mashinista/deepgram`
- saves your key in `.env` in that folder
- links the Claude skill into `~/.claude/skills/transcribe-deepgram`

## Use

In the Claude desktop app, open the Code tab, pick any folder, and say for
example:

> transcribe ~/Movies/lecture.mp4

Before it starts, Claude asks three quick questions, and the answers make the
transcript noticeably better:

- Who speaks: one person, several you can't name, or several whose names you
  type in. Several turns on speaker labels.
- Which language, or a mix? One language is more accurate and cheaper.
- Then, in a message you type: what is it about, and which names come up?
  People who are talked about, places, brands, products, technical terms,
  professions. Those become hints, so rare names come out spelled right. This
  one is worth the minute it takes.

The first two are buttons. To type an answer instead, such as the speakers'
names or another language, pick Other.

You can answer them up front in the same message and skip the questions:

> transcribe ~/Movies/interview.mp4. Two speakers, Anna and Mark, all in
> English. A podcast about opening a small bakery: sourdough, KitchenAid,
> Square, Etsy.

If it sounds like a doctor visit, Claude switches to the medical model on its
own and tells you. Say "just go" to skip the questions.

## How long a recording can be

Any video that fits on your Mac is fine, because only the sound is sent,
compressed to about 22 MB per hour. A 2 hour recording uploads about 45 MB
whether the video is 300 MB or 5 GB. Deepgram's upload limit is 2 GB, which
at that rate is about 90 hours. Recordings of a few hours work; nothing over
about 2 hours has been tested yet. Before it uploads, the run shows the length
and the expected price.

## Languages

Deepgram's nova-3 model, as of October 2026, transcribes these languages one
at a time: Afrikaans, Arabic, Armenian, Assamese, Belarusian, Bengali,
Bosnian, Bulgarian, Catalan, Chinese (Mandarin and Cantonese), Croatian,
Czech, Danish, Dutch, English, Estonian, Finnish, Flemish, French, Georgian,
German, Greek, Gujarati, Hebrew, Hindi, Hungarian, Indonesian, Italian,
Japanese, Kannada, Kazakh, Korean, Latvian, Lithuanian, Macedonian, Malay,
Marathi, Mongolian, Nepali, Norwegian, Pashto, Persian, Polish, Portuguese,
Punjabi, Romanian, Russian, Serbian, Slovak, Slovenian, Spanish, Swedish,
Tagalog, Tamil, Telugu, Thai, Turkish, Ukrainian, Urdu and Vietnamese.

- **One language:** the most accurate and cheapest choice. Several have
  regional variants, such as British English or Brazilian Portuguese.
- **A mix:** one recording that switches between languages. It covers most
  of the list above.
- **Doctor visits:** the medical model handles English on its own, and a mix
  of English, Spanish, French, German, Hindi, Russian, Portuguese, Japanese,
  Italian and Dutch. For any other language, the ordinary model is used with
  the medical words as hints.

Deepgram adds languages often. Its current list, with codes, is at
https://developers.deepgram.com/docs/models-languages-overview.

Two files appear next to the recording:

- `lecture.transcript.txt`, the transcript to read
- `lecture.response.json`, the raw Deepgram data, which you can ignore

From Terminal, the same thing is:

```bash
uv run ~/.claude/skills/transcribe-deepgram/scripts/transcribe.py ~/Movies/lecture.mp4
```

Add `--help` to see every option.

## Where things are

- `~/Library/Application Support/Mashinista/deepgram`: the program and your
  key (`.env`)
- `~/.claude/skills/transcribe-deepgram`: a link that lets Claude find the skill
- next to each recording: its `.transcript.txt` and `.response.json`
- Homebrew's own folder (`/opt/homebrew`, or `/usr/local` on Intel Macs): uv,
  ffmpeg and git
- `~/.cache/uv` and `~/.local/share/uv`: the Python that uv downloads for the
  script

## Update

Tell Claude in the Code tab "update mashinista-deepgram", or run the install
command again. It downloads the newest version and keeps your key.

## Change the key

Move `~/Library/Application Support/Mashinista/deepgram/.env` to the Trash,
then run the install command again. It asks for the new key.

## Remove

Move `~/Library/Application Support/Mashinista` and
`~/.claude/skills/transcribe-deepgram` to the Trash. To also remove the tools:
`brew uninstall uv ffmpeg`.

## License

MIT, see [LICENSE](LICENSE). Made by [Alex Samson](https://www.saalse.com/).
