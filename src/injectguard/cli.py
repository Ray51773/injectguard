from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path
from typing import Iterable, List, Sequence

from injectguard import detect_container, scan
from injectguard.types import ScanResult, Signal, Verdict

LOGGER = logging.getLogger("injectguard")


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
        return _exit_code(results)
    if args.command == "explain":
        result = _scan_file(Path(args.path))
        sys.stdout.write(result.explain() + "\n")
        return _exit_code([result])
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
        LOGGER.warning("skipped_non_utf8_file", extra={"path": str(path)})
        return None
    except OSError as exc:
        LOGGER.warning("skipped_unreadable_file", extra={"path": str(path), "error": str(exc)})
        return None


def _scan_file(path: Path) -> ScanResult:
    content = path.read_text(encoding="utf-8")
    container = detect_container(str(path), content)
    return scan(content, container, source=str(path))


def _emit(results: List[ScanResult], fmt: str) -> None:
    if fmt == "json":
        payload = (
            results[0].to_dict()
            if len(results) == 1
            else [result.to_dict() for result in results]
        )
        sys.stdout.write(json.dumps(payload, indent=2, sort_keys=True) + "\n")
    elif fmt == "sarif":
        sys.stdout.write(json.dumps(_to_sarif(results), indent=2, sort_keys=True) + "\n")
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
    header_row = "  ".join(
        header.ljust(widths[index])
        for index, header in enumerate(headers)
    )
    sys.stdout.write(header_row + "\n")
    sys.stdout.write("  ".join("-" * width for width in widths) + "\n")
    for row in rows:
        sys.stdout.write(
            "  ".join(str(value).ljust(widths[index]) for index, value in enumerate(row)) + "\n"
        )


def _exit_code(results: Sequence[ScanResult]) -> int:
    if any(result.verdict is Verdict.INJECTION for result in results):
        return 2
    if any(result.verdict is Verdict.SUSPICIOUS for result in results):
        return 1
    return 0


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
        location["physicalLocation"]["region"] = {
            "charOffset": signal.span[0],
            "charLength": signal.span[1] - signal.span[0],
        }
    message = (
        f"{signal.name} score={signal.score:.2f} "
        f"weight={signal.weight:.2f}: {signal.excerpt}"
    )
    return {
        "ruleId": signal.name,
        "level": level,
        "message": {"text": message},
        "locations": [location],
    }


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
