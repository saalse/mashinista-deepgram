"""Two-channel call transcripts and the command line, on synthetic data only.

Deepgram is replaced by a fake client; nothing is uploaded.
"""
import json
import shutil
import sys
import types
import wave
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parents[1] / "skills" / "transcribe-deepgram" / "scripts"
sys.path.insert(0, str(SCRIPTS))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import call_lines as cl  # noqa: E402
import transcribe  # noqa: E402
import transcribe_call  # noqa: E402
import transcribe_helpers  # noqa: E402
from synth import silence, speechlike, write_caf, write_stereo  # noqa: E402


def word(text, start, *, speaker=None, language=None):
    w = {"word": text.lower().strip(".,!?"), "punctuated_word": text,
         "start": start, "end": start + 0.3, "confidence": 0.9}
    if speaker is not None:
        w["speaker"] = speaker
    if language is not None:
        w["language"] = language
    return w


def utt(channel, start, text, *, speaker=None, language=None):
    words = [word(t, start + 0.4 * i, speaker=speaker, language=language)
             for i, t in enumerate(text.split())]
    return {"channel": channel, "start": start, "end": words[-1]["end"],
            "transcript": text, "words": words}


def response(*utterances):
    return {"metadata": {"duration": 120.0, "request_id": "test"},
            "results": {"channels": [], "utterances": list(utterances)}}


# --- Labels -----------------------------------------------------------------

def test_two_speakers_come_from_the_channel():
    data = response(
        utt(1, 5.0, "How was the trip?", speaker=0),
        utt(0, 1.0, "Hello there, can you hear me?", speaker=1),  # ignored
        utt(0, 8.0, "It was long but fine.", speaker=0),
    )
    lines = cl.call_lines(data, far_diarized=False)
    cl.label_lines(lines, [])
    assert [(l["label"], l["start"]) for l in lines] == [
        ("Me", 1.0), ("Speaker 1", 5.0), ("Me", 8.0)]


def test_three_speakers_diarize_only_the_far_side():
    data = response(
        utt(0, 0.0, "Shall we start with the budget?", speaker=2),
        utt(1, 3.0, "Yes, I have the numbers ready.", speaker=4),
        {"channel": 1, "start": 7.0, "end": 9.0, "transcript": "Good. Me too.",
         "words": [word("Good.", 7.0, speaker=1), word("Me", 8.0, speaker=4),
                   word("too.", 8.4, speaker=4)]},
        utt(1, 12.0, "Let me add one thing.", speaker=1),
        utt(0, 15.0, "Go ahead.", speaker=4),
    )
    lines = cl.call_lines(data, far_diarized=True)
    cl.label_lines(lines, ["Alex", "Dana", "Lee"])
    got = [(l["label"], l["text"]) for l in lines]
    assert got == [
        ("Alex", "Shall we start with the budget?"),
        ("Dana", "Yes, I have the numbers ready."),
        ("Lee", "Good."),           # a speaker change inside one utterance
        ("Dana", "Me too."),
        ("Lee", "Let me add one thing."),
        ("Alex", "Go ahead."),       # channel 0 stays Me whatever its speaker
    ]
    cl.label_lines(lines, [])
    assert [l["label"] for l in lines] == [
        "Me", "Speaker 1", "Speaker 2", "Speaker 1", "Speaker 2", "Me"]


def test_resolve_diarize():
    assert transcribe_call.resolve_diarize(None, call_mode=False, speaker_names=[])
    assert not transcribe_call.resolve_diarize(None, call_mode=True, speaker_names=[])
    assert not transcribe_call.resolve_diarize(None, call_mode=True, speaker_names=["A"])
    assert transcribe_call.resolve_diarize(None, call_mode=True, speaker_names=["A", "B"])
    assert transcribe_call.resolve_diarize(True, call_mode=True, speaker_names=[])
    assert not transcribe_call.resolve_diarize(False, call_mode=False, speaker_names=[])


# --- Cleanup ----------------------------------------------------------------

LONG_EN = "we should look at the plan for next week before friday"
LONG_DE = "wir sollten den plan für die nächste woche vor freitag ansehen"


