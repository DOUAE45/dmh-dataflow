import pandas as pd

from dmh.contracts import ColumnSpec, DatasetSchema
from dmh.quality.checks import assess_quality, check_rows

SCHEMA = DatasetSchema(
    name="t",
    columns=(
        ColumnSpec("id", "int", unique=True),
        ColumnSpec("day", "date"),
        ColumnSpec("amount", "float"),
        ColumnSpec("ok", "bool", required=False),
    ),
)


def _df(rows):
    return pd.DataFrame(rows, columns=["id", "day", "amount", "ok"], dtype="str")


def test_clean_data_scores_100():
    report = assess_quality(_df([["1", "2026-01-01", "3.5", "true"]]), SCHEMA)
    assert report.score == 100.0
    assert report.issues == []


def test_counts_missing_format_and_duplicates():
    df = _df(
        [
            ["1", "2026-01-01", "3.5", None],  # valide (ok facultatif)
            ["2", "01/01/2026", "1", "oui"],  # date au mauvais format
            ["3", "2026-01-02", None, "non"],  # montant manquant
            ["3", "2026-01-02", None, "non"],  # doublon exact
            ["1", "2026-01-03", "x", "true"],  # id répété + montant invalide
        ]
    )

    report = assess_quality(df, SCHEMA)

    assert report.rows_total == 5
    assert report.missing_by_column == {"id": 0, "day": 0, "amount": 2, "ok": 1}
    assert report.format_errors_by_column["day"] == 1
    assert report.format_errors_by_column["amount"] == 1
    assert report.duplicate_rows == 1
    checks = {(i.check, i.column) for i in report.issues}
    assert ("duplicate", "id") in checks
    assert ("missing_value", "ok") not in checks  # colonne facultative
    assert report.score == 20.0  # 1 ligne valide sur 5


def test_missing_required_column_rejects_every_row():
    df = pd.DataFrame({"id": ["1", "2"], "day": ["2026-01-01", "2026-01-02"]}, dtype="str")
    result = check_rows(df, SCHEMA)
    assert result.report.score == 0.0
    assert any(i.check == "missing_column" and i.column == "amount" for i in result.report.issues)
    assert not result.valid_mask.any()


def test_unexpected_column_is_reported_but_not_rejected():
    df = _df([["1", "2026-01-01", "3", "true"]]).assign(extra="x")
    report = assess_quality(df, SCHEMA)
    assert report.score == 100.0
    assert [i.check for i in report.issues] == ["unexpected_column"]


def test_empty_dataframe_scores_100():
    assert assess_quality(_df([]), SCHEMA).score == 100.0


def test_french_decimal_comma_is_accepted():
    report = assess_quality(_df([["1", "2026-01-01", "8,90", None]]), SCHEMA)
    assert report.format_errors_by_column["amount"] == 0
