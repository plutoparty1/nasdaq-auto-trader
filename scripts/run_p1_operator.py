"""Dedicated source entry point. Defaults to local simulation, never legacy GUI defaults."""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def verify_operating_sources() -> str:
    path = ROOT / 'experiments/p1_operations_v1/manifest.json'
    from nasdaq_auto_trader.p1_paper_codec import read_json
    from nasdaq_auto_trader.p1_paper_protocol import mapping, text_field
    value = mapping(read_json(path.read_text(encoding='utf-8')))
    if value.get('version') != 'p1-ops-v1':
        raise ValueError('operating_version_invalid')
    for name, expected in mapping(value.get('source_sha256')).items():
        source = (ROOT / name).resolve()
        if not source.is_relative_to(ROOT) or hashlib.sha256(source.read_bytes()).hexdigest() != text_field(expected):
            raise ValueError('operating_source_changed_requires_new_version')
    return hashlib.sha256(path.read_bytes()).hexdigest()


class Arguments(argparse.Namespace):
    status: bool = False
    start_paused: bool = False


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description='P1 operating dashboard: local simulation by default')
    _ = parser.add_argument('--status', action='store_true', help='Show isolated operating status without network')
    _ = parser.add_argument('--start-paused', action='store_true', help='Open dashboard without starting collection')
    args = Arguments()
    _ = parser.parse_args(argv, namespace=args)
    from nasdaq_auto_trader.p1_ops_controller import P1OperatingController
    from nasdaq_auto_trader.p1_paper_protocol import load_protocol
    from nasdaq_auto_trader.quant_data.resources import application_data_root
    from nasdaq_auto_trader.single_instance import SingleInstanceGuard
    guard = SingleInstanceGuard(application_data_root() / 'runtime/gui-instance.lock')
    controller = None
    try:
        version = verify_operating_sources()
        protocol = load_protocol(ROOT / 'experiments/p1_paper_v1/protocol.json')
        controller = P1OperatingController(application_data_root() / 'operations/p1-ops-v1', protocol)
        controller.version = 'p1-ops-v1/' + version[:12]
        if args.status:
            saved = controller.control.get('last_status')
            print(json.dumps({'status_kind': 'last_saved_observation_not_live_query',
                              'snapshot': saved if isinstance(saved, dict) else controller.status()},
                             ensure_ascii=False, indent=2))
            return 0
        if not guard.acquire():
            raise ValueError('existing_trader_gui_running_close_it_first')
        from nasdaq_auto_trader.p1_ops_gui import launch_p1_ops_gui
        launch_p1_ops_gui(controller, auto_start_local=not args.start_paused)
        return 0
    except (ValueError, OSError, RuntimeError) as error:
        safe = str(error) if isinstance(error, ValueError) and str(error).isascii() and str(error).replace('_', '').isalnum() else type(error).__name__
        if len(safe) > 160 or any(word in safe.lower() for word in ('secret', 'token', 'app_key')):
            safe = type(error).__name__
        message = 'P1 operating start blocked: ' + safe
        if args.status:
            print(message, file=sys.stderr)
        else:
            from tkinter import messagebox
            _ = messagebox.showerror('P1 operating build', message)
        return 2
    finally:
        if controller is not None:
            controller.close()
        guard.release()


if __name__ == '__main__':
    raise SystemExit(main())
