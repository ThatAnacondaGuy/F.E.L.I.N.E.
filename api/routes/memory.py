"""Memory endpoints."""
from fastapi import APIRouter, Query

router = APIRouter()

@router.get("/")
async def list_memories(category: str = None):
    return []

@router.post("/")
async def create_memory(content: str):
    return {"status": "saved", "id": "mem_1"}

@router.delete("/{mem_id}")
async def delete_memory(mem_id: str):
    return {"status": "forgotten"}

@router.put("/{mem_id}")
async def update_memory(mem_id: str, content: str):
    return {"status": "updated"}

@router.get("/search/")
async def search_memories(q: str = Query(...)):
    """Semantic search memories."""
    return [{"id": "mem_1", "content": "Aniket's target company is NVIDIA."}]

@router.post("/export")
async def export_memories():
    return {"file": "memories_export.json"}
