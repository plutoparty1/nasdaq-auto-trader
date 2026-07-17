from __future__ import annotations

import json
import subprocess
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CANARY_WATCHDOG = ROOT / "scripts" / "ensure_live_canary_running.ps1"
CANARY_INSTALLER = ROOT / "scripts" / "install_live_canary_task.ps1"
GUI_WATCHDOG = ROOT / "scripts" / "ensure_unattended_running.ps1"


class LiveCanaryWindowsTaskTests(unittest.TestCase):
    def test_canary_descriptor_launches_role_without_arm_command(self):
        executable = ROOT / "path with spaces" / "NasdaqAutoTrader.exe"
        config = ROOT / "path with spaces" / "config.kis.json"

        completed = subprocess.run(
            [
                "powershell.exe",
                "-NoProfile",
                "-File",
                str(CANARY_INSTALLER),
                "-ExecutablePath",
                str(executable),
                "-ConfigPath",
                str(config),
                "-DescribeOnly",
            ],
            check=True,
            capture_output=True,
            text=True,
        )
        descriptor = json.loads(completed.stdout)

        self.assertEqual(descriptor["settings"]["multiple_instances"], "IgnoreNew")
        self.assertEqual(descriptor["triggers"], ["AtLogOn", "Daily/PT5M"])
        self.assertIn("ensure_live_canary_running.ps1", descriptor["action"]["arguments"])
        self.assertNotIn("live-canary-arm", completed.stdout)
        self.assertNotIn("KIS_", completed.stdout)

    def test_watchdogs_match_distinct_process_roles(self):
        canary = CANARY_WATCHDOG.read_text(encoding="utf-8")
        gui = GUI_WATCHDOG.read_text(encoding="utf-8")

        self.assertIn("CommandLine", canary)
        self.assertIn("live-canary", canary)
        self.assertIn("--config", canary)
        self.assertIn("live-canary", gui)
        self.assertIn("-notmatch", gui)

    def test_build_copies_canary_operational_scripts(self):
        script = (ROOT / "scripts" / "build_gui_exe.ps1").read_text(encoding="utf-8")

        self.assertIn("ensure_live_canary_running.ps1", script)
        self.assertIn("install_live_canary_task.ps1", script)


if __name__ == "__main__":
    unittest.main()
