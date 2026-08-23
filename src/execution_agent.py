"""
CloseLoop Execution Agent
Autonomous multi-channel recovery execution under strict engineering safeguards:
1. Idempotency Key Engine: Prevents duplicate retry storms and double-charging.
2. Customer Timezone Quiet-Hours Gate: Enforces RBI recovery-conduct compliant hours in customer local time.
3. Distributed-style Circuit Breaker: Auto-pauses playbooks when opt-out / complaint rates spike.
4. Fatigue Tracker: Incurs exact fatigue penalties per channel (Silent Retry = 0.0 fatigue).
"""

import hashlib
import threading
from datetime import datetime, time
from typing import Dict, Any, Optional, Tuple
import pytz
from dataclasses import dataclass, asdict

import sys
from pathlib import Path

root_dir = Path(__file__).resolve().parent.parent
if str(root_dir) not in sys.path:
    sys.path.insert(0, str(root_dir))

try:
    from src.ingestion import UnifiedRecoveryEvent
    from src.playbook_selector import PlaybookSelectionResult
except ImportError:
    from ingestion import UnifiedRecoveryEvent
    from playbook_selector import PlaybookSelectionResult


@dataclass
class ExecutionResult:
    action_id: str
    event_id: str
    customer_id: str
    idempotency_key: str
    status: str  # EXECUTED, BLOCKED_IDEMPOTENCY, BLOCKED_QUIET_HOURS, BLOCKED_CIRCUIT_BREAKER, STOPPED_BY_FATIGUE, ESCALATED_HUMAN
    channel: str
    rendered_message: str
    fatigue_score_incurred: float
    is_compliant: bool
    execution_reason: str
    timestamp: str
    scheduled_for_local_time: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class CircuitBreaker:
    """Rolling Window Circuit Breaker for Playbook Categories."""

    def __init__(self, category: str, failure_threshold: float = 0.08, window_size: int = 20):
        self.category = category
        self.failure_threshold = failure_threshold
        self.window_size = window_size
        self.history = []  # list of booleans: True = success, False = complaint/opt-out
        self.state = "CLOSED"  # CLOSED, OPEN, HALF_OPEN
        self.tripped_at: Optional[str] = None
        self.trip_reason: Optional[str] = None
        self._lock = threading.Lock()

    def record_outcome(self, is_success: bool, is_complaint_or_opt_out: bool = False):
        with self._lock:
            self.history.append(not is_complaint_or_opt_out)
            if len(self.history) > self.window_size:
                self.history.pop(0)

            # Check trip condition if enough samples
            if len(self.history) >= 5:
                complaints = self.history.count(False)
                complaint_rate = complaints / len(self.history)
                if complaint_rate >= self.failure_threshold and self.state != "OPEN":
                    self.state = "OPEN"
                    self.tripped_at = datetime.now(pytz.UTC).isoformat()
                    self.trip_reason = (
                        f"Circuit Breaker TRIPPED for category '{self.category}': "
                        f"Complaint/opt-out rate reached {complaint_rate:.1%} "
                        f"(Threshold: {self.failure_threshold:.1%}). Playbook auto-paused."
                    )

    def can_execute(self) -> Tuple[bool, str]:
        with self._lock:
            if self.state == "OPEN":
                return False, f"CIRCUIT_BREAKER_OPEN: Playbook '{self.category}' is auto-paused due to elevated complaints."
            return True, "CLOSED"

    def reset(self):
        with self._lock:
            self.state = "CLOSED"
            self.history.clear()
            self.tripped_at = None
            self.trip_reason = None


