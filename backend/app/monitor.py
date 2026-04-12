import asyncio
from datetime import datetime
from typing import Any

from fastapi import WebSocket


class MonitorHub:
    def __init__(self) -> None:
        self._connections: set[WebSocket] = set()
        self._lock = asyncio.Lock()

    async def connect(self, websocket: WebSocket) -> None:
        await websocket.accept()
        async with self._lock:
            self._connections.add(websocket)

    async def disconnect(self, websocket: WebSocket) -> None:
        async with self._lock:
            if websocket in self._connections:
                self._connections.remove(websocket)

    async def broadcast(self, payload: dict[str, Any]) -> None:
        if not self._connections:
            return

        enriched_payload = {
            "timestamp": datetime.utcnow().isoformat() + "Z",
            **payload,
        }

        stale: list[WebSocket] = []
        for websocket in self._connections:
            try:
                await websocket.send_json(enriched_payload)
            except Exception:
                stale.append(websocket)

        if stale:
            async with self._lock:
                for websocket in stale:
                    self._connections.discard(websocket)


monitor_hub = MonitorHub()
