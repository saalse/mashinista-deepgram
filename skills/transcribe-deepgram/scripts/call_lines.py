"""
call_lines.py: the transcript side of a two-channel call.

After Deepgram: one line per utterance from both channels, labels for Me and
the far side, short noise lines dropped, and lines of yours that also appear
on the far channel counted.
"""
from __future__ import annotations

import re
import unicodedata
from bisect import bisect_left
from collections import Counter
from dataclasses import dataclass

SHORT_LINE_WORDS = 8
MAIN_LANGUAGE_SHARE = 0.10  # a language with this share of a channel's words
MAIN_SCRIPT_SHARE = 0.02    # a script writing this share of a channel's words
RARE_LETTERS = 2.0          # a letter this rare per 10,000 on a channel is foreign
RARE_LETTERS_MIN = 3        # ... or seen at most this many times
REPEAT_WINDOW_S = 1.0

# What Deepgram writes for hums and backchannels.
FILLERS = {"mhm", "mhmm", "mm", "mmm", "hmm", "hm", "uh", "um", "umm",
           "uh-huh", "uhhuh", "mm-hmm", "mmhmm", "huh", "ah", "oh", "eh",
           "er", "erm"}

_WORD = re.compile(r"[^\w'-]+")


def _norm(word: str) -> str:
    return _WORD.sub("", word.lower()).strip("-'")


def _script(ch: str) -> str | None:
    if not ch.isalpha():
        return None
    try:
        return unicodedata.name(ch).split()[0]
    except ValueError:
        return None


def call_lines(data: dict, *, far_diarized: bool) -> list[dict]:
    """One line per utterance (or per speaker run inside one), both channels.

    data is the response as a plain dict. Channel 0 is Me whatever Deepgram's
    speaker field says; on channel 1 the speaker comes from diarization when
    far_diarized, else it is the one far party. Sorted by start time.
    """
    lines = []
    for u in (data.get("results") or {}).get("utterances") or []:
        ch = int(u.get("channel") or 0)
        words = u.get("words") or []
        if ch == 1 and far_diarized and words:
            runs: list[list[dict]] = []
            for w in words:
                if runs and runs[-1][0].get("speaker") == w.get("speaker"):
                    runs[-1].append(w)
                else:
                    runs.append([w])
        else:
            runs = [words]
        for run in runs:
            if run and (len(runs) > 1 or not (u.get("transcript") or "").strip()):
                text = " ".join(w.get("punctuated_word") or w.get("word") or "" for w in run)
            else:
                text = u.get("transcript") or ""
            text = text.strip()
            if not text:
                continue
            spk = run[0].get("speaker") if (run and ch == 1 and far_diarized) else None
            lines.append({
                "channel": ch, "speaker": spk,
                "start": run[0]["start"] if run else u.get("start"),
                "end": run[-1]["end"] if run else u.get("end"),
                "text": text, "words": run,
            })
    lines.sort(key=lambda l: (l["start"] or 0, l["channel"]))
    return lines


def label_lines(lines: list[dict], names: list[str], *, me_label: str = "Me") -> None:
    """Set line["label"]: Me for channel 0; far speakers numbered by first word.

    names[0] names Me, names[1:] the far side in the order they first speak.
    """
    order: dict = {}
    for line in lines:
        if line["channel"] == 0:
            line["label"] = names[0] if names else me_label
            continue
        key = line["speaker"]
        if key not in order:
            order[key] = len(order)
        i = order[key]
        line["label"] = names[1 + i] if 1 + i < len(names) else f"Speaker {i + 1}"


def _word_script(word: str) -> str | None:
    scripts = Counter(s for s in map(_script, word) if s)
    return scripts.most_common(1)[0][0] if scripts else None


@dataclass
class _Expect:
    langs: set          # languages tagged on MAIN_LANGUAGE_SHARE of the words
    scripts: set        # scripts writing MAIN_SCRIPT_SHARE of the words
    dominant: str | None  # the script most words are in
    rare: set           # letters seen at most RARE_LETTERS times per 10,000


