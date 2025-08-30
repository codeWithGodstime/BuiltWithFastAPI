# chat room  you can join with your username
import aio_pika
import asyncio
import json
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
        print("This was called broadcast", message)
        disconnected_users = []
        for user_id, connection in self.active_connections.items():
            payload = message.copy()
            # mark if this message was sent by the current user
            payload["from_self"] = (user_id == payload.get('sender_id'))
            try:
                await connection.send_json(payload)
            except RuntimeError as e:
                print(f"Connection with {user_id} is no longer active. Error: {e}")
                disconnected_users.append(user_id)

        #Clean up disconnected users outside the loop
        for user_id in disconnected_users:
            self.disconnect(user_id)


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
                    print(message.body.decode())
                    # Decode the message body and broadcast it to clients
                    # <-- IMPORTANT CHANGE: Decode and parse JSON
                    decoded_message = json.loads(message.body.decode('utf-8'))
                    print(f"Received from RabbitMQ: {decoded_message}")
                    await manager.broadcast(decoded_message)


async def connect_to_rabbitmq(app: FastAPI):
    connection = await aio_pika.connect_robust(RABBITMQ_URL)
    channel = await connection.channel()

    app.state.rabbitmq_connection = connection
    app.state.rabbitmq_channel = channel

    # Declare exchange
    exchange = await channel.declare_exchange(EXCHANGE_NAME, aio_pika.ExchangeType.FANOUT)
    app.state.exchange = exchange

    # Declare queues and bind
    chat_queue = await channel.declare_queue(MESSAGE_QUEUE, durable=True)
    await chat_queue.bind(exchange)

    # Optionally, db queue
    # db_queue = await channel.declare_queue("db", durable=True)
    # await db_queue.bind(exchange)

    # Start consumer task
    async def consumer_wrapper():
        try:
            await RabbitMQ.consume_messages(app)
        except asyncio.CancelledError:
            pass

    app.state.consumer_task = asyncio.create_task(consumer_wrapper())

    yield  # for lifespan context

    # Shutdown
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

    exchange: aio_pika.Exchange = app.state.exchange

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

                await exchange.publish(
                    aio_pika.Message(body=json.dumps(payload).encode()),
                    routing_key=""
                )
  
            elif type_ == "message":
                message = data.get("message")

                payload = {
                    "type": "message",
                    "user_id": user_id,
                    "username": username,
                    "message": message,
                    "sender_id": user_id
                }
                
                await exchange.publish(
                    aio_pika.Message(body=json.dumps(payload).encode()),                    
                    routing_key="",
                )

            else:
                error_payload = {"error": "invalid message type"}
                await exchange.publish(
                    aio_pika.Message(body=json.dumps(error_payload).encode()),
                    routing_key="",
                )
 
    except WebSocketDisconnect:
        manager.disconnect(user_id)
        await manager.broadcast({"type:": "notifications", "message": f"{username} left the chat", "type": "user_left", "user_id": user_id, "username": username})
  