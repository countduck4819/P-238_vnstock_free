from pathlib import Path

from financial_ocr_mvp.text_pipeline.normalizer import digest
from financial_ocr_mvp.text_pipeline.run_normalization_bulk import should_normalize


def row(tmp_path: Path, **changes):
    raw = tmp_path / "data/ocr_annual_financials/raw.txt"
    raw.parent.mkdir(parents=True)
    raw.write_text("374.126.689.644\n", encoding="utf-8")

    normalized = tmp_path / "normalized.txt"
    normalized.write_text(raw.read_text(), encoding="utf-8")
    base = (
        "doc",
        "FPT",
        2022,
        "raw.txt",
        digest(raw.read_bytes()),
        1,
        True,
        "success",
        "txt_norm_v1",
        str(normalized),
        digest(normalized.read_bytes()),
    )
    values = list(base)
    names = [
        "document_id",
        "ticker",
        "year",
        "raw_rel",
        "raw_sha",
        "page_count",
        "has_table",
        "status",
        "version",
        "norm_path",
        "norm_sha",
    ]
    for key, value in changes.items():
        values[names.index(key)] = value
    return tuple(values)


def test_valid_success_skips(tmp_path):
    assert should_normalize(row(tmp_path), tmp_path)[0] is False


def test_warning_valid_skips(tmp_path):
    assert should_normalize(row(tmp_path, status="warning"), tmp_path)[0] is False


def test_missing_output_processes(tmp_path):
    assert should_normalize(
        row(tmp_path, norm_path=str(tmp_path / "missing")), tmp_path
    )[0] is True


def test_changed_raw_processes(tmp_path):
    assert should_normalize(row(tmp_path, raw_sha="bad"), tmp_path)[0] is True


def test_changed_version_processes(tmp_path):
    assert should_normalize(row(tmp_path, version="txt_norm_v2"), tmp_path)[0] is True


def test_changed_normalized_sha_processes(tmp_path):
    assert should_normalize(row(tmp_path, norm_sha="bad"), tmp_path)[0] is True


def test_failed_processes(tmp_path):
    assert should_normalize(row(tmp_path, status="failed"), tmp_path)[0] is True


def test_duplicate_not_canonical_is_filtered_by_query():
    pass
