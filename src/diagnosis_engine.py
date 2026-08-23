"""
CloseLoop Diagnosis Engine
Hybrid Rules + Lightweight Feature Classifier for Root-Cause Inference.

Every diagnosis produces:
1. Identified Root Cause (from formal taxonomy)
2. Confidence Score (0.0 to 1.0)
3. Human-readable Explainability Trace ("Why this was inferred")
4. Extracted Behavioral/System Signals
5. Recommended Action Modality (e.g. SILENT_RETRY, INCENTIVE_NUDGE, HUMAN_ESCALATION, VOICE_OUTREACH)
"""

import sys
from pathlib import Path
from dataclasses import dataclass, asdict
from typing import List, Dict, Any

root_dir = Path(__file__).resolve().parent.parent
if str(root_dir) not in sys.path:
    sys.path.insert(0, str(root_dir))

try:
    from src.ingestion import UnifiedRecoveryEvent
except ImportError:
    from ingestion import UnifiedRecoveryEvent


@dataclass
class DiagnosisResult:
    root_cause: str
    confidence: float
    explanation: str
    signals_detected: List[str]
    suggested_action_type: str

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class DiagnosisEngine:
    """Hybrid Rule-heuristic and Feature Diagnoser."""

    def __init__(self):
        pass

    def diagnose(self, event: UnifiedRecoveryEvent) -> DiagnosisResult:
        """Diagnoses the root cause of an ingestion event with full explainability."""
        signals = []
        err_code = (event.error_code or "").upper()
        err_msg = (event.error_message or "").lower()
        meta = event.metadata or {}

        # 1. Bank Downtime Diagnosis (Cluster / Latency / System Status)
        bank_status = str(meta.get("bank_system_status", "")).upper()
        concurrent_failures = meta.get("concurrent_failures_in_cluster", 0)
        
        if (
            bank_status == "DEGRADED"
            or concurrent_failures >= 10
            or (event.gateway_latency_ms >= 4000 and "timeout" in err_msg)
            or err_code in ["GATEWAY_TIMEOUT", "BANK_UNAVAILABLE", "504_GATEWAY_TIMEOUT"]
        ):
            signals.append(f"Gateway latency: {event.gateway_latency_ms}ms")
            if bank_status == "DEGRADED":
                signals.append(f"Bank system status reported DEGRADED for {event.bank or 'Issuer'}")
            if concurrent_failures > 0:
                signals.append(f"Clustered concurrent failure spike ({concurrent_failures} events)")
            
            explanation = (
                f"Classified as BANK_DOWNTIME. Issuer bank {event.bank or 'gateway'} experienced high "
                f"latency ({event.gateway_latency_ms}ms) and cluster failure spike ({concurrent_failures} events). "
                f"Action should be deferred to a silent retry window rather than contacting the customer."
            )
            return DiagnosisResult(
                root_cause="BANK_DOWNTIME",
                confidence=0.96,
                explanation=explanation,
                signals_detected=signals,
                suggested_action_type="SILENT_RETRY"
            )

        # 2. Card Expired
        if (
            err_code in ["CARD_EXPIRED", "EXPIRED_CARD", "INVALID_EXPIRY"]
            or "expired" in err_msg
            or meta.get("card_expiry") is not None
        ):
            signals.append(f"Card error code: {err_code}")
            if meta.get("card_expiry"):
                signals.append(f"Card expiry recorded: {meta.get('card_expiry')}")
            
            explanation = (
                f"Classified as CARD_EXPIRED. Error code '{err_code}' indicated the registered "
                f"payment instrument is past its validity date. Requires customer payment instrument update link."
            )
            return DiagnosisResult(
                root_cause="CARD_EXPIRED",
                confidence=0.98,
                explanation=explanation,
                signals_detected=signals,
                suggested_action_type="CARD_UPDATE_NUDGE"
            )

        # 3. Mandate Expired / Max Validity Exceeded
        if (
            err_code in ["MANDATE_MAX_VALIDITY_EXCEEDED", "MANDATE_EXPIRED", "MANDATE_CANCELLED"]
            or "mandate validity ended" in err_msg
            or meta.get("mandate_expiry_date") is not None
        ):
            signals.append(f"Mandate error code: {err_code}")
            if meta.get("mandate_id"):
                signals.append(f"Mandate ID: {meta.get('mandate_id')}")

            explanation = (
                f"Classified as MANDATE_EXPIRED. Recurring subscription mandate has lapsed its maximum "
                f"permitted validity window. Re-authorization via UPI Autopay / e-NACH link required."
            )
            return DiagnosisResult(
                root_cause="MANDATE_EXPIRED",
                confidence=0.95,
                explanation=explanation,
                signals_detected=signals,
                suggested_action_type="MANDATE_REAUTHORIZE"
            )

        # 4. Mandate Lapse / Technical Debit Rejection
        if (
            err_code in ["PRE_DEBIT_NOTIFICATION_FAILED", "MANDATE_REJECTED", "TECHNICAL_DECLINE"]
            or event.event_type == "subscription_renewal" and "pre-debit" in err_msg
        ):
            signals.append(f"Mandate pre-debit technical rejection: {err_code}")
            explanation = (
                f"Classified as MANDATE_LAPSE. Recurring debit failed pre-debit notification check "
                f"or technical limit. Candidate for automated mandate retry sequencer."
            )
            return DiagnosisResult(
                root_cause="MANDATE_LAPSE",
                confidence=0.90,
                explanation=explanation,
                signals_detected=signals,
                suggested_action_type="MANDATE_RETRY_SEQUENCER"
            )

        # 5. Insufficient Funds (Payment failure or Recurring Subscription)
        if (
            err_code in ["INSUFFICIENT_FUNDS", "LOW_BALANCE", "FUNDS_UNAVAILABLE"]
            or "balance not available" in err_msg
            or "insufficient" in err_msg
        ):
            signals.append(f"Balance check error: {err_code}")
            signals.append(f"Payment method: {event.payment_method}")
            
            explanation = (
                f"Classified as INSUFFICIENT_FUNDS. Debit declined due to temporary non-availability of funds. "
                f"Optimal intervention is polite low-friction WhatsApp / SMS reminder or scheduled retry after payday cycle."
            )
            return DiagnosisResult(
                root_cause="INSUFFICIENT_FUNDS",
                confidence=0.92,
                explanation=explanation,
                signals_detected=signals,
                suggested_action_type="FUNDS_RETRY_NUDGE"
            )

        # 6. B2B Genuine Dispute
        if (
            meta.get("dispute_flag") is True
            or err_code in ["INVOICE_DISPUTED", "DELIVERABLE_DISPUTE"]
            or "discrepancy" in err_msg
        ):
            signals.append("B2B dispute flag ACTIVE")
            if meta.get("dispute_reason"):
                signals.append(f"Dispute details: {meta.get('dispute_reason')}")

            explanation = (
                f"Classified as GENUINE_DISPUTE. Invoice is disputed by client ({meta.get('dispute_reason', 'Milestone query')}). "
                f"All automated collection bots MUST STOP. Route directly to dedicated Account Manager."
            )
            return DiagnosisResult(
                root_cause="GENUINE_DISPUTE",
                confidence=0.99,
                explanation=explanation,
                signals_detected=signals,
                suggested_action_type="PAUSE_AND_ESCALATE_HUMAN"
            )

        # 7. B2B Cash Flow Delay
        if (
            meta.get("extension_requested") is True
            or err_code == "CASH_FLOW_DELAY"
            or "extension" in err_msg
        ):
            signals.append("Customer requested cash-flow payment extension")
            explanation = (
                f"Classified as CASH_FLOW_DELAY. Trusted enterprise client communicated working capital cycle delay. "
                f"Lock promise-to-pay grace window and hold aggressive reminders."
            )
            return DiagnosisResult(
                root_cause="CASH_FLOW_DELAY",
                confidence=0.94,
                explanation=explanation,
                signals_detected=signals,
                suggested_action_type="PROMISE_TO_PAY_AGREEMENT"
            )

        # 8. B2B Routine Forgot Payment
        if event.event_type == "b2b_receivables" or err_code == "OVERDUE_UNNOTICED":
            days_overdue = meta.get("days_overdue", 7)
            signals.append(f"Days overdue: {days_overdue}")
            signals.append(f"Customer Trust Score: {event.historical_trust_score}")
            
            explanation = (
                f"Classified as FORGOT_PAYMENT. Routine overdue invoice ({days_overdue} days). Customer has high trust "
                f"score ({event.historical_trust_score}). Gentle Hinglish/English invoice nudge appropriate."
            )
            return DiagnosisResult(
                root_cause="FORGOT_PAYMENT",
                confidence=0.88,
                explanation=explanation,
                signals_detected=signals,
                suggested_action_type="POLITE_RECEIVABLES_REMINDER"
            )

        # 9. Checkout Abandonment - UX Friction
        if (
            err_code in ["OTP_SUBMISSION_FAILED", "FORM_ERROR", "VALIDATION_FAILED"]
            or meta.get("form_validation_errors", 0) >= 2
            or (meta.get("session_duration_seconds", 0) > 180 and "otp" in err_msg)
        ):
            validation_errors = meta.get("form_validation_errors", 1)
            signals.append(f"Checkout validation errors: {validation_errors}")
            signals.append("Customer was deep in checkout funnel (OTP stage)")
            
            explanation = (
                f"Classified as CHECKOUT_FRICTION. High intent demonstrated but customer faced {validation_errors} "
                f"form/OTP validation errors. Send 1-click checkout recovery link with prepopulated cart."
            )
            return DiagnosisResult(
                root_cause="CHECKOUT_FRICTION",
                confidence=0.91,
                explanation=explanation,
                signals_detected=signals,
                suggested_action_type="FRICTION_ASSIST_NUDGE"
            )

        # 10. Checkout Abandonment - Price Hesitation
        if (
            err_code == "COUPON_REJECTED"
            or meta.get("coupon_attempted") is not None
            or meta.get("dwell_time_seconds", 0) >= 300
        ):
            dwell = meta.get("dwell_time_seconds", 300)
            coupon = meta.get("coupon_attempted", "coupon")
            signals.append(f"Coupon attempted: {coupon}")
            signals.append(f"Cart dwell time: {dwell}s")
            
            explanation = (
                f"Classified as PRICE_HESITATION. Customer spent {dwell}s reviewing cart and attempted '{coupon}'. "
                f"Bounded 5% recovery discount nudge recommended if customer fatigue budget allows."
            )
            return DiagnosisResult(
                root_cause="PRICE_HESITATION",
                confidence=0.87,
                explanation=explanation,
                signals_detected=signals,
                suggested_action_type="DISCOUNT_INCENTIVE_NUDGE"
            )

        # 11. Checkout Abandonment - No Intent / Window Shopping
        if (
            err_code == "WINDOW_SHOPPING"
            or meta.get("dwell_time_seconds", 999) < 15
            or meta.get("shipping_address_filled") is False
        ):
            signals.append("Low session duration (<15s)")
            signals.append("No shipping info entered")
            
            explanation = (
                "Classified as NO_INTENT. Window shopping session with no real buying signals. "
                "CRITICAL STOP RULE: Do NOT spam customer with recovery messages to preserve goodwill."
            )
            return DiagnosisResult(
                root_cause="NO_INTENT",
                confidence=0.85,
                explanation=explanation,
                signals_detected=signals,
                suggested_action_type="NO_ACTION_PRESERVE_GOODWILL"
            )

        # Default fallback
        return DiagnosisResult(
            root_cause="INSUFFICIENT_FUNDS",
            confidence=0.70,
            explanation=f"Default diagnosis based on standard payment failure pattern ({event.error_code or 'UNKNOWN'}).",
            signals_detected=["Standard gateway decline"],
            suggested_action_type="FUNDS_RETRY_NUDGE"
        )
