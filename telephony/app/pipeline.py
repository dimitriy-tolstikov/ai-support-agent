"""демонстрирует: realtime-конвейер VAD → STT → LLM (тот же tool-loop, что и в чате, через backend)
→ TTS → RTP playback, с barge-in и логированием задержки «конец реплики → начало ответа»."""
import asyncio
import audioop
import logging
import os
import time

import httpx
import webrtcvad

from .rtp import RtpSender
from .stt_tts import STT_PROVIDER, synthesize, transcribe

log = logging.getLogger("pipeline")

BACKEND_URL = os.environ.get("BACKEND_URL", "http://backend:8000")
FRAME_16K = 640          # байт PCM s16le за 20 мс при 16 кГц
SILENCE_MS_END = 700     # пауза = конец реплики
MIN_UTTERANCE_MS = 300   # короче — считаем шумом

# общий клиент на все сессии: keep-alive соединение (пер-сессионный клиент даёт ~0.5с на TCP/DNS)
_http = httpx.AsyncClient(timeout=60)


class VoiceSession:
    """Одна голосовая сессия (звонок или sim): VAD-стейт, barge-in, очередь ходов."""

    def __init__(self, addr: tuple[str, int], sender: RtpSender) -> None:
        self.addr = addr
        self.sender = sender
        self.vad = webrtcvad.Vad(2)
        self.conversation_id: str | None = None
        self.utterance_no = 0
        self._buf = b""
        self._utterance = bytearray()
        self._in_speech = False
        self._silence_ms = 0
        self._play_task: asyncio.Task | None = None
        self._turn_task: asyncio.Task | None = None
        self._http = _http
        self._barged = False
        # конверсацию создаём в фоне сразу при начале сессии — установка HTTP-соединения
        # (TCP+DNS) идёт параллельно прослушиванию реплики и не входит в задержку ответа
        self._conv_task: asyncio.Task[str] = asyncio.create_task(self._create_conversation())

    # --- приём аудио -----------------------------------------------------

    def feed(self, pcm16: bytes) -> None:
        self._buf += pcm16
        while len(self._buf) >= FRAME_16K:
            frame, self._buf = self._buf[:FRAME_16K], self._buf[FRAME_16K:]
            self._process_frame(frame)

    def _is_speech(self, frame: bytes) -> bool:
        if self.vad.is_speech(frame, 16000):
            return True
        # mock-режим: sim-аудио — тоны/шум, webrtcvad их «речью» не считает;
        # разрешаем energy-based детект, чтобы конвейер работал на тестовых WAV
        if STT_PROVIDER == "mock":
            return audioop.rms(frame, 2) > 400
        return False

    def _process_frame(self, frame: bytes) -> None:
        speech = self._is_speech(frame)
        if speech:
            if self.sender.playing:
                self._barge_in()
            self._in_speech = True
            self._silence_ms = 0
            self._utterance += frame
        elif self._in_speech:
            self._silence_ms += 20
            self._utterance += frame
            if self._silence_ms >= SILENCE_MS_END:
                utterance = bytes(self._utterance)
                self._utterance.clear()
                self._in_speech = False
                self._silence_ms = 0
                if len(utterance) / 2 / 16000 * 1000 >= MIN_UTTERANCE_MS:
                    self._turn_task = asyncio.create_task(self._turn(utterance))

    # --- barge-in ----------------------------------------------------------

    def _barge_in(self) -> None:
        if not self._barged:
            log.info("barge-in: речь во время playback — останавливаю воспроизведение")
        self._barged = True
        if self._play_task:
            self._play_task.cancel()
        self.sender.flush()          # сброс буферов TTS

    # --- ход диалога -------------------------------------------------------

    async def _create_conversation(self) -> str:
        resp = await self._http.post(f"{BACKEND_URL}/api/v1/conversations",
                                     json={"title": f"Голосовой звонок {self.addr[0]}"})
        resp.raise_for_status()
        self.conversation_id = resp.json()["id"]
        log.info("voice conversation %s", self.conversation_id)
        return self.conversation_id

    async def _ensure_conversation(self) -> str:
        return await self._conv_task

    async def _turn(self, utterance: bytes) -> None:
        t_end = time.monotonic()
        transcript = await transcribe(utterance, self.utterance_no)
        self.utterance_no += 1
        log.info("stt final: %s (stt took %.0f ms)", transcript, (time.monotonic() - t_end) * 1000)

        t_llm = time.monotonic()
        conv_id = await self._ensure_conversation()
        log.info("ensure conversation took %.0f ms", (time.monotonic() - t_llm) * 1000)
        t_turn = time.monotonic()
        resp = await self._http.post(f"{BACKEND_URL}/api/v1/conversations/internal/agent-turn",
                                     json={"conversation_id": conv_id, "text": transcript})
        resp.raise_for_status()
        data = resp.json()
        log.info("agent-turn took %.0f ms", (time.monotonic() - t_turn) * 1000)
        if data["tool_calls"]:
            log.info("llm tool_calls: %s", data["tool_calls"])
        answer = data["answer"]
        log.info("llm answer: %s", answer)

        self._play_task = asyncio.create_task(self._play(answer, t_end))
        await self._play_task

    async def _play(self, text: str, t_end: float) -> None:
        first = True
        self._barged = False
        try:
            async for chunk in synthesize(text):
                if first:
                    latency_ms = (time.monotonic() - t_end) * 1000
                    log.info("latency end-of-speech -> first audio: %.0f ms (target <=500)", latency_ms)
                    first = False
                self.sender.enqueue(chunk)
        except asyncio.CancelledError:
            log.info("playback cancelled (barge-in)")
            raise


class SessionManager:
    def __init__(self) -> None:
        self.sessions: dict[tuple[str, int], VoiceSession] = {}

    def on_audio(self, addr: tuple[str, int], pcm16: bytes, sender: RtpSender) -> None:
        session = self.sessions.get(addr)
        if session is None:
            session = VoiceSession(addr, sender)
            self.sessions[addr] = session
            log.info("voice session started for %s:%d", *addr)
        session.feed(pcm16)
