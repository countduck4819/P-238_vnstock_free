"""
Điểm duy nhất python_data gọi thư viện vnstock (bản free/community).

Toàn bộ fetcher đi qua module này thay vì import vnstock trực tiếp, để:

- không còn phụ thuộc gói trả phí ``vnstock_data``;
- chọn nguồn dữ liệu (KBS/VCI) theo biến môi trường, tự fallback khi một
  nguồn lỗi hoặc trả rỗng;
- chuẩn hóa schema của bản free về đúng schema JSON mà NestJS/Next.js đang
  đọc (organ_name, icb_name3, news_title...);
- cache ngắn hạn các lời gọi tham chiếu (listing, ngành, VNINDEX) vì bản free
  bị giới hạn số request mỗi phút.

Các lớp dùng là API ổn định của vnstock 4.x: Listing, Quote, Company, Finance.
"""

from __future__ import annotations

import os
import threading
import time
from collections.abc import Callable, Iterable

import pandas as pd


# Nguồn mặc định: KBS là nguồn mặc định của vnstock 4 và không chặn IP cloud;
# VCI có phân ngành ICB đủ 4 cấp nên được ưu tiên cho dữ liệu ngành.
def _sources(env_name: str, default: str) -> list[str]:
    raw = os.environ.get(env_name, default)
    return [item.strip().upper() for item in raw.split(",") if item.strip()]


QUOTE_SOURCES = _sources("VNSTOCK_QUOTE_SOURCES", "KBS,VCI")
LISTING_SOURCES = _sources("VNSTOCK_LISTING_SOURCES", "KBS,VCI")
INDUSTRY_SOURCES = _sources("VNSTOCK_INDUSTRY_SOURCES", "VCI,KBS")
COMPANY_SOURCES = _sources("VNSTOCK_COMPANY_SOURCES", "KBS,VCI")
NEWS_SOURCES = _sources("VNSTOCK_NEWS_SOURCES", "VCI,KBS")
FINANCE_SOURCES = _sources("VNSTOCK_FINANCE_SOURCES", "KBS,VCI")

REFERENCE_CACHE_SECONDS = float(
    os.environ.get("VNSTOCK_REFERENCE_CACHE_SECONDS", str(6 * 3600))
)
INDEX_CACHE_SECONDS = float(
    os.environ.get("VNSTOCK_INDEX_CACHE_SECONDS", "600")
)

# Sàn theo định dạng TradingView.
_EXCHANGE_ALIASES = {
    "HSX": "HOSE",
    "HOSE": "HOSE",
    "HNX": "HNX",
    "XHNF": "HNX",
    "UPCOM": "UPCOM",
}

_cache: dict[str, tuple[float, object]] = {}
_cache_lock = threading.Lock()
_vnstock_lock = threading.Lock()
_vnstock_module = None


class VnstockUnavailableError(RuntimeError):
    """Mọi nguồn đều lỗi hoặc trả rỗng."""


def _vnstock():
    """Import lazy để server vẫn khởi động được khi vnstock chưa cài."""
    global _vnstock_module

    if _vnstock_module is None:
        with _vnstock_lock:
            if _vnstock_module is None:
                import vnstock

                _vnstock_module = vnstock

    return _vnstock_module


def _is_empty(result) -> bool:
    if result is None:
        return True

    if isinstance(result, (pd.DataFrame, pd.Series)):
        return result.empty

    return not result


def _first_success(
    label: str,
    sources: Iterable[str],
    call: Callable[[str], object],
):
    """Gọi lần lượt từng nguồn, trả kết quả không rỗng đầu tiên."""
    errors = []

    for source in sources:
        try:
            result = call(source)
        except (Exception, SystemExit) as exc:
            # vnai có thể raise SystemExit khi vượt quota; không để nó giết
            # worker thread của Flask.
            errors.append(f"{source}: {exc!r}")
            continue

        if not _is_empty(result):
            return result

        errors.append(f"{source}: rỗng")

    raise VnstockUnavailableError(f"{label} thất bại ({'; '.join(errors)})")


def _cached(key: str, ttl: float, loader: Callable[[], object]):
    now = time.time()

    with _cache_lock:
        hit = _cache.get(key)

        if hit and now - hit[0] < ttl:
            return hit[1].copy() if hasattr(hit[1], "copy") else hit[1]

    value = loader()

    with _cache_lock:
        _cache[key] = (time.time(), value)

    return value.copy() if hasattr(value, "copy") else value


# =========================
# GIÁ (OHLCV)
# =========================

def history(
    symbol: str,
    start: str,
    end: str,
    interval: str = "1D",
) -> pd.DataFrame:
    """OHLCV theo ngày, giá cổ phiếu tính theo nghìn đồng như vnstock."""
    symbol = symbol.upper().strip()

    def call(source):
        quote = _vnstock().Quote(symbol=symbol, source=source)
        return quote.history(start=start, end=end, interval=interval)

    return _first_success(f"Quote.history({symbol})", QUOTE_SOURCES, call)


