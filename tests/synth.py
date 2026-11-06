"""Synthetic stereo call recordings for the tests. No real recordings.

Left channel = the user's mic, right channel = the others, as Nistka records.
Standard library only: the sound is shaped noise, loud enough to count as
speech for the channel check, or exact digital silence.
"""
from __future__ import annotations

import random
import struct
import subprocess
import wave
from pathlib import Path

RATE = 16000


def speechlike(seconds: float, *, seed: int = 0, level: float = 6000.0) -> list[int]:
    """Noise with a syllable-rate envelope, as 16-bit samples."""
    rng = random.Random(seed)
    n = int(seconds * RATE)
    out = []
    for i in range(n):
        env = 0.5 + 0.5 * ((i // (RATE // 5)) % 2)  # five syllables a second
        out.append(int(max(-32767, min(32767, rng.gauss(0, level) * env))))
    return out


def silence(seconds: float) -> list[int]:
    return [0] * int(seconds * RATE)


def write_stereo(path: Path, left: list[int], right: list[int]) -> Path:
    """A 16-bit stereo WAV: left = you, right = the others."""
    n = min(len(left), len(right))
    frames = b"".join(struct.pack("<hh", left[i], right[i]) for i in range(n))
    path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(path), "wb") as w:
        w.setnchannels(2)
        w.setsampwidth(2)
        w.setframerate(RATE)
        w.writeframes(frames)
    return path


def write_caf(path: Path, left: list[int], right: list[int], ffmpeg: str) -> Path:
    """The same, as the 16-bit PCM CAF Nistka writes while recording."""
    wav = path.with_suffix(".tmp.wav")
    write_stereo(wav, left, right)
    subprocess.run([ffmpeg, "-nostdin", "-loglevel", "error", "-y", "-i", str(wav),
                    "-c:a", "pcm_s16le", str(path)], check=True)
    wav.unlink()
    return path
