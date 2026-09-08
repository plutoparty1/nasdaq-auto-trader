import io
import json
import os
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import patch

from nasdaq_auto_trader.ai_quant_lab.artifact_paths import (
    default_strategy_artifact_paths,
)
from nasdaq_auto_trader.cli import main
from tests.test_auto_symbol_live_guard import _write_champion
from tests.test_live_session_authorization_cli import (
    CONFIRMATION,
    _authorization_store_path,
    _write_config,
    _write_live_config,
)


class LiveSessionAuthorizationCliFailureTests(unittest.TestCase):
    def test_exact_phrase_config_failure_keeps_json_contract(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            with patch.dict(
                os.environ,
                {"LOCALAPPDATA": temp_dir},
                clear=True,
            ):
                config_path = _write_config(
                    root,
                    mode="live",
                    allow_live=False,
                )
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
                            str(root / "trading.json"),
                        ]
                    )

        payload = json.loads(output.getvalue())
        self.assertEqual(exit_code, 2)
        self.assertEqual(payload["status"], "blocked")
        self.assertFalse(payload["submitted_order"])
        self.assertFalse(payload["network_client_constructed"])

    def test_revoke_is_idempotent_and_never_constructs_broker(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            with patch.dict(os.environ, {"LOCALAPPDATA": temp_dir}, clear=False):
                config_path = _write_live_config(root)
                settings_path = root / "trading.json"
                _write_champion(default_strategy_artifact_paths())
                with redirect_stdout(io.StringIO()):
                    self.assertEqual(
                        main(
                            [
                                "--config",
                                str(config_path),
                                "authorize-live-session",
                                "--confirm",
                                CONFIRMATION,
                                "--trading-config",
                                str(settings_path),
                            ]
                        ),
                        0,
                    )

                outputs = []
                with patch(
                    "nasdaq_auto_trader.engine_clients.build_default_client",
                    side_effect=AssertionError(
                        "broker client must not be constructed"
                    ),
                ):
                    for _ in range(2):
                        output = io.StringIO()
                        with redirect_stdout(output):
                            exit_code = main(
                                [
                                    "--config",
                                    str(config_path),
                                    "revoke-live-session",
                                ]
                            )
                        outputs.append((exit_code, json.loads(output.getvalue())))

                store_path = _authorization_store_path()

        self.assertEqual([item[0] for item in outputs], [0, 0])
        self.assertEqual(
            [item[1]["status"] for item in outputs],
            ["revoked", "revoked"],
        )
        self.assertFalse(store_path.exists())


if __name__ == "__main__":
    unittest.main()
