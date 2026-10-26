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
- Costs about $0.40 to $0.80 for a 1 to 2 hour file at Deepgram's current
  pay as you go price.

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
3. Open the Claude desktop app, go to the Code tab, pick any folder (your
   Home folder is fine), and send Claude this message:

   ```
   Please install mashinista-deepgram by running this command with a 10 minute timeout:
   /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/saalse/mashinista-deepgram/main/install.sh)"
   ```

4. Claude asks before it runs the command. Allow it.
5. A small window asks for the Deepgram key. Paste it and click Save.

If Homebrew (the standard tool installer for Macs) is not on your Mac yet, a
Terminal window opens by itself instead. Type your Mac password there when
asked (nothing shows while you type, that is on purpose), then paste the
Deepgram key when asked. It is done when the window says All set.

You can also paste the same command into the Terminal app yourself; it works
the same way there.

The installer:

- installs Homebrew if it is missing, then uv, ffmpeg and git with it
- downloads this project to `~/Library/Application Support/Mashinista/deepgram`
- saves your key in `.env` in that folder
- links the Claude skill into `~/.claude/skills/transcribe-deepgram`

## Use

In the Claude desktop app, open the Code tab, pick any folder, and say for
example:

> transcribe ~/Movies/lecture.mp4

You can add details in plain words: the speakers' names, that it is a doctor
visit, that it is all in English. Claude picks the right options.

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
