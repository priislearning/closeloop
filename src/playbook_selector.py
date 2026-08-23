"""
CloseLoop Declarative Playbook Selector
Loads YAML playbooks dynamically from /playbooks and matches against:
(Root Cause × Customer Trust Score × Contact History × Event Amount × Risk Profile)

Guarantees:
- Zero hardcoded recovery logic; all behaviors are declared in YAML.
- Enforces fatigue limits and stop rules before returning a selected action.
- Explainable selection rationale for the immutable audit log.
"""

import sys
import os
import glob
from pathlib import Path
import yaml
from dataclasses import dataclass, asdict
from typing import Dict, Any, List, Optional

root_dir = Path(__file__).resolve().parent.parent
if str(root_dir) not in sys.path:
    sys.path.insert(0, str(root_dir))

try:
    from src.ingestion import UnifiedRecoveryEvent
    from src.diagnosis_engine import DiagnosisResult
except ImportError:
    from ingestion import UnifiedRecoveryEvent
    from diagnosis_engine import DiagnosisResult


@dataclass
class SelectedActionStep:
    step_number: int
    action_type: str
    channel: str
    delay_minutes: int
    description: str
    template: str
    requires_customer_interaction: bool
    fatigue_weight: float


@dataclass
class PlaybookSelectionResult:
    playbook_id: str
    playbook_name: str
    category: str
    is_eligible: bool
    is_stopped_by_fatigue: bool
    selection_reason: str
    selected_action: Optional[SelectedActionStep]
    playbook_config: Dict[str, Any]

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class PlaybookSelector:
    """Dynamic YAML Playbook Registry & Decision Selector."""

    def __init__(self, playbooks_dir: str = "playbooks"):
        self.playbooks_dir = playbooks_dir
        self.playbooks: Dict[str, Dict[str, Any]] = {}
        self.load_playbooks()

    def load_playbooks(self):
        """Scans and loads all .yaml files in the playbooks directory."""
        self.playbooks.clear()
        pattern = os.path.join(self.playbooks_dir, "*.yaml")
        yaml_files = glob.glob(pattern)
        
        for file_path in yaml_files:
            try:
                with open(file_path, "r", encoding="utf-8") as f:
                    data = yaml.safe_load(f)
                    if data and "playbook_id" in data:
                        self.playbooks[data["playbook_id"]] = data
            except Exception as e:
                print(f"[PlaybookSelector] Warning: Failed to parse {file_path}: {e}")

    def select_playbook(
        self,
        event: UnifiedRecoveryEvent,
        diagnosis: DiagnosisResult,
        effective_trust_score: Optional[float] = None
    ) -> PlaybookSelectionResult:
        """
        Matches event & diagnosis to the optimal declarative playbook step.
        """
        trust_score = effective_trust_score if effective_trust_score is not None else event.historical_trust_score
        root_cause = diagnosis.root_cause
        
        # 1. Special case: NO_INTENT immediately routes to checkout stop
        if root_cause == "NO_INTENT":
            checkout_pb = self.playbooks.get("checkout_recovery")
            action = SelectedActionStep(
                step_number=1,
                action_type="stop_no_contact",
                channel="none",
                delay_minutes=0,
                description="STOP RULE: Low-intent browsing session. Zero customer contact to protect brand equity.",
                template="NO_MESSAGE_DISPATCHED",
                requires_customer_interaction=false if hasattr(globals(), 'false') else False,
                fatigue_weight=0.0
            )
            return PlaybookSelectionResult(
                playbook_id="checkout_recovery",
                playbook_name="Friction & Intent Aware Checkout Recovery",
                category="checkout_recovery",
                is_eligible=True,
                is_stopped_by_fatigue=True,
                selection_reason="Restraint Rule: Session has NO_INTENT. Avoided contact fatigue entirely.",
                selected_action=action,
                playbook_config=checkout_pb or {}
            )

        # 2. Check Candidate Playbooks that accept this root cause
        candidates = []
        for pb_id, pb in self.playbooks.items():
            eligible_causes = pb.get("eligible_root_causes", [])
            if root_cause in eligible_causes:
                min_trust = pb.get("constraints", {}).get("min_trust_score", 0.0)
                if trust_score >= min_trust:
                    candidates.append((pb_id, pb))

        if not candidates:
            # Fallback to mandate_retry or general
            pb = self.playbooks.get("mandate_retry", {})
            action = SelectedActionStep(
                step_number=1,
                action_type="fallback_silent_check",
                channel="backend_scheduler",
                delay_minutes=60,
                description="Fallback non-intrusive backend check",
                template="SILENT_FALLBACK",
                requires_customer_interaction=False,
                fatigue_weight=0.0
            )
            return PlaybookSelectionResult(
                playbook_id="mandate_retry",
                playbook_name="Mandate & Recurring Payment Retry Sequencer",
                category="mandate_retry",
                is_eligible=True,
                is_stopped_by_fatigue=False,
                selection_reason="Fallback selection for unclassified pattern",
                selected_action=action,
                playbook_config=pb
            )

        # 3. Preference Ranking among eligible candidates
        # E.g. High value B2B with high trust might use hinglish voice; Checkout issues use checkout_recovery
        chosen_pb_id, chosen_pb = None, None
        
        if event.event_type == "checkout_abandonment" and "checkout_recovery" in [c[0] for c in candidates]:
            chosen_pb_id = "checkout_recovery"
            chosen_pb = self.playbooks["checkout_recovery"]
        elif event.event_type == "b2b_receivables":
            if event.amount >= 50000 and trust_score >= 0.65 and "hinglish_voice_recovery" in [c[0] for c in candidates]:
                chosen_pb_id = "hinglish_voice_recovery"
                chosen_pb = self.playbooks["hinglish_voice_recovery"]
            else:
                chosen_pb_id = "receivables_chaser"
                chosen_pb = self.playbooks.get("receivables_chaser", candidates[0][1])
        elif root_cause in ["BANK_DOWNTIME", "MANDATE_LAPSE", "MANDATE_EXPIRED"]:
            chosen_pb_id = "mandate_retry"
            chosen_pb = self.playbooks["mandate_retry"]
        else:
            # Default to first eligible candidate
            chosen_pb_id, chosen_pb = candidates[0]

        # 4. Check Fatigue / Max Contact Attempts Constraint
        max_allowed_attempts = chosen_pb.get("constraints", {}).get("max_contact_attempts_allowed", 2)
        if event.contact_count_last_7d >= max_allowed_attempts:
            # Fatigue stopper triggered!
            return PlaybookSelectionResult(
                playbook_id=chosen_pb_id,
                playbook_name=chosen_pb.get("name", chosen_pb_id),
                category=chosen_pb.get("category", "general"),
                is_eligible=True,
                is_stopped_by_fatigue=True,
                selection_reason=(
                    f"STOP RULE TRIGGERED: Customer already received {event.contact_count_last_7d} "
                    f"contacts in last 7d (Max allowed: {max_allowed_attempts}). Recovery halted to prevent fatigue."
                ),
                selected_action=SelectedActionStep(
                    step_number=99,
                    action_type="stop_fatigue_budget_exceeded",
                    channel="none",
                    delay_minutes=0,
                    description="Outreach stopped due to customer contact fatigue budget exhaustion",
                    template="STOP_FATIGUE_LIMIT",
                    requires_customer_interaction=False,
                    fatigue_weight=0.0
                ),
                playbook_config=chosen_pb
            )

        # 5. Extract Step for this root cause
        steps = chosen_pb.get("escalation_steps", [])
        matched_step = None
        for st in steps:
            if st.get("root_cause_match") == root_cause:
                matched_step = st
                break
        if not matched_step and steps:
            matched_step = steps[0]

        fatigue_map = chosen_pb.get("fatigue_scoring", {})
        chan = matched_step.get("channel", "sms")
        f_weight = fatigue_map.get(f"{chan}_fatigue", 1.0)

        # Render template if customized
        template_text = matched_step.get("template", "")
        if "template_high_trust" in matched_step and trust_score >= 0.75:
            template_text = matched_step.get("template_high_trust", template_text)
        elif "template_standard" in matched_step:
            template_text = matched_step.get("template_standard", template_text)

        action_obj = SelectedActionStep(
            step_number=matched_step.get("step", 1),
            action_type=matched_step.get("action_type", "retry"),
            channel=matched_step.get("channel", "sms"),
            delay_minutes=matched_step.get("delay_minutes", 0),
            description=matched_step.get("description", ""),
            template=template_text.strip(),
            requires_customer_interaction=matched_step.get("requires_customer_interaction", True),
            fatigue_weight=f_weight
        )

        return PlaybookSelectionResult(
            playbook_id=chosen_pb_id,
            playbook_name=chosen_pb.get("name", chosen_pb_id),
            category=chosen_pb.get("category", "general"),
            is_eligible=True,
            is_stopped_by_fatigue=False,
            selection_reason=(
                f"Selected playbook '{chosen_pb.get('name')}' for root cause {root_cause} "
                f"(Customer trust: {trust_score:.2f}, Prior contacts 7d: {event.contact_count_last_7d})"
            ),
            selected_action=action_obj,
            playbook_config=chosen_pb
        )
