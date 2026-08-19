from fastapi import WebSocket


class ConnectionManager:
    def __init__(self):
        self.active: dict[int, list[WebSocket]] = {}

    async def connect(self, family_id: int, websocket: WebSocket):
        await websocket.accept()
        if family_id not in self.active:
            self.active[family_id] = []
        self.active[family_id].append(websocket)

    def disconnect(self, family_id: int, websocket: WebSocket):
        if family_id in self.active:
            self.active[family_id] = [ws for ws in self.active[family_id] if ws != websocket]
            if not self.active[family_id]:
                del self.active[family_id]

    async def broadcast(self, family_id: int, message: dict):
        if family_id not in self.active:
            return
        dead = []
        for ws in self.active[family_id]:
            try:
                await ws.send_json(message)
            except Exception:
                dead.append(ws)
        for ws in dead:
            self.disconnect(family_id, ws)


ws_manager = ConnectionManager()
