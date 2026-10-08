"""Simple read-only PostgreSQL CLI for Financial OCR MVP."""
from __future__ import annotations

import os
import re
import unicodedata
from pathlib import Path
from typing import Any

try:
    import psycopg
except ImportError as exc:  # pragma: no cover
    raise SystemExit('Install dependencies: pip install -r requirements.txt') from exc

try:
    from dotenv import load_dotenv
except ImportError:  # pragma: no cover
    load_dotenv = None

CONCEPT_ALIASES = {
    "revenue": ("revenue", "doanh thu", "doanh thu ban hang"),
    "gross_profit": ("gross_profit", "loi nhuan gop", "lợi nhuận gộp"),
    "financial_expense": ("financial_expense", "chi phi tai chinh", "chi phí tài chính"),
    "total_assets": ("total_assets", "tong tai san", "tổng tài sản"),
    "liabilities": ("liabilities", "no phai tra", "nợ phải trả"),
    "equity": ("equity", "von chu so huu", "vốn chủ sở hữu"),
    "basic_earnings_per_share": ("basic_earnings_per_share", "eps", "lai co ban tren co phieu", "lãi cơ bản trên cổ phiếu"),
    "profit_before_tax": ("profit_before_tax", "loi nhuan truoc thue", "lợi nhuận trước thuế"),
    "net_income": ("net_income", "loi nhuan sau thue", "lợi nhuận sau thuế"),
    "low_confidence": ("confidence thấp", "confidence thap", "độ tin cậy thấp", "low confidence"),
}


def normalize(text: str) -> str:
    value = unicodedata.normalize("NFKD", text.lower())
    value = "".join(ch for ch in value if not unicodedata.combining(ch))
    return re.sub(r"\s+", " ", value.replace("đ", "d")).strip()


def load_environment() -> None:
    root = Path(__file__).resolve().parent.parent
    if load_dotenv:
        load_dotenv(root / ".env")
    if not os.environ.get("DATABASE_URL"):
        env_path = root / ".env"
        if env_path.exists():
            for line in env_path.read_text(encoding="utf-8").splitlines():
                if line.startswith("DATABASE_URL="):
                    os.environ["DATABASE_URL"] = line.split("=", 1)[1].strip().strip('"').strip("'")
                    break


def detect_concept(question: str) -> str | None:
    normalized = normalize(question)
    for concept, aliases in CONCEPT_ALIASES.items():
        if any(normalize(alias) in normalized for alias in aliases):
            return concept
    return None


def detect_period(question: str) -> tuple[str | None, str | None]:
    normalized = normalize(question)
    year = re.search(r"\b(20\d{2})\b", normalized)
    quarter = re.search(r"(?:q|quy|quý)\s*([1-4])", normalized)
    return (year.group(1) if year else None, quarter.group(1) if quarter else None)


def detect_ticker(question: str) -> str | None:
    match = re.search(r"\b([A-Z]{2,6})\b", question)
    if match and match.group(1) not in {"Q", "VND", "EPS"}:
        return match.group(1)
    if "fpt" in normalize(question):
        return "FPT"
    return None


def source_text(source: dict[str, Any]) -> str:
    return (
        f"Trang {source.get('page', '?')}, "
        f"bảng {source.get('table', '?')}, "
        f"dòng {source.get('row', '?')}, "
        f"cột {source.get('column', '?')}"
    )


def query_facts(conn: Any, concept: str, year: str | None, quarter: str | None, ticker: str | None) -> list[dict[str, Any]]:
    clauses = ["f.concept = %s"]
    params: list[Any] = [concept]
    if year:
        clauses.append("d.report_year = %s")
        params.append(int(year))
    if quarter:
        clauses.append("d.quarter = %s")
        params.append(int(quarter))
        clauses.append("(f.period ILIKE %s OR f.period ILIKE %s)")
        params.extend([f"%QUÝ {quarter}%", f"%QUY {quarter}%"])
    if ticker:
        clauses.append("d.ticker = %s")
        params.append(ticker)
    if concept == "revenue":
        # Prefer the primary revenue row (usually code 10), not child details.
        clauses.append("NULLIF(f.code, '') IS NOT NULL")
    sql = f"""
        SELECT d.ticker, d.company_name, d.report_year, d.quarter,
               f.concept, f.metric, f.period, f.value, f.final_value,
               f.raw_value, f.candidate_value, f.confidence, f.status,
               f.verification_status, f.source
        FROM financial.financial_facts f
        JOIN financial.financial_documents d ON d.id = f.document_id
        WHERE {' AND '.join(clauses)}
        ORDER BY f.confidence DESC, f.status, f.fact_id
    """
    with conn.cursor() as cur:
        cur.execute(sql, params)
        columns = [item.name for item in cur.description]
        return [dict(zip(columns, row)) for row in cur.fetchall()]


