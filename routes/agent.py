from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Header, HTTPException
from typing import Optional
import json
import asyncio
import os
AGENT_SECRET = os.getenv("AGENT_SECRET", "sova-agent-secret-2025")

router = APIRouter()

# Store active agent connections per user
# key: user_id, value: WebSocket
active_agents: dict[str, WebSocket] = {}

AGENT_SECRET = "sova-agent-secret-2025"  # Must match desktop agent

@router.websocket("/agent/ws/{user_id}")
async def agent_websocket(websocket: WebSocket, user_id: str, secret: str = ""):
    if secret != AGENT_SECRET:
        await websocket.close(code=4001)
        return

    await websocket.accept()
    active_agents[user_id] = websocket
    print(f"[Agent] Connected: {user_id}")

    try:
        while True:
            # Keep alive — wait for messages from agent
            data = await websocket.receive_text()
            msg = json.loads(data)
            print(f"[Agent] Message from {user_id}: {msg}")
    except WebSocketDisconnect:
        active_agents.pop(user_id, None)
        print(f"[Agent] Disconnected: {user_id}")

@router.post("/agent/command")
async def send_command(payload: dict):
    """Send a command to a user's desktop agent."""
    user_id = payload.get("user_id")
    command = payload.get("command")

    if not user_id or not command:
        raise HTTPException(status_code=400, detail="Missing user_id or command")

    ws = active_agents.get(user_id)
    if not ws:
        return {"status": "agent_offline", "message": "Desktop agent is not running"}

    try:
        await ws.send_text(json.dumps(command))
        return {"status": "sent"}
    except Exception as e:
        active_agents.pop(user_id, None)
        return {"status": "error", "message": str(e)}

@router.get("/agent/status/{user_id}")
async def agent_status(user_id: str):
    online = user_id in active_agents
    return {"online": online}