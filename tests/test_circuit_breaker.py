"""
Test Playbook Circuit Breaker Pattern
Proves that a spike in customer complaints or opt-outs trips the category circuit breaker into OPEN state,
blocking further automated recovery attempts.
"""

from src.execution_agent import ExecutionAgent, CircuitBreaker
from src.ingestion import UnifiedRecoveryEvent
from src.playbook_selector import PlaybookSelectionResult, SelectedActionStep


def test_circuit_breaker_trips_on_complaint_spike():
    agent = ExecutionAgent()
    cb = agent.circuit_breakers["checkout_recovery"]
    
    assert cb.state == "CLOSED"

    # Feed consecutive opt-outs / complaints
    for _ in range(6):
        cb.record_outcome(is_success=False, is_complaint_or_opt_out=True)

    # Breaker should now be OPEN
    assert cb.state == "OPEN"
    assert "Circuit Breaker TRIPPED" in cb.trip_reason

    # Attempt to execute an action in checkout_recovery category
    event = UnifiedRecoveryEvent(
        event_id="evt_cb_test_001",
        event_type="checkout_abandonment",
        customer_id="cust_3333",
        customer_name="Tanvi Choudhury",
        customer_email="tanvi@example.com",
        customer_phone="+919811223366",
        customer_timezone="Asia/Kolkata",
        amount=1200.0,
        currency="INR",
        timestamp="2026-08-23T11:00:00+05:30",
        payment_method="checkout_page",
        error_code="OTP_SUBMISSION_FAILED"
    )

    action = SelectedActionStep(
        step_number=1,
        action_type="friction_assist",
        channel="whatsapp",
        delay_minutes=0,
        description="Friction assist",
        template="Hi {customer_name}",
        requires_customer_interaction=True,
        fatigue_weight=1.0
    )

    selection = PlaybookSelectionResult(
        playbook_id="checkout_recovery",
        playbook_name="Checkout Recovery",
        category="checkout_recovery",
        is_eligible=True,
        is_stopped_by_fatigue=False,
        selection_reason="Friction assist",
        selected_action=action,
        playbook_config={"constraints": {"quiet_hours": {"start_hour": 9, "end_hour": 20}}}
    )

    result = agent.execute(event, selection)
    assert result.status == "BLOCKED_CIRCUIT_BREAKER"
    assert "CIRCUIT_BREAKER_OPEN" in result.execution_reason

    # Reset circuit breaker
    cb.reset()
    assert cb.state == "CLOSED"
    
    # Execution should now succeed
    result_after_reset = agent.execute(event, selection)
    assert result_after_reset.status == "EXECUTED"
