"""Goal tracking endpoints."""
from fastapi import APIRouter

router = APIRouter()

@router.get("/")
async def list_goals():
    return [
        {"id": "goal_1", "title": "NVIDIA Career", "progress": 65},
        {"id": "goal_2", "title": "Complete AI Course", "progress": 80}
    ]

@router.get("/{goal_id}")
async def get_goal(goal_id: str):
    return {"id": goal_id, "title": "NVIDIA Career", "progress": 65}

@router.get("/special/nvidia")
async def get_nvidia_progress():
    return {
        "title": "NVIDIA Career Progress",
        "progress": 65,
        "milestones": [
            {"name": "Learn CUDA", "status": "in_progress"},
            {"name": "Apply for Internship", "status": "pending"}
        ]
    }

@router.put("/{goal_id}/progress")
async def update_progress(goal_id: str, progress: int):
    return {"status": "updated", "progress": progress}
