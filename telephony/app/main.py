"""демонстрирует: точку входа телефонии — RTP endpoint (UDP), ARI Stasis-приложение,
HTTP-раздачу записей разговоров (/recordings)."""
import asyncio
import logging
import os
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer

from .ari import AriApp
from .pipeline import BACKEND_URL, SessionManager, _http
from .rtp import RtpProtocol

log = logging.getLogger("main")

RTP_LISTEN_PORT = int(os.environ.get("RTP_LISTEN_PORT", "10000"))
RECORDINGS_DIR = os.environ.get("RECORDINGS_DIR", "/recordings")
RECORDINGS_PORT = int(os.environ.get("RECORDINGS_PORT", "8090"))


def serve_recordings() -> None:
    """Отдаёт wav-записи разговоров по ссылке http://host:8090/<file>."""
    handler = partial(SimpleHTTPRequestHandler, directory=RECORDINGS_DIR)
    ThreadingHTTPServer(("0.0.0.0", RECORDINGS_PORT), handler).serve_forever()


async def keepalive() -> None:
    """Держим keep-alive соединение к backend тёплым (uvicorn рвёт idle через 5с)."""
    while True:
        try:
            await _http.get(f"{BACKEND_URL}/healthz")
        except Exception:  # noqa: BLE001
            pass
        await asyncio.sleep(3)


async def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")
    loop = asyncio.get_running_loop()

    sessions = SessionManager()
    await loop.create_datagram_endpoint(
        lambda: RtpProtocol(sessions.on_audio),
        local_addr=("0.0.0.0", RTP_LISTEN_PORT),
    )
    log.info("RTP listener on udp/%d", RTP_LISTEN_PORT)

    loop.run_in_executor(None, serve_recordings)
    log.info("recordings on http://0.0.0.0:%d", RECORDINGS_PORT)

    asyncio.create_task(keepalive())
    await AriApp().run()  # бесконечный цикл с реконнектом


if __name__ == "__main__":
    asyncio.run(main())
