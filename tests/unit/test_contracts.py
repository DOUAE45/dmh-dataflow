from datetime import UTC, datetime, timedelta

from dmh.contracts import ColumnSpec, DatasetSchema, RunResult, RunStatus


def _run(**kwargs) -> RunResult:
    return RunResult(
        run_id="r1",
        dataset="demo_sales",
        source_file="demo_sales.csv",
        triggered_by="test",
        started_at=datetime(2026, 1, 1, tzinfo=UTC),
        **kwargs,
    )


def test_new_run_is_running_without_duration():
    run = _run()
    assert run.status is RunStatus.RUNNING
    assert run.duration_seconds is None


def test_duration_is_computed_when_finished():
    run = _run(finished_at=datetime(2026, 1, 1, tzinfo=UTC) + timedelta(seconds=12.5))
    assert run.duration_seconds == 12.5


def test_status_serializes_as_plain_string():
    assert str(RunStatus.SUCCESS) == "success"


def test_schema_lists_column_names_in_order():
    schema = DatasetSchema(
        name="demo_sales",
        columns=(ColumnSpec("order_id", "int", unique=True), ColumnSpec("amount", "float")),
    )
    assert schema.column_names == ["order_id", "amount"]
