import json
import tempfile
import unittest
from pathlib import Path

from tests.ai_quant_fixtures import (
    FakeBroker,
    FakeLiveMarketData,
    MemorySpecStore,
    bars,
    promoted_payload,
    valid_spec,
    valid_spec_payload,
)
from nasdaq_auto_trader.ai_quant_lab.audit_logger import AuditLogger, NullAuditLogger
from nasdaq_auto_trader.ai_quant_lab.config import (
    AIQuantConfig,
    live_order_block_reason,
    load_ai_quant_config,
)
from nasdaq_auto_trader.ai_quant_lab.registry import StrategyRegistry
from nasdaq_auto_trader.ai_quant_lab.strategy_schema import (
    parse_strategy_spec_json,
    validate_strategy_spec,
)
from nasdaq_auto_trader.execution.risk_guard import (
    OrderIntent,
    RiskGuard,
    RiskGuardContext,
)
from nasdaq_auto_trader.execution.kill_switch import KillSwitchState
from nasdaq_auto_trader.execution.live_engine import LiveEngine
from nasdaq_auto_trader.execution.position_sizer import PortfolioState, SizingResult


class FixedNotionalSizer:
    def __init__(self, notional: float, order_qty: int) -> None:
        self.notional = notional
        self.order_qty = order_qty

    def calculate(self, request):
        return SizingResult(
            self.order_qty,
            self.order_qty,
            self.notional,
            0.0,
            "fixed_test_notional",
            "",
        )


