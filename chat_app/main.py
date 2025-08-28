# chat room  you can join with your username
import uuid
from contextlib import asynccontextmanager
import redis.asyncio as Redis
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Request, Depends
from fastapi.middleware.cors import CORSMiddleware

@asynccontextmanager
async def connect_to_redis(app: FastAPI):
    app.state.redis = Redis.from_url("redis://localhost:6379/0")
    try:
        # test connection at startup
        await app.state.redis.ping()
        print("✅ Connected to Redis")
        yield
    finally:
        await app.state.redis.close()
        print("❌ Redis connection closed")

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class ConnectionManager:
    def __init__(self):
        self.active_connections: Dict[str, WebSocket] = {}  # user_id → websocket

    async def connect(self, websocket: WebSocket, user_id: str):
        await websocket.accept()
        self.active_connections[user_id] = websocket

    def disconnect(self, user_id: str):
        if user_id in self.active_connections:
            del self.active_connections[user_id]

    async def send_personal_message(self, message: dict, user_id: str):
        websocket = self.active_connections.get(user_id)
        if websocket:
            await websocket.send_json(message)

    async def broadcast(self, message: dict, sender_id: str | None = None):
        for user_id, connection in self.active_connections.items():
            payload = message.copy()
            # mark if this message was sent by the current user
            payload["from_self"] = (user_id == sender_id)
            await connection.send_json(payload)

manager = ConnectionManager()

@app.websocket("/ws/")
async def websocket_endpoint(websocket: WebSocket):
    username = "Anonymous"
    user_id = str(uuid.uuid4()) # new unique id for each connection
    await manager.connect(websocket, user_id)
    try:
        while True:
            data = await websocket.receive_json()

            if type(data) != dict:
                await manager.broadcast({"error": "message must be a dict"})
                continue

            # data = json.loads(data)
            type_ = data.get("type")

            if type_ == "join":
                username = data.get("username")
                # user_id  = str(uuid.uuid4()) # reset user id on join
                await manager.broadcast({
                    "type": "user_joined",
                    "user_id": user_id,
                    "username": username,
                    "message": f"{username} joined the chat"
                }, sender_id=user_id)
            elif type_ == "message":
                message = data.get("message")
                
                await manager.broadcast({
                    "type": "message",
                    "user_id": user_id,
                    "username": username,
                    "message": message
                }, sender_id=user_id)
            else:
                await manager.broadcast({"error": "invalid message type"})
                continue

            # await manager.broadcast(f"{username}: {data}")
    except WebSocketDisconnect:
        manager.disconnect(user_id)
        await manager.broadcast({"type:": "notifications", "message": f"{username} left the chat", "type": "user_left", "user_id": user_id, "username": username})
