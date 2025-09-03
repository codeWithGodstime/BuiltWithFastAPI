import aio_pika
import asyncio
import json
from fastapi import FastAPI, WebSocket
from interface import DBInterface
from typing import Dict

RABBITMQ_URL = "amqp://guest:guest@rabbitmq:5672/"
MESSAGE_QUEUE = "chat_messages"
DATABASE_QUEUE = "write_to_db"
EXCHANGE_NAME = "message_exchange"

REDIS_URL = "redis://redis:6379"
MONGODB_URL = "mongodb://db:27017"


class ConnectionManager:
    def __init__(self):
        self.active_connections: Dict[str, WebSocket] = {}  # user_id → websocket

    async def connect(self, websocket: WebSocket, user_id: str):
        await websocket.accept()
        self.active_connections[user_id] = websocket

    def disconnect(self, user_id: str):
        if user_id in self.active_connections:
            del self.active_connections[user_id]
            return True
        return False

    async def send_personal_message(self, message: dict, user_id: str):
        websocket = self.active_connections.get(user_id)
        if websocket:
            await websocket.send_json(message)

    async def broadcast(self, message: dict, sender_id: str | None = None):
        print("This was called broadcast", message)
        disconnected_users = []
        for user_id, connection in self.active_connections.items():
            payload = message.copy()
            # mark if this message was sent by the current user
            payload["from_self"] = user_id == payload.get("sender_id")
            try:
                await connection.send_json(payload)
            except RuntimeError as e:
                print(f"Connection with {user_id} is no longer active. Error: {e}")
                disconnected_users.append(user_id)

        # Clean up disconnected users outside the loop
        for user_id in disconnected_users:
            self.disconnect(user_id)


connection_manager = ConnectionManager()


class Consumer:
    async def consume_messages(self, app: FastAPI):
        channel: aio_pika.Channel = app.state.rabbitmq_channel

        chat_queue = await channel.declare_queue(MESSAGE_QUEUE, durable=True)
        await chat_queue.bind(EXCHANGE_NAME, routing_key="")  # fanout ignores key

        async with chat_queue.iterator() as queue_iter:
            async for message in queue_iter:
                async with message.process():
                    try:
                        decoded_message = json.loads(message.body.decode("utf-8"))
                    except json.JSONDecodeError:
                        print("Skipping non-JSON message:", message.body)
                        continue

                    print(f"Broadcasting: {decoded_message}")
                    await connection_manager.broadcast(decoded_message)


    async def persist_to_db(self, app: FastAPI):
        channel: aio_pika.Channel = app.state.rabbitmq_channel

        db_queue = await channel.declare_queue(DATABASE_QUEUE, durable=True)
        await db_queue.bind(EXCHANGE_NAME, routing_key="")

        async with db_queue.iterator() as queue_iter:
            async for message in queue_iter:
                async with message.process():
                    try:
                        decoded_message = json.loads(message.body.decode("utf-8"))
                    except json.JSONDecodeError:
                        print("Skipping non-JSON message:", message.body)
                        continue

                    # Ignore system events
                    if decoded_message.get("type") in ("active_users_update", "user_left", "user_joined"):
                        print("Ignoring system update for database persistence.")
                        continue

                    db: DBInterface = app.state.db

                    save_message = {
                        "username": decoded_message['username'],
                        "message": decoded_message['message'],
                        "sender_id": decoded_message['sender_id'],
                        "timestamp": decoded_message['timestamp']
                    }

                    # Persist the chat message
                    inserted_id = await db.insert(save)
                    print(f"Saved message with id {inserted_id}")


    async def start(self, app: FastAPI):
        print("Starting consumers concurrently...")
        await asyncio.gather(
            self.persist_to_db(app),
            self.consume_messages(app),
        )


consumer = Consumer()

