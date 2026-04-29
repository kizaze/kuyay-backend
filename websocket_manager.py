"""WebSocket connection manager for real-time admin notifications."""
from fastapi import WebSocket
from typing import List
import asyncio


class ConnectionManager:
    def __init__(self):
        self.active: List[WebSocket] = []
        self._lock = asyncio.Lock()

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        async with self._lock:
            self.active.append(websocket)

    async def disconnect(self, websocket: WebSocket):
        async with self._lock:
            if websocket in self.active:
                self.active.remove(websocket)

    async def broadcast(self, message: dict):
        """Send a JSON message to all connected admins."""
        dead: List[WebSocket] = []
        for ws in list(self.active):
            try:
                await ws.send_json(message)
            except Exception:
                dead.append(ws)
        for ws in dead:
            await self.disconnect(ws)

    async def send_new_order(self, order_id: int, user_name: str, total: float, status: str):
        await self.broadcast({
            "type":      "new_order",
            "order_id":  order_id,
            "user_name": user_name,
            "total":     total,
            "status":    status,
        })

    async def send_status_change(self, order_id: int, new_status: str):
        await self.broadcast({
            "type":       "status_change",
            "order_id":   order_id,
            "new_status": new_status,
        })

    async def send_escalation(self, conv_id: int, user_name: str, preview: str):
        await self.broadcast({
            "type":      "escalation",
            "conv_id":   conv_id,
            "user_name": user_name,
            "preview":   preview,
        })


# Singleton used across the app
ws_manager = ConnectionManager()
