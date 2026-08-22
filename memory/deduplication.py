from typing import List, Tuple
from .knowledge_graph import KGEntity, KnowledgeGraph

class Deduplicator:
    """Entity resolution / deduplication."""
    
    def __init__(self, kg: KnowledgeGraph):
        self.kg = kg
        self.exact_match_threshold = 1.0
        self.fuzzy_threshold = 0.85

    def _levenshtein_distance(self, s1: str, s2: str) -> int:
        if len(s1) < len(s2):
            return self._levenshtein_distance(s2, s1)
        if len(s2) == 0:
            return len(s1)
        previous_row = range(len(s2) + 1)
        for i, c1 in enumerate(s1):
            current_row = [i + 1]
            for j, c2 in enumerate(s2):
                insertions = previous_row[j + 1] + 1
                deletions = current_row[j] + 1
                substitutions = previous_row[j] + (c1 != c2)
                current_row.append(min(insertions, deletions, substitutions))
            previous_row = current_row
        return previous_row[-1]

    def is_duplicate(self, entity1: KGEntity, entity2: KGEntity) -> Tuple[bool, float]:
        if entity1.type != entity2.type:
            return False, 0.0
            
        n1 = entity1.name.lower().strip()
        n2 = entity2.name.lower().strip()
        
        if n1 == n2:
            return True, self.exact_match_threshold
            
        max_len = max(len(n1), len(n2))
        if max_len == 0:
            return False, 0.0
            
        distance = self._levenshtein_distance(n1, n2)
        similarity = 1.0 - (distance / max_len)
        
        return similarity >= self.fuzzy_threshold, similarity

    def find_duplicates(self, entity: KGEntity, candidates: List[KGEntity]) -> List[Tuple[KGEntity, float]]:
        duplicates = []
        for candidate in candidates:
            if candidate.id == entity.id:
                continue
            is_dup, conf = self.is_duplicate(entity, candidate)
            if is_dup:
                duplicates.append((candidate, conf))
        return sorted(duplicates, key=lambda x: x[1], reverse=True)

    async def merge_entities(self, entity_ids: List[str]) -> str:
        """Merge multiple entities into one, keeping the properties of the first."""
        if not entity_ids:
            raise ValueError("No entities to merge")
            
        primary_id = entity_ids[0]
        primary = self.kg.get_entity(primary_id)
        if not primary:
            raise ValueError(f"Primary entity {primary_id} not found")
            
        # Re-link relations from secondary entities to primary
        for sec_id in entity_ids[1:]:
            # In-relations
            for rel in self.kg.get_relations(sec_id, direction='in'):
                self.kg.add_relation(rel.source_id, primary_id, rel.type, rel.weight, rel.properties)
            # Out-relations
            for rel in self.kg.get_relations(sec_id, direction='out'):
                self.kg.add_relation(primary_id, rel.target_id, rel.type, rel.weight, rel.properties)
                
            self.kg.delete_entity(sec_id)
            
        return primary_id