def test_short_odd_language_lines_and_fillers_are_dropped():
    data = response(
        utt(0, 0.0, LONG_EN, language="en"),
        utt(0, 10.0, LONG_DE, language="de"),
        utt(0, 20.0, LONG_EN, language="en"),
        utt(0, 25.0, LONG_DE, language="de"),
        *[utt(0, 60.0 + 10 * i, LONG_EN, language="en") for i in range(6)],
        utt(0, 30.0, "Okay, sounds good.", language="en"),      # kept
        utt(0, 33.0, "Ja, genau.", language="de"),              # kept
        utt(0, 36.0, "Perėjo kol.", language="lt"),             # odd language
        utt(0, 38.0, "Dale, chica.", language="es"),            # reads as Latin:
                                                                # cannot tell
        utt(0, 40.0, "Mhmm.", language="en"),                   # filler
        utt(0, 45.0, "Uh-huh, mm.", language="en"),             # filler
        utt(0, 50.0, "una frase larga que no tiene sentido pero sigue",
            language="es"),                                     # long: kept
        *[utt(1, 100.0 + 10 * i, LONG_EN, language="en") for i in range(6)],
        utt(1, 12.0, "Καλά.", language="en"),                   # odd script
        utt(1, 14.0, "No.", language="en"),                     # a real word: kept
    )
    lines = cl.call_lines(data, far_diarized=False)
    kept, dropped = cl.drop_noise_lines(lines)
    texts = [l["text"] for l in kept]
    assert "Okay, sounds good." in texts and "Ja, genau." in texts
    assert "No." in texts
    assert any(t.startswith("una frase larga") for t in texts)
    assert "Perėjo kol." not in texts and "Mhmm." not in texts
    assert "Καλά." not in texts
    assert dropped == {"fillers": 2, "unexpected language": 1, "unexpected script": 1}


def test_a_language_spoken_in_short_phrases_keeps_its_script():
    """Short English terms in a mostly Greek channel are content, not noise,
    even when the tags say otherwise."""
    long_el = "θα πρέπει να δούμε το σχέδιο για την επόμενη εβδομάδα πριν"
    data = response(
        *[utt(0, 10.0 * i, long_el, language="el") for i in range(6)],
        *[utt(0, 70.0 + 3 * i, "surface capture", language="el") for i in range(5)],
        utt(0, 90.0, "main actor,", language="el"),
        utt(0, 95.0, "Dale, chica.", language="es"),
        utt(0, 99.0, "το σχέδιο", language="bg"),  # a mislabel of the main language
    )
    lines = cl.call_lines(data, far_diarized=False)
    kept, dropped = cl.drop_noise_lines(lines)
    texts = [l["text"] for l in kept]
    assert "main actor," in texts and texts.count("surface capture") == 5
    assert "Dale, chica." not in texts  # another script than the channel's own
    assert "το σχέδιο" in texts
    assert dropped == {"unexpected language": 1}


def test_repeats_across_channels_are_counted():
    data = response(
        utt(1, 10.0, "the shipment arrives on tuesday morning"),
        utt(0, 10.2, "the shipment arrives on tuesday morning"),   # leaked copy
        utt(0, 30.0, "the shipment arrives on tuesday morning"),   # said again later
        utt(0, 40.0, "something else entirely here"),
    )
    lines = cl.call_lines(data, far_diarized=False)
    assert cl.count_repeats(lines) == (1, 3)


# --- Transcript and command line ------------------------------------------

def test_call_transcript_header_and_order(tmp_path):
    data = response(
        utt(1, 4.0, "Thanks for joining today everyone.", language="en"),
        utt(0, 1.0, "Hi, good to see you.", language="en"),
        utt(0, 9.0, LONG_EN, language="en"),
    )
    text, counts = transcribe_call.build_call_transcript(
        data, source=tmp_path / "2026-11-05 12-33-58.m4a", language="en",
        far_diarized=False, keyterms=[], mip_opt_out=True, speaker_names=[],
        model="nova-3", details=["you (left): peak -8 dB, average -35 dB"],
        keep_all_lines=False)
    assert "Anyone in the room with you is on your mic" in text
    assert "MIP opt-out ON" in text and "call, 2 channels" in text
    header, body, footer = text.split("-" * 60)
    assert "peak -8 dB" in footer and "peak -" not in header
    assert "request_id test" in footer and "Length:     02:00" in header
    assert body.index("Me  [00:01") < body.index("Speaker 1  [00:04") < body.index("Me  [00:09")
    assert counts["repeated"] == 0


