import pandas as pd

from dmh.ingestion.datasets import load_dataset_config
from dmh.ingestion.reader import read_csv
from dmh.pipeline.cleaning import REJECT_REASON_COLUMN, clean, normalize


def test_demo_file_is_split_into_valid_and_rejected():
    config = load_dataset_config("demo_sales")
    df = normalize(read_csv("data/sample/demo_sales.csv"), config)

    result = clean(df, config)

    assert len(result.valid) + len(result.rejected) == len(df) == 20
    assert len(result.rejected) == 8
    assert result.report.score == 60.0
    # Types convertis pour PostgreSQL
    assert str(result.valid["order_id"].dtype) == "Int64"
    assert pd.api.types.is_datetime64_any_dtype(result.valid["order_date"])
    assert 8.9 in result.valid["unit_price"].tolist()  # "8,90" accepté
    # Normalisation : espaces retirés et e-mail en minuscules
    assert "nadia.chraibi@example.com" in result.valid["customer_email"].tolist()


def test_rejected_rows_keep_original_values_and_reason():
    config = load_dataset_config("demo_sales")
    result = clean(normalize(read_csv("data/sample/demo_sales.csv"), config), config)

    bad_price = result.rejected[result.rejected["order_id"] == "1009"].iloc[0]
    assert bad_price["unit_price"] == "abc"
    assert "unit_price : format float invalide" in bad_price[REJECT_REASON_COLUMN]
    assert bad_price["_source_line"] == 10


def test_rename_option_maps_csv_headers(tmp_path):
    (tmp_path / "r.yaml").write_text(
        "columns:\n  - {name: id, dtype: int}\ncleaning:\n  rename: {ID: id}\n"
    )
    config = load_dataset_config("r", directory=tmp_path)
    df = normalize(pd.DataFrame({"ID": ["7"]}, dtype="str"), config)
    assert clean(df, config).valid["id"].tolist() == [7]
