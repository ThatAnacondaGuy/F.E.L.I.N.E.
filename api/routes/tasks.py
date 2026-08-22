"""Task CRUD endpoints."""
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import List, Optional
from datetime import datetime

router = APIRouter()

class TaskBase(BaseModel):
    title: str
    description: Optional[str] = None
    priority: int = 1
    project: Optional[str] = None
    category: Optional[str] = None

class TaskCreate(TaskBase):
    pass

class TaskResponse(TaskBase):
    id: str
    status: str
    created_at: datetime

# In-memory store for Phase 1 stub
TASKS = {}

@router.get("/", response_model=List[TaskResponse])
async def list_tasks(status: Optional[str] = None, priority: Optional[int] = None):
    """List tasks (filter by status, priority, project, category)."""
    result = list(TASKS.values())
    if status:
        result = [t for t in result if t.status == status]
    if priority:
        result = [t for t in result if t.priority == priority]
    return result

@router.post("/", response_model=TaskResponse)
async def create_task(task: TaskCreate):
    """Create task."""
    task_id = f"task_{len(TASKS) + 1}"
    new_task = TaskResponse(id=task_id, status="pending", created_at=datetime.now(), **task.model_dump())
    TASKS[task_id] = new_task
    return new_task

@router.get("/{task_id}", response_model=TaskResponse)
async def get_task(task_id: str):
    """Get task details."""
    if task_id not in TASKS:
        raise HTTPException(status_code=404, detail="Task not found")
    return TASKS[task_id]

@router.put("/{task_id}", response_model=TaskResponse)
async def update_task(task_id: str, task: TaskCreate):
    """Update task."""
    if task_id not in TASKS:
        raise HTTPException(status_code=404, detail="Task not found")
    updated = TaskResponse(id=task_id, status=TASKS[task_id].status, created_at=TASKS[task_id].created_at, **task.model_dump())
    TASKS[task_id] = updated
    return updated

@router.delete("/{task_id}")
async def delete_task(task_id: str):
    """Delete task."""
    if task_id in TASKS:
        del TASKS[task_id]
    return {"status": "deleted"}

@router.post("/{task_id}/complete")
async def complete_task(task_id: str):
    """Mark complete."""
    if task_id in TASKS:
        TASKS[task_id].status = "completed"
    return {"status": "completed"}

@router.post("/{task_id}/snooze")
async def snooze_task(task_id: str):
    """Snooze task."""
    return {"status": "snoozed"}

@router.get("/filter/overdue")
async def get_overdue_tasks():
    """Get overdue tasks."""
    return []

@router.get("/filter/today")
async def get_today_tasks():
    """Today's tasks."""
    return list(TASKS.values())
