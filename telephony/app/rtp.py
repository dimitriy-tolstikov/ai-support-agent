"""демонстрирует: RTP-транспорт — приём ulaw 8кГц от Asterisk (ExternalMedia) и отправка обратно,
ресемплинг 8↔16 кГц через audioop, пакетизация 20 мс."""
import asyncio
import audioop
import logging
import struct
from collections.abc import Callable

log = logging.getLogger("rtp")

SAMPLE_RATE_8K = 8000
SAMPLE_RATE_16K = 16000
FRAME_MS = 20
ULAW_FRAME = 160          # байт ulaw за 20 мс при 8 кГц


def ulaw_to_pcm16(data: bytes) -> bytes:
    """RTP payload (ulaw 8кГц) -> PCM s16le 16кГц для VAD/STT."""
    pcm8 = audioop.ulaw2lin(data, 2)
    return audioop.ratecv(pcm8, 2, 1, SAMPLE_RATE_8K, SAMPLE_RATE_16K, None)[0]


def pcm16_to_ulaw_frames(pcm16: bytes) -> list[bytes]:
    """PCM s16le 16кГц -> список ulaw-фреймов по 20 мс для RTP."""
    pcm8 = audioop.ratecv(pcm16, 2, 1, SAMPLE_RATE_16K, SAMPLE_RATE_8K, None)[0]
    ulaw = audioop.lin2ulaw(pcm8, 2)
    return [ulaw[i : i + ULAW_FRAME] for i in range(0, len(ulaw) - ULAW_FRAME + 1, ULAW_FRAME)]


class RtpSender:
    """Очередь PCM-чанков -> paced-отправка RTP (каждые 20 мс), с flush для barge-in."""

    def __init__(self, transport: asyncio.DatagramTransport, remote: tuple[str, int]) -> None:
        self._transport = transport
        self._remote = remote
        self._queue: asyncio.Queue[bytes] = asyncio.Queue()
        self._seq = 0
        self._ts = 0
        self._ssrc = 0x1234ABCD
        self._busy = False
        self._task = asyncio.create_task(self._run())

    @property
    def playing(self) -> bool:
        """Идёт ли сейчас воспроизведение (очередь или текущий чанк)."""
        return self._busy or not self._queue.empty()

    def enqueue(self, pcm16: bytes) -> None:
        self._queue.put_nowait(pcm16)

    def flush(self) -> None:
        """Barge-in: выбрасываем всё невоспроизведённое аудио."""
        while not self._queue.empty():
            self._queue.get_nowait()

    async def _run(self) -> None:
        while True:
            pcm16 = await self._queue.get()
            self._busy = True
            for frame in pcm16_to_ulaw_frames(pcm16):
                header = struct.pack("!BBHII", 0x80, 0, self._seq & 0xFFFF,
                                     self._ts & 0xFFFFFFFF, self._ssrc)
                self._transport.sendto(header + frame, self._remote)
                self._seq += 1
                self._ts += ULAW_FRAME
                await asyncio.sleep(FRAME_MS / 1000)  # реальное время воспроизведения
            self._busy = False


class RtpProtocol(asyncio.DatagramProtocol):
    """UDP endpoint: создаёт голосовую сессию на первый пакет с нового адреса."""

    def __init__(self, on_audio: Callable[[tuple[str, int], bytes, "RtpSender"], None]) -> None:
        self._on_audio = on_audio
        self._senders: dict[tuple[str, int], RtpSender] = {}

    def connection_made(self, transport: asyncio.BaseTransport) -> None:
        self._transport = transport  # type: ignore[assignment]

    def datagram_received(self, data: bytes, addr: tuple[str, int]) -> None:
        if len(data) < 13:
            return
        payload = data[12:]  # RTP-заголовок 12 байт без CSRC
        sender = self._senders.get(addr)
        if sender is None:
            sender = RtpSender(self._transport, addr)  # type: ignore[arg-type]
            self._senders[addr] = sender
            log.info("new RTP source %s:%d", *addr)
        self._on_audio(addr, ulaw_to_pcm16(payload), sender)
