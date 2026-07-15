from __future__ import annotations

import json
import unittest
from pathlib import Path

from scripts.evaluate_corpus import evaluate


class EfficacyTests(unittest.TestCase):
    def test_corpus_efficacy_meets_recorded_threshold(self) -> None:
        root = Path(__file__).resolve().parent
        report = evaluate(root / "corpus")
        threshold = json.loads((root / "efficacy_threshold.json").read_text(encoding="utf-8"))

        self.assertGreaterEqual(
            report["f1"],
            threshold["min_f1"],
            json.dumps(report, indent=2, sort_keys=True),
        )
        self.assertGreaterEqual(len(report["per_signal_contribution"]), 7)


if __name__ == "__main__":
    unittest.main()

