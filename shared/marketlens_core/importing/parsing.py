"""File parsing for CSV, JSON and JSONL. Values are kept as the original strings."""

import csv
import io
import json
from dataclasses import dataclass, field
from pathlib import PurePath

FORMATS = {".csv": "csv", ".json": "json", ".jsonl": "jsonl", ".ndjson": "jsonl"}


class FileFormatError(ValueError):
    pass


@dataclass
class ParsedRow:
    number: int  # 1-based data row (CSV: excludes header; JSONL: line number)
    values: dict[str, str]
    problems: list[str] = field(default_factory=list)


@dataclass
class ParsedFile:
    format: str
    columns: list[str]
    rows: list[ParsedRow]


def detect_format(filename: str) -> str:
    fmt = FORMATS.get(PurePath(filename or "").suffix.lower())
    if not fmt:
        raise FileFormatError("Only CSV, JSON and JSONL files can be imported.")
    return fmt


def _decode(data: bytes) -> str:
    try:
        return data.decode("utf-8-sig")
    except UnicodeDecodeError:
        raise FileFormatError("The file is not UTF-8 text. Save it as UTF-8 and try again.") from None


def _scalar(value) -> str | None:
    """JSON value -> string; None for nested values."""
    if value is None:
        return ""
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float, str)):
        return str(value)
    return None


def _record(number: int, obj, columns: list[str]) -> ParsedRow:
    if not isinstance(obj, dict):
        return ParsedRow(number, {}, [f"record {number} is not an object with named fields"])
    values, problems = {}, []
    for key, raw in obj.items():
        key = str(key)
        if key not in columns:
            columns.append(key)
        text = _scalar(raw)
        if text is None:
            problems.append(f"field '{key}' holds a nested value; only flat records can be imported")
            text = ""
        values[key] = text
    return ParsedRow(number, values, problems)


def parse_file(data: bytes, fmt: str, max_rows: int) -> ParsedFile:
    text = _decode(data)
    rows: list[ParsedRow] = []
    columns: list[str] = []

    if fmt == "csv":
        reader = csv.reader(io.StringIO(text, newline=""))
        try:
            header = next(reader)
        except StopIteration:
            raise FileFormatError("The file is empty.") from None
        header = [h.strip() for h in header]
        if any(not h for h in header):
            raise FileFormatError("The header row has a blank column name.")
        dupes = sorted({h for h in header if header.count(h) > 1})
        if dupes:
            raise FileFormatError(f"The header names {', '.join(dupes)} more than once.")
        columns = header
        number = 0
        for values in reader:
            if not values or all(v == "" for v in values) and len(values) <= 1:
                continue  # blank line
            number += 1
            if number > max_rows:
                raise FileFormatError(f"The file has more than {max_rows} rows.")
            problems = []
            if len(values) != len(header):
                problems.append(f"row has {len(values)} values but the header has {len(header)} columns")
            rows.append(ParsedRow(number, dict(zip(header, values)), problems))

    elif fmt == "json":
        try:
            payload = json.loads(text)
        except json.JSONDecodeError as exc:
            raise FileFormatError(f"The file is not valid JSON (line {exc.lineno}).") from None
        if isinstance(payload, dict) and isinstance(payload.get("records"), list):
            payload = payload["records"]
        if not isinstance(payload, list):
            raise FileFormatError('A JSON file must contain a list of records (or {"records": [...]}).')
        if len(payload) > max_rows:
            raise FileFormatError(f"The file has more than {max_rows} rows.")
        rows = [_record(i, obj, columns) for i, obj in enumerate(payload, start=1)]

    elif fmt == "jsonl":
        for line_no, line in enumerate(text.splitlines(), start=1):
            if not line.strip():
                continue
            if len(rows) >= max_rows:
                raise FileFormatError(f"The file has more than {max_rows} rows.")
            try:
                obj = json.loads(line)
            except json.JSONDecodeError:
                rows.append(ParsedRow(line_no, {}, [f"line {line_no} is not valid JSON"]))
                continue
            rows.append(_record(line_no, obj, columns))
    else:
        raise FileFormatError("Only CSV, JSON and JSONL files can be imported.")

    if not rows:
        raise FileFormatError("The file has no data rows.")
    return ParsedFile(fmt, columns, rows)


def profile(parsed: ParsedFile, examples: int = 3) -> dict:
    """Per-column summary for the wizard's Profile step."""
    cols = []
    for c in parsed.columns:
        counts: dict[str, int] = {}
        blanks = 0
        for r in parsed.rows:
            v = r.values.get(c, "")
            if v.strip() == "":
                blanks += 1
            else:
                counts[v] = counts.get(v, 0) + 1
        top = sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))[:examples]
        cols.append(
            {
                "name": c,
                "blank": blanks,
                "distinct": len(counts),
                "examples": [v if len(v) <= 80 else v[:77] + "…" for v, _ in top],
            }
        )
    return {
        "format": parsed.format,
        "row_count": len(parsed.rows),
        "rows_with_problems": sum(1 for r in parsed.rows if r.problems),
        "columns": cols,
    }
