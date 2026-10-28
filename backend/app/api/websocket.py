import asyncio
import json
import random
from datetime import datetime, timezone
from typing import List, Set
from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from sqlalchemy.orm import Session
from app.core.database import SessionLocal
from app.models.entities import Segment, MoistureNode, DTSReading, Alarm

router = APIRouter(tags=["WebSocket Real-Time Stream"])

class ConnectionManager:
    def __init__(self):
        self.active_connections: Set[WebSocket] = set()

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.add(websocket)

    def disconnect(self, websocket: WebSocket):
        self.active_connections.discard(websocket)

    async def broadcast(self, message: dict):
        if not self.active_connections:
            return
        payload = json.dumps(message)
        dead = []
        for connection in self.active_connections:
            try:
                await connection.send_text(payload)
            except Exception:
                dead.append(connection)
        for d in dead:
            self.active_connections.discard(d)

manager = ConnectionManager()

@router.websocket("/ws/live")
async def websocket_live_endpoint(websocket: WebSocket):
    await manager.connect(websocket)
    try:
        # Send initial connection handshake
        await websocket.send_text(json.dumps({
            "type": "CONNECTION_ESTABLISHED",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "message": "Connected to InsulGuard 4.0 Real-time Industrial Field Stream"
        }))
        while True:
            # Keep receiving client heartbeats or messages
            data = await websocket.receive_text()
            # Echo back pong or acknowledge
            try:
                parsed = json.loads(data)
                if parsed.get("type") == "PING":
                    await websocket.send_text(json.dumps({"type": "PONG", "timestamp": datetime.now(timezone.utc).isoformat()}))
            except Exception:
                pass
    except WebSocketDisconnect:
        manager.disconnect(websocket)
    except Exception:
        manager.disconnect(websocket)

async def telemetry_background_broadcaster():
    """Simulates ongoing field telemetry pulses every 3 seconds."""
    while True:
        await asyncio.sleep(3.0)
        if not manager.active_connections:
            continue
        
        try:
            db: Session = SessionLocal()
            try:
                # Pick 4 random nodes to emit dynamic readings
                nodes = db.query(MoistureNode).order_by(MoistureNode.last_seen.asc()).limit(4).all()
                now = datetime.now(timezone.utc)
                updates = []
                for n in nodes:
                    # Small ambient noise jitter (+/- 0.4%)
                    jitter = random.uniform(-0.4, 0.4)
                    new_moist = round(max(0.0, min(100.0, n.moisture_pct + jitter)), 1)
                    n.moisture_pct = new_moist
                    n.battery_pct = round(max(10.0, n.battery_pct - 0.001), 1)
                    n.last_seen = now
                    updates.append({
                        "node_id": n.id,
                        "segment_id": n.segment_id,
                        "clock_position": n.clock_position,
                        "moisture_pct": new_moist,
                        "jacket_temp_C": n.jacket_temp_C,
                        "battery_pct": n.battery_pct,
                        "last_seen": now.isoformat()
                    })
                db.commit()

                await manager.broadcast({
                    "type": "NODE_TELEMETRY_BATCH",
                    "timestamp": now.isoformat(),
                    "readings": updates
                })
            finally:
                db.close()
        except Exception as e:
            # Suppress background stream hiccups
            pass
