import sqlite3
import uuid
import json
from typing import List, Dict, Any, Optional
from pydantic import BaseModel
from .vector_store import VectorStore

class KGEntity(BaseModel):
    id: str
    type: str
    name: str
    properties: Dict[str, Any]

class KGRelation(BaseModel):
    id: str
    source_id: str
    target_id: str
    type: str
    weight: float
    properties: Dict[str, Any]

class KnowledgeGraph:
    """Knowledge Graph stored in SQLite and ChromaDB for semantic search."""
    
    def __init__(self, db_path: str, vector_store: VectorStore):
        self.db_path = db_path
        self.vector_store = vector_store
        self._init_db()

    def _init_db(self):
        with sqlite3.connect(self.db_path) as conn:
            conn.execute('''
                CREATE TABLE IF NOT EXISTS entities (
                    id TEXT PRIMARY KEY,
                    type TEXT,
                    name TEXT,
                    properties TEXT
                )
            ''')
            conn.execute('''
                CREATE VIRTUAL TABLE IF NOT EXISTS entities_fts USING fts5(
                    name, properties, content='entities', content_rowid='rowid'
                )
            ''')
            conn.execute('''
                CREATE TABLE IF NOT EXISTS relations (
                    id TEXT PRIMARY KEY,
                    source_id TEXT,
                    target_id TEXT,
                    type TEXT,
                    weight REAL,
                    properties TEXT,
                    FOREIGN KEY(source_id) REFERENCES entities(id) ON DELETE CASCADE,
                    FOREIGN KEY(target_id) REFERENCES entities(id) ON DELETE CASCADE
                )
            ''')
            conn.commit()

    async def add_entity(self, type: str, name: str, properties: Dict[str, Any]) -> str:
        entity_id = str(uuid.uuid4())
        prop_str = json.dumps(properties)
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                "INSERT INTO entities (id, type, name, properties) VALUES (?, ?, ?, ?)",
                (entity_id, type, name, prop_str)
            )
            conn.execute(
                "INSERT INTO entities_fts (rowid, name, properties) VALUES (last_insert_rowid(), ?, ?)",
                (name, prop_str)
            )
        
        doc_text = f"{name} ({type}): {prop_str}"
        await self.vector_store.add("documents", entity_id, doc_text, {"type": "entity", "entity_type": type})
        return entity_id

    def add_relation(self, source_id: str, target_id: str, relation_type: str, weight: float = 1.0, properties: Optional[Dict[str, Any]] = None) -> str:
        rel_id = str(uuid.uuid4())
        prop_str = json.dumps(properties or {})
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                "INSERT INTO relations (id, source_id, target_id, type, weight, properties) VALUES (?, ?, ?, ?, ?, ?)",
                (rel_id, source_id, target_id, relation_type, weight, prop_str)
            )
        return rel_id

    def get_entity(self, entity_id: str) -> Optional[KGEntity]:
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.execute("SELECT * FROM entities WHERE id = ?", (entity_id,))
            row = cursor.fetchone()
            if row:
                return KGEntity(id=row['id'], type=row['type'], name=row['name'], properties=json.loads(row['properties']))
        return None

    def find_entities(self, type: Optional[str] = None, name_pattern: Optional[str] = None) -> List[KGEntity]:
        query = "SELECT * FROM entities WHERE 1=1"
        params = []
        if type:
            query += " AND type = ?"
            params.append(type)
        if name_pattern:
            query += " AND name LIKE ?"
            params.append(f"%{name_pattern}%")
            
        entities = []
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            for row in conn.execute(query, params):
                entities.append(KGEntity(id=row['id'], type=row['type'], name=row['name'], properties=json.loads(row['properties'])))
        return entities

    def get_relations(self, entity_id: str, direction: str = 'both', relation_type: Optional[str] = None) -> List[KGRelation]:
        query = "SELECT * FROM relations WHERE "
        params = []
        if direction == 'out':
            query += "source_id = ?"
            params.append(entity_id)
        elif direction == 'in':
            query += "target_id = ?"
            params.append(entity_id)
        else:
            query += "(source_id = ? OR target_id = ?)"
            params.extend([entity_id, entity_id])
            
        if relation_type:
            query += " AND type = ?"
            params.append(relation_type)
            
        relations = []
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            for row in conn.execute(query, params):
                relations.append(KGRelation(id=row['id'], source_id=row['source_id'], target_id=row['target_id'], type=row['type'], weight=row['weight'], properties=json.loads(row['properties'])))
        return relations

    def traverse(self, start_id: str, max_depth: int = 3, relation_types: Optional[List[str]] = None) -> Dict[str, Any]:
        # Basic traversal using recursive CTE would be better, but simplified for clarity
        visited = set()
        queue = [(start_id, 0)]
        subgraph = {"entities": [], "relations": []}
        
        while queue:
            current_id, depth = queue.pop(0)
            if current_id in visited or depth > max_depth:
                continue
            visited.add(current_id)
            
            entity = self.get_entity(current_id)
            if entity:
                subgraph["entities"].append(entity)
                
            if depth < max_depth:
                relations = self.get_relations(current_id, direction='out')
                if relation_types:
                    relations = [r for r in relations if r.type in relation_types]
                    
                for rel in relations:
                    subgraph["relations"].append(rel)
                    queue.append((rel.target_id, depth + 1))
                    
        return subgraph

    def find_path(self, source_id: str, target_id: str) -> List[KGRelation]:
        # Simplified BFS for shortest path
        visited = {source_id}
        queue = [(source_id, [])]
        
        while queue:
            current, path = queue.pop(0)
            if current == target_id:
                return path
                
            for rel in self.get_relations(current, direction='out'):
                if rel.target_id not in visited:
                    visited.add(rel.target_id)
                    queue.append((rel.target_id, path + [rel]))
        return []

    async def semantic_search(self, query: str, entity_type: Optional[str] = None) -> List[KGEntity]:
        filters = {"entity_type": entity_type} if entity_type else None
        results = await self.vector_store.search("documents", query, n_results=5, filters=filters)
        
        entities = []
        for res in results:
            entity = self.get_entity(res["id"])
            if entity:
                entities.append(entity)
        return entities

    def delete_entity(self, entity_id: str):
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("PRAGMA foreign_keys = ON")
            conn.execute("DELETE FROM entities WHERE id = ?", (entity_id,))
        self.vector_store.delete("documents", entity_id)

    def delete_relation(self, relation_id: str):
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("DELETE FROM relations WHERE id = ?", (relation_id,))

    async def bootstrap_aniket(self):
        """Bootstrap method to populate Aniket's initial knowledge graph."""
        college_id = await self.add_entity("Organization", "College", {"type": "University"})
        
        ai_course = await self.add_entity("Course", "Artificial Intelligence", {"code": "PCC301COM", "priority": "highest"})
        cn_course = await self.add_entity("Course", "Computer Networks", {"code": "PCC302COM", "priority": "standard"})
        toc_course = await self.add_entity("Course", "Theory of Computation", {"code": "PCC303COM", "priority": "standard"})
        rob_course = await self.add_entity("Course", "Robotics and Automation", {"code": "MDM331COM", "priority": "high", "topic": "edge AI"})
        cloud_course = await self.add_entity("Course", "Cloud Computing", {"code": "PEC321BCOM", "priority": "high", "topic": "distributed systems"})
        
        nvidia_id = await self.add_entity("Company", "NVIDIA", {"goal": "Career Target"})
        
        self.add_relation(ai_course, college_id, "part_of")
        self.add_relation(ai_course, nvidia_id, "relevant_for", weight=0.9)
        self.add_relation(rob_course, nvidia_id, "relevant_for", weight=0.8)
        self.add_relation(cloud_course, nvidia_id, "relevant_for", weight=0.7)
