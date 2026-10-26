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
#
# For testing: MASHINISTA_REPO, MASHINISTA_DIR and MASHINISTA_INSTALL_URL
# override the clone source, the install folder and this script's address;
# MASHINISTA_KEY_STDIN=1 reads the key from stdin.
set -euo pipefail

INSTALL_URL="${MASHINISTA_INSTALL_URL:-https://raw.githubusercontent.com/saalse/mashinista-deepgram/main/install.sh}"
REPO_URL="${MASHINISTA_REPO:-https://github.com/saalse/mashinista-deepgram.git}"
DIR="${MASHINISTA_DIR:-$HOME/Library/Application Support/Mashinista/deepgram}"
SKILL_TARGET="$DIR/skills/transcribe-deepgram"
SKILL_LINK="$HOME/.claude/skills/transcribe-deepgram"
HOMEBREW_INSTALL_URL="https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh"

say() { printf '%s\n' "$*"; }
stop() { printf '\nStopped: %s\n' "$*" >&2; exit 1; }

if [ -t 0 ] || { : </dev/tty; } 2>/dev/null; then TTY=yes; else TTY=no; fi

# 1. Homebrew, the standard way to add tools to a Mac.
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
  # No terminal to type the Mac password into: rerun this installer in one.
  cmd="${TMPDIR:-/tmp}/mashinista-install-$$.command"
  cat >"$cmd" <<EOF
#!/bin/bash
export MASHINISTA_REPO=$(printf '%q' "$REPO_URL")
export MASHINISTA_DIR=$(printf '%q' "$DIR")
export MASHINISTA_INSTALL_URL=$(printf '%q' "$INSTALL_URL")
/bin/bash -c "\$(curl -fsSL $(printf '%q' "$INSTALL_URL"))"
EOF
  chmod 700 "$cmd"
  open "$cmd"
  say "Homebrew has to be installed first, and that needs the Mac password,"
  say "so the installer has opened in a new Terminal window. Type the Mac"
  say "password there when asked (nothing shows while typing), then paste the"
  say "Deepgram key when asked. The install is done when that window says All set."
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
fi
eval "$("$BREW" shellenv)"
if [ "$brew_on_path" = no ]; then
  # What Homebrew's "Next steps" asks for: put brew on the PATH of new shells.
  line="eval \"\$($BREW shellenv)\""
  grep -qsF "$line" "$HOME/.zprofile" || printf '\n%s\n' "$line" >>"$HOME/.zprofile"
fi

# 2. Tools: uv runs the Python script, ffmpeg pulls audio out of video, git
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

# 3. Download, or update if it is already here.
if [ -d "$DIR/.git" ]; then
  say "Updating $DIR ..."
  git -C "$DIR" pull --ff-only --quiet
elif [ -e "$DIR" ]; then
  stop "$DIR exists but was not made by this installer. Move it to the Trash, then run this again."
else
  say "Downloading to $DIR ..."
  mkdir -p "$(dirname "$DIR")"
  git clone --quiet "$REPO_URL" "$DIR"
fi

# 4. The Deepgram key, asked for once and kept in .env (readable only by you).
ENV_FILE="$DIR/.env"
if [ ! -s "$ENV_FILE" ]; then
  key=""
  if [ -n "${MASHINISTA_KEY_STDIN:-}" ]; then
    IFS= read -r key || true
  elif [ "$TTY" = yes ]; then
    say ""
    say "Paste your Deepgram API key and press Return. It stays hidden while you paste."
    IFS= read -r -s key </dev/tty || true
    say ""
  else
    say "Asking for the Deepgram key in a Mac dialog ..."
    key="$(osascript \
      -e 'display dialog "Paste your Deepgram API key. It stays hidden." default answer "" with hidden answer with title "mashinista-deepgram" buttons {"Cancel", "Save"} default button "Save"' \
      -e 'text returned of result' 2>/dev/null)" || true
  fi
  key="$(printf '%s' "$key" | tr -d '[:space:]')"
  [ -n "$key" ] || stop "no key was entered. Run this again and paste the key."

  # Check the key once with Deepgram. curl reads the header from stdin, so the
  # key never appears in a process list.
  code="$(curl -sS -o /dev/null -w '%{http_code}' --config - <<EOF || true
url = "https://api.deepgram.com/v1/projects"
header = "Authorization: Token $key"
EOF
)"
  if [ "$code" = "401" ] || [ "$code" = "403" ]; then
    stop "Deepgram did not accept that key. Copy it again from console.deepgram.com and rerun."
  elif [ "$code" != "200" ]; then
    say "Could not check the key with Deepgram right now (HTTP $code). Saving it anyway."
  fi

  (umask 077 && printf 'DEEPGRAM_API_KEY=%s\n' "$key" >"$ENV_FILE")
  key=""
  say "Key saved."
else
  say "Deepgram key already saved, keeping it."
fi
chmod 600 "$ENV_FILE"

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
say "All set. In the Claude app, open the Code tab and say, for example:"
say "  transcribe ~/Movies/lecture.mp4"