def index_history(
    symbol: str,
    start: str,
    end: str,
    interval: str = "1D",
) -> pd.DataFrame:
    key = f"index:{symbol}:{start}:{end}:{interval}"
    return _cached(
        key,
        INDEX_CACHE_SECONDS,
        lambda: history(symbol, start, end, interval),
    )


# =========================
# DANH MỤC MÃ / NGÀNH
# =========================

def all_symbols() -> pd.DataFrame:
    """Cột: symbol, organ_name."""

    def call(source):
        df = _vnstock().Listing(source=source).all_symbols()
        if "organ_name" not in df.columns and "name" in df.columns:
            df = df.rename(columns={"name": "organ_name"})
        return df

    return _cached(
        "listing:all_symbols",
        REFERENCE_CACHE_SECONDS,
        lambda: _first_success("Listing.all_symbols", LISTING_SOURCES, call),
    )


def symbols_by_exchange() -> pd.DataFrame:
    """Cột tối thiểu: symbol, exchange (HOSE/HNX/UPCOM), type."""

    def call(source):
        df = _vnstock().Listing(source=source).symbols_by_exchange()
        if "exchange" not in df.columns and "board" in df.columns:
            df = df.rename(columns={"board": "exchange"})
        if "exchange" in df.columns:
            df = df.copy()
            df["exchange"] = (
                df["exchange"]
                .astype("string")
                .str.upper()
                .map(lambda value: _EXCHANGE_ALIASES.get(value, value))
            )
        return df

    return _cached(
        "listing:symbols_by_exchange",
        REFERENCE_CACHE_SECONDS,
        lambda: _first_success(
            "Listing.symbols_by_exchange", LISTING_SOURCES, call
        ),
    )


def _industries_wide_from_vci_long(df: pd.DataFrame) -> pd.DataFrame:
    """
    VCI free trả dạng dài (một dòng cho mỗi cấp ICB):
        symbol, organ_name, com_type_code, icb_level, icb_code, icb_name
    Chuyển về dạng rộng giống schema cũ:
        symbol, organ_name, icb_name2..4, com_type_code, icb_code1..4
    """
    base = (
        df[["symbol", "organ_name", "com_type_code"]]
        .drop_duplicates("symbol")
        .set_index("symbol")
    )

    levels = df.dropna(subset=["icb_level"]).copy()
    levels["icb_level"] = levels["icb_level"].astype(int)

    names = levels.pivot_table(
        index="symbol",
        columns="icb_level",
        values="icb_name",
        aggfunc="first",
    )
    names.columns = [f"icb_name{level}" for level in names.columns]

    codes = levels.pivot_table(
        index="symbol",
        columns="icb_level",
        values="icb_code",
        aggfunc="first",
    )
    codes.columns = [f"icb_code{level}" for level in codes.columns]

    wide = base.join(names).join(codes).reset_index()

    ordered = [
        "symbol",
        "organ_name",
        "icb_name3",
        "icb_name2",
        "icb_name4",
        "com_type_code",
        "icb_code1",
        "icb_code2",
        "icb_code3",
        "icb_code4",
    ]
    for column in ordered:
        if column not in wide.columns:
            wide[column] = None

    return wide[ordered + [c for c in wide.columns if c not in ordered]]


def _industries_wide_from_kbs(df: pd.DataFrame) -> pd.DataFrame:
    """KBS free dùng bộ ngành riêng: symbol, industry_code, industry_name."""
    names = {}

    try:
        names_df = all_symbols()
        names = dict(zip(names_df["symbol"], names_df["organ_name"]))
    except Exception:
        pass

    wide = df.drop_duplicates("symbol").copy()
    wide["organ_name"] = wide["symbol"].map(names)
    wide["icb_name3"] = wide["industry_name"]
    wide["icb_name2"] = wide["industry_name"]
    wide["icb_name4"] = wide["industry_name"]
    wide["com_type_code"] = None
    wide["icb_code1"] = None
    wide["icb_code2"] = None
    wide["icb_code3"] = wide["industry_code"].astype("string")
    wide["icb_code4"] = None

    return wide[
        [
            "symbol",
            "organ_name",
            "icb_name3",
            "icb_name2",
            "icb_name4",
            "com_type_code",
            "icb_code1",
            "icb_code2",
            "icb_code3",
            "icb_code4",
        ]
    ]


