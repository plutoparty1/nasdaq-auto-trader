import io
import json
import os
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest.mock import patch

from nasdaq_auto_trader.ai_quant_lab.artifact_paths import default_strategy_artifact_paths
from nasdaq_auto_trader.cli import main
from nasdaq_auto_trader.live_authorization_store import LiveAuthorizationStore
from nasdaq_auto_trader.quant_data.resources import application_data_root
from tests.test_auto_symbol_live_guard import _write_champion


CONFIRMATION = "I UNDERSTAND THIS WILL PLACE REAL ORDERS DURING ONE NASDAQ SESSION"


class LiveSessionAuthorizationCliTests(unittest.TestCase):
    def test_auto_once_without_stored_authorization_is_load_only(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            client = _NoNetworkClient()
            with patch.dict(os.environ, {"LOCALAPPDATA": temp_dir}, clear=False):
                config_path = _write_live_config(root)
                settings_path = root / "trading.json"
                _write_champion(default_strategy_artifact_paths())
                output = io.StringIO()
                with patch(
                    "nasdaq_auto_trader.engine.build_default_client",
                    return_value=client,
                ):
                    with redirect_stdout(output):
                        exit_code = main(
                            [
                                "--config",
                                str(config_path),
                                "once",
                                "--auto-select",
                                "--confirm-live-orders",
                                "--trading-config",
                                str(settings_path),
                            ]
                        )
                store_path = _authorization_store_path()

        payload = json.loads(output.getvalue())
        self.assertEqual(exit_code, 2)
        self.assertEqual(
            payload["selection"]["blocked_reasons"],
            ["live_authorization_required"],
        )
        self.assertEqual(client.submitted_orders, 0)
        self.assertFalse(store_path.exists())

    def test_authorize_live_session_requires_exact_phrase(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            with patch.dict(os.environ, {"LOCALAPPDATA": temp_dir}, clear=False):
                config_path = _write_live_config(root)
                _write_champion(default_strategy_artifact_paths())
                output = io.StringIO()

                with redirect_stdout(output), redirect_stderr(io.StringIO()):
                    exit_code = main(
                        [
                            "--config",
                            str(config_path),
                            "authorize-live-session",
                            "--confirm",
                            "WRONG",
                            "--trading-config",
                            str(root / "trading.json"),
                        ]
                    )

                store_path = _authorization_store_path()

        self.assertEqual(exit_code, 2)
        self.assertEqual(
            json.loads(output.getvalue())["reason"],
            "live_session_confirmation_required",
        )
        self.assertFalse(store_path.exists())

    def test_missing_settings_preserve_live_base_and_never_construct_broker(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            with patch.dict(os.environ, {"LOCALAPPDATA": temp_dir}, clear=False):
                config_path = _write_live_config(root)
                settings_path = root / "trading.json"
                _write_champion(default_strategy_artifact_paths())
                authorize_output = io.StringIO()
                revoke_output = io.StringIO()
                with patch(
                    "nasdaq_auto_trader.engine_clients.build_default_client",
                    side_effect=AssertionError("broker client must not be constructed"),
                ):
                    with redirect_stdout(authorize_output):
                        authorize_exit = main(
                            [
                                "--config",
                                str(config_path),
                                "authorize-live-session",
                                "--max-attempts",
                                "12",
                                "--confirm",
                                CONFIRMATION,
                                "--trading-config",
                                str(settings_path),
                            ]
                        )
                    store_path = _authorization_store_path()
                    stored = LiveAuthorizationStore(store_path).load()
                    settings_created = settings_path.exists()
                    with redirect_stdout(revoke_output):
                        revoke_exit = main(
                            ["--config", str(config_path), "revoke-live-session"]
                        )

        authorize_payload = json.loads(authorize_output.getvalue())
        revoke_payload = json.loads(revoke_output.getvalue())
        self.assertEqual(authorize_exit, 0)
        self.assertEqual(authorize_payload["status"], "authorized")
        self.assertFalse(authorize_payload["submitted_order"])
        self.assertFalse(authorize_payload["network_client_constructed"])
        self.assertTrue(settings_created)
        self.assertEqual(stored.attempts, 0)
        self.assertEqual(stored.envelope.max_attempts, 12)
        self.assertEqual(revoke_exit, 0)
        self.assertEqual(revoke_payload["status"], "revoked")
        self.assertFalse(store_path.exists())

    def test_authorize_honors_live_settings_when_base_config_is_dry_run(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            with patch.dict(os.environ, {"LOCALAPPDATA": temp_dir}, clear=False):
                config_path = _write_config(root, mode="dry_run", allow_live=False)
                settings_path = root / "trading.json"
                settings_path.write_text(
                    json.dumps({"live_trading": True, "dry_run": False}),
                    encoding="utf-8",
                )
                _write_champion(default_strategy_artifact_paths())
                output = io.StringIO()

                with redirect_stdout(output):
                    exit_code = main(
                        [
                            "--config",
                            str(config_path),
                            "authorize-live-session",
                            "--confirm",
                            CONFIRMATION,
                            "--trading-config",
                            str(settings_path),
                        ]
                    )

        payload = json.loads(output.getvalue())
        self.assertEqual(exit_code, 0)
        self.assertEqual(payload["status"], "authorized")
        self.assertFalse(payload["network_client_constructed"])


def _authorization_store_path() -> Path:
    return application_data_root() / "runtime" / "trading_session.live-authorization.json"


def _write_live_config(root: Path) -> Path:
    return _write_config(root, mode="live", allow_live=True)


def _write_config(root: Path, *, mode: str, allow_live: bool) -> Path:
    path = root / "config.json"
    path.write_text(
        json.dumps(
            {
                "mode": mode,
                "broker": "alpaca",
                "allow_live_trading": allow_live,
                "regular_market_hours_only": True,
                "alpaca": {
                    "api_key": "test-key",
                    "secret_key": "test-secret",
                    "paper": False,
                },
            }
        ),
        encoding="utf-8",
    )
    (root / ".env").write_text(
        "NASDAQ_AUTO_TRADER_ALLOW_LIVE=YES\n",
        encoding="utf-8",
    )
    return path


class _NoNetworkClient:
    def __init__(self) -> None:
        self.submitted_orders = 0

    def submit_order(self, order):
        del order
        self.submitted_orders += 1
        raise AssertionError("order must not be submitted")


if __name__ == "__main__":
    unittest.main()
