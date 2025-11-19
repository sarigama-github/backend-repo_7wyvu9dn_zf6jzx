import os
from datetime import datetime
from typing import Any, Dict, Optional, List
from pymongo import MongoClient
from pymongo.collection import Collection

DATABASE_URL = os.getenv("DATABASE_URL", "mongodb://localhost:27017")
DATABASE_NAME = os.getenv("DATABASE_NAME", "appdb")

_client: Optional[MongoClient] = None
_db = None

def get_db():
    global _client, _db
    if _db is None:
        _client = MongoClient(DATABASE_URL)
        _db = _client[DATABASE_NAME]
    return _db


def collection(name: str) -> Collection:
    return get_db()[name]


def create_document(collection_name: str, data: Dict[str, Any]) -> Dict[str, Any]:
    col = collection(collection_name)
    now = datetime.utcnow()
    data.update({"created_at": now, "updated_at": now})
    res = col.insert_one(data)
    doc = col.find_one({"_id": res.inserted_id})
    return serialize_document(doc)


def update_document(collection_name: str, doc_id, updates: Dict[str, Any]) -> Dict[str, Any]:
    from bson import ObjectId
    col = collection(collection_name)
    updates.update({"updated_at": datetime.utcnow()})
    col.update_one({"_id": ObjectId(doc_id)}, {"$set": updates})
    doc = col.find_one({"_id": ObjectId(doc_id)})
    return serialize_document(doc)


def delete_document(collection_name: str, doc_id) -> bool:
    from bson import ObjectId
    col = collection(collection_name)
    res = col.delete_one({"_id": ObjectId(doc_id)})
    return res.deleted_count == 1


def get_documents(collection_name: str, filter_dict: Dict[str, Any] = None, limit: int = 1000, sort: Optional[List] = None) -> List[Dict[str, Any]]:
    col = collection(collection_name)
    cursor = col.find(filter_dict or {})
    if sort:
        cursor = cursor.sort(sort)
    if limit:
        cursor = cursor.limit(limit)
    return [serialize_document(d) for d in cursor]


def get_document(collection_name: str, doc_id) -> Optional[Dict[str, Any]]:
    from bson import ObjectId
    col = collection(collection_name)
    doc = col.find_one({"_id": ObjectId(doc_id)})
    return serialize_document(doc) if doc else None


def serialize_document(doc: Dict[str, Any]) -> Dict[str, Any]:
    if not doc:
        return doc
    doc = dict(doc)
    _id = doc.pop("_id", None)
    if _id is not None:
        doc["id"] = str(_id)
    return doc
