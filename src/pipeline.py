"""
CloseLoop Recovery Pipeline
Unified orchestrator executing the full causal flow:
Ingestion → Explainable Diagnosis → Declarative Playbook Selection → Gated Execution → Audit Logging
"""

import sys
from pathlib import Path

root_dir = Path(__file__).resolve().parent.parent
if str(root_dir) not in sys.path:
    sys.path.insert(0, str(root_dir))

import random
from typing import Dict, Any, Optional
from datetime import datetime, timedelta
import pytz

try:
    from src.ingestion import UnifiedRecoveryEvent, ingest_event
    from src.diagnosis_engine import DiagnosisEngine, DiagnosisResult
    from src.playbook_selector import PlaybookSelector, PlaybookSelectionResult
    from src.execution_agent import ExecutionAgent, ExecutionResult
    from src.promise_tracker import PromiseTracker
    from src.audit_log import AuditLog
except ImportError:
    from ingestion import UnifiedRecoveryEvent, ingest_event
    from diagnosis_engine import DiagnosisEngine, DiagnosisResult
    from playbook_selector import PlaybookSelector, PlaybookSelectionResult
    from execution_agent import ExecutionAgent, ExecutionResult
    from promise_tracker import PromiseTracker
    from audit_log import AuditLog


class CloseLoopPipeline:
    """End-to-End Autonomous Revenue Recovery Engine."""

    def __init__(self, playbooks_dir: str = "playbooks", audit_file: Optional[str] = None):
        self.diagnoser = DiagnosisEngine()
        self.selector = PlaybookSelector(playbooks_dir=playbooks_dir)
        self.executor = ExecutionAgent()
        self.promise_tracker = PromiseTracker()
        self.audit_log = AuditLog(storage_file=audit_file)

    def process_event(self, raw_or_event: Any) -> Dict[str, Any]:
        """
        Executes one recovery event through the entire CloseLoop pipeline.
        """
        if isinstance(raw_or_event, UnifiedRecoveryEvent):
            event = raw_or_event
        else:
            event = ingest_event(raw_or_event)

        # 1. Audit Ingestion
        self.audit_log.record(
            event_id=event.event_id,
            customer_id=event.customer_id,
            customer_name=event.customer_name,
            stage="INGESTION",
            action_type="EVENT_INGESTED",
            status="SUCCESS",
            explanation=f"Received {event.event_type} event for {event.customer_name} (Amount: INR {event.amount:,.2f})",
            details=event.to_dict()
        )

        # 2. Check Active Promise Grace Period Hold
        if self.promise_tracker.has_active_grace_period(event.customer_id):
            pause_msg = f"Hold active: Customer {event.customer_id} has an open Promise-to-Pay within grace period."
            self.audit_log.record(
                event_id=event.event_id,
                customer_id=event.customer_id,
                customer_name=event.customer_name,
                stage="GATE_EVALUATION",
                action_type="PROMISE_GRACE_HOLD",
                status="STOPPED",
                explanation=pause_msg,
                details={"customer_id": event.customer_id}
            )
            return {
                "event": event.to_dict(),
                "diagnosis": None,
                "selection": None,
                "execution": {
                    "status": "STOPPED_PROMISE_GRACE",
                    "channel": "none",
                    "fatigue_score_incurred": 0.0,
                    "rendered_message": "[ESCALATION PAUSED] Customer is currently inside an active Promise-to-Pay grace period.",
                    "is_compliant": True,
                    "execution_reason": pause_msg,
                },
                "estimated_revenue_recovered": 0.0,
                "fatigue_score": 0.0,
            }

        # 3. Diagnosis Engine
        diagnosis = self.diagnoser.diagnose(event)
        self.audit_log.record(
            event_id=event.event_id,
            customer_id=event.customer_id,
            customer_name=event.customer_name,
            stage="DIAGNOSIS",
            action_type="CLASSIFY_ROOT_CAUSE",
            status="SUCCESS",
            explanation=diagnosis.explanation,
            details=diagnosis.to_dict()
        )

        # 4. Playbook Selection
        current_trust = self.promise_tracker.get_trust_score(event.customer_id, event.historical_trust_score)
        selection = self.selector.select_playbook(event, diagnosis, effective_trust_score=current_trust)
        
        self.audit_log.record(
            event_id=event.event_id,
            customer_id=event.customer_id,
            customer_name=event.customer_name,
            stage="PLAYBOOK_SELECTION",
            action_type="SELECT_BOUNDED_PLAYBOOK",
            status="STOPPED" if selection.is_stopped_by_fatigue else "SUCCESS",
            explanation=selection.selection_reason,
            details=selection.to_dict()
        )

        # 5. Gated Execution
        execution = self.executor.execute(event, selection)
        
        self.audit_log.record(
            event_id=event.event_id,
            customer_id=event.customer_id,
            customer_name=event.customer_name,
            stage="EXECUTION",
            action_type=execution.channel,
            status=execution.status,
            explanation=execution.execution_reason,
            details=execution.to_dict()
        )

        # 6. Promise-to-Pay Registration if applicable
        if diagnosis.root_cause == "CASH_FLOW_DELAY" and execution.status == "EXECUTED":
            promise_date = (datetime.now(pytz.UTC) + timedelta(days=10)).isoformat()
            self.promise_tracker.record_promise(
                customer_id=event.customer_id,
                event_id=event.event_id,
                amount=event.amount,
                promised_date_iso=promise_date,
                notes="10-day extension recorded via B2B Receivables Playbook"
            )

        # 7. Recovery Outcome Simulation (Realistic probabilistic recovery)
        recovered_amount = 0.0
        if execution.status in ["EXECUTED", "BLOCKED_QUIET_HOURS"]:
            # Probability model based on root cause & channel suitability
            base_prob = 0.72
            if diagnosis.root_cause == "BANK_DOWNTIME":
                base_prob = 0.88  # Silent retries succeed very well once bank stabilizes
            elif diagnosis.root_cause == "CHECKOUT_FRICTION":
                base_prob = 0.78  # 1-click cart recovery
            elif diagnosis.root_cause == "PRICE_HESITATION":
                base_prob = 0.65  # 5% coupon conversion
            elif diagnosis.root_cause == "CARD_EXPIRED":
                base_prob = 0.60  # Requires user updating card
            elif diagnosis.root_cause == "MANDATE_EXPIRED":
                base_prob = 0.70  # Re-authorization link
            elif diagnosis.root_cause == "GENUINE_DISPUTE":
                base_prob = 0.50  # Routed to account manager
            elif diagnosis.root_cause == "CASH_FLOW_DELAY":
                base_prob = 0.80  # Promise-to-pay extension fulfilled
            
            # Trust score multiplier
            prob = min(0.95, base_prob * (0.6 + 0.4 * current_trust))
            if execution.status == "BLOCKED_QUIET_HOURS":
                prob *= 0.90  # Minor discount for morning deferred delivery
            
            # Deterministic simulation hash for repeatability
            sim_seed = hash(f"{event.event_id}:{execution.action_id}") % 100
            if sim_seed < (prob * 100):
                recovered_amount = event.amount

        return {
            "event": event.to_dict(),
            "diagnosis": diagnosis.to_dict(),
            "selection": selection.to_dict(),
            "execution": execution.to_dict(),
            "estimated_revenue_recovered": recovered_amount,
            "fatigue_score": execution.fatigue_score_incurred,
        }