def test_price_counts_each_channel():
    one = transcribe.estimate_cost(3600, model="nova-3", language="multi", keyterms=[])
    two = transcribe.estimate_cost(3600, model="nova-3", language="multi", keyterms=[],
                                   channels=2)
    assert two == pytest.approx(2 * one)


needs_ffmpeg = pytest.mark.skipif(transcribe_helpers.find_tool("ffmpeg") is None,
                                  reason="the channel check and uploads need ffmpeg")


@pytest.fixture
def nistka(monkeypatch, tmp_path):
    """A stand-in for ~/Documents/Nistka."""
    folder = tmp_path / "Nistka"
    folder.mkdir()
    monkeypatch.setattr(transcribe_call, "NISTKA_DIR", folder)
    return folder


@pytest.fixture
def no_key(monkeypatch, tmp_path):
    monkeypatch.delenv("DEEPGRAM_API_KEY", raising=False)
    monkeypatch.setattr(transcribe, "ENV_FILES", [tmp_path / "missing.env"])


class FakeDeepgram:
    """Records the request instead of sending it."""

    calls: list = []

    def __init__(self, api_key):
        self.listen = types.SimpleNamespace(v1=types.SimpleNamespace(
            media=types.SimpleNamespace(transcribe_file=self.transcribe_file)))

    def transcribe_file(self, *, request, request_options, **opts):
        FakeDeepgram.calls.append((request, opts))
        data = response(utt(0, 1.0, LONG_EN, language="en"),
                        utt(1, 6.0, "Thanks, that works for me.", speaker=0,
                            language="en"))
        return types.SimpleNamespace(
            model_dump=lambda mode="json": data,
            results=types.SimpleNamespace(utterances=[], channels=[]),
            metadata=types.SimpleNamespace(duration=10.0, request_id="test"))


@pytest.fixture
def fake_deepgram(monkeypatch):
    FakeDeepgram.calls = []
    dg = types.ModuleType("deepgram")
    dg.DeepgramClient = FakeDeepgram
    core = types.ModuleType("deepgram.core")
    api_error = types.ModuleType("deepgram.core.api_error")
    api_error.ApiError = type("ApiError", (Exception,), {})
    for name, mod in [("deepgram", dg), ("deepgram.core", core),
                      ("deepgram.core.api_error", api_error)]:
        monkeypatch.setitem(sys.modules, name, mod)
    monkeypatch.setenv("DEEPGRAM_API_KEY", "test-key-not-real")
    return FakeDeepgram


def a_call(folder: Path, name="2026-11-05 12-33-58.wav", *, left=True, right=True,
           seconds=8.0) -> Path:
    return write_stereo(folder / name,
                        speechlike(seconds, seed=1) if left else silence(seconds),
                        speechlike(seconds, seed=2) if right else silence(seconds))


def sent_channels(audio: bytes, tmp_path: Path) -> int:
    probe = transcribe_helpers.find_tool("ffprobe")
    f = tmp_path / "sent.bin"
    f.write_bytes(audio)
    import subprocess
    out = subprocess.run([probe, "-v", "error", "-show_entries", "stream=channels",
                          "-of", "csv=p=0", str(f)], capture_output=True, text=True)
    return int(out.stdout.strip())


@needs_ffmpeg
@pytest.mark.parametrize("speakers, me, far_diarize, far_label", [
    (None, None, False, "Speaker 1"),
    ("Dana", None, False, "Dana"),
    ("Dana", "Alex", False, "Dana"),
    ("Dana,Lee", None, True, "Speaker 1")])