def _expected(lines: list[dict]) -> _Expect:
    """What one channel normally looks like.

    Scripts are counted from the text, not from the language tags: Deepgram
    tags many words with the wrong language, and a language spoken in short
    phrases, such as technical terms, still writes a fair share of the words.
    """
    langs = Counter(w.get("language") for l in lines for w in l["words"] if w.get("language"))
    total = sum(langs.values())
    main_langs = {k for k, v in langs.items() if total and v / total >= MAIN_LANGUAGE_SHARE}
    scripts = Counter(s for l in lines for s in map(_word_script, l["text"].split()) if s)
    total = sum(scripts.values())
    main_scripts = {k for k, v in scripts.items() if total and v / total >= MAIN_SCRIPT_SHARE}
    letters = Counter(c for l in lines for c in l["text"].lower() if c.isalpha())
    limit = max(RARE_LETTERS_MIN, RARE_LETTERS * sum(letters.values()) / 10000)
    return _Expect(langs=main_langs, scripts=main_scripts,
                   dominant=scripts.most_common(1)[0][0] if scripts else None,
                   rare={c for c, n in letters.items() if n <= limit})


def drop_noise_lines(lines: list[dict]) -> tuple[list[dict], Counter]:
    """Drop pure fillers, and short lines in an unexpected language or script.

    With language=multi Deepgram turns short backchannels into odd one-off
    languages. A line of SHORT_LINE_WORDS words or fewer goes when none of
    its letters are in a script the channel uses, or when most of its words
    are tagged with a language that is rare on the channel and the line does
    not read like the channel either: most of it is in another script than
    the channel's main one, or it has letters the channel hardly ever uses.
    A rare tag on a line in the channel's own alphabet is a mislabel of the
    channel's language, and the line stays. Longer lines always stay.
    """
    expected = {ch: _expected([l for l in lines if l["channel"] == ch]) for ch in (0, 1)}
    kept, dropped = [], Counter()
    for line in lines:
        words = [_norm(w) for w in line["text"].split()]
        words = [w for w in words if w]
        if words and all(w in FILLERS for w in words):
            dropped["fillers"] += 1
            continue
        if len(line["text"].split()) <= SHORT_LINE_WORDS:
            exp = expected[line["channel"]]
            scripts = Counter(s for s in map(_script, line["text"]) if s)
            if exp.scripts and scripts and not set(scripts) & exp.scripts:
                dropped["unexpected script"] += 1
                continue
            tags = [w.get("language") for w in line["words"] if w.get("language")]
            odd = sum(t not in exp.langs for t in tags)
            if exp.langs and tags and odd * 2 > len(tags):
                own = scripts[exp.dominant] * 2 > sum(scripts.values())
                strange = any(c in exp.rare for c in line["text"].lower() if c.isalpha())
                if not own or strange:
                    dropped["unexpected language"] += 1
                    continue
        kept.append(line)
    return kept, dropped


def count_repeats(lines: list[dict]) -> tuple[int, int]:
    """Me lines whose words also appear on the far channel within ±1 s.

    A high count means far-side audio got into Me. Returns (repeated, Me
    lines with two or more words).
    """
    far: dict[str, list[float]] = {}
    for line in lines:
        if line["channel"] == 1:
            for w in line["words"]:
                k = _norm(w.get("word") or "")
                if k:
                    far.setdefault(k, []).append(float(w["start"]))
    for v in far.values():
        v.sort()
    repeated = total = 0
    for line in lines:
        if line["channel"] != 0:
            continue
        words = [(_norm(w.get("word") or ""), float(w["start"])) for w in line["words"]]
        words = [(k, t) for k, t in words if k]
        if len(words) < 2:
            continue
        total += 1
        hits = 0
        for k, t in words:
            starts = far.get(k)
            if starts:
                i = bisect_left(starts, t - REPEAT_WINDOW_S)
                if i < len(starts) and starts[i] <= t + REPEAT_WINDOW_S:
                    hits += 1
        if hits >= 2 and hits * 2 >= len(words):
            repeated += 1
    return repeated, total
