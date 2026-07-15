from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Iterable, List, Sequence

from injectguard import detect_container, scan
from injectguard.types import ScanResult, Signal, Verdict


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="injectguard")
    subparsers = parser.add_subparsers(dest="command", required=True)

    scan_parser = subparsers.add_parser("scan", help="scan a file, directory, or stdin")
    scan_parser.add_argument("path", help="path to scan, or '-' for stdin")
    scan_parser.add_argument("--recursive", action="store_true", help="walk a directory tree")
    scan_parser.add_argument("--format", choices=("json", "table", "sarif"), default="table")

    explain_parser = subparsers.add_parser("explain", help="show a verbose signal breakdown")
    explain_parser.add_argument("path", help="path to explain")

    args = parser.parse_args(argv)
    if args.command == "scan":
        results = list(_scan_paths(args.path, recursive=args.recursive))
        _emit(results, args.format)
        return 1 if any(result.verdict is Verdict.INJECTION for result in results) else 0
    if args.command == "explain":
        result = _scan_file(Path(args.path))
        print(result.explain())
        return 1 if result.verdict is Verdict.INJECTION else 0
    return 2


def _scan_paths(path_arg: str, recursive: bool) -> Iterable[ScanResult]:
    if path_arg == "-":
        content = sys.stdin.read()
        container = detect_container(None, content)
        yield scan(content, container, source="<stdin>")
        return

    path = Path(path_arg)
    if path.is_dir():
        if not recursive:
            raise SystemExit("directory scans require --recursive")
        for file_path in sorted(path.rglob("*")):
            if file_path.is_file():
                result = _try_scan_file(file_path)
                if result is not None:
                    yield result
        return

    yield _scan_file(path)


def _try_scan_file(path: Path) -> ScanResult | None:
    try:
        return _scan_file(path)
    except UnicodeDecodeError:
        return None
    except OSError as exc:
        print(f"injectguard: skipped {path}: {exc}", file=sys.stderr)
        return None


def _scan_file(path: Path) -> ScanResult:
    content = path.read_text(encoding="utf-8")
    container = detect_container(str(path), content)
    return scan(content, container, source=str(path))


def _emit(results: List[ScanResult], fmt: str) -> None:
    if fmt == "json":
        payload = results[0].to_dict() if len(results) == 1 else [result.to_dict() for result in results]
        print(json.dumps(payload, indent=2, sort_keys=True))
    elif fmt == "sarif":
        print(json.dumps(_to_sarif(results), indent=2, sort_keys=True))
    else:
        _emit_table(results)


def _emit_table(results: List[ScanResult]) -> None:
    rows = [
        (
            result.source or "<stdin>",
            result.container.value,
            result.verdict.value,
            f"{result.risk:.2f}",
            ", ".join(signal.name for signal in result.signals[:3]) or "-",
        )
        for result in results
    ]
    headers = ("SOURCE", "CONTAINER", "VERDICT", "RISK", "TOP SIGNALS")
    widths = [
        max(len(str(row[index])) for row in rows + [headers])
        for index in range(len(headers))
    ]
    print("  ".join(header.ljust(widths[index]) for index, header in enumerate(headers)))
    print("  ".join("-" * width for width in widths))
    for row in rows:
        print("  ".join(str(value).ljust(widths[index]) for index, value in enumerate(row)))


def _to_sarif(results: List[ScanResult]) -> dict:
    rules = {}
    sarif_results = []
    for result in results:
        for signal in result.signals:
            rules[signal.name] = {
                "id": signal.name,
                "name": signal.name,
                "shortDescription": {"text": signal.details or signal.name},
            }
            sarif_results.append(_sarif_result(result, signal))

    return {
        "$schema": "https://json.schemastore.org/sarif-2.1.0.json",
        "version": "2.1.0",
        "runs": [
            {
                "tool": {
                    "driver": {
                        "name": "injectguard",
                        "rules": list(rules.values()),
                    }
                },
                "results": sarif_results,
            }
        ],
    }


def _sarif_result(result: ScanResult, signal: Signal) -> dict:
    level = "error" if result.verdict is Verdict.INJECTION else "warning"
    location = {
        "physicalLocation": {
            "artifactLocation": {"uri": result.source or "<stdin>"},
        }
    }
    if signal.span:
        location["physicalLocation"]["region"] = {"charOffset": signal.span[0], "charLength": signal.span[1] - signal.span[0]}
    return {
        "ruleId": signal.name,
        "level": level,
        "message": {
            "text": f"{signal.name} score={signal.score:.2f} weight={signal.weight:.2f}: {signal.excerpt}",
        },
        "locations": [location],
    }


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())

