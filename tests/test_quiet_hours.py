"""
Test Quiet-Hours Timezone Compliance
Proves that actions scheduled during a customer's local night hours are blocked / deferred,
preventing RBI recovery-conduct violations regardless of server time.
"""

from src.ingestion import UnifiedRecoveryEvent
from src.execution_agent import ExecutionAgent
from src.playbook_selector import PlaybookSelectionResult, SelectedActionStep


def test_quiet_hours_blocks_customer_night_contact():
    agent = ExecutionAgent()

    # UTC timestamp: 2026-08-23 21:30:00 UTC (9:30 PM UTC)
    # In Asia/Kolkata (+5:30), this is 03:00 AM (3 AM next morning -> Severe night violation!)
    event_night = UnifiedRecoveryEvent(
        event_id="evt_night_test_001",
        event_type="b2b_receivables",
        customer_id="cust_8888",
        customer_name="Pooja Patel",
        customer_email="pooja@example.com",
        customer_phone="+919811223344",
        customer_timezone="Asia/Kolkata",
        amount=25000.0,
        currency="INR",
        timestamp="2026-08-23T21:30:00Z",
        payment_method="neft_rtgs_invoice",
        error_code="OVERDUE_UNNOTICED"
    )

    action = SelectedActionStep(
        step_number=1,
        action_type="voice_call",
        channel="hinglish_voice_bot",
        delay_minutes=0,
        description="Conversational Voice Call",
        template="Namaste {customer_name}",
        requires_customer_interaction=True,
        fatigue_weight=3.5
    )

    selection = PlaybookSelectionResult(
        playbook_id="hinglish_voice_recovery",
        playbook_name="Hinglish Voice Recovery",
        category="hinglish_voice_recovery",
        is_eligible=True,
        is_stopped_by_fatigue=False,
        selection_reason="Invoice reminder",
        selected_action=action,
        playbook_config={"constraints": {"quiet_hours": {"start_hour": 9, "end_hour": 19}}}
    )

    result = agent.execute(event_night, selection)

    # Must be blocked by quiet hours
    assert result.status == "BLOCKED_QUIET_HOURS"
    assert "RBI Quiet-Hours Violation Prevented" in result.execution_reason
    assert result.scheduled_for_local_time == "Next business day 09:30 AM"
    assert result.fatigue_score_incurred == 0.0


def test_quiet_hours_allows_customer_daytime_contact():
    agent = ExecutionAgent()

    # UTC timestamp: 2026-08-23 07:00:00 UTC
    # In Asia/Kolkata (+5:30), this is 12:30 PM (Compliant daytime window)
    event_day = UnifiedRecoveryEvent(
        event_id="evt_day_test_002",
        event_type="b2b_receivables",
        customer_id="cust_7777",
        customer_name="Aarav Sharma",
        customer_email="aarav@example.com",
        customer_phone="+919811223355",
        customer_timezone="Asia/Kolkata",
        amount=15000.0,
        currency="INR",
        timestamp="2026-08-23T07:00:00Z",
        payment_method="neft_rtgs_invoice",
        error_code="OVERDUE_UNNOTICED"
    )

    action = SelectedActionStep(
        step_number=1,
        action_type="whatsapp_nudge",
        channel="whatsapp",
        delay_minutes=0,
        description="WhatsApp invoice link",
        template="Hi {customer_name}, invoice {amount}",
        requires_customer_interaction=True,
        fatigue_weight=1.0
    )

    selection = PlaybookSelectionResult(
        playbook_id="receivables_chaser",
        playbook_name="Receivables Chaser",
        category="b2b_receivables",
        is_eligible=True,
        is_stopped_by_fatigue=False,
        selection_reason="Invoice reminder",
        selected_action=action,
        playbook_config={"constraints": {"quiet_hours": {"start_hour": 9, "end_hour": 19}}}
    )

    result = agent.execute(event_day, selection)
    assert result.status == "EXECUTED"
    assert result.fatigue_score_incurred == 1.0
