#!/bin/bash
# install.sh: install or update mashinista-deepgram. Safe to run again: the
# same command installs the first time and updates every time after that.
#
#   /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/saalse/mashinista-deepgram/main/install.sh)"
#
# It works both in the Terminal app and when Claude runs it from the Code tab,
# which has no terminal: there the key is asked for in a Mac dialog, and if
# Homebrew is missing the installer reopens itself in a Terminal window,
# because Homebrew's own installer needs the Mac password typed in a terminal.
# The Code tab run then waits for that window to finish.
#
# For testing: MASHINISTA_REPO, MASHINISTA_DIR and MASHINISTA_INSTALL_URL
# override the clone source, the install folder and this script's address;
# MASHINISTA_KEY_STDIN=1 reads the key from stdin; MASHINISTA_WAIT is how many
# seconds the Code tab run may take in all before it stops waiting for the
# Terminal window (default 570, inside Claude's 10 minute timeout).
set -euo pipefail

INSTALL_URL="${MASHINISTA_INSTALL_URL:-https://raw.githubusercontent.com/saalse/mashinista-deepgram/main/install.sh}"
REPO_URL="${MASHINISTA_REPO:-https://github.com/saalse/mashinista-deepgram.git}"
DIR="${MASHINISTA_DIR:-$HOME/Library/Application Support/Mashinista/deepgram}"
SKILL_TARGET="$DIR/skills/transcribe-deepgram"
SKILL_LINK="$HOME/.claude/skills/transcribe-deepgram"
HOMEBREW_INSTALL_URL="https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh"
ENV_FILE="$DIR/.env"

say() { printf '%s\n' "$*"; }
stop() { printf '\nStopped: %s\n' "$*" >&2; exit 1; }

# 0. Only on a Mac. Claude Chat runs commands on a cloud computer, not on the
#    user's Mac, so this is also where a Chat session ends up.
if [ "$(uname -s)" != Darwin ]; then
  stop "this installer only runs on a Mac, from the Code tab of the Claude desktop app. Claude Chat runs commands on a cloud computer, not on your Mac, so it cannot install this. Open the Code tab in the Claude desktop app and send the same message there."
fi

if [ -t 0 ] || { : </dev/tty; } 2>/dev/null; then TTY=yes; else TTY=no; fi

# In a terminal, end with a clear last line, and tell a waiting Code tab run
# (MASHINISTA_DONE_FILE) how this run ended.
on_exit() {
  local status=$?
  if [ -n "${MASHINISTA_DONE_FILE:-}" ]; then
    printf '%s\n' "$status" >"$MASHINISTA_DONE_FILE" || true
  fi
  if [ "$TTY" = yes ]; then
    say ""
    if [ "$status" = 0 ]; then
      say "You can close this window now."
    else
      say "Something went wrong; the reason is just above. Go back to the Claude app"
      say "and tell Claude what this window says. Then you can close this window."
    fi
  fi
}
trap on_exit EXIT

KEY_HELP="No key yet? Sign up at console.deepgram.com (new accounts get free credit), open API Keys and create one. Or ask Claude to help you get one."
ASK_KEY_DIALOG='on run argv
  set answer to display dialog (item 1 of argv) default answer "" with hidden answer with title "mashinista-deepgram" buttons {"Cancel", "Save"} default button "Save" cancel button "Cancel"
  return text returned of answer
end run'

# 1. The Deepgram key, first, so nothing slow runs before it is in hand.
#    Checked with Deepgram right away and kept in .env (readable only by you).
ask_key() {
  local intro="$1"
  key=""
  if [ -n "${MASHINISTA_KEY_STDIN:-}" ]; then
    IFS= read -r key || true
  elif [ "$TTY" = yes ]; then
    say ""
    say "$intro"
    say "$KEY_HELP"
    say "Paste the key and press Return. It stays hidden while you paste."
    IFS= read -r -s key </dev/tty || true
    say ""
  else
    say "Asking for the Deepgram key in a Mac dialog ..."
    key="$(osascript -e "$ASK_KEY_DIALOG" "$intro"$'\n\n'"$KEY_HELP" 2>/dev/null)" || true
  fi
  key="$(printf '%s' "$key" | tr -d '[:space:]')"
}