def symbols_by_industries() -> pd.DataFrame:
    """Danh sách mã kèm phân ngành, theo schema rộng cũ (icb_name3...)."""

    def call(source):
        listing = _vnstock().Listing(source=source)
        df = listing.symbols_by_industries(lang="vi")

        if df is None or df.empty:
            return df

        if "icb_level" in df.columns:
            return _industries_wide_from_vci_long(df)

        if "industry_name" in df.columns:
            return _industries_wide_from_kbs(df)

        # Schema rộng sẵn (phòng khi nguồn đổi lại).
        return df

    return _cached(
        "listing:symbols_by_industries",
        REFERENCE_CACHE_SECONDS,
        lambda: _first_success(
            "Listing.symbols_by_industries", INDUSTRY_SOURCES, call
        ),
    )


def industry_names() -> list[str]:
    """Tên ngành ICB (tiếng Việt), đã sắp xếp."""

    def call(source):
        df = _vnstock().Listing(source=source).industries_icb()

        if df is None or df.empty:
            return []

        for column in ("icb_name", "industry_name", "name"):
            if column in df.columns:
                return sorted(
                    {
                        str(value).strip()
                        for value in df[column].dropna()
                        if str(value).strip()
                    }
                )

        return []

    def load():
        try:
            return _first_success(
                "Listing.industries_icb", INDUSTRY_SOURCES, call
            )
        except VnstockUnavailableError:
            # Fallback: lấy tên ngành từ danh sách mã theo ngành.
            df = symbols_by_industries()
            values = set()
            for column in ("icb_name2", "icb_name3", "icb_name4"):
                if column in df.columns:
                    values.update(
                        str(v).strip() for v in df[column].dropna() if str(v).strip()
                    )
            if not values:
                raise
            return sorted(values)

    return _cached("listing:industry_names", REFERENCE_CACHE_SECONDS, load)


# =========================
# DOANH NGHIỆP
# =========================

def company_overview(symbol: str) -> dict:
    """Thông tin hồ sơ (outstanding_shares, charter_capital, exchange...)."""
    symbol = symbol.upper().strip()

    def call(source):
        df = _vnstock().Company(symbol=symbol, source=source).overview()
        if df is None or df.empty:
            return {}
        return df.iloc[0].to_dict()

    return _first_success(
        f"Company.overview({symbol})", COMPANY_SOURCES, call
    )


# Bản free mỗi nguồn đặt tên cột tin tức khác nhau; gom về một schema.
_NEWS_COLUMN_ALIASES = {
    "id": ("news_id", "id", "article_id"),
    "title": ("news_title", "title", "head", "headline"),
    "summary": (
        "news_short_content",
        "news_sub_title",
        "summary",
        "sapo",
        "short_content",
        "description",
    ),
    "content": ("news_full_content", "content", "body", "full_content"),
    "image_url": (
        "news_image_url",
        "image_url",
        "news_small_image_url",
        "image",
        "thumbnail",
    ),
    "url": ("news_source_link", "url", "link", "source_link"),
    "source": ("news_source", "source", "source_name"),
    "category": ("news_category_code", "category", "category_name"),
    "publish_time": (
        "public_date",
        "publish_time",
        "published_at",
        "publish_date",
        "date",
        "created_at",
    ),
}


def _normalize_news(df: pd.DataFrame) -> pd.DataFrame:
    result = pd.DataFrame(index=df.index)

    for target, aliases in _NEWS_COLUMN_ALIASES.items():
        column = next((name for name in aliases if name in df.columns), None)
        result[target] = df[column] if column else None

    return result.reset_index(drop=True)


def company_news(symbol: str, limit: int = 50) -> pd.DataFrame:
    """
    Tin tức doanh nghiệp, cột: id, title, summary, content, image_url,
    url, source, category, publish_time.
    """
    symbol = symbol.upper().strip()

    def call(source):
        company = _vnstock().Company(symbol=symbol, source=source)

        if source == "KBS":
            df = company.news(page=1, page_size=limit)
        else:
            df = company.news()

        if df is None or df.empty:
            return df

        return _normalize_news(df).head(limit)

    return _first_success(f"Company.news({symbol})", NEWS_SOURCES, call)


# =========================
# CHỈ SỐ TÀI CHÍNH
# =========================

def financial_ratio(symbol: str, period: str = "quarter") -> pd.DataFrame:
    """
    Bảng chỉ số tài chính.

    KBS trả dạng rộng (item, item_id, 2026-Q1, 2025-Q4...), bản free chỉ có
    vài kỳ gần nhất. VCI trả mỗi dòng một kỳ; finance_fetcher xử lý cả hai.
    """
    symbol = symbol.upper().strip()

    def call(source):
        finance = _vnstock().Finance(symbol=symbol, source=source, period=period)

        if source == "VCI":
            return finance.ratio(period=period, lang="en", dropna=False)

        return finance.ratio(period=period)

    return _first_success(f"Finance.ratio({symbol})", FINANCE_SOURCES, call)
