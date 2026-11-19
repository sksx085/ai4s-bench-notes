#!/usr/bin/env python3
"""Validate a magnetic-moment submission using only the published test times."""

import argparse
import csv
import math
import re
from pathlib import Path


QUERY_HEADER = ("run_id", "point_id", "nominal_temperature_K", "elapsed_time_s")
PREDICTION_HEADER = ("run_id", "point_id", "moment_emu")
METHOD_HEADINGS = ("输入与预处理", "预测方法", "复现")
DECIMAL = re.compile(r"[+-]?(?:[0-9]+(?:\.[0-9]*)?|\.[0-9]+)(?:[eE][+-]?[0-9]+)?")
HEADING = re.compile(r"^ {0,3}(#{1,6})[ \t]+(.*)$")
FENCE = re.compile(r"^ {0,3}(`{3,}|~{3,})(.*)$")

PointKey = tuple[str, str]


def csv_rows(path: Path, header: tuple[str, ...]):
    with path.open(encoding="utf-8-sig", newline="") as handle:
        reader = csv.reader(handle, strict=True)
        try:
            if tuple(next(reader, [])) != header:
                raise ValueError(f"{path.name}: expected header {','.join(header)}")
            for row in reader:
                if len(row) != len(header):
                    raise ValueError(f"{path.name}:{reader.line_num}: expected {len(header)} columns")
                yield reader.line_num, row
        except csv.Error as error:
            raise ValueError(f"{path.name}:{reader.line_num}: malformed CSV: {error}") from error


def load_queries(path) -> dict[PointKey, dict[str, str]]:
    """Read published query rows by literal (run_id, point_id)."""
    path = Path(path)
    queries = {}
    for line, row in csv_rows(path, QUERY_HEADER):
        key = (row[0], row[1])
        if not all(key):
            raise ValueError(f"{path.name}:{line}: missing run_id or point_id")
        if key in queries:
            raise ValueError(f"{path.name}:{line}: duplicate sampling point {key!r}")
        queries[key] = dict(zip(QUERY_HEADER, row))
    if not queries:
        raise ValueError(f"{path.name}: no test times")
    return queries


def validate_method(path: Path) -> None:
    """Require a nonempty section for each heading in the submission contract."""
    sections = {}
    current = None
    fence = None
    for line in path.read_text(encoding="utf-8-sig").splitlines():
        fence_match = FENCE.match(line)
        if fence:
            if (
                fence_match
                and fence_match.group(1).startswith(fence)
                and not fence_match.group(2).strip()
            ):
                fence = None
                continue
        elif fence_match:
            fence = fence_match.group(1)
            continue
        else:
            heading = HEADING.match(line)
            if heading:
                level, title = heading.groups()
                if len(level) <= 2:
                    title = re.sub(r"[ \t]+#+[ \t]*$", "", title).strip()
                    current = title if len(level) == 2 and title in METHOD_HEADINGS else None
                    if current:
                        sections.setdefault(current, False)
                continue
        if current and line.strip():
            sections[current] = True

    for title in METHOD_HEADINGS:
        if title not in sections:
            raise ValueError(f"{path.name}: missing heading '## {title}'")
        if not sections[title]:
            raise ValueError(f"{path.name}: section '## {title}' is empty")


def load_submission(test_times_path, output_dir) -> dict[PointKey, float]:
    """Validate the submission and return one finite prediction per query key."""
    queries = load_queries(test_times_path)
    output_dir = Path(output_dir)
    path = output_dir / "predictions.csv"
    predictions = {}
    for line, row in csv_rows(path, PREDICTION_HEADER):
        key = (row[0], row[1])
        if key not in queries:
            raise ValueError(f"{path.name}:{line}: unknown sampling point {key!r}")
        if key in predictions:
            raise ValueError(f"{path.name}:{line}: duplicate sampling point {key!r}")
        value = row[2].strip()
        if not DECIMAL.fullmatch(value):
            raise ValueError(f"{path.name}:{line}: moment_emu must use decimal or scientific notation")
        moment = float(value)
        if not math.isfinite(moment):
            raise ValueError(f"{path.name}:{line}: moment_emu must be finite")
        predictions[key] = moment
    if len(predictions) != len(queries):
        example = next(key for key in queries if key not in predictions)
        raise ValueError(
            f"{path.name}: missing {len(queries) - len(predictions)} sampling points; "
            f"first missing point is {example!r}"
        )

    validate_method(output_dir / "method.md")
    return predictions


def main(argv=None) -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("test_times_csv", type=Path)
    parser.add_argument("output_dir", type=Path)
    args = parser.parse_args(argv)
    try:
        predictions = load_submission(args.test_times_csv, args.output_dir)
    except (OSError, ValueError) as error:
        parser.error(str(error))
    print(len(predictions))


if __name__ == "__main__":
    main()
