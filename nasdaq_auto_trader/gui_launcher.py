"""Windows GUI launcher used by the packaged executable."""

from __future__ import annotations

import os
import sys
import traceback
from pathlib import Path


ENV_KEYS = {
    "ALPACA_API_KEY",
    "ALPACA_SECRET_KEY",
    "ALPACA_DATA_FEED",
    "KIS_APP_KEY",
    "KIS_APP_SECRET",
    "KIS_ACCOUNT_NO",
    "KIS_ACCOUNT_PRODUCT_CODE",
    "KIS_ORDER_EXCHANGE_CODE",
    "KIS_PRICE_EXCHANGE_CODE",
    "KIS_CURRENCY",
}

CLI_LAUNCH_ERRORS = (ImportError, KeyError, OSError, RuntimeError, ValueError)


def _app_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parents[1]


def _default_argv(app_dir: Path) -> list[str]:
    config_path = app_dir / "config.kis.json"
    if not config_path.exists():
        config_path = app_dir / "config.example.json"

    argv: list[str] = []
    if config_path.exists():
        argv.extend(["--config", str(config_path)])
    argv.extend(
        [
            "gui",
            "--trading-config",
            str(app_dir / "trading_config.json"),
        ]
    )
    return argv


def _show_error(message: str) -> None:
    try:
        import tkinter as tk
        from tkinter import messagebox
    except ImportError:
        print(message, file=sys.stderr)
        return

    try:
        root = tk.Tk()
        try:
            root.withdraw()
            messagebox.showerror("NASDAQ Auto Trader 실행 실패", message)
        finally:
            root.destroy()
    except (OSError, tk.TclError):
        print(message, file=sys.stderr)


def _read_dotenv(path: Path) -> dict[str, str]:
    if not path.exists():
        return {}

    values: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8-sig").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        if stripped.startswith("export "):
            stripped = stripped[7:].lstrip()

        key, separator, value = stripped.partition("=")
        if not separator:
            continue
        key = key.strip()
        if key not in ENV_KEYS:
            continue

        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in ("'", '"'):
            value = value[1:-1]
        values[key] = value
    return values


def _load_exe_env(app_dir: Path) -> list[Path]:
    loaded_paths: list[Path] = []
    candidates = [app_dir / ".env", app_dir.parent / ".env"]
    for path in dict.fromkeys(candidates):
        values = _read_dotenv(path)
        if not values:
            continue
        for key, value in values.items():
            os.environ.setdefault(key, value)
        loaded_paths.append(path)
    return loaded_paths


def run(arguments: list[str] | None = None) -> int:
    app_dir = _app_dir()
    os.chdir(app_dir)
    if str(app_dir) not in sys.path:
        sys.path.insert(0, str(app_dir))
    argv = arguments
    if argv is None:
        argv = sys.argv[1:] if len(sys.argv) > 1 else _default_argv(app_dir)
    from nasdaq_auto_trader.frozen_diagnostic import (
        DiagnosticUsageError,
        parse_diagnostic_request,
        run_frozen_diagnostic,
    )

    try:
        diagnostic = parse_diagnostic_request(argv)
    except DiagnosticUsageError as exc:
        print(str(exc), file=sys.stderr)
        return 2
    if diagnostic is not None:
        try:
            return run_frozen_diagnostic(
                diagnostic.output_path,
                diagnostic.fixture_root,
            )
        except DiagnosticUsageError as exc:
            print(str(exc), file=sys.stderr)
            return 2
        except CLI_LAUNCH_ERRORS as exc:
            print(str(exc), file=sys.stderr)
            return 1

    _load_exe_env(app_dir)
    from nasdaq_auto_trader.cli import main as cli_main

    try:
        return cli_main(argv)
    except SystemExit as exc:
        code = exc.code if isinstance(exc.code, int) else 1
        if code:
            _show_error(f"프로그램 실행 옵션을 확인하세요.\n\n종료 코드: {code}")
        return code
    except CLI_LAUNCH_ERRORS as exc:
        _show_error(f"{exc}\n\n자세한 오류:\n{traceback.format_exc()}")
        return 1


if __name__ == "__main__":
    raise SystemExit(run())
