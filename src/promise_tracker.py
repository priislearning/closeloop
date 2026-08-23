"""
CloseLoop Promise-to-Pay Tracker & Trust Feedback Loop
Manages commitment dates, pauses active escalation during grace periods,
and dynamically feeds back promise fulfillment into a continuous Customer Trust Score.
"""

from dataclasses import dataclass, asdict
from datetime import datetime, timedelta
from typing import Dict, Any, Optional, Tuple
import pytz


@dataclass
class PromiseToPay:
    promise_id: str
    customer_id: str
    event_id: str
    amount: float
    promised_date: str  # ISO-8601 string
    grace_period_hours: int
    status: str  # PENDING, KEPT, BROKEN, CANCELLED
    created_at: str
    resolved_at: Optional[str] = None
    notes: Optional[str] = None

    def get_deadline_with_grace(self) -> datetime:
        clean_ts = self.promised_date.replace("Z", "+00:00")
        dt = datetime.fromisoformat(clean_ts)
        if dt.tzinfo is None:
            dt = pytz.UTC.localize(dt)
        return dt + timedelta(hours=self.grace_period_hours)

    def is_in_grace_period(self, current_time: Optional[datetime] = None) -> bool:
        if self.status != "PENDING":
            return False
        now = current_time or datetime.now(pytz.UTC)
        return now <= self.get_deadline_with_grace()

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class PromiseTracker:
    """Stateful Promise-to-Pay Manager with Customer Trust Feedback Loop."""

    def __init__(self):
        self.promises: Dict[str, PromiseToPay] = {}
        # customer_id -> trust_score (0.0 to 1.0)
        self.customer_trust_scores: Dict[str, float] = {}

    def get_trust_score(self, customer_id: str, default_score: float = 0.8) -> float:
        """Returns the customer's current learned trust score."""
        return self.customer_trust_scores.get(customer_id, default_score)

    def set_trust_score(self, customer_id: str, score: float):
        self.customer_trust_scores[customer_id] = max(0.1, min(1.0, round(score, 2)))

    def record_promise(
        self,
        customer_id: str,
        event_id: str,
        amount: float,
        promised_date_iso: str,
        grace_period_hours: int = 48,
        notes: str = "Client committed payment date"
    ) -> PromiseToPay:
        """Registers a new promise-to-pay commitment."""
        promise_id = f"p2p_{event_id[:8]}_{len(self.promises)+1}"
        promise = PromiseToPay(
            promise_id=promise_id,
            customer_id=customer_id,
            event_id=event_id,
            amount=amount,
            promised_date=promised_date_iso,
            grace_period_hours=grace_period_hours,
            status="PENDING",
            created_at=datetime.now(pytz.UTC).isoformat(),
            notes=notes
        )
        self.promises[promise_id] = promise
        return promise

    def has_active_grace_period(self, customer_id: str, current_time: Optional[datetime] = None) -> bool:
        """Checks if the customer has an active pending promise within its grace window."""
        for p in self.promises.values():
            if p.customer_id == customer_id and p.is_in_grace_period(current_time):
                return True
        return False

    def resolve_promise(
        self,
        promise_id: str,
        payment_received: bool,
        current_time: Optional[datetime] = None
    ) -> Tuple[PromiseToPay, float]:
        """
        Resolves a promise and updates customer trust score.
        Reward on fulfilled promise (+0.12), penalty on broken promise (-0.25).
        """
        now = current_time or datetime.now(pytz.UTC)
        promise = self.promises.get(promise_id)
        if not promise:
            raise ValueError(f"Promise ID '{promise_id}' not found.")

        old_score = self.get_trust_score(promise.customer_id)
        if payment_received:
            promise.status = "KEPT"
            new_score = min(1.0, old_score + 0.12)
            promise.notes = f"Fulfilled on time. Trust increased from {old_score:.2f} -> {new_score:.2f}"
        else:
            promise.status = "BROKEN"
            new_score = max(0.10, old_score - 0.25)
            promise.notes = f"Promise broken. Trust decreased from {old_score:.2f} -> {new_score:.2f}"

        promise.resolved_at = now.isoformat()
        self.set_trust_score(promise.customer_id, new_score)
        return promise, new_score

    def get_customer_history(self, customer_id: str) -> list:
        return [p.to_dict() for p in self.promises.values() if p.customer_id == customer_id]
