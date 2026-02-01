"""
Atlas Budget System

Budgets constrain resource consumption during observation.
Eyes must respect budgets to ensure safe, bounded extraction.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum, auto
from typing import Optional


class BudgetType(Enum):
    """Types of budgets that can constrain operations."""
    TIME = auto()          # Wall-clock time limit
    BYTES_READ = auto()    # Total bytes read
    FILES_SCANNED = auto() # Number of files examined
    DEPTH = auto()         # Directory/nesting depth
    ITEMS = auto()         # Number of artifacts
    MEMORY = auto()        # Memory consumption
    API_CALLS = auto()     # External API calls


@dataclass
class BudgetLimit:
    """A single budget constraint."""
    budget_type: BudgetType
    limit: float
    consumed: float = 0.0
    
    @property
    def remaining(self) -> float:
        """How much budget remains."""
        return max(0.0, self.limit - self.consumed)
    
    @property
    def exhausted(self) -> bool:
        """Whether budget is fully consumed."""
        return self.consumed >= self.limit
    
    @property
    def utilization(self) -> float:
        """Fraction of budget consumed (0.0 to 1.0+)."""
        if self.limit == 0:
            return 1.0
        return self.consumed / self.limit
    
    def consume(self, amount: float) -> bool:
        """
        Consume budget. Returns True if consumption was within limits.
        """
        self.consumed += amount
        return self.consumed <= self.limit
    
    def can_consume(self, amount: float) -> bool:
        """Check if amount can be consumed without exceeding."""
        return self.consumed + amount <= self.limit


@dataclass
class Budget:
    """
    Collection of budget limits for an operation.
    
    Budgets are checked before each extraction step.
    When any budget is exhausted, extraction must stop.
    """
    limits: dict[BudgetType, BudgetLimit] = field(default_factory=dict)
    started_at: Optional[datetime] = None
    ended_at: Optional[datetime] = None
    
    @classmethod
    def create(
        cls,
        *,
        time_seconds: Optional[float] = None,
        bytes_limit: Optional[int] = None,
        files_limit: Optional[int] = None,
        depth_limit: Optional[int] = None,
        items_limit: Optional[int] = None,
        memory_mb: Optional[float] = None,
        api_calls: Optional[int] = None,
    ) -> Budget:
        """Create a budget with specified limits."""
        limits = {}
        
        if time_seconds is not None:
            limits[BudgetType.TIME] = BudgetLimit(
                BudgetType.TIME, time_seconds
            )
        if bytes_limit is not None:
            limits[BudgetType.BYTES_READ] = BudgetLimit(
                BudgetType.BYTES_READ, bytes_limit
            )
        if files_limit is not None:
            limits[BudgetType.FILES_SCANNED] = BudgetLimit(
                BudgetType.FILES_SCANNED, files_limit
            )
        if depth_limit is not None:
            limits[BudgetType.DEPTH] = BudgetLimit(
                BudgetType.DEPTH, depth_limit
            )
        if items_limit is not None:
            limits[BudgetType.ITEMS] = BudgetLimit(
                BudgetType.ITEMS, items_limit
            )
        if memory_mb is not None:
            limits[BudgetType.MEMORY] = BudgetLimit(
                BudgetType.MEMORY, memory_mb
            )
        if api_calls is not None:
            limits[BudgetType.API_CALLS] = BudgetLimit(
                BudgetType.API_CALLS, api_calls
            )
        
        return cls(limits=limits)
    
    def start(self) -> None:
        """Mark budget tracking as started."""
        self.started_at = datetime.utcnow()
    
    def stop(self) -> None:
        """Mark budget tracking as stopped."""
        self.ended_at = datetime.utcnow()
    
    @property
    def elapsed_seconds(self) -> float:
        """Seconds elapsed since start."""
        if self.started_at is None:
            return 0.0
        end = self.ended_at or datetime.utcnow()
        return (end - self.started_at).total_seconds()
    
    @property
    def any_exhausted(self) -> bool:
        """Whether any budget is exhausted."""
        # Check time budget specially
        if BudgetType.TIME in self.limits:
            time_limit = self.limits[BudgetType.TIME]
            if self.elapsed_seconds >= time_limit.limit:
                return True
        
        return any(limit.exhausted for limit in self.limits.values())
    
    @property
    def exhausted_budgets(self) -> list[BudgetType]:
        """List of exhausted budget types."""
        exhausted = []
        
        if BudgetType.TIME in self.limits:
            time_limit = self.limits[BudgetType.TIME]
            if self.elapsed_seconds >= time_limit.limit:
                exhausted.append(BudgetType.TIME)
        
        for budget_type, limit in self.limits.items():
            if budget_type != BudgetType.TIME and limit.exhausted:
                exhausted.append(budget_type)
        
        return exhausted
    
    def consume(self, budget_type: BudgetType, amount: float) -> bool:
        """
        Consume from a specific budget.
        Returns True if within limits.
        """
        if budget_type not in self.limits:
            return True  # No limit set
        return self.limits[budget_type].consume(amount)
    
    def can_consume(self, budget_type: BudgetType, amount: float) -> bool:
        """Check if consumption would be within limits."""
        if budget_type not in self.limits:
            return True
        return self.limits[budget_type].can_consume(amount)
    
    def remaining(self, budget_type: BudgetType) -> Optional[float]:
        """Get remaining budget for a type, None if unlimited."""
        if budget_type == BudgetType.TIME:
            if BudgetType.TIME in self.limits:
                return self.limits[BudgetType.TIME].limit - self.elapsed_seconds
            return None
        
        if budget_type not in self.limits:
            return None
        return self.limits[budget_type].remaining
    
    def summary(self) -> dict[str, dict[str, float]]:
        """Get summary of all budgets."""
        result = {}
        
        for budget_type, limit in self.limits.items():
            consumed = limit.consumed
            if budget_type == BudgetType.TIME:
                consumed = self.elapsed_seconds
            
            result[budget_type.name.lower()] = {
                "limit": limit.limit,
                "consumed": consumed,
                "remaining": max(0.0, limit.limit - consumed),
                "utilization": consumed / limit.limit if limit.limit > 0 else 1.0,
            }
        
        return result


# -----------------------------------------------------------------------------
# Budget Presets
# -----------------------------------------------------------------------------

class BudgetPresets:
    """Common budget configurations."""
    
    @staticmethod
    def quick_scan() -> Budget:
        """Fast, shallow scan for discovery."""
        return Budget.create(
            time_seconds=30,
            files_limit=100,
            bytes_limit=10 * 1024 * 1024,  # 10 MB
            depth_limit=3,
        )
    
    @staticmethod
    def standard() -> Budget:
        """Standard extraction budget."""
        return Budget.create(
            time_seconds=300,  # 5 minutes
            files_limit=1000,
            bytes_limit=100 * 1024 * 1024,  # 100 MB
            depth_limit=10,
        )
    
    @staticmethod
    def deep_analysis() -> Budget:
        """Thorough analysis with generous limits."""
        return Budget.create(
            time_seconds=3600,  # 1 hour
            files_limit=10000,
            bytes_limit=1024 * 1024 * 1024,  # 1 GB
            depth_limit=20,
        )
    
    @staticmethod
    def metadata_only() -> Budget:
        """Minimal budget for metadata-only scans."""
        return Budget.create(
            time_seconds=60,
            files_limit=500,
            bytes_limit=1024 * 1024,  # 1 MB
            depth_limit=5,
        )
    
    @staticmethod
    def unlimited() -> Budget:
        """No budget constraints (use carefully)."""
        return Budget()


# -----------------------------------------------------------------------------
# Budget Guard Context Manager
# -----------------------------------------------------------------------------

class BudgetGuard:
    """
    Context manager for budget-aware operations.
    
    Usage:
        budget = Budget.create(time_seconds=30, files_limit=100)
        with BudgetGuard(budget) as guard:
            for file in files:
                if not guard.can_continue():
                    break
                guard.consume_file()
                process(file)
    """
    
    def __init__(self, budget: Budget):
        self.budget = budget
        self._files_processed = 0
        self._bytes_processed = 0
    
    def __enter__(self) -> BudgetGuard:
        self.budget.start()
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        self.budget.stop()
    
    def can_continue(self) -> bool:
        """Check if operation should continue."""
        return not self.budget.any_exhausted
    
    def consume_file(self, size_bytes: int = 0) -> bool:
        """Record file processing. Returns True if within budget."""
        self._files_processed += 1
        self._bytes_processed += size_bytes
        
        within_files = self.budget.consume(BudgetType.FILES_SCANNED, 1)
        within_bytes = self.budget.consume(BudgetType.BYTES_READ, size_bytes)
        
        return within_files and within_bytes
    
    def consume_item(self) -> bool:
        """Record item creation. Returns True if within budget."""
        return self.budget.consume(BudgetType.ITEMS, 1)
    
    def consume_api_call(self) -> bool:
        """Record API call. Returns True if within budget."""
        return self.budget.consume(BudgetType.API_CALLS, 1)
    
    def at_depth(self, depth: int) -> bool:
        """Check if depth is within budget."""
        limit = self.budget.limits.get(BudgetType.DEPTH)
        if limit is None:
            return True
        return depth <= limit.limit
    
    @property
    def summary(self) -> dict:
        """Get current budget summary."""
        return {
            "exhausted": self.budget.any_exhausted,
            "exhausted_types": [t.name for t in self.budget.exhausted_budgets],
            "budgets": self.budget.summary(),
        }
