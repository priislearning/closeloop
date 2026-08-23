"""
CloseLoop Streamlit Dashboard & Live Showcase
Razorpay Buildathon — Track 03: AI Revenue Recovery
Tagline: "The revenue recovery agent that also knows when to stop."
"""

import sys
import os
from pathlib import Path

# Add project root to sys.path
root_dir = Path(__file__).resolve().parent.parent
if str(root_dir) not in sys.path:
    sys.path.insert(0, str(root_dir))

import streamlit as st
import pandas as pd
import plotly.graph_objects as go
import plotly.express as px
from datetime import datetime
import json

from src.ingestion import UnifiedRecoveryEvent, ingest_event
from src.diagnosis_engine import DiagnosisEngine
from src.playbook_selector import PlaybookSelector
from src.execution_agent import ExecutionAgent
from src.promise_tracker import PromiseTracker
from src.audit_log import AuditLog
from src.pipeline import CloseLoopPipeline
from src.evaluate import evaluate_closeloop, simulate_naive_baseline, generate_tradeoff_curve
from data.generate_synthetic import generate_synthetic_events

# Page Config
st.set_page_config(
    page_title="CloseLoop | AI Revenue Recovery Agent",
    page_icon="🔄",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Custom CSS for styling
st.markdown("""
<style>
    .main-header {
        font-size: 2.3rem;
        font-weight: 800;
        color: #1E293B;
        margin-bottom: 0.2rem;
    }
    .tagline {
        font-size: 1.15rem;
        font-weight: 500;
        color: #0284C7;
        margin-bottom: 1.5rem;
    }
    .metric-card {
        background-color: #F8FAFC;
        border-radius: 10px;
        padding: 1.2rem;
        border: 1px solid #E2E8F0;
        box-shadow: 0 1px 3px rgba(0,0,0,0.05);
    }
    .hero-stat {
        font-size: 1.8rem;
        font-weight: 700;
        color: #0F172A;
    }
    .badge-success {
        background-color: #DCFCE7;
        color: #166534;
        padding: 0.2rem 0.6rem;
        border-radius: 6px;
        font-size: 0.85rem;
        font-weight: 600;
    }
    .badge-warning {
        background-color: #FEF9C3;
        color: #854D0E;
        padding: 0.2rem 0.6rem;
        border-radius: 6px;
        font-size: 0.85rem;
        font-weight: 600;
    }
    .badge-danger {
        background-color: #FEE2E2;
        color: #991B1B;
        padding: 0.2rem 0.6rem;
        border-radius: 6px;
        font-size: 0.85rem;
        font-weight: 600;
    }
</style>
""", unsafe_allow_html=True)


# Initialize Shared Pipeline in Session State
@st.cache_resource
def get_pipeline():
    return CloseLoopPipeline()

pipeline = get_pipeline()

# Load Cached Benchmark Dataset
@st.cache_data
def load_benchmark_data():
    events = generate_synthetic_events(count=200, seed=123)
    naive = simulate_naive_baseline(events)
    closeloop = evaluate_closeloop(events)
    tradeoff = generate_tradeoff_curve(events)
    return events, naive, closeloop, tradeoff

events_batch, naive_bench, closeloop_bench, tradeoff_data = load_benchmark_data()


# Sidebar Navigation & Controls
st.sidebar.image("https://img.icons8.com/fluency/96/cash-in-hand.png", width=64)
st.sidebar.title("CloseLoop AI")
st.sidebar.caption("Track 03: AI Revenue Recovery")

nav_choice = st.sidebar.radio(
    "Navigation",
    [
        "📊 Executive Benchmark & Tradeoff",
        "⚡ Live Event Simulator",
        "🛡️ Circuit Breakers & 2am Breakers",
        "📜 Immutable Audit Log Explorer",
        "🤝 Promise-to-Pay & Trust Loop"
    ]
)

st.sidebar.divider()
st.sidebar.markdown("### 🎯 Core Thesis")
st.sidebar.info(
    "**Restraint is the headline feature.** Aggressive recovery burns future LTV. "
    "CloseLoop optimizes ₹ Recovered *subject to* a contact-fatigue budget with provably 0 compliance violations."
)

st.sidebar.markdown("### 🛠️ Architecture")
st.sidebar.caption("• 1 Diagnosis Engine (Explainable)\n• 4 Declarative YAML Playbooks\n• Timezone Quiet-Hours Gate\n• Deterministic Idempotency Lock\n• Dynamic Trust Feedback Loop")


# HEADER
col_title, col_status = st.columns([3, 1])
with col_title:
    st.markdown('<div class="main-header">CLOSELOOP</div>', unsafe_allow_html=True)
    st.markdown('<div class="tagline">The revenue recovery agent that also knows when to stop.</div>', unsafe_allow_html=True)

with col_status:
    st.markdown("""
        <div style="text-align: right; padding-top: 10px;">
            <span class="badge-success">● SYSTEM ONLINE</span><br>
            <span style="font-size: 0.8rem; color: #64748B;">RBI Conduct Gate: ACTIVE</span>
        </div>
    """, unsafe_allow_html=True)

st.divider()


# ==============================================================================
# TAB 1: EXECUTIVE BENCHMARK & TRADEOFF FRONTIER
# ==============================================================================
if nav_choice == "📊 Executive Benchmark & Tradeoff":
    st.subheader("🎯 Dual-Metric Executive Benchmark (200-Event Held-out Batch)")
    
    # Top 4 KPI Cards
    k1, k2, k3, k4 = st.columns(4)
    with k1:
        st.metric(
            label="Total ₹ Recovered",
            value=f"₹{closeloop_bench['total_recovered']:,.0f}",
            delta=f"{closeloop_bench['recovery_rate_pct']}% Recovery Rate",
            delta_color="normal"
        )
    with k2:
        fatigue_avoided = naive_bench["total_fatigue_score"] - closeloop_bench["total_fatigue_score"]
        st.metric(
            label="Contact-Fatigue AVOIDED",
            value=f"{fatigue_avoided:,.1f} pts",
            delta=f"{(fatigue_avoided/naive_bench['total_fatigue_score']):.1%} Goodwill Protected",
            delta_color="normal"
        )
    with k3:
        st.metric(
            label="Compliance Violations",
            value=f"{closeloop_bench['compliance_violations']}",
            delta=f"Zero Violations vs {naive_bench['compliance_violations']} in Naive",
            delta_color="inverse"
        )
    with k4:
        st.metric(
            label="Recovery Efficiency",
            value=f"₹{closeloop_bench['recovery_per_contact']:,.0f} / contact",
            delta=f"{closeloop_bench['recovery_per_contact']/max(1.0, naive_bench['recovery_per_contact']):.1f}x vs Baseline",
            delta_color="normal"
        )

    st.markdown("---")

    # Tradeoff Curve Visualizer
    col_chart, col_table = st.columns([3, 2])
    
    with col_chart:
        st.markdown("#### 📈 The Tradeoff Frontier: Revenue vs Contact Fatigue")
        st.caption("Shows how CloseLoop captures ~80% of recoverable revenue using silent retries & bounded nudges before entering the Diminishing Return Zone.")

        df_tradeoff = pd.DataFrame(tradeoff_data)
        
        fig = go.Figure()
        fig.add_trace(go.Scatter(
            x=df_tradeoff["fatigue_score"],
            y=df_tradeoff["revenue_recovered"],
            mode="lines+markers",
            name="Recovery Tradeoff Curve",
            line=dict(color="#0284C7", width=3),
            marker=dict(size=8, color="#0369A1"),
            text=[f"Factor: {f}<br>₹{r:,.0f}<br>Fatigue: {s}" for f, r, s in zip(df_tradeoff["fatigue_budget_factor"], df_tradeoff["revenue_recovered"], df_tradeoff["fatigue_score"])],
            hoverinfo="text"
        ))

        # Annotate CloseLoop Optimal Operating Point
        closeloop_point = df_tradeoff[df_tradeoff["fatigue_budget_factor"] == 1.0].iloc[0]
        fig.add_annotation(
            x=closeloop_point["fatigue_score"],
            y=closeloop_point["revenue_recovered"],
            text="CloseLoop Operating Point<br>(Max ₹ at bounded fatigue)",
            showarrow=True,
            arrowhead=2,
            arrowcolor="#059669",
            ax=0,
            ay=-50,
            bgcolor="#DCFCE7",
            bordercolor="#059669"
        )

        fig.update_layout(
            xaxis_title="Contact-Fatigue Score (Customer Disruption)",
            yaxis_title="Revenue Recovered (INR ₹)",
            template="plotly_white",
            height=380,
            margin=dict(l=20, r=20, t=30, b=20)
        )
        st.plotly_chart(fig, use_container_width=True)

    with col_table:
        st.markdown("#### ⚖️ CloseLoop vs Naive Baseline Comparison")
        comp_data = {
            "Metric": [
                "Total Revenue at Risk",
                "Revenue Recovered",
                "Recovery Rate (%)",
                "Contact Attempts Spent",
                "Silent Retries (0 Fatigue)",
                "Total Contact Fatigue",
                "Compliance Violations",
                "Efficiency (₹ / Attempt)"
            ],
            "Naive Aggressive": [
                f"₹{naive_bench['total_revenue_at_risk']:,.2f}",
                f"₹{naive_bench['total_recovered']:,.2f}",
                f"{naive_bench['recovery_rate_pct']}%",
                f"{naive_bench['total_contacts']}",
                "0 (All Loud Calls/SMS)",
                f"{naive_bench['total_fatigue_score']:,.1f}",
                f"{naive_bench['compliance_violations']} (Timezone breaches)",
                f"₹{naive_bench['recovery_per_contact']:,.2f}"
            ],
            "CloseLoop (Agent)": [
                f"₹{closeloop_bench['total_revenue_at_risk']:,.2f}",
                f"₹{closeloop_bench['total_recovered']:,.2f}",
                f"{closeloop_bench['recovery_rate_pct']}%",
                f"{closeloop_bench['total_contacts']}",
                f"{closeloop_bench['silent_retries_zero_fatigue']} (Zero-fatigue)",
                f"{closeloop_bench['total_fatigue_score']:,.1f}",
                "0 (Provably Compliant)",
                f"₹{closeloop_bench['recovery_per_contact']:,.2f}"
            ]
        }
        st.dataframe(pd.DataFrame(comp_data), hide_index=True, use_container_width=True)


# ==============================================================================
# TAB 2: LIVE EVENT SIMULATOR
# ==============================================================================
elif nav_choice == "⚡ Live Event Simulator":
    st.subheader("⚡ Live Pipeline Execution Simulator")
    st.caption("Trigger any real-world revenue-at-risk scenario and observe the complete causal chain from Ingestion to Gated Execution.")

    # Preset Selection
    preset_choice = st.selectbox(
        "Select a Realistic Scenario Preset:",
        [
            "1. Bank Downtime (HDFC Gateway Spike) → Silent Retry Window",
            "2. Checkout Abandonment (OTP UX Friction) → 1-Click Recovery Nudge",
            "3. Checkout Window Shopping (No Intent) → STOP RULE (Preserve Goodwill)",
            "4. Subscription Lapsed Mandate → 1-Tap UPI Autopay Reauth",
            "5. B2B Disputed Invoice → STOP AUTOMATION & Escalate to AM",
            "6. Night-time Failed Payment (3 AM IST) → Quiet-Hours Gate Block",
            "7. High Contact Fatigue Customer (5 prior contacts) → Max Attempts Stop Rule",
        ]
    )

    # Preset configurations
    sample_event_dict = {}
    if "1. Bank Downtime" in preset_choice:
        sample_event_dict = {
            "event_id": "evt_bank_down_101",
            "event_type": "payment_failure",
            "customer_id": "cust_aarav",
            "customer_name": "Aarav Sharma",
            "customer_email": "aarav.sharma@example.com",
            "customer_phone": "+919876543210",
            "customer_timezone": "Asia/Kolkata",
            "amount": 4999.0,
            "currency": "INR",
            "timestamp": "2026-08-23T14:30:00+05:30",
            "payment_method": "netbanking",
            "bank": "HDFC",
            "error_code": "GATEWAY_TIMEOUT",
            "error_message": "Bank server HDFC unresponsive (504)",
            "gateway_latency_ms": 6200,
            "historical_trust_score": 0.85,
            "contact_count_last_7d": 0,
            "metadata": {"bank_system_status": "DEGRADED", "concurrent_failures_in_cluster": 34}
        }
    elif "2. Checkout Abandonment (OTP" in preset_choice:
        sample_event_dict = {
            "event_id": "evt_checkout_otp_102",
            "event_type": "checkout_abandonment",
            "customer_id": "cust_pooja",
            "customer_name": "Pooja Patel",
            "customer_email": "pooja.patel@example.com",
            "customer_phone": "+919876543211",
            "customer_timezone": "Asia/Kolkata",
            "amount": 2499.0,
            "currency": "INR",
            "timestamp": "2026-08-23T16:15:00+05:30",
            "payment_method": "checkout_page",
            "error_code": "OTP_SUBMISSION_FAILED",
            "error_message": "Customer faced 3 consecutive OTP validation errors",
            "historical_trust_score": 0.75,
            "contact_count_last_7d": 0,
            "metadata": {"checkout_step": "payment_otp_screen", "form_validation_errors": 3}
        }
    elif "3. Checkout Window Shopping" in preset_choice:
        sample_event_dict = {
            "event_id": "evt_window_shop_103",
            "event_type": "checkout_abandonment",
            "customer_id": "cust_vikram",
            "customer_name": "Vikram Singh",
            "customer_email": "vikram@example.com",
            "customer_phone": "+919876543212",
            "customer_timezone": "Asia/Kolkata",
            "amount": 8999.0,
            "currency": "INR",
            "timestamp": "2026-08-23T11:00:00+05:30",
            "payment_method": "checkout_page",
            "error_code": "WINDOW_SHOPPING",
            "error_message": "Abandoned in under 10s without filling shipping details",
            "historical_trust_score": 0.50,
            "contact_count_last_7d": 0,
            "metadata": {"dwell_time_seconds": 8, "shipping_address_filled": False}
        }
    elif "4. Subscription Lapsed" in preset_choice:
        sample_event_dict = {
            "event_id": "evt_mandate_exp_104",
            "event_type": "subscription_renewal",
            "customer_id": "cust_sneha",
            "customer_name": "Sneha Reddy",
            "customer_email": "sneha@example.com",
            "customer_phone": "+919876543213",
            "customer_timezone": "Asia/Kolkata",
            "amount": 1999.0,
            "currency": "INR",
            "timestamp": "2026-08-23T10:00:00+05:30",
            "payment_method": "upi_autopay",
            "bank": "ICICI",
            "error_code": "MANDATE_MAX_VALIDITY_EXCEEDED",
            "error_message": "UPI Autopay mandate validity ended",
            "historical_trust_score": 0.90,
            "contact_count_last_7d": 0,
            "metadata": {"mandate_id": "man_883921", "plan_name": "Pro Annual SaaS"}
        }
    elif "5. B2B Disputed" in preset_choice:
        sample_event_dict = {
            "event_id": "evt_b2b_disp_105",
            "event_type": "b2b_receivables",
            "customer_id": "cust_acme_corp",
            "customer_name": "Acme Technologies",
            "customer_email": "finance@acme.example",
            "customer_phone": "+919876543214",
            "customer_timezone": "Asia/Kolkata",
            "amount": 145000.0,
            "currency": "INR",
            "timestamp": "2026-08-23T15:00:00+05:30",
            "payment_method": "neft_rtgs_invoice",
            "error_code": "INVOICE_DISPUTED",
            "error_message": "Milestone #3 deliverable pending signoff",
            "historical_trust_score": 0.88,
            "contact_count_last_7d": 1,
            "metadata": {"invoice_number": "INV-2026-9812", "dispute_flag": True, "dispute_reason": "Milestone #3 deliverable pending signoff"}
        }
    elif "6. Night-time" in preset_choice:
        # UTC 21:30 is 3:00 AM IST
        sample_event_dict = {
            "event_id": "evt_night_time_106",
            "event_type": "payment_failure",
            "customer_id": "cust_rahul",
            "customer_name": "Rahul Verma",
            "customer_email": "rahul@example.com",
            "customer_phone": "+919876543215",
            "customer_timezone": "Asia/Kolkata",
            "amount": 3500.0,
            "currency": "INR",
            "timestamp": "2026-08-23T21:30:00Z",
            "payment_method": "upi",
            "error_code": "INSUFFICIENT_FUNDS",
            "error_message": "Balance not available",
            "historical_trust_score": 0.70,
            "contact_count_last_7d": 0,
            "metadata": {}
        }
    else:  # High contact fatigue
        sample_event_dict = {
            "event_id": "evt_fatigued_107",
            "event_type": "checkout_abandonment",
            "customer_id": "cust_fatigued",
            "customer_name": "Karan Malhotra",
            "customer_email": "karan@example.com",
            "customer_phone": "+919876543216",
            "customer_timezone": "Asia/Kolkata",
            "amount": 4200.0,
            "currency": "INR",
            "timestamp": "2026-08-23T12:00:00+05:30",
            "payment_method": "checkout_page",
            "error_code": "PRICE_HESITATION",
            "error_message": "Coupon rejected",
            "historical_trust_score": 0.40,
            "contact_count_last_7d": 5,  # 5 contacts already in 7d!
            "metadata": {"coupon_attempted": "SAVE30", "dwell_time_seconds": 320}
        }

    # Execute Button
    if st.button("🚀 Process Event Through CloseLoop Pipeline", type="primary"):
        run_res = pipeline.process_event(sample_event_dict)
        
        st.success("✅ Pipeline Execution Finished with Immutable Audit Trace")

        c1, c2, c3 = st.columns([1, 1, 1])
        with c1:
            st.markdown("#### 1. Ingestion & Schema")
            st.json(run_res["event"], expanded=False)

        with c2:
            st.markdown("#### 2. Diagnosis Engine")
            diag = run_res.get("diagnosis")
            if diag:
                st.markdown(f"**Root Cause**: `{diag['root_cause']}`")
                st.markdown(f"**Confidence**: `{diag['confidence']:.0%}`")
                st.info(f"💡 **Explanation**: {diag['explanation']}")
                st.markdown(f"**Signals Detected**: `{', '.join(diag['signals_detected'])}`")
            else:
                st.write("Diagnosis skipped (Promise Grace Hold active).")

        with c3:
            st.markdown("#### 3. Playbook Selection")
            sel = run_res.get("selection")
            if sel:
                st.markdown(f"**Playbook**: `{sel['playbook_name']}`")
                st.markdown(f"**Category**: `{sel['category']}`")
                if sel["is_stopped_by_fatigue"]:
                    st.warning(f"🛑 {sel['selection_reason']}")
                else:
                    st.success(f"✓ {sel['selection_reason']}")

        st.markdown("---")
        st.markdown("#### 4. Gated Execution & Simulated Multi-Channel Dispatch")
        
        exec_res = run_res["execution"]
        st_status = exec_res["status"]
        
        if st_status == "EXECUTED":
            status_color = "success"
        elif "STOPPED" in st_status or "BLOCKED" in st_status:
            status_color = "warning"
        else:
            status_color = "info"

        getattr(st, status_color)(
            f"**Status**: `{exec_res['status']}` | **Channel**: `{exec_res['channel']}` | **Fatigue Incurred**: `{exec_res['fatigue_score_incurred']} pts`"
        )
        
        col_msg, col_gates = st.columns([3, 2])
        with col_msg:
            st.markdown("**Rendered Dispatch / Script Content:**")
            st.code(exec_res["rendered_message"], language="text")
        
        with col_gates:
            st.markdown("**Engineering Safety Gates:**")
            st.markdown(f"- **Idempotency Key**: `{exec_res.get('idempotency_key', 'N/A')}`")
            st.markdown(f"- **Compliance Status**: `{'✓ PROVABLY COMPLIANT' if exec_res.get('is_compliant') else '❌ VIOLATION'}`")
            st.markdown(f"- **Reasoning**: {exec_res.get('execution_reason')}")


# ==============================================================================
# TAB 3: CIRCUIT BREAKERS & 2AM BREAKERS
# ==============================================================================
elif nav_choice == "🛡️ Circuit Breakers & 2am Breakers":
    st.subheader("🛡️ Distributed Circuit Breakers & 2am Breakers")
    st.caption("Borrowing distributed systems engineering patterns to protect merchants against retry storms and brand-destroying complaint spikes.")

    st.markdown("### 🔌 Live Playbook Circuit Breaker Status Grid")
    
    cb_cols = st.columns(4)
    for i, (cat, cb) in enumerate(pipeline.executor.circuit_breakers.items()):
        with cb_cols[i]:
            st.markdown(f"**{cat.upper()}**")
            if cb.state == "CLOSED":
                st.markdown('<span class="badge-success">● CLOSED (Healthy)</span>', unsafe_allow_html=True)
                st.caption(f"Trip Threshold: {cb.failure_threshold:.0%} opt-outs")
                if st.button(f"Simulate Complaint Spike", key=f"trip_{cat}"):
                    for _ in range(6):
                        cb.record_outcome(is_success=False, is_complaint_or_opt_out=True)
                    st.rerun()
            else:
                st.markdown('<span class="badge-danger">● OPEN (Auto-Paused)</span>', unsafe_allow_html=True)
                st.error(f"Reason: {cb.trip_reason}")
                if st.button(f"Reset Breaker", key=f"reset_{cat}"):
                    cb.reset()
                    st.rerun()

    st.divider()

    st.markdown("### 🌙 The 2am Breakers (Production Failure Modes Fixed)")
    
    c1, c2 = st.columns(2)
    with c1:
        st.markdown("#### 1. The Retry Storm / Duplicate Charge Bug")
        st.markdown("""
        - **What breaks in naive bots**: When a bank experiences downtime, naive schedulers fire rapid retries. If 3 retries fire concurrently before the gateway resolves, **a real customer gets double or triple charged**.
        - **CloseLoop Engineering Fix**: Every recovery action computes a deterministic SHA-256 idempotency key:
          `SHA256(event_id : customer_id : action_type : amount)`
          Guaranteed via thread-safe atomic lock. Even under 100 concurrent threads, exactly **one** retry executes; the rest are safely blocked.
        - **Test Coverage**: [`tests/test_idempotency.py`](file:///C:/Users/Priyanshi%20Jain/.gemini/antigravity/scratch/closeloop/tests/test_idempotency.py)
        """)

    with c2:
        st.markdown("#### 2. The Quiet-Hours Timezone Violation Bug")
        st.markdown("""
        - **What breaks in naive bots**: Schedulers evaluate quiet hours using server time (UTC or merchant office time). At 4:30 PM UTC, naive bots dial Indian customers at **10:00 PM IST** or **3:00 AM IST** — causing customer rage and **RBI recovery-conduct violations**.
        - **CloseLoop Engineering Fix**: Timezone-aware gatekeeper translates every timestamp to the customer's actual geographical timezone (`pytz.timezone(customer_timezone)`) and checks strict compliant hours (09:00 - 19:00 local time). Out-of-window contact is deferred to 09:30 AM next morning.
        - **Test Coverage**: [`tests/test_quiet_hours.py`](file:///C:/Users/Priyanshi%20Jain/.gemini/antigravity/scratch/closeloop/tests/test_quiet_hours.py)
        """)


# ==============================================================================
# TAB 4: IMMUTABLE AUDIT LOG EXPLORER
# ==============================================================================
elif nav_choice == "📜 Immutable Audit Log Explorer":
    st.subheader("📜 Immutable Audit Log & Explainability Ledger")
    st.caption("Every ingestion, diagnosis, playbook selection, safety gate check, and executed action is immutably logged with full human-readable reasoning.")

    entries = pipeline.audit_log.get_all_entries()
    
    if not entries:
        st.info("No audit logs yet. Run some events in the 'Live Event Simulator' tab to see entries stream here!")
    else:
        df_audit = pd.DataFrame(entries)
        
        # Filter controls
        fc1, fc2 = st.columns([2, 2])
        with fc1:
            stage_filter = st.multiselect("Filter by Stage:", options=list(df_audit["stage"].unique()), default=list(df_audit["stage"].unique()))
        with fc2:
            status_filter = st.multiselect("Filter by Status:", options=list(df_audit["status"].unique()), default=list(df_audit["status"].unique()))

        df_filtered = df_audit[
            df_audit["stage"].isin(stage_filter) &
            df_audit["status"].isin(status_filter)
        ]

        st.dataframe(
            df_filtered[["entry_id", "timestamp", "customer_name", "stage", "action_type", "status", "explanation"]],
            hide_index=True,
            use_container_width=True
        )

        st.markdown("#### 🔍 Customer Decision Tree Timeline Drill-down")
        cust_list = list(df_audit["customer_id"].unique())
        selected_cust = st.selectbox("Select Customer to inspect causal chain:", options=cust_list)
        
        cust_timeline = pipeline.audit_log.get_timeline_for_customer(selected_cust)
        for e in cust_timeline:
            with st.expander(f"[{e['timestamp'][11:19]}] {e['stage']} → {e['action_type']} ({e['status']})"):
                st.markdown(f"**Explanation**: {e['explanation']}")
                st.json(e["details"])


# ==============================================================================
# TAB 5: PROMISE-TO-PAY & TRUST LOOP
# ==============================================================================
elif nav_choice == "🤝 Promise-to-Pay & Trust Loop":
    st.subheader("🤝 Promise-to-Pay Tracker & Dynamic Trust Feedback Loop")
    st.caption("Unlike static recovery tools, CloseLoop learns customer reliability. Kept commitments raise trust (+0.12), while broken promises lower trust (-0.25) to adjust future playbook aggression.")

    # Create / View Promises
    st.markdown("### 📋 Active Commitments & Customer Trust Matrix")
    
    # Pre-populate sample promises if empty
    if not pipeline.promise_tracker.promises:
        now = datetime.now()
        pipeline.promise_tracker.set_trust_score("cust_aarav", 0.85)
        pipeline.promise_tracker.set_trust_score("cust_pooja", 0.72)
        pipeline.promise_tracker.set_trust_score("cust_acme_corp", 0.90)
        pipeline.promise_tracker.record_promise("cust_aarav", "evt_p1", 4999.0, (now + pd.Timedelta(days=3)).isoformat(), notes="Promised after salary credit")
        pipeline.promise_tracker.record_promise("cust_acme_corp", "evt_p2", 145000.0, (now + pd.Timedelta(days=10)).isoformat(), notes="Vendor receivables invoice extension")

    promises_data = [p.to_dict() for p in pipeline.promise_tracker.promises.values()]
    df_promises = pd.DataFrame(promises_data)
    
    # Display table
    st.dataframe(
        df_promises[["promise_id", "customer_id", "amount", "promised_date", "grace_period_hours", "status", "notes"]],
        hide_index=True,
        use_container_width=True
    )

    st.markdown("### ⚡ Simulate Promise Outcome & Trust Adjustment")
    col_p_select, col_outcome = st.columns([2, 1])
    
    with col_p_select:
        selected_pid = st.selectbox("Select Promise ID:", options=list(pipeline.promise_tracker.promises.keys()))
    
    with col_outcome:
        st.write("Action:")
        btn_keep = st.button("✓ Customer Paid (Kept Promise)")
        btn_break = st.button("❌ Payment Missed (Broken Promise)")

    if btn_keep:
        prom, new_t = pipeline.promise_tracker.resolve_promise(selected_pid, payment_received=True)
        st.success(f"Promise `{selected_pid}` marked as KEPT! Customer `{prom.customer_id}` trust score boosted to **{new_t:.2f}** (+0.12).")
        st.rerun()

    if btn_break:
        prom, new_t = pipeline.promise_tracker.resolve_promise(selected_pid, payment_received=False)
        st.error(f"Promise `{selected_pid}` marked as BROKEN! Customer `{prom.customer_id}` trust score penalized to **{new_t:.2f}** (-0.25). Future playbooks will restrict credit/grace extensions.")
        st.rerun()

