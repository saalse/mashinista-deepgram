"""Plain (not call) transcripts, on synthetic data only."""
import sys
import types
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1] / "skills" / "transcribe-deepgram" / "scripts"
sys.path.insert(0, str(SCRIPTS))

import transcribe_helpers as th  # noqa: E402


def words(text, start, speaker):
    return [types.SimpleNamespace(word=t.lower().strip(".,?"), punctuated_word=t,
                                  start=start + 0.4 * i, end=start + 0.4 * i + 0.3,
                                  speaker=speaker)
            for i, t in enumerate(text.split())]


def utterance(*turns, speaker):
    """One Deepgram utterance holding several quick turns, as (speaker, text)."""
    ws, t = [], 0.0
    for spk, text in turns:
        ws += words(text, t, spk)
        t = ws[-1].end + 0.05  # no pause between turns
    return types.SimpleNamespace(start=ws[0].start, end=ws[-1].end, speaker=speaker,
                                 transcript=" ".join(text for _, text in turns),
                                 words=ws)


def render(*utterances, diarize=True):
    response = types.SimpleNamespace(
        results=types.SimpleNamespace(utterances=list(utterances), channels=[]),
        metadata=types.SimpleNamespace(duration=10.0, request_id="test"))
    text = th.build_transcript_text(
        response, source=Path("talk.wav"), language="en", diarize=diarize,
        keyterms=[], mip_opt_out=True, speaker_names=[], model="nova-3")
    return text.split("-" * 60, 1)[1]


def test_quick_turns_inside_one_utterance_are_split_by_word_speaker():
    # Deepgram gave the whole utterance speaker 1; the words say 0, 1, 0.
    body = render(utterance((0, "How many beds?"), (1, "Six raised beds."),
                            (0, "Great."), speaker=1))
    blocks = [b.strip().splitlines() for b in body.strip().split("\n\n")]
    assert [b[0].split("  ")[0] for b in blocks] == ["Speaker 0", "Speaker 1", "Speaker 0"]
    assert [b[1].strip() for b in blocks] == ["How many beds?", "Six raised beds.", "Great."]


def test_one_speaker_keeps_the_utterance_text_and_merges_with_the_next():
    body = render(utterance((0, "Good morning."), speaker=0),
                  utterance((0, "Thanks for coming."), speaker=0))
    assert body.count("Speaker 0") == 1
    assert "Good morning. Thanks for coming." in body


def test_an_utterance_without_words_keeps_its_own_speaker():
    bare = types.SimpleNamespace(start=0.0, end=1.0, speaker=2,
                                 transcript="Hello there.", words=[])
    body = render(bare)
    assert "Speaker 2" in body and "Hello there." in body


def test_without_diarization_the_utterances_stay_as_they_are():
    body = render(utterance((0, "How many beds?"), (1, "Six."), speaker=1),
                  diarize=False)
    assert "Speaker" not in body and "How many beds? Six." in body
