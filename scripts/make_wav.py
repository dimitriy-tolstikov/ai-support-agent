"""демонстрирует: генератор тестовых WAV для sim-звонка (рече-подобные шумовые всплески 16 кГц).

    python scripts/make_wav.py
"""
import math
import random
import struct
import wave
from pathlib import Path

OUT = Path(__file__).parent / "audio"


def speech_like(seconds: float, rate: int = 16000) -> bytes:
    """Амплитудно-модулированный шум — по энергетике похож на речь (для energy-VAD)."""
    random.seed(7)
    frames = bytearray()
    n = int(seconds * rate)
    for i in range(n):
        env = abs(math.sin(2 * math.pi * 4 * i / rate)) ** 0.7  # «слоги» ~4 Гц
        sample = int(12000 * env * (random.random() * 2 - 1))
        frames += struct.pack("<h", sample)
    return bytes(frames)


def write_wav(path: Path, pcm: bytes, rate: int = 16000) -> None:
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(pcm)
    print(f"written {path} ({len(pcm) / 2 / rate:.1f} s)")


if __name__ == "__main__":
    OUT.mkdir(exist_ok=True)
    write_wav(OUT / "utt1.wav", speech_like(1.5))
    write_wav(OUT / "utt2.wav", speech_like(1.0))
