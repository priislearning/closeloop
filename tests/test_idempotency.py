"""
Test Idempotency & Concurrent Retry Storm Prevention
Proves that firing duplicate failed payment events concurrently executes exactly ONE retry action,
locking subsequent invocations to prevent duplicate customer charges.
"""

import concurrent.futures
from src.ingestion import UnifiedRecoveryEvent
from src.execution_agent import ExecutionAgent
from src.playbook_selector import PlaybookSelectionResult, SelectedActionStep


def test_idempotency_concurrent_execution():
    agent = ExecutionAgent()
    
    event = UnifiedRecoveryEvent(
        event_id="evt_test_concurrent_001",
        event_type="payment_failure",
        customer_id="cust_9999",
        customer_name="Rohan Mehta",
        customer_email="rohan@example.com",
        customer_phone="+919876543210",
        customer_timezone="Asia/Kolkata",
        amount=4500.0,
        currency="INR",
        timestamp="2026-08-23T11:00:00+05:30",
        payment_method="credit_card",
        error_code="GATEWAY_TIMEOUT",
        metadata={"order_id": "ord_99999"}
    )

    action = SelectedActionStep(
        step_number=1,
        action_type="silent_retry",
        channel="backend_scheduler",
        delay_minutes=45,
        description="Silent backend gateway retry",
        template="SILENT_RETRY",
        requires_customer_interaction=False,
        fatigue_weight=0.0
    )

    selection = PlaybookSelectionResult(
        playbook_id="mandate_retry",
        playbook_name="Mandate Retry Sequencer",
        category="mandate_retry",
        is_eligible=True,
        is_stopped_by_fatigue=False,
        selection_reason="Silent retry on bank downtime",
        selected_action=action,
        playbook_config={"constraints": {"quiet_hours": {"start_hour": 9, "end_hour": 19}}}
    )

    # Fire 10 simultaneous threads trying to execute the exact same payment retry
    num_threads = 10
    results = []

    with concurrent.futures.ThreadPoolExecutor(max_workers=num_threads) as executor:
        futures = [executor.submit(agent.execute, event, selection) for _ in range(num_threads)]
        for f in concurrent.futures.as_completed(futures):
            results.append(f.result())

    # Assertions:
    # 1. Exactly ONE action should have status == "EXECUTED"
    executed_actions = [r for r in results if r.status == "EXECUTED"]
    assert len(executed_actions) == 1, f"Expected exactly 1 execution, got {len(executed_actions)}"

    # 2. The remaining 9 actions MUST have status == "BLOCKED_IDEMPOTENCY"
    blocked_duplicates = [r for r in results if r.status == "BLOCKED_IDEMPOTENCY"]
    assert len(blocked_duplicates) == (num_threads - 1), (
        f"Expected {num_threads - 1} blocked duplicate attempts, got {len(blocked_duplicates)}"
    )

    # 3. All actions share the identical deterministic idempotency key
    keys = {r.idempotency_key for r in results}
    assert len(keys) == 1, "Expected identical idempotency key across all concurrent attempts"
    print(f"\n[PASS] Idempotency test passed: 1 EXECUTED, {len(blocked_duplicates)} BLOCKED_DUPLICATES.")
