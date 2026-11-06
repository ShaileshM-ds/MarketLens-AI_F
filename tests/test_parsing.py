import json

import pytest

from marketlens_core.importing.parsing import FileFormatError, detect_format, parse_file


def test_detect_format():
    assert detect_format("a.csv") == "csv"
    assert detect_format("a.JSON") == "json"
    assert detect_format("a.jsonl") == "jsonl"
    with pytest.raises(FileFormatError, match="CSV, JSON and JSONL"):
        detect_format("a.xlsx")


def test_csv_with_bom_and_original_values_preserved():
    data = "﻿product_id,price\nMCL0001, 1380 \n".encode("utf-8")
    parsed = parse_file(data, "csv", max_rows=10)
    assert parsed.columns == ["product_id", "price"]
    assert parsed.rows[0].values == {"product_id": "MCL0001", "price": " 1380 "}
    assert parsed.rows[0].number == 1


def test_csv_row_with_wrong_field_count_is_a_row_problem():
    parsed = parse_file(b"a,b\n1,2\n1,2,3\n", "csv", max_rows=10)
    assert parsed.rows[0].problems == []
    assert "3 values" in parsed.rows[1].problems[0]


def test_csv_duplicate_header_rejected():
    with pytest.raises(FileFormatError, match="more than once"):
        parse_file(b"a,a\n1,2\n", "csv", max_rows=10)


def test_non_utf8_rejected():
    with pytest.raises(FileFormatError, match="UTF-8"):
        parse_file("a\n\xe9\n".encode("latin-1"), "csv", max_rows=10)


def test_json_list_and_records_wrapper():
    rows = [{"product_id": "MCL0001", "price": 1380, "flag": True, "note": None}]
    for payload in (rows, {"records": rows}):
        parsed = parse_file(json.dumps(payload).encode(), "json", max_rows=10)
        assert parsed.rows[0].values == {"product_id": "MCL0001", "price": "1380", "flag": "true", "note": ""}


def test_json_must_be_a_list():
    with pytest.raises(FileFormatError, match="list of records"):
        parse_file(b'{"a": 1}', "json", max_rows=10)


def test_json_nested_value_is_a_row_problem():
    parsed = parse_file(json.dumps([{"a": {"b": 1}}]).encode(), "json", max_rows=10)
    assert "nested" in parsed.rows[0].problems[0]


def test_jsonl_bad_line_is_a_row_problem():
    parsed = parse_file(b'{"a": "1"}\nnot json\n\n{"a": "2"}\n', "jsonl", max_rows=10)
    # JSONL rows are numbered by file line (blank lines skipped) so they can be found in the file.
    assert [r.number for r in parsed.rows] == [1, 2, 4]
    assert parsed.rows[1].problems == ["line 2 is not valid JSON"]


def test_row_limit():
    with pytest.raises(FileFormatError, match="more than 2 rows"):
        parse_file(b"a\n1\n2\n3\n", "csv", max_rows=2)