class AIQuantBoundaryTests(unittest.TestCase):
    def test_malformed_json_config_loads_fail_closed_defaults(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            config_path = Path(temp_dir) / "config.json"
            config_path.write_text("{", encoding="utf-8")

            config = load_ai_quant_config(config_path)

        self.assertEqual(live_order_block_reason(config), "live_trading_disabled")

    def test_non_finite_json_config_loads_fail_closed_defaults(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            config_path = Path(temp_dir) / "config.json"
            config_path.write_text(
                '{"live_trading": true, "dry_run": false, '
                '"controlled_live_enabled": true, "max_order_notional": Infinity}',
                encoding="utf-8",
            )

            config = load_ai_quant_config(config_path)

        self.assertEqual(live_order_block_reason(config), "live_trading_disabled")

    def test_strategy_schema_rejects_bool_numeric_fields(self):
        payload = valid_spec_payload()
        payload["signals"] = [{"type": "cross_sectional_momentum", "weight": True}]
        payload["entry_rule"]["threshold"] = True

        validation = validate_strategy_spec(payload)

        self.assertFalse(validation.valid)
        self.assertIn("signal_weight_required", validation.reasons)
        self.assertIn("entry_rule_threshold_out_of_range", validation.reasons)

    def test_strategy_schema_rejects_non_finite_json_numbers(self):
        payload = valid_spec_payload()
        payload["exit_rule"]["stop_loss_atr_multiple"] = float("nan")

        validation = parse_strategy_spec_json(json.dumps(payload))

        self.assertFalse(validation.valid)
        self.assertIn("strategy_spec_invalid_json", validation.reasons)

    def test_strategy_schema_rejects_unknown_and_order_fields(self):
        payload = valid_spec_payload()
        payload["order_qty"] = 999
        payload["python_code"] = "broker.submit_order(order)"

        validation = validate_strategy_spec(payload)

        self.assertFalse(validation.valid)
        self.assertIn("unknown_field:order_qty", validation.reasons)
        self.assertIn("field_not_allowed:python_code", validation.reasons)

    def test_strategy_schema_rejects_broker_and_raw_order_fields(self):
        payload = valid_spec_payload()
        payload["broker"] = "alpaca"
        payload["entry_rule"]["raw_order"] = {"side": "buy"}
        payload["metadata"]["broker_order"] = {"qty": 10}

        validation = validate_strategy_spec(payload)

        self.assertFalse(validation.valid)
        self.assertIn("field_not_allowed:broker", validation.reasons)
        self.assertIn("field_not_allowed:entry_rule.raw_order", validation.reasons)
        self.assertIn("field_not_allowed:metadata.broker_order", validation.reasons)

    def test_strategy_schema_rejects_unknown_nested_fields(self):
        payload = valid_spec_payload()
        payload["entry_rule"]["unlisted_nested_field"] = "x"
        payload["metadata"]["script"] = "print('unsafe')"

        validation = validate_strategy_spec(payload)

        self.assertFalse(validation.valid)
        self.assertIn(
            "unknown_field:entry_rule.unlisted_nested_field",
            validation.reasons,
        )
        self.assertIn("unknown_field:metadata.script", validation.reasons)

    def test_strategy_spec_raw_does_not_alias_input_payload(self):
        payload = valid_spec_payload()
        validation = validate_strategy_spec(payload)
        self.assertTrue(validation.valid)
        self.assertIsNotNone(validation.spec)

        payload["research_basis"]["source_ids"] = ["mutated-source"]

        self.assertEqual(validation.spec.raw["research_basis"]["source_ids"], ["source-1"])

    def test_strategy_schema_rejects_non_bool_risk_controls(self):
        payload = valid_spec_payload()
        payload["risk_controls"]["use_kill_switch"] = "yes"

        validation = validate_strategy_spec(payload)

        self.assertFalse(validation.valid)
        self.assertIn("use_kill_switch_must_be_bool", validation.reasons)

    def test_strategy_schema_rejects_non_bool_strategy_flags(self):
        payload = valid_spec_payload()
        payload["exit_rule"]["trailing_stop"] = "yes"
        payload["position_sizing"]["confidence_adjusted"] = "yes"

        validation = validate_strategy_spec(payload)

        self.assertFalse(validation.valid)
        self.assertIn("trailing_stop_must_be_bool", validation.reasons)
        self.assertIn("confidence_adjusted_must_be_bool", validation.reasons)

    def test_risk_guard_blocks_projected_single_position_exposure(self):
        config = AIQuantConfig(
            live_trading=True,
            dry_run=False,
            controlled_live_enabled=True,
            max_order_notional=10_000,
        )
        intent = OrderIntent("s1", "QQQ", "buy", 10, 100.0, 1_000.0)
        with tempfile.TemporaryDirectory() as temp_dir:
            guard = RiskGuard(AuditLogger(Path(temp_dir) / "audit.jsonl"))

            result = guard.check(
                RiskGuardContext(
                    config,
                    intent,
                    promoted_payload("s1"),
                    available_cash=100_000,
                    total_exposure=5_000,
                    account_equity=100_000,
                    symbol_position_value=5_000,
                )
            )

        self.assertFalse(result.allowed)
        self.assertEqual(result.block_reason, "single_position_exposure_exceeded")

    def test_null_audit_logger_cannot_claim_durable_live_permission(self):
        config = AIQuantConfig(
            live_trading=True,
            dry_run=False,
            controlled_live_enabled=True,
            max_order_notional=10_000,
        )
        intent = OrderIntent("s1", "QQQ", "buy", 10, 100.0, 1_000.0)

        result = RiskGuard(NullAuditLogger(durable=True)).check(
            RiskGuardContext(
                config,
                intent,
                promoted_payload("s1"),
                available_cash=100_000,
                total_exposure=0,
                account_equity=100_000,
            )
        )

        self.assertFalse(result.allowed)
        self.assertEqual(result.block_reason, "audit_logger_not_durable")

    def test_risk_guard_blocks_projected_total_exposure(self):
        config = AIQuantConfig(
            live_trading=True,
            dry_run=False,
            controlled_live_enabled=True,
            max_order_notional=10_000,
        )
        intent = OrderIntent("s1", "AAPL", "buy", 10, 100.0, 1_000.0)
        with tempfile.TemporaryDirectory() as temp_dir:
            guard = RiskGuard(AuditLogger(Path(temp_dir) / "audit.jsonl"))

            result = guard.check(
                RiskGuardContext(
                    config,
                    intent,
                    promoted_payload("s1"),
                    available_cash=100_000,
                    total_exposure=30_000,
                    account_equity=100_000,
                )
            )

        self.assertFalse(result.allowed)
        self.assertEqual(result.block_reason, "total_exposure_exceeded")

    def test_risk_guard_allows_sell_exit_when_cash_is_low(self):
        config = AIQuantConfig(live_trading=True, dry_run=False, controlled_live_enabled=True)
        intent = OrderIntent("s1", "QQQ", "sell", 5, 100.0, 500.0)
        with tempfile.TemporaryDirectory() as temp_dir:
            result = RiskGuard(AuditLogger(Path(temp_dir) / "audit.jsonl")).check(
                RiskGuardContext(
                    config,
                    intent,
                    promoted_payload("s1"),
                    current_positions={"QQQ": 10},
                    available_cash=0,
                    total_exposure=5_000,
                    account_equity=100_000,
                    symbol_position_value=1_000,
                )
            )

        self.assertTrue(result.allowed)

    def test_live_engine_reserves_pending_exposure_within_cycle(self):
        spec = valid_spec()
        broker = FakeBroker()
        config = AIQuantConfig(
            live_trading=True,
            dry_run=False,
            controlled_live_enabled=True,
            max_total_exposure_pct=0.30,
            max_single_position_pct=1.0,
            max_order_notional=25_000,
        )
        with tempfile.TemporaryDirectory() as temp_dir:
            registry = StrategyRegistry(
                Path(temp_dir) / "registry.json",
                Path(temp_dir) / "promoted.json",
                config,
            )
            registry.promoted_path.write_text(
                json.dumps(promoted_payload(spec.strategy_id)),
                encoding="utf-8",
            )
            engine = LiveEngine(
                registry,
                MemorySpecStore(spec),
                FakeLiveMarketData(
                    {"QQQ": bars("QQQ"), "AAPL": bars("AAPL")},
                    PortfolioState(100_000, 100_000, {}, 0),
                ),
                broker,
                risk_guard=RiskGuard(AuditLogger(Path(temp_dir) / "audit.jsonl")),
                position_sizer=FixedNotionalSizer(20_000, 100),
            )

            result = engine.run_cycle(KillSwitchState())

        self.assertEqual(len(broker.orders), 1)
        self.assertEqual(result.submitted_orders, 1)
        self.assertIn("total_exposure_exceeded", result.blocked_reasons)


if __name__ == "__main__":
    unittest.main()
