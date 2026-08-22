"""Natural language chat (WebSocket)."""
from fastapi import APIRouter, WebSocket, WebSocketDisconnect
import json
import logging
from typing import List

router = APIRouter()
logger = logging.getLogger(__name__)

class ConnectionManager:
    def __init__(self):
        self.active_connections: List[WebSocket] = []

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)

    def disconnect(self, websocket: WebSocket):
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)

    async def broadcast(self, message: str):
        for connection in self.active_connections:
            await connection.send_text(message)

manager = ConnectionManager()

from pydantic import BaseModel

class ChatRequest(BaseModel):
    message: str

class ChatResponse(BaseModel):
    response: str
    status: str = "ok"

@router.post("", response_model=ChatResponse)
@router.post("/", response_model=ChatResponse)
async def chat_post_endpoint(req: ChatRequest):
    """HTTP POST /api/chat endpoint."""
    user_msg = req.message
    logger.info(f"Received HTTP chat: {user_msg}")
    reply = f"Meow! I received: '{user_msg}'. Tracking your NVIDIA & TE Computer Engineering goals."
    return ChatResponse(response=reply)

@router.websocket("")
@router.websocket("/")
async def chat_endpoint(websocket: WebSocket):
    """WebSocket /ws/chat and /api/chat."""
    await manager.connect(websocket)
    try:
        while True:
            data = await websocket.receive_text()
            logger.info(f"Received WS chat: {data}")
            response = {
                "type": "message",
                "content": f"Meow! I heard: '{data}'. Ready for Deep Focus & CUDA learning!"
            }
            await websocket.send_text(json.dumps(response))
    except WebSocketDisconnect:
        manager.disconnect(websocket)