def answer_low_confidence(conn: Any) -> None:
    with conn.cursor() as cur:
        cur.execute("""
            SELECT metric, concept, value, confidence, status, source
            FROM financial.financial_facts
            WHERE confidence < 0.70 OR status = 'needs_review'
            ORDER BY confidence, fact_id
            LIMIT 20
        """)
        rows = cur.fetchall()
    if not rows:
        print("Không tìm thấy fact confidence thấp hoặc needs_review.")
        return
    print(f"Có {len(rows)} fact confidence thấp/needs_review (tối đa 20):")
    for metric, concept, value, confidence, status, source in rows:
        print(f"- {metric}: {value or '[trống]'} | confidence={confidence:.3f} | {status} | {source_text(source)}")


def answer_sources(conn: Any) -> None:
    with conn.cursor() as cur:
        cur.execute("""
            SELECT DISTINCT source->>'page'
            FROM financial.financial_facts
            WHERE source->>'page' IS NOT NULL
            ORDER BY source->>'page'
        """)
        pages = [row[0] for row in cur.fetchall()]
    print("Các trang có dữ liệu: " + (", ".join(pages) if pages else "không có"))


def answer_question(conn: Any, question: str) -> None:
    concept = detect_concept(question)
    year, quarter = detect_period(question)
    ticker = detect_ticker(question)
    normalized = normalize(question)

    if concept == "low_confidence" or "confidence thap" in normalized or "trang nao" in normalized or "trang nào" in question.lower():
        if "trang" in normalized or "page" in normalized:
            answer_sources(conn)
        else:
            answer_low_confidence(conn)
        return
    if concept is None:
        print("Chưa nhận diện được metric/concept từ câu hỏi.")
        print("Hãy thử: doanh thu, lợi nhuận gộp, chi phí tài chính, EPS, lợi nhuận sau thuế.")
        return

    rows = query_facts(conn, concept, year, quarter, ticker)
    if not rows:
        print(f"Không tìm thấy dữ liệu cho concept={concept}, period={year or '[tất cả]'}.")
        print("Database hiện chưa có dữ liệu balance_sheet/cash_flow cho concept này nếu áp dụng.")
        return

    print(f"Kết quả cho {concept}:")
    for row in rows[:10]:
        value = row["value"] or row["final_value"] or "[trống]"
        print(f"- Ticker: {row['ticker'] or '[chưa có]'} | Company: {row['company_name'] or '[chưa có]'}")
        print(f"  Metric: {row['metric']}")
        print(f"  Giá trị: {value}")
        print(f"  Confidence: {row['confidence']:.3f}")
        print(f"  Status: {row['status']} ({row['verification_status']})")
        print(f"  Period: {row['period']} | Year: {row['report_year']} | Quarter: {row['quarter']}")
        print(f"  Source: {source_text(row['source'])}")
        if row["raw_value"] and row["candidate_value"]:
            print(f"  Raw: {row['raw_value']} | Candidate: {row['candidate_value']}")


def main() -> None:
    load_environment()
    database_url = os.environ.get("DATABASE_URL")
    if not database_url:
        raise SystemExit("DATABASE_URL chưa được cấu hình trong môi trường hoặc .env")
    print("Financial AI Assistant")
    print("Nhập 'quit' hoặc 'exit' để thoát.")
    try:
        with psycopg.connect(database_url, connect_timeout=5) as conn:
            while True:
                try:
                    question = input("\nQuestion: ").strip()
                except (EOFError, KeyboardInterrupt):
                    print()
                    break
                if question.lower() in {"quit", "exit"}:
                    break
                if question:
                    answer_question(conn, question)
    except psycopg.Error as exc:
        raise SystemExit(f"Không kết nối được PostgreSQL: {exc}") from exc


if __name__ == "__main__":
    main()
