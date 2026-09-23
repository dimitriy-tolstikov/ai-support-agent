"""демонстрирует: ARI Stasis-приложение — answer, bridge, ExternalMedia (RTP ulaw) и запись разговора."""
import asyncio
import logging
import os

import httpx
import websockets

log = logging.getLogger("ari")

ARI_URL = os.environ.get("ARI_URL", "http://localhost:8088")
ARI_USER = os.environ.get("ARI_USER", "ari")
ARI_PASSWORD = os.environ.get("ARI_PASSWORD", "ari_secret")
RTP_HOST = os.environ.get("RTP_ADVERTISE_HOST", "telephony")   # куда Asterisk шлёт RTP
RTP_PORT = int(os.environ.get("RTP_LISTEN_PORT", "10000"))
APP = "ai-support"


class AriApp:
    def __init__(self) -> None:
        self._http = httpx.AsyncClient(base_url=f"{ARI_URL}/ari",
                                       auth=(ARI_USER, ARI_PASSWORD), timeout=30)
        self.calls: dict[str, dict] = {}

    async def run(self) -> None:
        """WS-подписка на события Stasis с реконнектом."""
        ws_url = (f"{ARI_URL.replace('http', 'ws')}/ari/events"
                  f"?app={APP}&subscribeAll=true&api_key={ARI_USER}:{ARI_PASSWORD}")
        while True:
            try:
                async with websockets.connect(ws_url) as ws:
                    log.info("ARI websocket connected")
                    import json
                    async for raw in ws:
                        await self._on_event(json.loads(raw))
            except Exception as exc:  # noqa: BLE001
                log.warning("ARI connection lost: %s; retry in 5s", exc)
                await asyncio.sleep(5)

    async def _on_event(self, event: dict) -> None:
        etype = event.get("type")
        if etype == "StasisStart":
            name = event["channel"]["name"]
            if name.startswith("Local/") and name.endswith(";1"):
                # originate через Local-канал: «заглушечное» плечо ;1 пропускаем,
                # работаем с плечом ;2, которое исполняет dialplan
                return
            if name.startswith("UnicastRTP/") or name.startswith("Snoop/"):
                # наш же ExternalMedia/Snoop-канал — не обрабатываем как новый звонок
                return
            await self._start_call(event["channel"])
        elif etype == "StasisEnd":
            self.calls.pop(event["channel"]["id"], None)
            log.info("call ended: %s", event["channel"]["id"])

    async def _start_call(self, channel: dict) -> None:
        caller_id = channel["id"]
        log.info("StasisStart: %s", caller_id)
        await self._http.post(f"/channels/{caller_id}/answer")

        resp = await self._http.post("/bridges", json={"type": "mixing"})
        bridge_id = resp.json()["id"]
        await self._http.post(f"/bridges/{bridge_id}/addChannel", json={"channel": caller_id})

        # ExternalMedia: Asterisk устанавливает RTP (ulaw) в наш обработчик
        resp = await self._http.post("/channels/externalMedia", params={
            "app": APP,
            "external_host": f"{RTP_HOST}:{RTP_PORT}",
            "encapsulation": "rtp",
            "transport": "udp",
            "connection_type": "client",
            "format": "ulaw",
            "direction": "both",
        })
        em_id = resp.json()["id"]
        await self._http.post(f"/bridges/{bridge_id}/addChannel", json={"channel": em_id})

        # Запись разговора: канал в бридже записывать нельзя («Cannot record channel while in
        # bridge»), поэтому пишем через Snoop-каналы — по файлу на плечо (in/out = «стерео»)
        for name, ch in (("in", caller_id), ("out", em_id)):
            resp = await self._http.post(f"/channels/{ch}/snoop", params={
                "app": APP, "spy": "both", "whisper": "none",
            })
            snoop_id = resp.json()["id"]
            await self._http.post(f"/channels/{snoop_id}/record", params={
                "name": f"call_{caller_id[:8]}_{name}", "format": "wav",
                "maxDurationSeconds": 600, "beep": "false", "ifExists": "overwrite",
            })
        self.calls[caller_id] = {"bridge": bridge_id, "external_media": em_id}
        log.info("call %s: bridge %s, ExternalMedia %s -> %s:%d", caller_id, bridge_id, em_id, RTP_HOST, RTP_PORT)

    async def stop_playback(self, playback_id: str) -> None:
        """ARI stop playback (используется при barge-in, если ответ игрался через ARI)."""
        await self._http.delete(f"/playbacks/{playback_id}")
