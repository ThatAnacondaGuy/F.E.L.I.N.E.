"""Dashboard endpoints."""
from fastapi import APIRouter
from datetime import datetime

router = APIRouter()

@router.get("/now")
async def get_now():
    """Current moment: active task, next event, urgent alerts."""
    return {
        "active_task": {"id": 1, "title": "Implement Meow OS API"},
        "next_event": {"title": "AI Lecture (PCC301COM)", "time": "11:30 AM"},
        "alerts": [{"level": "high", "msg": "Assignment due in 2 hours"}]
    }

@router.get("/today")
async def get_today():
    """Today's schedule, tasks, events."""
    return {
        "schedule": [],
        "tasks": [{"id": 2, "title": "Review Theory of Computation"}],
        "events": [{"title": "College M-F", "time": "9:15 AM - 4:30 PM"}]
    }

@router.get("/week")
async def get_week():
    """This week's deadlines, milestones, events."""
    return {
        "deadlines": [],
        "milestones": [{"title": "Submit Technical Seminar Draft"}],
        "events": []
    }

@router.get("/summary")
async def get_summary():
    """Quick stats: tasks completed, pending, overdue, upcoming deadlines."""
    return {
        "tasks_completed": 12,
        "tasks_pending": 5,
        "tasks_overdue": 0,
        "upcoming_deadlines": 2
    }
