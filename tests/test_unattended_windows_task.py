import json
import subprocess
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
WATCHDOG = ROOT / "scripts" / "ensure_unattended_running.ps1"
INSTALLER = ROOT / "scripts" / "install_unattended_task.ps1"
HIDDEN_LAUNCHER = ROOT / "scripts" / "run_hidden.vbs"


class UnattendedWindowsTaskTests(unittest.TestCase):
    def test_watchdog_targets_exact_executable_without_credentials(self):
        script = WATCHDOG.read_text(encoding="utf-8")

        self.assertIn("ExecutablePath", script)
        self.assertIn("OrdinalIgnoreCase", script)
        self.assertIn("Start-Process -FilePath $resolvedExecutable", script)
        self.assertIn("-WindowStyle Hidden", script)
        for secret_name in ("KIS_APP_KEY", "KIS_APP_SECRET", "KIS_ACCOUNT_NO", "token"):
            self.assertNotIn(secret_name, script)

    def test_scheduler_descriptor_is_limited_interactive_and_repeating(self):
        executable = ROOT / "path with spaces" / "NasdaqAutoTrader.exe"

        completed = subprocess.run(
            [
                "powershell.exe",
                "-NoProfile",
                "-File",
                str(INSTALLER),
                "-ExecutablePath",
                str(executable),
                "-DescribeOnly",
            ],
            check=True,
            capture_output=True,
            text=True,
        )
        descriptor = json.loads(completed.stdout)

        self.assertEqual(descriptor["principal"]["logon_type"], "InteractiveToken")
        self.assertEqual(descriptor["principal"]["run_level"], "Limited")
        self.assertEqual(descriptor["settings"]["multiple_instances"], "IgnoreNew")
        self.assertEqual(descriptor["triggers"], ["AtLogOn", "Daily/PT5M"])
        self.assertTrue(descriptor["action"]["executable"].lower().endswith("wscript.exe"))
        self.assertIn("//B //NoLogo", descriptor["action"]["arguments"])
        self.assertIn(str(HIDDEN_LAUNCHER), descriptor["action"]["arguments"])
        self.assertIn("powershell.exe", descriptor["action"]["arguments"])
        self.assertIn("-WindowStyle Hidden", descriptor["action"]["arguments"])
        self.assertIn(f'"{executable}"', descriptor["action"]["arguments"])
        self.assertNotIn("KIS_", completed.stdout)

    def test_hidden_launcher_propagates_child_exit_code(self):
        completed = subprocess.run(
            [
                "wscript.exe",
                "//B",
                "//NoLogo",
                str(HIDDEN_LAUNCHER),
                "powershell.exe",
                "-NoProfile",
                "-NonInteractive",
                "-Command",
                "exit 7",
            ],
            check=False,
        )

        self.assertEqual(completed.returncode, 7)

    def test_build_copies_both_operational_scripts(self):
        script = (ROOT / "scripts" / "build_gui_exe.ps1").read_text(encoding="utf-8")

        self.assertIn("ensure_unattended_running.ps1", script)
        self.assertIn("install_unattended_task.ps1", script)
        self.assertIn("run_hidden.vbs", script)


if __name__ == "__main__":
    unittest.main()
