from contextlib import asynccontextmanager
from fastapi import FastAPI, Depends, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from pymongo import AsyncMongoClient
import redis.asyncio as Redis
from bson import ObjectId


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Initialize Redis client
    app.state.redis = Redis.from_url("redis://redis:6379", decode_responses=True)

    # Mongo async client
    app.state.mongo_client = AsyncMongoClient("mongodb://mongodb:27017")
    app.state.db = app.state.mongo_client["spill"]

    try:
        yield
    finally:
        await app.state.redis.close()
        await app.state.mongo_client.close()

app = FastAPI(lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=['*'],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# pydantic models
class StoryCreateRequest(BaseModel):
    content: str
    latitude: float
    longitude: float


@app.post("/stories/")
async def create_story(story: StoryCreateRequest):
    db: AsyncMongoClient = app.state.db
    collection = db.spill

    # Insert into Mongo
    result = await collection.insert_one(story.dict())
    story_id = str(result.inserted_id)

    # Add geo index in Redis
    await app.state.redis.geoadd(
        "stories_geo",
        (story.longitude, story.latitude, story_id)  # Redis expects (lng, lat, member)
    )

    return {"status": "ok"}


@app.get("/stories/")
async def get_stories(
    latitude: float = Query(..., description="Your current latitude"),
    longitude: float = Query(..., description="Your current longitude"),
    radius_km: int = Query(5, description="Search radius in kilometers"),
):
    # Find nearby story IDs from Redis
    story_ids = await app.state.redis.georadius(
        "stories_geo",
        longitude,
        latitude,
        radius_km,
        unit="km"
    )

    if not story_ids:
        return {"stories": []}

    # Fetch stories from Mongo by IDs
    db = app.state.db
    collection = db.spill
    cursor = collection.find({"_id": {"$in": [ObjectId(sid) for sid in story_ids]}})
    stories = []
    async for doc in cursor:
        doc["_id"] = str(doc["_id"])
        stories.append(doc)

    return {"stories": stories}
