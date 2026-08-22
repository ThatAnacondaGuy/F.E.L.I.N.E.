"""Project endpoints."""
from fastapi import APIRouter
from pydantic import BaseModel
from typing import List, Optional

router = APIRouter()

class Project(BaseModel):
    id: str
    name: str
    status: str
    github_repo: Optional[str] = None

PROJECTS = {
    "proj_1": Project(id="proj_1", name="Meow OS", status="active", github_repo="ThatAnacondaGuy/meow-os")
}

@router.get("/")
async def list_projects():
    return list(PROJECTS.values())

@router.post("/")
async def create_project(project: Project):
    PROJECTS[project.id] = project
    return project

@router.get("/{project_id}")
async def get_project(project_id: str):
    return PROJECTS.get(project_id, {})

@router.put("/{project_id}")
async def update_project(project_id: str, project: Project):
    if project_id in PROJECTS:
        PROJECTS[project_id] = project
    return project

@router.get("/filter/inactive")
async def get_inactive_projects():
    return [p for p in PROJECTS.values() if p.status == "inactive"]

@router.get("/{project_id}/github")
async def get_project_github(project_id: str):
    return {"commits": 10, "open_issues": 2}
