import pytest

from dmh.ingestion.datasets import DatasetConfigError, list_datasets, load_dataset_config
from dmh.ingestion.reader import IngestionError, read_csv


def test_reads_semicolon_csv_with_bom_and_trims_values(tmp_path):
    path = tmp_path / "f.csv"
    path.write_bytes("﻿id;name\n1;  Alice \n2;\n".encode())

    df = read_csv(path)

    assert list(df.columns) == ["id", "name"]
    assert df.loc[0, "name"] == "Alice"
    assert df["name"].isna().tolist() == [False, True]


def test_reads_latin1_file(tmp_path):
    path = tmp_path / "f.csv"
    path.write_bytes("produit\nÉcran\n".encode("latin-1"))

    assert read_csv(path).loc[0, "produit"] == "Écran"


@pytest.mark.parametrize("content", [b"", b"a,,c\n1,2,3\n", b"a,a\n1,2\n"])
def test_rejects_empty_file_or_bad_header(tmp_path, content):
    path = tmp_path / "f.csv"
    path.write_bytes(content)
    with pytest.raises(IngestionError):
        read_csv(path)


def test_missing_file_raises(tmp_path):
    with pytest.raises(IngestionError):
        read_csv(tmp_path / "absent.csv")


def test_demo_config_is_valid():
    config = load_dataset_config("demo_sales")
    assert "demo_sales" in list_datasets()
    assert config.schema.column_names[0] == "order_id"
    assert config.cleaning.lowercase == ("customer_email",)


@pytest.mark.parametrize("name", ["../etc", "Sales", "drop table"])
def test_dataset_name_is_restricted(name):
    with pytest.raises(DatasetConfigError):
        load_dataset_config(name)


def test_unknown_dtype_is_rejected(tmp_path):
    (tmp_path / "x.yaml").write_text("columns:\n  - {name: a, dtype: money}\n")
    with pytest.raises(DatasetConfigError, match="type inconnu"):
        load_dataset_config("x", directory=tmp_path)
