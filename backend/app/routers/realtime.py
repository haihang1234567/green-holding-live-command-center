from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from app.core.security import decode_access_token
from app.services.realtime import manager

router = APIRouter(tags=["realtime"])


@router.websocket("/ws/dashboard")
async def dashboard_ws(websocket: WebSocket):
    token = websocket.query_params.get("token")
    try:
        if not token: raise ValueError("missing token")
        decode_access_token(token)
    except ValueError:
        await websocket.close(code=4401)
        return
    await manager.connect(websocket)
    try:
        await websocket.send_json({"type": "CONNECTED"})
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        await manager.disconnect(websocket)
