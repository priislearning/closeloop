"""
CloseLoop Synthetic Data Generator
Generates realistic datasets covering 4 revenue-at-risk event streams:
1. Payment degradation / failure (card expired, insufficient funds, bank downtime, retry storm)
2. Checkout drop-off / abandonment (UX friction, price hesitation, no intent)
3. Subscription / mandate renewal failure (UPI mandate expired, mandate lapse, insufficient funds)
4. Overdue B2B receivables (genuine dispute, forgot, cash-flow delay)

Includes deliberate edge cases:
- Bank downtime clustering vs individual gateway timeouts
- Cross-timezone customers (Asia/Kolkata, America/New_York, Europe/London, Asia/Singapore, etc.)
- Concurrent duplicate events (testing idempotency)
- Highly fatigued customers with existing contact counts
"""

import json
import random
import uuid
from datetime import datetime, timedelta
import pytz

ROOT_CAUSES = [
    "CARD_EXPIRED",
    "INSUFFICIENT_FUNDS",
    "BANK_DOWNTIME",
    "MANDATE_EXPIRED",
    "CHECKOUT_FRICTION",
    "PRICE_HESITATION",
    "NO_INTENT",
    "GENUINE_DISPUTE",
    "FORGOT_PAYMENT",
    "CASH_FLOW_DELAY",
]

TIMEZONES = [
    "Asia/Kolkata",
    "Asia/Kolkata",
    "Asia/Kolkata",  # Weighted higher for India e-commerce / BFSI
    "America/New_York",
    "Europe/London",
    "Asia/Dubai",
    "Asia/Singapore",
    "America/Los_Angeles",
]

BANKS = ["HDFC", "ICICI", "SBI", "AXIS", "KOTAK"]
GATEWAYS = ["razorpay", "payu", "stripe", "cashfree"]


