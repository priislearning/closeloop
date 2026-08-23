"""
Test Promise-to-Pay Tracker & Trust Feedback Loop
Proves grace-period hold stops active escalation and fulfillment updates customer trust score.
"""

from datetime import datetime, timedelta
import pytz
from src.promise_tracker import PromiseTracker


def test_promise_grace_period_and_trust_feedback():
    tracker = PromiseTracker()
    customer_id = "cust_5555"
    
    # Set initial baseline trust
    tracker.set_trust_score(customer_id, 0.70)
    assert tracker.get_trust_score(customer_id) == 0.70

    now = datetime.now(pytz.UTC)
    future_promise = (now + timedelta(days=5)).isoformat()

    # Record a promise
    p = tracker.record_promise(
        customer_id=customer_id,
        event_id="evt_p2p_001",
        amount=50000.0,
        promised_date_iso=future_promise,
        grace_period_hours=24
    )

    # Active grace period must be True
    assert tracker.has_active_grace_period(customer_id, current_time=now) is True

    # Check beyond grace period
    future_after_grace = now + timedelta(days=7)
    assert tracker.has_active_grace_period(customer_id, current_time=future_after_grace) is False

    # Fulfill promise (payment received)
    p_res, updated_trust = tracker.resolve_promise(p.promise_id, payment_received=True)
    assert p_res.status == "KEPT"
    assert updated_trust == 0.82  # 0.70 + 0.12

    # Break subsequent promise
    p2 = tracker.record_promise(
        customer_id=customer_id,
        event_id="evt_p2p_002",
        amount=20000.0,
        promised_date_iso=future_promise
    )
    p_res2, penalty_trust = tracker.resolve_promise(p2.promise_id, payment_received=False)
    assert p_res2.status == "BROKEN"
    assert penalty_trust == 0.57  # 0.82 - 0.25