# Prints the HTTP status Deepgram gives the key. curl reads the header from
# stdin, so the key never appears in a process list.
check_key() {
  curl -sS -o /dev/null -w '%{http_code}' --config - <<EOF || true
url = "https://api.deepgram.com/v1/projects"
header = "Authorization: Token $key"
EOF
}

if [ -s "$ENV_FILE" ]; then
  say "Deepgram key already saved, keeping it."
else
  intro="Paste your Deepgram API key. It stays hidden."
  for attempt in 1 2 3; do
    ask_key "$intro"
    [ -n "$key" ] || stop "no key was entered. $KEY_HELP Then run the install again."
    code="$(check_key)"
    if [ "$code" = "401" ] || [ "$code" = "403" ]; then
      [ "$attempt" -lt 3 ] && [ -z "${MASHINISTA_KEY_STDIN:-}" ] \
        || stop "Deepgram did not accept that key. Copy it again from console.deepgram.com (API Keys), then run the install again."
      say "Deepgram did not accept that key."
      intro="Deepgram did not accept that key. Copy it again from console.deepgram.com (API Keys) and paste it here."
      continue
    elif [ "$code" != "200" ]; then
      say "Could not check the key with Deepgram right now (HTTP $code). Saving it anyway."
    fi
    break
  done
  mkdir -p "$DIR"
  (umask 077 && printf 'DEEPGRAM_API_KEY=%s\n' "$key" >"$ENV_FILE")
  key=""
  say "Key saved."
fi
chmod 600 "$ENV_FILE"

# 2. Homebrew, the standard way to add tools to a Mac.
find_brew() {
  BREW=""
  if command -v brew >/dev/null 2>&1; then
    BREW="$(command -v brew)"
  elif [ -x /opt/homebrew/bin/brew ]; then
    BREW=/opt/homebrew/bin/brew
  elif [ -x /usr/local/bin/brew ]; then
    BREW=/usr/local/bin/brew
  fi
}
brew_on_path=yes
command -v brew >/dev/null 2>&1 || brew_on_path=no
find_brew

if [ -z "$BREW" ] && [ "$TTY" = no ]; then
  # No terminal to type the Mac password into: rerun this installer in one,
  # and wait here until it says how it ended.
  cmd="${TMPDIR:-/tmp}/mashinista-install-$$.command"
  done_file="${TMPDIR:-/tmp}/mashinista-install-$$.done"
  rm -f "$done_file"
  cat >"$cmd" <<EOF
#!/bin/bash
export MASHINISTA_REPO=$(printf '%q' "$REPO_URL")
export MASHINISTA_DIR=$(printf '%q' "$DIR")
export MASHINISTA_INSTALL_URL=$(printf '%q' "$INSTALL_URL")
export MASHINISTA_DONE_FILE=$(printf '%q' "$done_file")
/bin/bash -c "\$(curl -fsSL $(printf '%q' "$INSTALL_URL"))"
EOF
  chmod 700 "$cmd"
  open "$cmd"
  say "Homebrew has to be installed first, and that needs the Mac password,"
  say "so the installer has opened in a new Terminal window. Type the Mac"
  say "password there when asked (nothing shows while typing). Waiting for"
  say "that window to finish ..."
  while [ ! -s "$done_file" ] && [ "$SECONDS" -lt "${MASHINISTA_WAIT:-570}" ]; do
    sleep 5
  done
  if [ ! -s "$done_file" ]; then
    say "The Terminal window is still working; installing Homebrew can take a"
    say "while. The install is done when that window says All set."
    exit 0
  fi
  status="$(cat "$done_file")"
  rm -f "$done_file" "$cmd"
  [ "$status" = 0 ] || stop "the install in the Terminal window ended with an error. Ask the user what that window says."
  say "The Terminal window finished and says All set."
  say "Use it in the Code tab of the Claude app (not Chat)."
  exit 0
