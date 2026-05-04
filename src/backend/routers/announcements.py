"""
Announcement endpoints for the High School Management System API
"""

from datetime import date, datetime
from typing import Any, Dict, List, Optional
from uuid import uuid4

from fastapi import APIRouter, Body, HTTPException, Query

from ..database import announcements_collection, teachers_collection

router = APIRouter(
    prefix="/announcements",
    tags=["announcements"]
)


def require_teacher(username: Optional[str]) -> Dict[str, Any]:
    """Validate that the request is associated with a known teacher account."""
    if not username:
        raise HTTPException(status_code=401, detail="Authentication required for this action")

    teacher = teachers_collection.find_one({"_id": username})
    if not teacher:
        raise HTTPException(status_code=401, detail="Invalid teacher credentials")

    return teacher


def parse_date_field(value: Optional[str], field_name: str, required: bool = False) -> Optional[str]:
    if value in (None, ""):
        if required:
            raise HTTPException(status_code=400, detail=f"{field_name} is required")
        return None

    try:
        return date.fromisoformat(value).isoformat()
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=f"{field_name} must use YYYY-MM-DD format") from exc


def serialize_announcement(document: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "id": str(document["_id"]),
        "title": document["title"],
        "message": document["message"],
        "starts_on": document.get("starts_on"),
        "expires_on": document["expires_on"],
        "created_at": document.get("created_at"),
        "updated_at": document.get("updated_at")
    }


def validate_announcement_payload(payload: Dict[str, Any]) -> Dict[str, Any]:
    title = (payload.get("title") or "").strip()
    message = (payload.get("message") or "").strip()
    starts_on = parse_date_field(payload.get("starts_on"), "starts_on")
    expires_on = parse_date_field(payload.get("expires_on"), "expires_on", required=True)

    if not title:
        raise HTTPException(status_code=400, detail="title is required")

    if not message:
        raise HTTPException(status_code=400, detail="message is required")

    if starts_on and starts_on > expires_on:
        raise HTTPException(status_code=400, detail="starts_on cannot be later than expires_on")

    return {
        "title": title,
        "message": message,
        "starts_on": starts_on,
        "expires_on": expires_on
    }


@router.get("", response_model=List[Dict[str, Any]])
@router.get("/", response_model=List[Dict[str, Any]])
def get_active_announcements() -> List[Dict[str, Any]]:
    """Get announcements that are currently active based on the current date."""
    today = date.today().isoformat()
    query = {
        "expires_on": {"$gte": today},
        "$or": [
            {"starts_on": {"$exists": False}},
            {"starts_on": None},
            {"starts_on": ""},
            {"starts_on": {"$lte": today}}
        ]
    }

    announcements = announcements_collection.find(query).sort([
        ("expires_on", 1),
        ("created_at", -1)
    ])
    return [serialize_announcement(document) for document in announcements]


@router.get("/manage", response_model=List[Dict[str, Any]])
def get_all_announcements(teacher_username: Optional[str] = Query(None)) -> List[Dict[str, Any]]:
    """Get all announcements for the management dialog."""
    require_teacher(teacher_username)
    announcements = announcements_collection.find().sort([
        ("expires_on", 1),
        ("created_at", -1)
    ])
    return [serialize_announcement(document) for document in announcements]


@router.post("", response_model=Dict[str, Any])
@router.post("/", response_model=Dict[str, Any])
def create_announcement(
    payload: Dict[str, Any] = Body(...),
    teacher_username: Optional[str] = Query(None)
) -> Dict[str, Any]:
    """Create a new announcement."""
    require_teacher(teacher_username)
    normalized_payload = validate_announcement_payload(payload)
    timestamp = datetime.utcnow().replace(microsecond=0).isoformat()
    announcement = {
        "_id": payload.get("id") or uuid4().hex,
        **normalized_payload,
        "created_at": timestamp,
        "updated_at": timestamp
    }
    announcements_collection.insert_one(announcement)
    return serialize_announcement(announcement)


@router.put("/{announcement_id}", response_model=Dict[str, Any])
def update_announcement(
    announcement_id: str,
    payload: Dict[str, Any] = Body(...),
    teacher_username: Optional[str] = Query(None)
) -> Dict[str, Any]:
    """Update an existing announcement."""
    require_teacher(teacher_username)
    normalized_payload = validate_announcement_payload(payload)
    existing = announcements_collection.find_one({"_id": announcement_id})
    if not existing:
        raise HTTPException(status_code=404, detail="Announcement not found")

    update_document = {
        **normalized_payload,
        "updated_at": datetime.utcnow().replace(microsecond=0).isoformat()
    }
    announcements_collection.update_one(
        {"_id": announcement_id},
        {"$set": update_document}
    )

    return serialize_announcement({**existing, **update_document})


@router.delete("/{announcement_id}")
def delete_announcement(
    announcement_id: str,
    teacher_username: Optional[str] = Query(None)
) -> Dict[str, str]:
    """Delete an announcement."""
    require_teacher(teacher_username)
    result = announcements_collection.delete_one({"_id": announcement_id})
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Announcement not found")

    return {"message": "Announcement deleted"}