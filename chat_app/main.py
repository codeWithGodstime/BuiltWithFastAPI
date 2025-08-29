# chat room  you can join with your username
import aio_pika
import asyncio
import uuid
from typing import Dict
from contextlib import asynccontextmanager
import redis.asyncio as Redis
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware

RABBITMQ_URL = "amqp://guest:guest@rabbitmq:5672/"
MESSAGE_QUEUE = "chat_messages"
DATABASE_QUEUE = "write_to_db"
EXCHANGE_NAME = "message_exchange"


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


class RabbitMQ:

    @staticmethod
    async def publish_message(message: str):
        pass
    
    @staticmethod
    async def consume_messages(app: FastAPI):
        channel: aio_pika.Channel = app.state.rabbitmq_channel

        chat_queue = await channel.declare_queue(MESSAGE_QUEUE, durable=True)
        await chat_queue.bind(EXCHANGE_NAME, routing_key="")   # fanout ignores key

        # db_queue = await channel.declare_queue("db", durable=True)
        # await db_queue.bind(EXCHANGE_NAME, routing_key="")

        async with chat_queue.iterator() as queue_iter:
            async for message in queue_iter:
                async with message.process():
                    # Decode the message body and broadcast it to clients
                    decoded_message = message.body.decode()
                    print(f"Received from RabbitMQ: {decoded_message}")
                    await manager.broadcast(decoded_message)

@asynccontextmanager
async def connect_to_rabbitmq(app: FastAPI):
    # create RabbitMQ connection
    connection = await aio_pika.connect_robust(RABBITMQ_URL)
    channel = await connection.channel()        

    # store in app.state for access in routes
    app.state.rabbitmq_connection = connection
    app.state.rabbitmq_channel = channel

    app.state.exchange = await app.state.rabbitmq_connection.declare_exchange(EXCHANGE_NAME, aio_pika.ExchangeType.FANOUT)
    
    app.state.rabbitmq_channel.queue_declare(queue=MESSAGE_QUEUE)
    # app.state.rabbitmq_channel.queue_declare(queue="db")

    # to bind the queue to the exchange
    await app.state.rabbitmq_channel.queue_bind(exchange=EXCHANGE_NAME, queue=MESSAGE_QUEUE)

    app.state.consumer_task = asyncio.create_task(RabbitMQ.consume_messages())

    yield

    # cleanup on shutdown
    app.state.consumer_task.cancel()
    await channel.close()
    await connection.close()


app = FastAPI(lifespan=connect_to_rabbitmq)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.websocket("/ws/")
async def websocket_endpoint(websocket: WebSocket):
    username = "Anonymous"
    user_id = str(uuid.uuid4()) # new unique id for each connection
    await manager.connect(websocket, user_id)

    channel = app.state.rabbitmq_channel

    try:
        while True:
            data = await websocket.receive_json()

            if type(data) != dict:
                await manager.broadcast({"error": "message must be a dict"})
                continue

            type_ = data.get("type")

            if type_ == "join":
                username = data.get("username")

                payload = {
                    "type": "user_joined",
                    "user_id": user_id,
                    "username": username,
                    "message": f"{username} joined the chat"
                }

                channel.basic_publish(
                    exchange=EXCHANGE_NAME,
                    routing_key="",
                    body=aio_pika.Message(body=str(payload).encode())
                )

            elif type_ == "message":
                message = data.get("message")

                payload = {
                    "type": "message",
                    "user_id": user_id,
                    "username": username,
                    "message": message
                }
                channel.basic_publish(
                    exchange=EXCHANGE_NAME,
                    routing_key="",
                    body=aio_pika.Message(body=str(payload).encode())
                )

            else:
                error_payload = {"error": "invalid message type"}
                channel.basic_publish(
                    exchange=EXCHANGE_NAME,
                    routing_key="",
                    body=aio_pika.Message(body=str(error_payload).encode())
                )

    except WebSocketDisconnect:
        manager.disconnect(user_id)
        await manager.broadcast({"type:": "notifications", "message": f"{username} left the chat", "type": "user_left", "user_id": user_id, "username": username})
