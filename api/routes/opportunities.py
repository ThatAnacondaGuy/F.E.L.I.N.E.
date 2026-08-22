"""Opportunity endpoints."""
from fastapi import APIRouter

router = APIRouter()

@router.get("/")
async def list_opportunities():
    """List discovered opportunities (sorted by score)."""
    return [
        {"id": "opp_1", "title": "NVIDIA Internship Application", "score": 98, "deadline": "2026-09-15"},
        {"id": "opp_2", "title": "AI Hackathon", "score": 85, "deadline": "2026-09-01"}
    ]

@router.get("/{opp_id}")
async def get_opportunity(opp_id: str):
    return {"id": opp_id, "title": "NVIDIA Internship Application", "details": "Software Eng Intern"}

@router.post("/{opp_id}/track")
async def track_opportunity(opp_id: str):
    return {"status": "tracked"}

@router.post("/{opp_id}/dismiss")
async def dismiss_opportunity(opp_id: str):
    return {"status": "dismissed"}

@router.get("/filter/expiring")
async def get_expiring_opportunities():
    return []
