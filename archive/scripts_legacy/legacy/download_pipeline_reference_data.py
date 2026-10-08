"""Download the non-equity inputs required by the Wave Ignition data pipeline."""

from __future__ import annotations

from datetime import date
from pathlib import Path

try:
    from vnstock_data import Market, Reference
except ImportError:
    from vnstock import Market, Reference

OUTPUT_DIR = Path("data/vnstock/reference")
START_DATE = "2000-01-01"


def main() -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    end_date = date.today().isoformat()

    market = Market()
    vnindex = market.index("VNINDEX").ohlcv(
        start=START_DATE,
        end=end_date,
        interval="1D",
    )
    if vnindex.empty:
        raise RuntimeError("VNINDEX OHLCV query returned no rows.")
    vnindex.to_csv(OUTPUT_DIR / "vnindex_ohlcv_1d.csv", index=False, encoding="utf-8-sig")

    industry_map = Reference().industry.sectors()
    if industry_map.empty:
        raise RuntimeError("Industry-map query returned no rows.")
    industry_map.to_csv(OUTPUT_DIR / "industry_map_icb.csv", index=False, encoding="utf-8-sig")

    print(f"VNINDEX rows: {len(vnindex):,}")
    print(f"Industry-map rows: {len(industry_map):,}")
    print(f"Output directory: {OUTPUT_DIR.resolve()}")


if __name__ == "__main__":
    main()