def test_a_nistka_call_goes_up_as_it_is_on_two_channels(
        nistka, fake_deepgram, speakers, me, far_diarize, far_label):
    rec = a_call(nistka)
    argv = ([str(rec)] + (["--speakers", speakers] if speakers else [])
            + (["--me", me] if me else []))
    assert transcribe.main(argv) == 0
    (audio, opts), = fake_deepgram.calls
    assert audio == rec.read_bytes()  # no re-encode, no downmix
    assert opts["multichannel"] is True
    assert opts["diarize"] is far_diarize
    assert opts["mip_opt_out"] is True
    names = ([me] if me else []) + (speakers.split(",") if speakers else [])
    assert opts.get("keyterm", []) == names
    text = (nistka / "2026-11-05 12-33-58.transcript.txt").read_text()
    assert f"{me or 'Me'}  [00:01" in text
    assert f"{far_label}  [00:06" in text
    assert "the channels stayed apart" in text
    assert "you (left): peak" in text.split("-" * 60)[-1]
    saved = json.loads((nistka / "2026-11-05 12-33-58.response.json").read_text())
    assert saved["metadata"]["request_id"] == "test"


@needs_ffmpeg
def test_a_big_call_is_never_cut_down_to_mono(nistka, fake_deepgram, monkeypatch):
    monkeypatch.setattr(transcribe, "EXTRACT_ABOVE_MB", 0)
    rec = a_call(nistka)
    assert transcribe.main([str(rec)]) == 0
    (audio, opts), = fake_deepgram.calls
    assert audio == rec.read_bytes() and opts["multichannel"] is True


@needs_ffmpeg
def test_a_leftover_caf_goes_up_as_two_lossless_channels(nistka, fake_deepgram,
                                                         tmp_path):
    ffmpeg = transcribe_helpers.find_tool("ffmpeg")
    rec = write_caf(nistka / "2026-11-05 12-38-10 source.caf",
                    speechlike(6, seed=3), speechlike(6, seed=4), ffmpeg)
    assert transcribe.main([str(rec)]) == 0
    (audio, opts), = fake_deepgram.calls
    assert audio[:4] == b"fLaC" and sent_channels(audio, tmp_path) == 2
    assert opts["multichannel"] is True
    assert (nistka / "2026-11-05 12-38-10 source.transcript.txt").is_file()


@needs_ffmpeg
def test_a_stereo_file_elsewhere_is_ordinary_unless_call(tmp_path, nistka,
                                                         fake_deepgram):
    rec = a_call(tmp_path / "elsewhere")
    assert transcribe.main([str(rec)]) == 0
    assert transcribe.main([str(rec), "--call"]) == 0
    (_, plain), (_, call) = fake_deepgram.calls
    assert "multichannel" not in plain and plain["diarize"] is True
    assert call["multichannel"] is True


@needs_ffmpeg
def test_no_call_turns_it_off_in_the_nistka_folder(nistka, fake_deepgram):
    rec = a_call(nistka)
    assert transcribe.main([str(rec), "--no-call"]) == 0
    (_, opts), = fake_deepgram.calls
    assert "multichannel" not in opts and opts["diarize"] is True