fi

if [ -z "$BREW" ]; then
  say "Homebrew is not installed. Installing it now with Homebrew's own installer."
  say "It asks for your Mac password (nothing shows while you type) and may first"
  say "install Apple's developer tools, which takes a few minutes."
  /bin/bash -c "$(curl -fsSL "$HOMEBREW_INSTALL_URL")" </dev/tty \
    || stop "Homebrew did not install. Your Mac user has to be an administrator; see https://brew.sh."
  find_brew
  [ -n "$BREW" ] || stop "Homebrew finished but cannot be found. Close this window, open a new one and run the install line again."
  say ""
  say "Homebrew is installed. Its \"Next steps\" above are already taken care of"
  say "by this installer: there is nothing to type. Carrying on ..."
fi
eval "$("$BREW" shellenv)"
if [ "$brew_on_path" = no ]; then
  # What Homebrew's "Next steps" asks for: put brew on the PATH of new shells.
  line="eval \"\$($BREW shellenv)\""
  grep -qsF "$line" "$HOME/.zprofile" || printf '\n%s\n' "$line" >>"$HOME/.zprofile"
fi

# 3. Tools: uv runs the Python script, ffmpeg pulls audio out of video, git
#    downloads and updates this folder. Anything already working is skipped.
works() {
  if [ "$1" = ffmpeg ]; then ffmpeg -version; else "$1" --version; fi
}
missing=()
for tool in uv ffmpeg git; do
  if ! works "$tool" >/dev/null 2>&1; then
    missing+=("$tool")
  fi
done
if [ "${#missing[@]}" -gt 0 ]; then
  say "Installing ${missing[*]} with Homebrew. This can take a few minutes ..."
  "$BREW" install "${missing[@]}"
else
  say "uv, ffmpeg and git are already installed."
fi

# 4. Download, or update if it is already here. The folder already holds the
#    .env from step 1, so the project is cloned next to it and moved in.
if [ -d "$DIR/.git" ]; then
  say "Updating $DIR ..."
  git -C "$DIR" pull --ff-only --quiet
elif [ -n "$(find "$DIR" -mindepth 1 -maxdepth 1 ! -name .env 2>/dev/null | head -1)" ]; then
  stop "$DIR exists but was not made by this installer. Move it to the Trash, then run this again."
else
  say "Downloading to $DIR ..."
  mkdir -p "$DIR"
  tmp="$(mktemp -d "$(dirname "$DIR")/.download.XXXXXX")"
  git clone --quiet --no-checkout "$REPO_URL" "$tmp"
  mv "$tmp/.git" "$DIR/.git"
  rmdir "$tmp"
  git -C "$DIR" reset --quiet --hard
fi

# 5. The skill for the Claude app. A link, so every update reaches it.
mkdir -p "$HOME/.claude/skills"
if [ -L "$SKILL_LINK" ]; then
  if [ "$(readlink "$SKILL_LINK")" != "$SKILL_TARGET" ]; then
    stop "$SKILL_LINK already points somewhere else. Move it to the Trash, then run this again."
  fi
elif [ -e "$SKILL_LINK" ]; then
  stop "$SKILL_LINK already exists. Move it to the Trash, then run this again."
else
  ln -s "$SKILL_TARGET" "$SKILL_LINK"
fi
say "Claude skill linked: $SKILL_LINK"

# 6. Fetch Python and the Deepgram library now, so the first real run is quick.
say "Checking Python and the Deepgram library (the first time takes a minute) ..."
uv run --quiet "$SKILL_TARGET/scripts/transcribe.py" --help >/dev/null

say ""
say "All set. In the Claude app, open the Code tab (not Chat) and ask, for example:"
say "  transcribe ~/Movies/lecture.mp4"
say "Claude then asks a few quick questions about the recording."
