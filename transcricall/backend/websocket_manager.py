from typing import Dict, Set
from fastapi import WebSocket
import asyncio


class ConnectionManager:
    def __init__(self):
        self._lock = asyncio.Lock()
        self._agent_to_clients: Dict[str, Set[WebSocket]] = {"all": set()}

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        async with self._lock:
            self._agent_to_clients.setdefault("all", set()).add(websocket)

    async def disconnect(self, websocket: WebSocket):
        async with self._lock:
            for clients in self._agent_to_clients.values():
                if websocket in clients:
                    clients.remove(websocket)

    async def subscribe(self, websocket: WebSocket, agent_id: str):
        async with self._lock:
            self._agent_to_clients.setdefault(agent_id, set()).add(websocket)

    async def unsubscribe(self, websocket: WebSocket, agent_id: str):
        async with self._lock:
            if agent_id in self._agent_to_clients and websocket in self._agent_to_clients[agent_id]:
                self._agent_to_clients[agent_id].remove(websocket)

    async def broadcast(self, agent_id: str, message):
        async with self._lock:
            targets = set()
            targets |= self._agent_to_clients.get("all", set())
            targets |= self._agent_to_clients.get(agent_id, set())
        to_remove = []
        for ws in targets:
            try:
                await ws.send_json(message)
            except Exception:
                to_remove.append(ws)
        if to_remove:
            async with self._lock:
                for ws in to_remove:
                    for clients in self._agent_to_clients.values():
                        clients.discard(ws)