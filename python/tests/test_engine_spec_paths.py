from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from match_runner.uci_engine import EngineSpec


class EngineSpecPathTests(unittest.TestCase):
    def test_existing_executable_path_with_spaces_is_single_argument(self):
        with tempfile.TemporaryDirectory(prefix="Neuro Chess ") as tmp:
            exe = Path(tmp) / "stockfish windows x64.exe"
            exe.write_bytes(b"")
            spec = EngineSpec.from_command("Stockfish", str(exe))
            self.assertEqual(spec.command, (str(exe),))

    def test_quoted_existing_path_is_single_argument(self):
        with tempfile.TemporaryDirectory(prefix="Neuro Chess ") as tmp:
            exe = Path(tmp) / "engine.exe"
            exe.write_bytes(b"")
            spec = EngineSpec.from_command("Engine", f'"{exe}"')
            self.assertEqual(spec.command, (str(exe),))


if __name__ == "__main__":
    unittest.main()
