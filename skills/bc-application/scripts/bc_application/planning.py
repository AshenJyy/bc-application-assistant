"""Internal future bridge contracts. No College Planner API/integration is present."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, Protocol

PlanningKind = Literal["application_requirement", "deadline", "task", "financial_aid", "scholarship", "fee_waiver"]


@dataclass(frozen=True)
class ProfileRef:
    """References the one canonical profile; never a second profile payload."""
    profile_id: str
    revision: int


@dataclass(frozen=True)
class PlanningItem:
    external_id: str
    target_id: str
    kind: PlanningKind
    source_url: str
    label: str
    canonical_field_refs: tuple[str, ...] = ()
    deadline_raw: str | None = None
    timezone: str | None = None
    status: Literal["unknown", "pending", "complete"] = "unknown"


@dataclass(frozen=True)
class ProgressUpdate:
    """Status references only; does not export grades, essays, credentials or identity."""
    external_id: str
    canonical_checkpoint_id: str
    status: Literal["pending", "complete"]


class PlanningProvider(Protocol):
    def capabilities(self) -> frozenset[PlanningKind]: ...
    def read_items(self, profile: ProfileRef, target_ids: tuple[str, ...]) -> tuple[PlanningItem, ...]: ...
    def propose_progress_sync(self, profile: ProfileRef, updates: tuple[ProgressUpdate, ...]) -> object:
        """Return a proposal for confirmation; no implicit external mutation."""
        ...


class PlannerUnavailable(RuntimeError):
    pass


class UnconfiguredPlanningProvider:
    """Explicitly unavailable until an authorized, documented API exists."""
    def capabilities(self) -> frozenset[PlanningKind]:
        return frozenset()

    def read_items(self, profile: ProfileRef, target_ids: tuple[str, ...]) -> tuple[PlanningItem, ...]:
        raise PlannerUnavailable("No planning service is connected")

    def propose_progress_sync(self, profile: ProfileRef, updates: tuple[ProgressUpdate, ...]) -> object:
        raise PlannerUnavailable("No planning service is connected")
