"""
Atlas Relations

Typed, directional, confidence-weighted relations between artifacts.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum, auto
from typing import Optional
from uuid import UUID

from .confidence import ConfidenceAssessment


class RelationType(Enum):
    """Standard relation types in Atlas."""
    
    # Derivation relations
    DERIVES_FROM = auto()     # Target is source of this artifact
    GENERATES = auto()        # This artifact generates target
    
    # Reference relations
    IMPORTS = auto()          # Code import
    REFERENCES = auto()       # General reference
    LINKS_TO = auto()         # Hyperlink or URI reference
    
    # Containment relations
    CONTAINS = auto()         # Target is contained in this
    PART_OF = auto()          # This is part of target
    
    # Dependency relations
    DEPENDS_ON = auto()       # Runtime/build dependency
    REQUIRED_BY = auto()      # Target requires this
    
    # Versioning relations
    SUPERSEDES = auto()       # This replaces target
    VERSION_OF = auto()       # This is a version of target
    
    # Similarity relations
    SIMILAR_TO = auto()       # Content similarity
    DUPLICATE_OF = auto()     # Exact or near duplicate
    
    # Semantic relations
    IMPLEMENTS = auto()       # Implements interface/contract
    EXTENDS = auto()          # Extends/inherits from
    USES = auto()             # Uses functionality from


@dataclass(frozen=True)
class RelationEdge:
    """
    A directed edge representing a relation between artifacts.
    
    Relations are:
    - Typed: Have a specific meaning
    - Directional: From source to target
    - Confidence-weighted: Carry uncertainty
    """
    source_id: UUID
    target_id: UUID
    relation_type: RelationType
    confidence: ConfidenceAssessment
    metadata: dict = None
    
    def __post_init__(self):
        if self.metadata is None:
            object.__setattr__(self, 'metadata', {})
    
    @property
    def is_strong(self) -> bool:
        """Whether this relation has high confidence."""
        return self.confidence.effective_score >= 0.75
    
    def inverse(self) -> Optional[RelationEdge]:
        """
        Get the inverse relation if one exists.
        
        Not all relations have meaningful inverses.
        """
        inverse_type = _INVERSE_RELATIONS.get(self.relation_type)
        if inverse_type is None:
            return None
        
        return RelationEdge(
            source_id=self.target_id,
            target_id=self.source_id,
            relation_type=inverse_type,
            confidence=self.confidence,
            metadata=self.metadata,
        )


# Mapping of relations to their inverses
_INVERSE_RELATIONS: dict[RelationType, RelationType] = {
    RelationType.DERIVES_FROM: RelationType.GENERATES,
    RelationType.GENERATES: RelationType.DERIVES_FROM,
    RelationType.CONTAINS: RelationType.PART_OF,
    RelationType.PART_OF: RelationType.CONTAINS,
    RelationType.DEPENDS_ON: RelationType.REQUIRED_BY,
    RelationType.REQUIRED_BY: RelationType.DEPENDS_ON,
    RelationType.SUPERSEDES: RelationType.VERSION_OF,
    RelationType.IMPLEMENTS: RelationType.EXTENDED_BY if hasattr(RelationType, 'EXTENDED_BY') else None,
}


class RelationGraph:
    """
    Graph of relations between artifacts.
    
    Supports efficient queries for related artifacts.
    """
    
    def __init__(self):
        self._edges: list[RelationEdge] = []
        self._outgoing: dict[UUID, list[RelationEdge]] = {}
        self._incoming: dict[UUID, list[RelationEdge]] = {}
        self._by_type: dict[RelationType, list[RelationEdge]] = {}
    
    def add(self, edge: RelationEdge) -> None:
        """Add a relation edge to the graph."""
        self._edges.append(edge)
        
        # Index by source
        if edge.source_id not in self._outgoing:
            self._outgoing[edge.source_id] = []
        self._outgoing[edge.source_id].append(edge)
        
        # Index by target
        if edge.target_id not in self._incoming:
            self._incoming[edge.target_id] = []
        self._incoming[edge.target_id].append(edge)
        
        # Index by type
        if edge.relation_type not in self._by_type:
            self._by_type[edge.relation_type] = []
        self._by_type[edge.relation_type].append(edge)
    
    def outgoing(
        self,
        artifact_id: UUID,
        relation_type: Optional[RelationType] = None,
    ) -> list[RelationEdge]:
        """Get outgoing relations from an artifact."""
        edges = self._outgoing.get(artifact_id, [])
        if relation_type is not None:
            edges = [e for e in edges if e.relation_type == relation_type]
        return edges
    
    def incoming(
        self,
        artifact_id: UUID,
        relation_type: Optional[RelationType] = None,
    ) -> list[RelationEdge]:
        """Get incoming relations to an artifact."""
        edges = self._incoming.get(artifact_id, [])
        if relation_type is not None:
            edges = [e for e in edges if e.relation_type == relation_type]
        return edges
    
    def related(
        self,
        artifact_id: UUID,
        relation_type: Optional[RelationType] = None,
    ) -> list[RelationEdge]:
        """Get all relations involving an artifact."""
        return (
            self.outgoing(artifact_id, relation_type)
            + self.incoming(artifact_id, relation_type)
        )
    
    def of_type(self, relation_type: RelationType) -> list[RelationEdge]:
        """Get all relations of a specific type."""
        return self._by_type.get(relation_type, [])
    
    def path_exists(
        self,
        source_id: UUID,
        target_id: UUID,
        relation_types: Optional[set[RelationType]] = None,
        max_depth: int = 10,
    ) -> bool:
        """Check if a path exists between two artifacts."""
        if source_id == target_id:
            return True
        
        visited: set[UUID] = set()
        queue: list[tuple[UUID, int]] = [(source_id, 0)]
        
        while queue:
            current, depth = queue.pop(0)
            
            if current in visited:
                continue
            visited.add(current)
            
            if depth >= max_depth:
                continue
            
            for edge in self.outgoing(current):
                if relation_types and edge.relation_type not in relation_types:
                    continue
                
                if edge.target_id == target_id:
                    return True
                
                if edge.target_id not in visited:
                    queue.append((edge.target_id, depth + 1))
        
        return False
    
    def find_path(
        self,
        source_id: UUID,
        target_id: UUID,
        relation_types: Optional[set[RelationType]] = None,
        max_depth: int = 10,
    ) -> Optional[list[RelationEdge]]:
        """Find a path between two artifacts, if one exists."""
        if source_id == target_id:
            return []
        
        visited: set[UUID] = set()
        queue: list[tuple[UUID, list[RelationEdge]]] = [(source_id, [])]
        
        while queue:
            current, path = queue.pop(0)
            
            if current in visited:
                continue
            visited.add(current)
            
            if len(path) >= max_depth:
                continue
            
            for edge in self.outgoing(current):
                if relation_types and edge.relation_type not in relation_types:
                    continue
                
                new_path = path + [edge]
                
                if edge.target_id == target_id:
                    return new_path
                
                if edge.target_id not in visited:
                    queue.append((edge.target_id, new_path))
        
        return None
    
    def descendants(
        self,
        artifact_id: UUID,
        relation_type: RelationType,
        max_depth: int = 10,
    ) -> set[UUID]:
        """Get all descendants via a relation type."""
        result: set[UUID] = set()
        queue: list[tuple[UUID, int]] = [(artifact_id, 0)]
        
        while queue:
            current, depth = queue.pop(0)
            
            if depth >= max_depth:
                continue
            
            for edge in self.outgoing(current, relation_type):
                if edge.target_id not in result:
                    result.add(edge.target_id)
                    queue.append((edge.target_id, depth + 1))
        
        return result
    
    def ancestors(
        self,
        artifact_id: UUID,
        relation_type: RelationType,
        max_depth: int = 10,
    ) -> set[UUID]:
        """Get all ancestors via a relation type."""
        result: set[UUID] = set()
        queue: list[tuple[UUID, int]] = [(artifact_id, 0)]
        
        while queue:
            current, depth = queue.pop(0)
            
            if depth >= max_depth:
                continue
            
            for edge in self.incoming(current, relation_type):
                if edge.source_id not in result:
                    result.add(edge.source_id)
                    queue.append((edge.source_id, depth + 1))
        
        return result
