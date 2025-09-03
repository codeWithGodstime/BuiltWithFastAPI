import aio_pika
import asyncio
import json
from datetime import datetime, timezone
import uuid
from contextlib import asynccontextmanager
import redis.asyncio as Redis
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware


from mongo import MongoDB
from interface import DBInterface
from utils import (
    consumer,
    connection_manager,
    RABBITMQ_URL,
    MESSAGE_QUEUE,
    DATABASE_QUEUE,
    EXCHANGE_NAME,
    REDIS_URL,
    MONGODB_URL,
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    connection = await aio_pika.connect_robust(RABBITMQ_URL)
    channel = await connection.channel()
    db: DBInterface = MongoDB(MONGODB_URL, "chatdb", "messages")

    redis = Redis.from_url(REDIS_URL)

    app.state.rabbitmq_connection = connection
    app.state.rabbitmq_channel = channel
    app.state.redis = redis
    app.state.db = db

    # Declare exchange
    exchange = await channel.declare_exchange(
        EXCHANGE_NAME, aio_pika.ExchangeType.FANOUT
    )
    app.state.exchange = exchange

    # Declare queues and bind
    chat_queue = await channel.declare_queue(MESSAGE_QUEUE, durable=True)
    await chat_queue.bind(exchange)

    # db queue for message persistence
    db_queue = await channel.declare_queue(DATABASE_QUEUE, durable=True)
    await db_queue.bind(exchange)

    # Start consumer task
    async def consumer_wrapper():
        try:
            await consumer.start(app)
        except asyncio.CancelledError:
            pass

    app.state.consumer_task = asyncio.create_task(consumer_wrapper())

    yield  # for lifespan context

    # Shutdown
    app.state.consumer_task.cancel()
    await channel.close()
    await connection.close()
    await app.state.redis.close()


app = FastAPI(lifespan=lifespan)

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
    user_id = str(uuid.uuid4())  # new unique id for each connection
    redis: Redis.Redis = app.state.redis
    exchange: aio_pika.Exchange = app.state.exchange
    db: DBInterface = app.state.db

    # increment the number of active users
    active_users_count = await redis.incr("active_users")
    await connection_manager.connect(websocket, user_id)

    last_messages = await db.get_recent()

    active_users_payload = {
        "type": "active_users_update",
        "active_users": active_users_count,
    }

    await websocket.send_json({"type": "history", "messages": last_messages})

    await connection_manager.broadcast(active_users_payload)

    try:
        while True:
            data = await websocket.receive_json()

            if type(data) is not dict:
                await connection_manager.broadcast({"error": "message must be a dict"})
                continue

            type_ = data.get("type")

            if type_ == "join":
                username = data.get("username")

                payload = {
                    "type": "user_joined",
                    "user_id": user_id,
                    "username": username,
                    "message": f"{username} joined the chat",
                }

                await exchange.publish(
                    aio_pika.Message(body=json.dumps(payload).encode()), routing_key=""
                )

            elif type_ == "message":
                message = data.get("message")

                payload = {
                    "type": "message",
                    "user_id": user_id,
                    "username": username,
                    "message": message,
                    "sender_id": user_id,
                    "timestamp": datetime.now(timezone.utc).isoformat(),
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
        if connection_manager.disconnect(user_id):
            await redis.decr("active_users")

        active_users_payload = {
            "type": "active_users_update",
            "active_users": active_users_count,
        }

        await exchange.publish(
            aio_pika.Message(body=json.dumps(active_users_payload).encode()),
            routing_key="",
        )
        await connection_manager.broadcast(
            {
                "type:": "notifications",
                "message": f"{username} left the chat",
                "type": "user_left",
                "user_id": user_id,
                "username": username,
            }
        )
