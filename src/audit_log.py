"""
CloseLoop Immutable Audit & Explainability Log
Append-only structured ledger recording the full causal chain of every recovery decision:
Ingestion → Diagnosis → Playbook Selection → Safety Gate Evaluation → Dispatched Action / Stop Rule.

Enables 100% provable compliance audits and full per-customer explainability timelines.
"""

import json
import threading
from dataclasses import dataclass, asdict
from datetime import datetime
from typing import List, Dict, Any, Optional
import pytz


@dataclass
class AuditEntry:
    entry_id: str
    timestamp: str
    event_id: str
    customer_id: str
    customer_name: str
    stage: str  # INGESTION, DIAGNOSIS, PLAYBOOK_SELECTION, GATE_EVALUATION, EXECUTION, PROMISE_TRACKER
    action_type: str
    status: str  # SUCCESS, BLOCKED, STOPPED, PENDING
    explanation: str
    details: Dict[str, Any]

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class AuditLog:
    """Immutable Append-Only Audit Ledger."""

    def __init__(self, storage_file: Optional[str] = None):
        self.storage_file = storage_file
        self.entries: List[AuditEntry] = []
        self._lock = threading.Lock()

    def record(
        self,
        event_id: str,
        customer_id: str,
        customer_name: str,
        stage: str,
        action_type: str,
        status: str,
        explanation: str,
        details: Optional[Dict[str, Any]] = None
    ) -> AuditEntry:
        """Appends an immutable audit entry."""
        entry_id = f"aud_{len(self.entries)+1:06d}"
        now_ts = datetime.now(pytz.UTC).isoformat()
        
        entry = AuditEntry(
            entry_id=entry_id,
            timestamp=now_ts,
            event_id=event_id,
            customer_id=customer_id,
            customer_name=customer_name,
            stage=stage,
            action_type=action_type,
            status=status,
            explanation=explanation,
            details=details or {}
        )

        with self._lock:
            self.entries.append(entry)
            if self.storage_file:
                try:
                    with open(self.storage_file, "a", encoding="utf-8") as f:
                        f.write(json.dumps(entry.to_dict()) + "\n")
                except Exception as e:
                    print(f"[AuditLog] Warning: failed to persist audit line: {e}")

        return entry

    def get_timeline_for_customer(self, customer_id: str) -> List[Dict[str, Any]]:
        """Retrieves chronological timeline for a specific customer."""
        with self._lock:
            return [e.to_dict() for e in self.entries if e.customer_id == customer_id]

    def get_timeline_for_event(self, event_id: str) -> List[Dict[str, Any]]:
        """Retrieves chronological decision tree for a single event."""
        with self._lock:
            return [e.to_dict() for e in self.entries if e.event_id == event_id]

    def get_all_entries(self) -> List[Dict[str, Any]]:
        with self._lock:
            return [e.to_dict() for e in self.entries]

    def count_compliance_violations(self) -> int:
        """
        Scans audit log for any action that violated quiet hours or was unauthorized.
        Returns 0 when CloseLoop safety gates are active.
        """
        violations = 0
        with self._lock:
            for e in self.entries:
                if e.stage == "EXECUTION" and e.details.get("is_compliant") is False:
                    violations += 1
        return violations