@needs_ffmpeg
def test_call_refuses_a_mono_file(tmp_path, fake_deepgram):
    mono = tmp_path / "voice.wav"
    with wave.open(str(mono), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(16000)
        w.writeframes(b"\0\0" * 16000)
    with pytest.raises(SystemExit):
        transcribe.main([str(mono), "--call"])
    assert fake_deepgram.calls == []


@needs_ffmpeg
@pytest.mark.parametrize("left, right, kept", [(True, False, 0), (False, True, 1)])
def test_one_silent_channel_sends_the_other_alone(nistka, fake_deepgram, tmp_path,
                                                  capsys, left, right, kept):
    rec = a_call(nistka, left=left, right=right)
    assert transcribe.main([str(rec), "--speakers", "Dana"]) == 0
    (audio, opts), = fake_deepgram.calls
    assert "multichannel" not in opts and opts["diarize"] is True
    assert opts["keyterm"] == ["Dana"]
    assert audio[:4] == b"OggS" and sent_channels(audio, tmp_path) == 1
    sent = tmp_path / "sent.ogg"
    sent.write_bytes(audio)
    peak, _ = transcribe_call.channel_levels(sent)[0]
    assert peak > transcribe_call.SILENT_PEAK_DB  # the channel with sound
    err = capsys.readouterr().err
    assert ("right) is silent" if kept == 0 else "left) is silent") in err
    text = (nistka / "2026-11-05 12-33-58.transcript.txt").read_text()
    assert "Diarization:on" in text


@needs_ffmpeg
def test_both_channels_silent_stops_before_upload(nistka, fake_deepgram):
    rec = a_call(nistka, left=False, right=False)
    with pytest.raises(SystemExit):
        transcribe.main([str(rec)])
    assert fake_deepgram.calls == []


@needs_ffmpeg
def test_check_on_a_call_needs_no_key_and_writes_nothing(nistka, no_key, capsys):
    rec = a_call(nistka)
    before = sorted(p.name for p in nistka.iterdir())
    assert transcribe.main([str(rec), "--check", "--lang", "en",
                            "--speakers", "Dana"]) == 0
    err = capsys.readouterr().err
    assert "Both channels have sound" in err
    assert "Settings: English, you and the other person on separate channels" in err
    assert "labelled Me and Dana" in err and "two channels billed separately" in err
    assert "Nothing was uploaded or charged." in err
    assert sorted(p.name for p in nistka.iterdir()) == before


@needs_ffmpeg
def test_output_puts_the_files_elsewhere_and_names_them(nistka, fake_deepgram,
                                                        tmp_path):
    rec = a_call(nistka)
    out_dir = tmp_path / "archive"
    out_dir.mkdir()
    assert transcribe.main([str(rec), "--output", str(out_dir / "recording_ABC")]) == 0
    text = (out_dir / "recording_ABC.transcript.txt").read_text()
    assert text.startswith("Transcript: recording_ABC\n")
    assert f"Source:     {out_dir / 'recording_ABC'}" in text
    assert (out_dir / "recording_ABC.response.json").is_file()
    assert not (nistka / "2026-11-05 12-33-58.transcript.txt").exists()


@needs_ffmpeg
def test_output_works_outside_a_call(tmp_path, fake_deepgram):
    rec = a_call(tmp_path / "elsewhere")
    assert transcribe.main([str(rec), "--output", str(tmp_path / "plain")]) == 0
    text = (tmp_path / "plain.transcript.txt").read_text()
    assert text.startswith("Transcript: plain\n")


@pytest.mark.parametrize("bad", ["missing/folder/name", "out.transcript.txt"])
def test_output_refuses_bad_targets(tmp_path, fake_deepgram, bad):
    rec = a_call(tmp_path / "elsewhere")
    with pytest.raises(SystemExit):
        transcribe.main([str(rec), "--output", str(tmp_path / bad)])
    assert fake_deepgram.calls == []


def test_placeholders_label_but_never_become_keyterms():
    is_placeholder = transcribe_call.is_placeholder
    assert is_placeholder("Speaker A") and is_placeholder("speaker 2")
    assert not is_placeholder("Speakerman") and not is_placeholder("Dana")
    assert transcribe_call.with_names([], ["Dana", "Speaker A", "Speaker B"]) == ["Dana"]


def test_names_join_the_keyterms_once():
    assert transcribe_call.with_names(["Dana", "Widget"], ["dana", "Lee"]) == [
        "Dana", "Widget", "Lee"]
    assert transcribe_call.call_labels(None, ["Dana"]) == ["Me", "Dana"]
    assert transcribe_call.call_labels("Alex", ["Dana", "Lee"]) == ["Alex"]


def test_settings_line_names_the_labels():
    settings_line = transcribe_helpers.settings_line
    one = settings_line(language="en", call_mode=True, diarize=False,
                        keyterms=[], mip_opt_out=True,
                        labels=["Me", "Dana"])
    assert one.startswith("Settings: English, ") and "labelled Me and Dana" in one
    many = settings_line(language="xx", call_mode=True, diarize=True,
                         keyterms=["Dana"], mip_opt_out=True, labels=["Me"])
    assert "language xx" in many and "Speaker 1, 2" in many


def test_length_rounds_to_the_nearest_minute():
    assert transcribe_helpers.fmt_length(3347) == "56 min"
    assert transcribe_helpers.fmt_length(6700) == "1 h 52 min"
    assert transcribe_helpers.fmt_length(45) == "45 s"


def test_a_few_repeats_are_explained():
    assert transcribe_call.repeat_text(0, 500).endswith("the channels stayed apart")
    assert "a few are normal" in transcribe_call.repeat_text(2, 500)
    assert "apart" not in transcribe_call.repeat_text(50, 500)
