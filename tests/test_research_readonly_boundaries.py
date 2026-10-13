import json
import os
import subprocess
import sys
from pathlib import Path

from nasdaq_auto_trader.research_readonly_credentials import load_credentials
from nasdaq_auto_trader.research_readonly_history import summarize_history
from nasdaq_auto_trader.research_readonly_minute import normalize_minutes


def test_history_duplicate_partial_and_roundtrip_accounting():
    def row(number, side, qty, filled, price):
        return {
            "ovno": "ignored",
            "ovrs_excg_cd": "NASD",
            "ord_dt": "20260923",
            "ord_tmd": f"09{number:02}00",
            "odno": str(number),
            "pdno": "FAKE",
            "sll_buy_dvsn_cd": side,
            "ft_ord_qty": str(qty),
            "ft_ccld_qty": str(filled),
            "ft_ccld_unpr3": str(price),
        }

    buy = row(30, "02", 2, 2, 10)
    part_sell = row(35, "01", 2, 1, 11)
    final_sell = row(40, "01", 1, 1, 9.5)
    pending = row(45, "02", 1, 0, 0)
    report = summarize_history([buy, buy, part_sell, final_sell, pending])
    assert report["deduplicated_orders"] == 4
    assert report["closed_position_cycles_within_window"] == 1
    assert report["matched_cycle_gross_pnl_usd"] == 0.5
    assert report["status_counts"]["partially_filled"] == 1
    assert report["status_counts"]["accepted_or_unknown_unfilled"] == 1
    assert report["fees_usd"] is None
    assert report["roundtrip_holding_time_available"] is False


def test_minute_timezone_and_incomplete_session_removal(tmp_path):
    def row(day, hour, kday, khour):
        return {
            "xymd": day,
            "xhms": hour,
            "kymd": kday,
            "khms": khour,
            "open": "10",
            "high": "11",
            "low": "9",
            "last": "10.5",
            "evol": "2",
        }

    destination = tmp_path / "minutes.csv"
    report = normalize_minutes(
        [
            row("20260923", "093000", "20260923", "223000"),
            row("20260929", "093000", "20260929", "223000"),
            row("20260923", "093500", "20260923", "223000"),
        ],
        destination,
        "FAKE",
    )
    assert report["canonical_rows"] == 1
    assert report["timezone_pair_mismatches"] == 1
    assert report["current_day_rows_excluded"] == 1
    assert "2026-09-23T13:30:00+00:00" in destination.read_text()


def test_credentials_match_launcher_precedence(tmp_path, monkeypatch):
    for key in tuple(os.environ):
        if key.startswith("KIS_"):
            monkeypatch.delenv(key)
    local = tmp_path / "local"
    appdata = local / "NasdaqAutoTrader"
    appdata.mkdir(parents=True)
    app = tmp_path / "dist" / "app"
    app.mkdir(parents=True)
    config = app / "config.kis.json"
    config.write_text(json.dumps({"broker": "kis", "kis": {"paper": False}}))
    (appdata / ".env").write_text(
        "KIS_APP_KEY=local-key\nKIS_APP_SECRET=local-secret\nKIS_ACCOUNT_NO=12345678\n"
    )
    (app / ".env").write_text("KIS_APP_KEY=app-key\n")
    monkeypatch.setenv("LOCALAPPDATA", str(local))
    monkeypatch.setenv("KIS_APP_KEY", "process-key")
    credentials = load_credentials(config)
    assert credentials.app_key == "process-key"
    assert credentials.app_secret == "local-secret"
    assert "local-secret" not in repr(credentials)


def test_standalone_collector_imports_no_broker_or_engine():
    repo = Path(__file__).resolve().parents[1]
    driver = "import runpy,sys; runpy.run_path('scripts/collect_entry_policy_data.py',run_name='inspection'); print([key for key in sys.modules if key.startswith(('nasdaq_auto_trader.engine','nasdaq_auto_trader.brokers','nasdaq_auto_trader.config'))])"
    result = subprocess.run(
        [sys.executable, "-c", driver],
        cwd=repo,
        capture_output=True,
        text=True,
        check=True,
    )
    assert result.stdout.strip() == "[]"


def test_credentials_last_duplicate_wins_within_first_priority_file(
    tmp_path, monkeypatch
):
    for key in tuple(os.environ):
        if key.startswith("KIS_"):
            monkeypatch.delenv(key)
    local = tmp_path / "local"
    appdata = local / "NasdaqAutoTrader"
    appdata.mkdir(parents=True)
    app = tmp_path / "dist" / "app"
    app.mkdir(parents=True)
    config = app / "config.kis.json"
    config.write_text(json.dumps({"broker": "kis", "kis": {"paper": False}}))
    (appdata / ".env").write_text(
        "KIS_APP_KEY=first-key\nKIS_APP_KEY=last-key\nKIS_APP_SECRET=first-secret\nKIS_APP_SECRET=last-secret\nKIS_ACCOUNT_NO=12345678\n"
    )
    (app / ".env").write_text(
        "KIS_APP_KEY=lower-priority-key\nKIS_APP_SECRET=lower-priority-secret\n"
    )
    monkeypatch.setenv("LOCALAPPDATA", str(local))
    credentials = load_credentials(config)
    assert credentials.app_key == "last-key"
    assert credentials.app_secret == "last-secret"


def test_existing_or_outside_summary_fails_before_auth(tmp_path):
    repo = Path(__file__).resolve().parents[1]
    destination = tmp_path / "existing.json"
    destination.write_text("preserve")
    result = subprocess.run(
        [
            sys.executable,
            "scripts/collect_entry_policy_data.py",
            "--collect",
            "--summary",
            str(destination),
        ],
        cwd=repo,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 2
    assert json.loads(result.stdout)["status"] == "summary_destination_denied"
    assert destination.read_text() == "preserve"
