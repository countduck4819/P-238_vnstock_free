from __future__ import annotations

import argparse
import json
import os

import psycopg
from dotenv import load_dotenv

load_dotenv()


def query(ticker: str, year: int | None = None) -> dict[str, object]:
    with psycopg.connect(os.environ["DATABASE_URL"]) as conn:
        with conn.cursor() as cur:
            if year is not None:
                cur.execute("""SELECT document_available, canonical_document_id
                    FROM financial.data_coverage WHERE ticker=%s AND year=%s AND report_type='annual'""", (ticker, year))
                row = cur.fetchone()
                return {"ticker": ticker, "year": year, "available": bool(row and row[0]), "document_id": row[1] if row and row[0] else None}
            cur.execute("""SELECT year FROM financial.data_coverage
                WHERE ticker=%s AND report_type='annual' AND document_available ORDER BY year""", (ticker,))
            available = [row[0] for row in cur.fetchall()]
            if not available:
                return {"ticker": ticker, "available_years": [], "missing_years": [], "min_year": None, "max_year": None, "report_count": 0}
            years = list(range(min(available), max(available) + 1))
            cur.execute("SELECT COUNT(*) FROM financial.document_registry WHERE ticker=%s", (ticker,))
            return {"ticker": ticker, "available_years": available, "missing_years": [y for y in years if y not in available], "min_year": min(available), "max_year": max(available), "report_count": cur.fetchone()[0]}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("ticker")
    parser.add_argument("--year", type=int)
    args = parser.parse_args()
    print(json.dumps(query(args.ticker, args.year), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
