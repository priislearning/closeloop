"""
CloseLoop Signal Ingestion Layer
Normalizes heterogeneous events from 4 distinct revenue-at-risk sources:
1. Payment Gateway Failures
2. Checkout Drop-offs / Abandonment
3. Subscription / Mandate Renewal Failures
4. B2B Overdue Invoices / Receivables

Emits a unified, strongly-typed schema: UnifiedRecoveryEvent
"""

from dataclasses import dataclass, field, asdict
from datetime import datetime
from typing import Dict, Any, Optional
import pytz


@dataclass
class UnifiedRecoveryEvent:
    event_id: str
    event_type: str  # payment_failure, checkout_abandonment, subscription_renewal, b2b_receivables
    customer_id: str
    customer_name: str
    customer_email: str
    customer_phone: str
    customer_timezone: str  # e.g., "Asia/Kolkata", "America/New_York"
    amount: float
    currency: str  # INR, USD, etc.
    timestamp: str  # ISO-8601 string
    payment_method: str  # credit_card, upi, upi_autopay, e_nach, netbanking, checkout_page, neft_rtgs_invoice
    bank: Optional[str] = None
    gateway: Optional[str] = None
    error_code: Optional[str] = None
    error_message: Optional[str] = None
    gateway_latency_ms: int = 0
    retry_count: int = 0
    historical_trust_score: float = 0.8  # 0.0 to 1.0 scale
    contact_count_last_7d: int = 0
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    # Ingestion audit timestamp
    ingested_at: str = field(default_factory=lambda: datetime.now(pytz.UTC).isoformat())

    def get_parsed_timestamp(self) -> datetime:
        """Parses the event timestamp with UTC fallback."""
        try:
            clean_ts = self.timestamp.replace("Z", "+00:00")
            dt = datetime.fromisoformat(clean_ts)
            if dt.tzinfo is None:
                dt = pytz.UTC.localize(dt)
            return dt
        except Exception:
            return datetime.now(pytz.UTC)

    def get_customer_local_time(self) -> datetime:
        """Translates UTC/event timestamp to the customer's actual local timezone."""
        utc_dt = self.get_parsed_timestamp()
        try:
            cust_tz = pytz.timezone(self.customer_timezone)
            return utc_dt.astimezone(cust_tz)
        except Exception:
            # Fallback to IST
            return utc_dt.astimezone(pytz.timezone("Asia/Kolkata"))

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "UnifiedRecoveryEvent":
        """Normalizes and safely casts arbitrary raw webhook / event dictionaries."""
        return cls(
            event_id=str(data.get("event_id", "")),
            event_type=str(data.get("event_type", "payment_failure")),
            customer_id=str(data.get("customer_id", "unknown_customer")),
            customer_name=str(data.get("customer_name", "Valued Customer")),
            customer_email=str(data.get("customer_email", "")),
            customer_phone=str(data.get("customer_phone", "")),
            customer_timezone=str(data.get("customer_timezone", "Asia/Kolkata")),
            amount=float(data.get("amount", 0.0)),
            currency=str(data.get("currency", "INR")),
            timestamp=str(data.get("timestamp", datetime.now(pytz.UTC).isoformat())),
            payment_method=str(data.get("payment_method", "unknown")),
            bank=data.get("bank"),
            gateway=data.get("gateway"),
            error_code=data.get("error_code"),
            error_message=data.get("error_message"),
            gateway_latency_ms=int(data.get("gateway_latency_ms", 0)),
            retry_count=int(data.get("retry_count", 0)),
            historical_trust_score=float(data.get("historical_trust_score", 0.8)),
            contact_count_last_7d=int(data.get("contact_count_last_7d", 0)),
            metadata=dict(data.get("metadata", {})),
            ingested_at=str(data.get("ingested_at", datetime.now(pytz.UTC).isoformat())),
        )


def ingest_event(raw_payload: Dict[str, Any]) -> UnifiedRecoveryEvent:
    """Ingests and validates raw event payload, returning normalized UnifiedRecoveryEvent."""
    return UnifiedRecoveryEvent.from_dict(raw_payload)


def ingest_batch(raw_events: list) -> list:
    """Batch ingestion helper."""
    return [ingest_event(item) for item in raw_events]
