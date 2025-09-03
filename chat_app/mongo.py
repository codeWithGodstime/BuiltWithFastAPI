from typing import Any, Dict, List, Optional
from pymongo import ASCENDING
from pymongo.mongo_client import MongoClient
from pymongo.errors import PyMongoError
from motor.motor_asyncio import AsyncIOMotorClient
from interface import DBInterface


class MongoDB(DBInterface):
    def __init__(self, uri: str, db_name: str, collection_name: str):
        self.client = AsyncIOMotorClient(uri)
        self.db = self.client[db_name]
        self.collection = self.db[collection_name]

    async def create(self, indexes: Optional[List[Dict[str, Any]]] = None) -> None:
        """
        Optionally create indexes on the collection.
        """
        if indexes:
            for index in indexes:
                field = index.get("field")
                unique = index.get("unique", False)
                await self.collection.create_index([(field, ASCENDING)], unique=unique)

    async def insert(self, document: Dict[str, Any]) -> str:
        """
        Insert a single document and return inserted id as string.
        """
        result = await self.collection.insert_one(document)
        return str(result.inserted_id)

    async def delete(self, query: Dict[str, Any]) -> int:
        """
        Delete documents matching query.
        Returns the count of deleted documents.
        """
        result = await self.collection.delete_many(query)
        return result.deleted_count

    async def find(self, query: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """
        Find a single document matching query.
        """
        return await self.collection.find(query)

    async def find_all(self, query: Dict[str, Any] = None) -> List[Dict[str, Any]]:
        """
        Find all documents matching query.
        """
        query = query or {}
        cursor = self.collection.find(query)
        results = []
        async for doc in cursor:
            results.append(doc)
        return results

    async def get_recent(self, limit: int = 100) -> List[Dict[str, Any]]:
        cursor = self.collection.find({}).sort("timestamp", -1).limit(limit)
        results: List[Dict[str, Any]] = []
        async for doc in cursor:
            doc["_id"] = str(doc["_id"])
            results.append(doc)

        results.reverse()  # oldest → newest
        return results