class ExecutionAgent:
    """
    Executes bounded playbooks with Idempotency Locks, Timezone Compliance,
    and Category Circuit Breakers.
    """

    def __init__(self):
        self._idempotency_store: Dict[str, ExecutionResult] = {}
        self._idempotency_lock = threading.Lock()
        self.circuit_breakers: Dict[str, CircuitBreaker] = {
            "mandate_retry": CircuitBreaker("mandate_retry", failure_threshold=0.10),
            "checkout_recovery": CircuitBreaker("checkout_recovery", failure_threshold=0.08),
            "b2b_receivables": CircuitBreaker("b2b_receivables", failure_threshold=0.06),
            "hinglish_voice_recovery": CircuitBreaker("hinglish_voice_recovery", failure_threshold=0.06),
        }

    def generate_idempotency_key(self, event: UnifiedRecoveryEvent, action_type: str, step_num: int) -> str:
        """
        Creates a deterministic SHA-256 key per event, customer, action, and amount.
        Prevents double-charging & duplicate retry storms.
        """
        raw_key = f"{event.event_id}:{event.customer_id}:{action_type}:{step_num}:{event.amount}"
        return hashlib.sha256(raw_key.encode("utf-8")).hexdigest()[:24]

    def check_quiet_hours_compliance(
        self,
        event: UnifiedRecoveryEvent,
        action_step,
        start_hour: int = 9,
        end_hour: int = 19
    ) -> Tuple[bool, str, str]:
        """
        Translates event timestamp to customer's actual timezone and checks
        if current local time falls inside compliant contact hours (e.g. 09:00 - 19:00).
        Silent retries are non-intrusive and bypass quiet hours.
        """
        if not action_step.requires_customer_interaction or action_step.channel in ["backend_scheduler", "none", "internal_crm_ticket"]:
            return True, "Compliant (Non-intrusive / Backend action)", "N/A"

        cust_local_time = event.get_customer_local_time()
        local_hour = cust_local_time.hour
        local_time_str = cust_local_time.strftime("%I:%M %p (%Z)")

        if start_hour <= local_hour < end_hour:
            return True, f"Compliant: Customer local time is {local_time_str} (Within {start_hour:02d}:00 - {end_hour:02d}:00 window)", local_time_str
        else:
            return False, (
                f"RBI Quiet-Hours Violation Prevented: Customer local time is {local_time_str} in "
                f"timezone '{event.customer_timezone}', which is outside permissible hours ({start_hour:02d}:00 - {end_hour:02d}:00). "
                f"Outreach deferred to next morning 09:30 AM."
            ), local_time_str

    def execute(
        self,
        event: UnifiedRecoveryEvent,
        selection: PlaybookSelectionResult,
        override_timestamp: Optional[str] = None
    ) -> ExecutionResult:
        """
        Executes the chosen recovery action through all gatekeepers.
        """
        now_ts = override_timestamp or datetime.now(pytz.UTC).isoformat()
        action = selection.selected_action

        if not action:
            return ExecutionResult(
                action_id=f"act_none_{event.event_id}",
                event_id=event.event_id,
                customer_id=event.customer_id,
                idempotency_key="N/A",
                status="STOPPED",
                channel="none",
                rendered_message="No action designated.",
                fatigue_score_incurred=0.0,
                is_compliant=True,
                execution_reason="No viable action found.",
                timestamp=now_ts
            )

        # 1. Stop if stopped by fatigue budget
        if selection.is_stopped_by_fatigue:
            return ExecutionResult(
                action_id=f"act_stop_{event.event_id}",
                event_id=event.event_id,
                customer_id=event.customer_id,
                idempotency_key="N/A",
                status="STOPPED_BY_FATIGUE",
                channel="none",
                rendered_message="[ACTION HALTED] Contact fatigue budget or no-intent threshold reached.",
                fatigue_score_incurred=0.0,
                is_compliant=True,
                execution_reason=selection.selection_reason,
                timestamp=now_ts
            )

        # 2. Idempotency Lock Check
        idempotency_key = self.generate_idempotency_key(event, action.action_type, action.step_number)
        
        with self._idempotency_lock:
            if idempotency_key in self._idempotency_store:
                prev = self._idempotency_store[idempotency_key]
                return ExecutionResult(
                    action_id=f"act_dup_{event.event_id}",
                    event_id=event.event_id,
                    customer_id=event.customer_id,
                    idempotency_key=idempotency_key,
                    status="BLOCKED_IDEMPOTENCY",
                    channel=action.channel,
                    rendered_message=f"[BLOCKED DUPLICATE] Action already executed with key {idempotency_key} at {prev.timestamp}",
                    fatigue_score_incurred=0.0,
                    is_compliant=True,
                    execution_reason="Prevented duplicate charge / retry storm via deterministic idempotency lock.",
                    timestamp=now_ts
                )

        # 3. Circuit Breaker Check
        cb = self.circuit_breakers.get(selection.category)
        if cb:
            can_run, cb_reason = cb.can_execute()
            if not can_run:
                return ExecutionResult(
                    action_id=f"act_cb_{event.event_id}",
                    event_id=event.event_id,
                    customer_id=event.customer_id,
                    idempotency_key=idempotency_key,
                    status="BLOCKED_CIRCUIT_BREAKER",
                    channel=action.channel,
                    rendered_message=f"[BLOCKED CIRCUIT BREAKER] {cb_reason}",
                    fatigue_score_incurred=0.0,
                    is_compliant=True,
                    execution_reason=cb_reason,
                    timestamp=now_ts
                )

        # 4. Quiet-Hours Timezone Compliance Gate
        qh_config = selection.playbook_config.get("constraints", {}).get("quiet_hours", {})
        start_hr = qh_config.get("start_hour", 9)
        end_hr = qh_config.get("end_hour", 19)
        
        is_compliant, qh_reason, cust_local_str = self.check_quiet_hours_compliance(
            event, action, start_hour=start_hr, end_hour=end_hr
        )

        if not is_compliant:
            return ExecutionResult(
                action_id=f"act_qh_{event.event_id}",
                event_id=event.event_id,
                customer_id=event.customer_id,
                idempotency_key=idempotency_key,
                status="BLOCKED_QUIET_HOURS",
                channel=action.channel,
                rendered_message=f"[DEFERRED OUTREACH] Blocked night-time customer contact. Customer local time: {cust_local_str}",
                fatigue_score_incurred=0.0,
                is_compliant=True,  # Because we successfully blocked non-compliant action!
                execution_reason=qh_reason,
                timestamp=now_ts,
                scheduled_for_local_time="Next business day 09:30 AM"
            )

        # 5. Render Message Template
        template_vars = {
            "customer_name": event.customer_name,
            "amount": f"{event.amount:,.2f}",
            "currency": event.currency,
            "invoice_number": event.metadata.get("invoice_number", "INV-2026"),
            "dispute_reason": event.metadata.get("dispute_reason", "Milestone query"),
            "plan_name": event.metadata.get("plan_name", "Subscription"),
            "recovery_url": f"https://pay.rzp.io/r/{event.event_id[:8]}",
            "retry_url": f"https://pay.rzp.io/retry/{event.event_id[:8]}",
            "payment_url": f"https://pay.rzp.io/inv/{event.event_id[:8]}",
            "reauth_url": f"https://pay.rzp.io/mandate/{event.event_id[:8]}",
        }
        
        rendered = action.template
        for k, v in template_vars.items():
            rendered = rendered.replace(f"{{{k}}}", str(v))

        # 6. Execute & Persist Idempotency Record
        result = ExecutionResult(
            action_id=f"act_exec_{event.event_id}",
            event_id=event.event_id,
            customer_id=event.customer_id,
            idempotency_key=idempotency_key,
            status="EXECUTED",
            channel=action.channel,
            rendered_message=rendered,
            fatigue_score_incurred=action.fatigue_weight,
            is_compliant=True,
            execution_reason=f"Dispatched via channel '{action.channel}' under playbook '{selection.playbook_id}'",
            timestamp=now_ts,
            scheduled_for_local_time=cust_local_str
        )

        with self._idempotency_lock:
            self._idempotency_store[idempotency_key] = result

        return result
