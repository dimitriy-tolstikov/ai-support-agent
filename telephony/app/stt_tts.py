"""демонстрирует: подменяемые STT/TTS-провайдеры — OpenAI-совместимые API (base_url из env)
и mock-режим (STT_PROVIDER=mock / TTS_PROVIDER=mock) для работы без внешних ключей."""
import asyncio
import io
import logging
import math
import os
import struct
import wave
from collections.abc import AsyncIterator

import httpx

log = logging.getLogger("stt_tts")

STT_PROVIDER = os.environ.get("STT_PROVIDER", "mock")
STT_BASE_URL = os.environ.get("STT_BASE_URL", "https://api.openai.com/v1")
STT_API_KEY = os.environ.get("STT_API_KEY", "")
TTS_PROVIDER = os.environ.get("TTS_PROVIDER", "mock")
TTS_BASE_URL = os.environ.get("TTS_BASE_URL", "https://api.openai.com/v1")
TTS_API_KEY = os.environ.get("TTS_API_KEY", "")

# Скрипт mock-распознавания: каждая реплика звонящего -> следующая строка
MOCK_TRANSCRIPTS = [
    "здравствуйте, где мой заказ 1001",
    "а когда он приедет, создайте тикет",
    "спасибо, до свидания",
]


def pcm_to_wav(pcm16: bytes, rate: int = 16000) -> bytes:
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(pcm16)
    return buf.getvalue()


async def transcribe(pcm16: bytes, utterance_no: int) -> str:
    """Финальный транскрипт реплики. Mock — по скрипту; real — OpenAI-совместимый Whisper API."""
    if STT_PROVIDER == "mock":
        text = MOCK_TRANSCRIPTS[min(utterance_no, len(MOCK_TRANSCRIPTS) - 1)]
        # частичные гипотезы, как у потокового STT
        words = text.split()
        for i in range(1, len(words) + 1):
            log.info("stt partial: %s", " ".join(words[:i]))
            await asyncio.sleep(0.005)
        return text
    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.post(
            f"{STT_BASE_URL}/audio/transcriptions",
            headers={"Authorization": f"Bearer {STT_API_KEY}"},
            files={"file": ("speech.wav", pcm_to_wav(pcm16), "audio/wav")},
            data={"model": "whisper-1"},
        )
        resp.raise_for_status()
        return resp.json()["text"]


def _tone(freq: float, ms: int, rate: int = 16000) -> bytes:
    n = rate * ms // 1000
    return b"".join(
        struct.pack("<h", int(6000 * math.sin(2 * math.pi * freq * i / rate))) for i in range(n)
    )


async def synthesize(text: str) -> AsyncIterator[bytes]:
    """Потоковый TTS: отдаёт PCM s16le 16кГц чанками. Mock — тональные посылки по длине текста."""
    if TTS_PROVIDER == "mock":
        chunks = max(2, min(10, len(text) // 25))
        for i in range(chunks):
            yield _tone(440 + 40 * (i % 3), 250)
            await asyncio.sleep(0)
        return
    async with httpx.AsyncClient(timeout=60) as client:
        async with client.stream(
            "POST",
            f"{TTS_BASE_URL}/audio/speech",
            headers={"Authorization": f"Bearer {TTS_API_KEY}"},
            json={"model": "tts-1", "voice": "alloy", "input": text, "response_format": "pcm"},
        ) as resp:
            resp.raise_for_status()
            async for chunk in resp.aiter_bytes(4096):
                yield chunk