def generate_synthetic_events(count: int = 250, seed: int = 42) -> list:
    random.seed(seed)
    events = []
    base_time = datetime(2026, 8, 23, 10, 0, 0, tzinfo=pytz.UTC)

    customers = [
        {
            "customer_id": f"cust_{i:04d}",
            "name": name,
            "email": f"{name.lower().replace(' ', '.')}@example.com",
            "phone": f"+9198{random.randint(10000000, 99999999)}",
            "timezone": random.choice(TIMEZONES),
            "historical_trust_score": round(random.uniform(0.3, 0.95), 2),
            "contact_count_last_7d": random.choice([0, 0, 1, 1, 2, 3, 5]),
            "opt_out": False,
        }
        for i, name in enumerate([
            "Aarav Sharma", "Pooja Patel", "Rohan Mehta", "Ananya Iyer", "Vikram Singh",
            "Sneha Reddy", "Rahul Verma", "Kavita Nair", "Arjun Gupta", "Neha Deshmukh",
            "Deepak Rao", "Priyanka Joshi", "Aditya Kulkarni", "Meera Sen", "Karan Malhotra",
            "Tanvi Choudhury", "Siddharth Das", "Ishita Roy", "Varun Bhat", "Divya Menon",
            "Rajesh Agarwal", "Swati Saxena", "Nikhil Chopra", "Ritu Sethi", "Gaurav Bansal",
            "Alex Smith", "John Doe", "Emma Watson", "Liam Chen", "Sophia Miller"
        ])
    ]

    for i in range(count):
        cust = random.choice(customers)
        # Stagger timestamps across past 72 hours
        event_time = base_time - timedelta(
            hours=random.randint(0, 72),
            minutes=random.randint(0, 59),
            seconds=random.randint(0, 59)
        )
        event_id = f"evt_{uuid.uuid4().hex[:12]}"
        
        event_category = random.choices(
            ["payment_failure", "checkout_abandonment", "subscription_renewal", "b2b_receivables"],
            weights=[0.35, 0.25, 0.25, 0.15],
            k=1
        )[0]

        if event_category == "payment_failure":
            scenario = random.choices(
                ["bank_downtime", "card_expired", "insufficient_funds", "duplicate_retry_storm"],
                weights=[0.3, 0.3, 0.3, 0.1],
                k=1
            )[0]

            bank = random.choice(BANKS)
            amount = round(random.uniform(299.0, 15000.0), 2)

            if scenario == "bank_downtime":
                raw_event = {
                    "event_id": event_id,
                    "event_type": "payment_failure",
                    "customer_id": cust["customer_id"],
                    "customer_name": cust["name"],
                    "customer_email": cust["email"],
                    "customer_phone": cust["phone"],
                    "customer_timezone": cust["timezone"],
                    "amount": amount,
                    "currency": "INR",
                    "timestamp": event_time.isoformat(),
                    "payment_method": "netbanking",
                    "bank": bank,
                    "gateway": "razorpay",
                    "error_code": "GATEWAY_TIMEOUT",
                    "error_message": f"Bank server {bank} unresponsive (504)",
                    "gateway_latency_ms": random.randint(4500, 9500),
                    "retry_count": 0,
                    "historical_trust_score": cust["historical_trust_score"],
                    "contact_count_last_7d": cust["contact_count_last_7d"],
                    "metadata": {
                        "bank_system_status": "DEGRADED",
                        "concurrent_failures_in_cluster": random.randint(15, 80),
                        "card_expiry": None,
                        "user_agent": "Mozilla/5.0 Android",
                    }
                }
            elif scenario == "card_expired":
                raw_event = {
                    "event_id": event_id,
                    "event_type": "payment_failure",
                    "customer_id": cust["customer_id"],
                    "customer_name": cust["name"],
                    "customer_email": cust["email"],
                    "customer_phone": cust["phone"],
                    "customer_timezone": cust["timezone"],
                    "amount": amount,
                    "currency": "INR",
                    "timestamp": event_time.isoformat(),
                    "payment_method": "credit_card",
                    "bank": bank,
                    "gateway": "razorpay",
                    "error_code": "CARD_EXPIRED",
                    "error_message": "Card expiration date passed",
                    "gateway_latency_ms": random.randint(200, 600),
                    "retry_count": 0,
                    "historical_trust_score": cust["historical_trust_score"],
                    "contact_count_last_7d": cust["contact_count_last_7d"],
                    "metadata": {
                        "card_expiry": "06/26",
                        "card_network": random.choice(["VISA", "MASTERCARD", "RUPAY"]),
                        "bank_system_status": "HEALTHY",
                    }
                }
            elif scenario == "insufficient_funds":
                raw_event = {
                    "event_id": event_id,
                    "event_type": "payment_failure",
                    "customer_id": cust["customer_id"],
                    "customer_name": cust["name"],
                    "customer_email": cust["email"],
                    "customer_phone": cust["phone"],
                    "customer_timezone": cust["timezone"],
                    "amount": amount,
                    "currency": "INR",
                    "timestamp": event_time.isoformat(),
                    "payment_method": "upi",
                    "bank": bank,
                    "gateway": "razorpay",
                    "error_code": "INSUFFICIENT_FUNDS",
                    "error_message": "Debit failed: Balance not available in account",
                    "gateway_latency_ms": random.randint(350, 900),
                    "retry_count": random.choice([0, 1]),
                    "historical_trust_score": cust["historical_trust_score"],
                    "contact_count_last_7d": cust["contact_count_last_7d"],
                    "metadata": {
                        "upi_app": random.choice(["GPay", "PhonePe", "Paytm", "Cred"]),
                        "bank_system_status": "HEALTHY",
                    }
                }
            else:  # duplicate retry storm injection
                raw_event = {
                    "event_id": event_id,
                    "event_type": "payment_failure",
                    "customer_id": cust["customer_id"],
                    "customer_name": cust["name"],
                    "customer_email": cust["email"],
                    "customer_phone": cust["phone"],
                    "customer_timezone": cust["timezone"],
                    "amount": amount,
                    "currency": "INR",
                    "timestamp": event_time.isoformat(),
                    "payment_method": "credit_card",
                    "bank": bank,
                    "gateway": "razorpay",
                    "error_code": "PAYMENT_PENDING_RETRY",
                    "error_message": "Temporary gateway network glitch",
                    "gateway_latency_ms": 1200,
                    "retry_count": 0,
                    "historical_trust_score": cust["historical_trust_score"],
                    "contact_count_last_7d": cust["contact_count_last_7d"],
                    "is_duplicate_storm_sample": True,
                    "metadata": {
                        "order_id": f"ord_{random.randint(100000, 999999)}",
                        "bank_system_status": "HEALTHY",
                    }
                }

        elif event_category == "checkout_abandonment":
            scenario = random.choices(
                ["ux_friction", "price_hesitation", "no_intent"],
                weights=[0.4, 0.4, 0.2],
                k=1
            )[0]
            cart_value = round(random.uniform(500.0, 25000.0), 2)

            if scenario == "ux_friction":
                raw_event = {
                    "event_id": event_id,
                    "event_type": "checkout_abandonment",
                    "customer_id": cust["customer_id"],
                    "customer_name": cust["name"],
                    "customer_email": cust["email"],
                    "customer_phone": cust["phone"],
                    "customer_timezone": cust["timezone"],
                    "amount": cart_value,
                    "currency": "INR",
                    "timestamp": event_time.isoformat(),
                    "payment_method": "checkout_page",
                    "bank": None,
                    "gateway": None,
                    "error_code": "OTP_SUBMISSION_FAILED",
                    "error_message": "Customer faced 3 consecutive OTP validation errors",
                    "gateway_latency_ms": 0,
                    "retry_count": 0,
                    "historical_trust_score": cust["historical_trust_score"],
                    "contact_count_last_7d": cust["contact_count_last_7d"],
                    "metadata": {
                        "checkout_step": "payment_otp_screen",
                        "form_validation_errors": 3,
                        "session_duration_seconds": 240,
                        "cart_items_count": random.randint(1, 5),
                    }
                }
            elif scenario == "price_hesitation":
                raw_event = {
                    "event_id": event_id,
                    "event_type": "checkout_abandonment",
                    "customer_id": cust["customer_id"],
                    "customer_name": cust["name"],
                    "customer_email": cust["email"],
                    "customer_phone": cust["phone"],
                    "customer_timezone": cust["timezone"],
                    "amount": cart_value,
                    "currency": "INR",
                    "timestamp": event_time.isoformat(),
                    "payment_method": "checkout_page",
                    "bank": None,
                    "gateway": None,
                    "error_code": "COUPON_REJECTED",
                    "error_message": "Attempted expired promo code 'SAVE30', abandoned at cart review",
                    "gateway_latency_ms": 0,
                    "retry_count": 0,
                    "historical_trust_score": cust["historical_trust_score"],
                    "contact_count_last_7d": cust["contact_count_last_7d"],
                    "metadata": {
                        "checkout_step": "coupon_apply",
                        "coupon_attempted": "SAVE30",
                        "dwell_time_seconds": 380,
                        "cart_items_count": random.randint(2, 6),
                    }
                }
            else:
                raw_event = {
                    "event_id": event_id,
                    "event_type": "checkout_abandonment",
                    "customer_id": cust["customer_id"],
                    "customer_name": cust["name"],
                    "customer_email": cust["email"],
                    "customer_phone": cust["phone"],
                    "customer_timezone": cust["timezone"],
                    "amount": cart_value,
                    "currency": "INR",
                    "timestamp": event_time.isoformat(),
                    "payment_method": "checkout_page",
                    "bank": None,
                    "gateway": None,
                    "error_code": "WINDOW_SHOPPING",
                    "error_message": "Abandoned in under 10s without filling shipping details",
                    "gateway_latency_ms": 0,
                    "retry_count": 0,
                    "historical_trust_score": cust["historical_trust_score"],
                    "contact_count_last_7d": cust["contact_count_last_7d"],
                    "metadata": {
                        "checkout_step": "initial_cart_view",
                        "dwell_time_seconds": 9,
                        "shipping_address_filled": False,
                    }
                }

        elif event_category == "subscription_renewal":
            scenario = random.choices(
                ["mandate_expired", "mandate_lapse", "insufficient_funds_mandate"],
                weights=[0.35, 0.35, 0.3],
                k=1
            )[0]
            plan_amount = round(random.choice([499.0, 999.0, 1999.0, 4999.0, 9999.0]), 2)

            if scenario == "mandate_expired":
                raw_event = {
                    "event_id": event_id,
                    "event_type": "subscription_renewal",
                    "customer_id": cust["customer_id"],
                    "customer_name": cust["name"],
                    "customer_email": cust["email"],
                    "customer_phone": cust["phone"],
                    "customer_timezone": cust["timezone"],
                    "amount": plan_amount,
                    "currency": "INR",
                    "timestamp": event_time.isoformat(),
                    "payment_method": "upi_autopay",
                    "bank": random.choice(BANKS),
                    "gateway": "razorpay_subscriptions",
                    "error_code": "MANDATE_MAX_VALIDITY_EXCEEDED",
                    "error_message": "UPI Autopay mandate validity ended on 2026-08-01",
                    "gateway_latency_ms": 400,
                    "retry_count": 0,
                    "historical_trust_score": cust["historical_trust_score"],
                    "contact_count_last_7d": cust["contact_count_last_7d"],
                    "metadata": {
                        "mandate_id": f"man_{uuid.uuid4().hex[:8]}",
                        "plan_name": "Pro Annual SaaS",
                        "renewal_cycle": "monthly",
                        "mandate_expiry_date": "2026-08-01",
                    }
                }
            elif scenario == "mandate_lapse":
                raw_event = {
                    "event_id": event_id,
                    "event_type": "subscription_renewal",
                    "customer_id": cust["customer_id"],
                    "customer_name": cust["name"],
                    "customer_email": cust["email"],
                    "customer_phone": cust["phone"],
                    "customer_timezone": cust["timezone"],
                    "amount": plan_amount,
                    "currency": "INR",
                    "timestamp": event_time.isoformat(),
                    "payment_method": "e_nach",
                    "bank": random.choice(BANKS),
                    "gateway": "razorpay_subscriptions",
                    "error_code": "PRE_DEBIT_NOTIFICATION_FAILED",
                    "error_message": "Customer bank rejected pre-debit 24h SMS notice",
                    "gateway_latency_ms": 700,
                    "retry_count": 1,
                    "historical_trust_score": cust["historical_trust_score"],
                    "contact_count_last_7d": cust["contact_count_last_7d"],
                    "metadata": {
                        "mandate_id": f"man_{uuid.uuid4().hex[:8]}",
                        "plan_name": "Enterprise Growth",
                        "renewal_cycle": "annual",
                    }
                }
            else:
                raw_event = {
                    "event_id": event_id,
                    "event_type": "subscription_renewal",
                    "customer_id": cust["customer_id"],
                    "customer_name": cust["name"],
                    "customer_email": cust["email"],
                    "customer_phone": cust["phone"],
                    "customer_timezone": cust["timezone"],
                    "amount": plan_amount,
                    "currency": "INR",
                    "timestamp": event_time.isoformat(),
                    "payment_method": "upi_autopay",
                    "bank": random.choice(BANKS),
                    "gateway": "razorpay_subscriptions",
                    "error_code": "INSUFFICIENT_FUNDS",
                    "error_message": "Recurring auto-debit bounced due to balance",
                    "gateway_latency_ms": 500,
                    "retry_count": 1,
                    "historical_trust_score": cust["historical_trust_score"],
                    "contact_count_last_7d": cust["contact_count_last_7d"],
                    "metadata": {
                        "mandate_id": f"man_{uuid.uuid4().hex[:8]}",
                        "plan_name": "Premium Tier",
                        "renewal_cycle": "monthly",
                    }
                }

        else:  # b2b_receivables
            scenario = random.choices(
                ["genuine_dispute", "forgot_payment", "cash_flow_delay"],
                weights=[0.3, 0.4, 0.3],
                k=1
            )[0]
            invoice_amount = round(random.uniform(15000.0, 250000.0), 2)
            days_overdue = random.randint(3, 45)

            if scenario == "genuine_dispute":
                raw_event = {
                    "event_id": event_id,
                    "event_type": "b2b_receivables",
                    "customer_id": cust["customer_id"],
                    "customer_name": cust["name"],
                    "customer_email": cust["email"],
                    "customer_phone": cust["phone"],
                    "customer_timezone": cust["timezone"],
                    "amount": invoice_amount,
                    "currency": "INR",
                    "timestamp": event_time.isoformat(),
                    "payment_method": "neft_rtgs_invoice",
                    "bank": "HDFC",
                    "gateway": "invoicing",
                    "error_code": "INVOICE_DISPUTED",
                    "error_message": "Customer flagged discrepancy in milestone deliverables",
                    "gateway_latency_ms": 0,
                    "retry_count": 0,
                    "historical_trust_score": cust["historical_trust_score"],
                    "contact_count_last_7d": cust["contact_count_last_7d"],
                    "metadata": {
                        "invoice_number": f"INV-2026-{random.randint(1000, 9999)}",
                        "days_overdue": days_overdue,
                        "dispute_flag": True,
                        "dispute_reason": "Milestone #3 deliverable pending signoff",
                        "account_manager": "Priyanshi J.",
                    }
                }
            elif scenario == "forgot_payment":
                raw_event = {
                    "event_id": event_id,
                    "event_type": "b2b_receivables",
                    "customer_id": cust["customer_id"],
                    "customer_name": cust["name"],
                    "customer_email": cust["email"],
                    "customer_phone": cust["phone"],
                    "customer_timezone": cust["timezone"],
                    "amount": invoice_amount,
                    "currency": "INR",
                    "timestamp": event_time.isoformat(),
                    "payment_method": "neft_rtgs_invoice",
                    "bank": "ICICI",
                    "gateway": "invoicing",
                    "error_code": "OVERDUE_UNNOTICED",
                    "error_message": "Routine payment overdue by 7 days",
                    "gateway_latency_ms": 0,
                    "retry_count": 1,
                    "historical_trust_score": max(0.75, cust["historical_trust_score"]),
                    "contact_count_last_7d": cust["contact_count_last_7d"],
                    "metadata": {
                        "invoice_number": f"INV-2026-{random.randint(1000, 9999)}",
                        "days_overdue": days_overdue,
                        "dispute_flag": False,
                        "account_manager": "Priyanshi J.",
                    }
                }
            else:
                raw_event = {
                    "event_id": event_id,
                    "event_type": "b2b_receivables",
                    "customer_id": cust["customer_id"],
                    "customer_name": cust["name"],
                    "customer_email": cust["email"],
                    "customer_phone": cust["phone"],
                    "customer_timezone": cust["timezone"],
                    "amount": invoice_amount,
                    "currency": "INR",
                    "timestamp": event_time.isoformat(),
                    "payment_method": "neft_rtgs_invoice",
                    "bank": "SBI",
                    "gateway": "invoicing",
                    "error_code": "CASH_FLOW_DELAY",
                    "error_message": "Client requested 10-day payment extension due to vendor receivables cycle",
                    "gateway_latency_ms": 0,
                    "retry_count": 1,
                    "historical_trust_score": cust["historical_trust_score"],
                    "contact_count_last_7d": cust["contact_count_last_7d"],
                    "metadata": {
                        "invoice_number": f"INV-2026-{random.randint(1000, 9999)}",
                        "days_overdue": days_overdue,
                        "extension_requested": True,
                        "dispute_flag": False,
                    }
                }

        events.append(raw_event)

    return events


def save_synthetic_dataset(output_file: str = "data/synthetic_events.json", count: int = 250):
    events = generate_synthetic_events(count=count)
    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(events, f, indent=2)
    print(f"[CloseLoop] Successfully generated {len(events)} synthetic recovery events into '{output_file}'")
    return events


if __name__ == "__main__":
    import os
    os.makedirs("data", exist_ok=True)
    save_synthetic_dataset("data/synthetic_events.json", count=250)
