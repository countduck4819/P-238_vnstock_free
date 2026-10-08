import pandas as pd

from src.features.fundamentals import validate_point_in_time_frame


def test_point_in_time_validator_blocks_future_publication():
    frame = pd.DataFrame(
        {
            "symbol": ["AAA", "AAA"],
            "report_period": ["2024-03-31", "2024-03-31"],
            "publication_date": ["2024-04-20", "2024-06-20"],
            "date": ["2024-05-01", "2024-05-01"],
        }
    )
    report = validate_point_in_time_frame(frame)
    assert report["status"] == "blocked"
    assert report["future_publication_rows"] == 1
    assert report["duplicate_asof_key_rows"] == 2
