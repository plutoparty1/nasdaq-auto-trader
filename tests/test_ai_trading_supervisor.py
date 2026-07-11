import json
import unittest
from datetime import datetime, timedelta, timezone

from nasdaq_auto_trader.ai_trading_supervisor import SupervisorDecisionError, parse_supervisor_decision


class AITradingSupervisorTests(unittest.TestCase):
    def test_valid_decision_is_structured_and_orderless(self):
        now = datetime(2026, 7, 12, tzinfo=timezone.utc)
        payload = _payload(now)

        decision = parse_supervisor_decision(json.dumps(payload), now, max_age_seconds=60)

        self.assertEqual(decision.action.value, "BUY")
        self.assertEqual(decision.reason_codes, ("trend_confirmed",))
        self.assertFalse(hasattr(decision, "order_qty"))

    def test_stale_signal_is_rejected(self):
        now = datetime(2026, 7, 12, tzinfo=timezone.utc)
        payload = _payload(now - timedelta(minutes=5))

        with self.assertRaisesRegex(SupervisorDecisionError, "stale"):
            parse_supervisor_decision(json.dumps(payload), now, max_age_seconds=60)

    def test_unknown_field_is_rejected(self):
        now = datetime(2026, 7, 12, tzinfo=timezone.utc)
        payload = _payload(now)
        payload["order_qty"] = 100

        with self.assertRaisesRegex(SupervisorDecisionError, "unknown"):
            parse_supervisor_decision(json.dumps(payload), now, max_age_seconds=60)


def _payload(timestamp):
    return {
        "symbol": "QQQ",
        "action": "BUY",
        "confidence": 0.8,
        "target_position_pct": 0.02,
        "signal_timestamp": timestamp.isoformat(),
        "model_version": "alpha:v3",
        "market_regime": "uptrend",
        "reason_codes": ["trend_confirmed"],
        "risk_flags": [],
        "summary": "추세와 리스크 한도를 함께 확인함",
    }
