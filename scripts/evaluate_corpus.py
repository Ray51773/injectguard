from __future__ import annotations

import json
import sys
from collections import Counter
from pathlib import Path
from typing import Any

from injectguard import Verdict, detect_container, scan


def evaluate(corpus_dir: Path) -> dict[str, Any]:
    rows = []
    signal_counts: Counter[str] = Counter()
    true_positive = 0
    false_positive = 0
    true_negative = 0
    false_negative = 0

    for expected_malicious, directory in (
        (False, corpus_dir / "benign"),
        (True, corpus_dir / "malicious"),
    ):
        for path in sorted(directory.iterdir()):
            if not path.is_file():
                continue
            content = path.read_text(encoding="utf-8")
            container = detect_container(str(path), content)
            result = scan(content, container=container, source=str(path))
            predicted_malicious = result.verdict is not Verdict.CLEAN

            if expected_malicious and predicted_malicious:
                true_positive += 1
                for signal in result.signals:
                    signal_counts[signal.name] += 1
            elif expected_malicious:
                false_negative += 1
            elif predicted_malicious:
                false_positive += 1
            else:
                true_negative += 1

            rows.append(
                {
                    "path": str(path),
                    "expected": "malicious" if expected_malicious else "benign",
                    "predicted": "malicious" if predicted_malicious else "benign",
                    "verdict": result.verdict.value,
                    "risk": result.risk,
                    "signals": [signal.name for signal in result.signals],
                }
            )

    precision = _ratio(true_positive, true_positive + false_positive)
    recall = _ratio(true_positive, true_positive + false_negative)
    f1 = _ratio(2 * precision * recall, precision + recall)
    return {
        "precision": round(precision, 4),
        "recall": round(recall, 4),
        "f1": round(f1, 4),
        "counts": {
            "true_positive": true_positive,
            "false_positive": false_positive,
            "true_negative": true_negative,
            "false_negative": false_negative,
        },
        "per_signal_contribution": dict(sorted(signal_counts.items())),
        "rows": rows,
    }


def main(argv: list[str] | None = None) -> int:
    args = argv or sys.argv[1:]
    corpus_dir = Path(args[0]) if args else Path("tests/corpus")
    report = evaluate(corpus_dir)
    sys.stdout.write(json.dumps(report, indent=2, sort_keys=True) + "\n")
    return 0


def _ratio(numerator: float, denominator: float) -> float:
    if denominator == 0:
        return 0.0
    return numerator / denominator


if __name__ == "__main__":
    raise SystemExit(main())

