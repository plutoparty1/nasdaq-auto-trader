import os
import sys
import unittest
from unittest.mock import patch

from nasdaq_auto_trader.ai_quant_lab.insane_search_research import (
    CommandInsaneSearchRunner,
)


class AIQuantResearchCommandSecurityTests(unittest.TestCase):
    def test_research_command_does_not_inherit_broker_secret(self):
        script = (
            "import json, os; "
            "visible=os.getenv('KIS_APP_SECRET', 'missing'); "
            "print(json.dumps({'research_id':'r1','summary':visible,'sources':"
            "[{'source_id':'s1','title':'source','url':'https://example.test'}]}))"
        )
        with patch.dict(os.environ, {"KIS_APP_SECRET": "broker-secret"}):
            result = CommandInsaneSearchRunner(
                (sys.executable, "-c", script)
            ).run("query")

        self.assertTrue(result.usable)
        self.assertEqual(result.summary, "missing")

    def test_research_command_failure_does_not_persist_stderr(self):
        secret = "broker-secret-from-stderr"
        script = f"import sys; sys.stderr.write({secret!r}); sys.exit(1)"

        result = CommandInsaneSearchRunner(
            (sys.executable, "-c", script)
        ).run("query")

        self.assertFalse(result.usable)
        self.assertEqual(result.failure_reason, "insane_search_command_failed")
        self.assertNotIn(secret, result.failure_reason)


if __name__ == "__main__":
    unittest.main()
