import tempfile
import unittest
from pathlib import Path

from nasdaq_auto_trader.ai_quant_lab import storage


class AIQuantStorageTests(unittest.TestCase):
    def test_safe_artifact_path_sanitizes_name_inside_base_directory(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            base = Path(temp_dir)

            path = storage.safe_artifact_path(base, "../bad name", ".json")

        self.assertEqual(path.name, "bad_name.json")

    def test_safe_artifact_path_raises_typed_error_when_suffix_escapes_base(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            base = Path(temp_dir).resolve()

            with self.assertRaises(storage.ArtifactPathEscapedBaseError) as context:
                storage.safe_artifact_path(base, "artifact", "/nested.json")

        self.assertEqual(str(context.exception), "artifact_path_escaped_base")
        self.assertEqual(context.exception.base, base)
        self.assertNotEqual(context.exception.attempted_path.parent, base)


if __name__ == "__main__":
    unittest.main()
