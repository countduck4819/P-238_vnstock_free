from vnstock_data import Reference, Fundamental
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from difflib import SequenceMatcher
from urllib.parse import quote, unquote

import os
import time
import json
import traceback
import pandas as pd
import re
import tempfile
import unicodedata
import threading
import multiprocessing as mp

from core.paths import data_path


# =========================
# CONFIG
# =========================

_last_call = 0
_request_rate_lock = threading.Lock()
_symbol_locks = {}
_symbol_locks_guard = threading.Lock()
_symbol_flights = {}
_pdf_flights = set()
_pdf_flights_guard = threading.Lock()
_upstream_slots = threading.BoundedSemaphore(
    int(os.environ.get("NEWS_MAX_UPSTREAM_REQUESTS", "8"))
)

NEWS_REQUEST_DELAY_SECONDS = float(
    os.environ.get("NEWS_REQUEST_DELAY_SECONDS", "0.5")
)

NEWS_REQUEST_TIMEOUT_SECONDS = float(
    os.environ.get("NEWS_REQUEST_TIMEOUT_SECONDS", "110")
)
NEWS_SLOT_TIMEOUT_SECONDS = float(
    os.environ.get("NEWS_SLOT_TIMEOUT_SECONDS", "30")
)
NEWS_UPSTREAM_CALL_TIMEOUT_SECONDS = float(
    os.environ.get("NEWS_UPSTREAM_CALL_TIMEOUT_SECONDS", "70")
)
FILING_CACHE_TTL_HOURS = float(
    os.environ.get("NEWS_FILING_CACHE_TTL_HOURS", "24")
)

VN_TZ = ZoneInfo("Asia/Ho_Chi_Minh")

MAX_SLUG_LEN = 80

# Pool news để DB có dữ liệu phân trang.
# Frontend vẫn lấy 10 bài/lần từ NestJS.
NEWS_LOOKBACK_DAYS = 90
NEWS_LIMIT = 50

# Dùng để cache cũ 2-3 bài tự refresh 1 lần.
CACHE_VERSION = 3

# News v2 và v3 dùng cùng schema; v3 chỉ giảm pool từ 300 xuống 100 bài.
# Cho phép trả cache v2 ngay để deploy mới không bắt mọi symbol fetch lại
# gần một phút. Worker nền sẽ tự nâng file lên v3.
USABLE_CACHE_VERSIONS = {2, CACHE_VERSION}

CACHE_DIR = data_path("news")
os.makedirs(CACHE_DIR, exist_ok=True)


class NewsFetchTimeoutError(TimeoutError):
    pass


# =========================
# CACHE
# =========================

def save_json(filename, data):
    path = os.path.join(CACHE_DIR, filename)

    # Ghi file tạm cùng thư mục rồi replace nguyên tử để NestJS không bao giờ
    # đọc trúng JSON đang được ghi dở.
    temp_path = None

    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=CACHE_DIR,
            prefix=f".{filename}.",
            suffix=".tmp",
            delete=False,
        ) as temp_file:
            temp_path = temp_file.name
            json.dump(
                data,
                temp_file,
                ensure_ascii=False,
                indent=2,
            )
            temp_file.flush()
            os.fsync(temp_file.fileno())

        os.replace(temp_path, path)
    finally:
        if temp_path and os.path.exists(temp_path):
            os.unlink(temp_path)

    print(f"💾 Saved {filename} → {path}")


def load_json(filename):
    path = os.path.join(CACHE_DIR, filename)

    if not os.path.exists(path):
        return None

    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)

    except Exception as e:
        print(f"⚠️ Lỗi đọc cache {filename}: {e}")
        return None


# =========================
# HELPERS
# =========================

def _safe_text(value):
    if value is None:
        return ""

    try:
        if pd.isna(value):
            return ""
    except Exception:
        pass

    text = str(value).strip()

    if text.lower() in {
        "none",
        "null",
        "nan",
        "<na>",
        "nat",
    }:
        return ""

    return text


def _safe_date(x):
    if x is None:
        return None

    try:
        if pd.isna(x):
            return None
    except Exception:
        pass

    try:
        if isinstance(x, (int, float)):
            if x > 1e12:
                x = x / 1000

            dt = datetime.fromtimestamp(x)

            if dt.year < 2000:
                return None

            return dt.strftime("%Y-%m-%d %H:%M:%S")

        if hasattr(x, "strftime"):
            return x.strftime("%Y-%m-%d %H:%M:%S")

        s = str(x).strip()

        if not s:
            return None

        if s.isdigit():
            return _safe_date(float(s))

        dt = pd.to_datetime(
            s,
            errors="coerce",
        )

        if pd.isna(dt) or dt.year < 2000:
            return None

        return dt.strftime("%Y-%m-%d %H:%M:%S")

    except Exception:
        return None


def slugify(text: str):
    if not text:
        return ""

    text = unicodedata.normalize(
        "NFD",
        text,
    )

    text = (
        text
        .encode("ascii", "ignore")
        .decode("utf-8")
    )

    text = re.sub(
        r"[^a-zA-Z0-9]+",
        "-",
        text,
    )

    return text.strip("-").lower()


def _pace_upstream_request():
    global _last_call

    # Chỉ tuần tự hóa thời điểm bắt đầu request. Phần gọi upstream vẫn được
    # chạy đồng thời theo giới hạn của _upstream_slots.
    with _request_rate_lock:
        now = time.time()
        wait_time = NEWS_REQUEST_DELAY_SECONDS - (now - _last_call)

        if wait_time > 0:
            time.sleep(wait_time)

        _last_call = time.time()


def _subprocess_call_entry(queue, func, args, kwargs):
    """Chạy một lời gọi upstream trong process riêng để có thể terminate thật."""
    try:
        result = func(*args, **kwargs)
        queue.put(("ok", result))
    except BaseException as exc:
        queue.put(("error", repr(exc)))


def _call_with_hard_timeout(func, *args, timeout=None, **kwargs):
    """
    Chạy func trong process riêng.

    Nếu quá timeout thì terminate process con để worker hiện tại có thể thoát
    và nhả semaphore slot trong finally.
    """
    if timeout is None:
        timeout = NEWS_UPSTREAM_CALL_TIMEOUT_SECONDS

    # VPS Linux: dùng fork để tránh phải khởi tạo lại toàn bộ Flask app.
    ctx = mp.get_context("fork")
    queue = ctx.Queue(maxsize=1)
    proc = ctx.Process(
        target=_subprocess_call_entry,
        args=(queue, func, args, kwargs),
        daemon=True,
    )

    proc.start()
    proc.join(timeout)

    if proc.is_alive():
        proc.terminate()
        proc.join(5)

        if proc.is_alive():
            proc.kill()
            proc.join(5)

        queue.close()
        queue.join_thread()
        raise TimeoutError(f"Upstream call quá {timeout:g}s")

    if queue.empty():
        exit_code = proc.exitcode
        queue.close()
        queue.join_thread()
        raise RuntimeError(
            f"Upstream process kết thúc bất thường, exitcode={exit_code}"
        )

    status, payload = queue.get()
    queue.close()
    queue.join_thread()

    if status == "error":
        raise RuntimeError(payload)

    return payload


def _vnstock_news_call(symbol, limit):
    ref = Reference()
    return (
        ref
        .company(symbol)
        .news(
            length=NEWS_LOOKBACK_DAYS,
            mode="detail",
            limit=limit,
        )
    )


def _vnstock_filing_call(symbol):
    fun = Fundamental()
    return (
        fun
        .equity(symbol)
        .filing()
    )


def _get_symbol_lock(symbol: str):
    symbol = symbol.upper().strip()

    with _symbol_locks_guard:
        lock = _symbol_locks.get(symbol)

        if lock is None:
            lock = threading.Lock()
            _symbol_locks[symbol] = lock

        return lock


def _now_vn():
    return datetime.now(VN_TZ)


def _need_refresh(cached):
    if not cached:
        return True

    if cached.get("cache_version") != CACHE_VERSION:
        return True

    last_update = cached.get("updated_at")

    if not last_update:
        return True

    now = _now_vn()
    today = now.strftime("%Y-%m-%d")

    return (
        today > str(last_update)[:10]
        and now.hour >= 17
    )


def _cache_is_usable(cached):
    """Cache đúng schema vẫn có thể trả ngay trong lúc refresh nền."""
    return bool(
        cached
        and cached.get("cache_version") in USABLE_CACHE_VERSIONS
        and isinstance(cached.get("data"), list)
        and cached.get("data")
    )


# =========================
# PDF
# =========================

def _normalize_match_text(value):
    text = _safe_text(value)

    if not text:
        return ""

    text = slugify(text)
    text = text.replace("-", " ")

    # 06 tháng -> 6 tháng
    text = re.sub(
        r"\b0+(\d+)\b",
        r"\1",
        text,
    )

    return re.sub(
        r"\s+",
        " ",
        text,
    ).strip()


def _normalize_pdf_url(url):
    url = _safe_text(url)

    if not url:
        return ""

    # Vietstock có một số URL cũ là http.
    if url.startswith(
        "http://static2.vietstock.vn/"
    ):
        url = (
            "https://"
            + url[len("http://"):]
        )

    # Encode khoảng trắng:
    # QUY 2 -> QUY%202
    return quote(
        url,
        safe=":/?&=%#",
    )


def _extract_pdf_urls(content):
    content = _safe_text(content)

    if not content:
        return []

    matches = re.findall(
        r'https?://[^\s"\'<>]+\.pdf'
        r'(?:\?[^\s"\'<>]*)?',
        content,
        flags=re.IGNORECASE,
    )

    result = []

    for url in matches:
        url = url.rstrip(
            ".,;)]}"
        )

        url = _normalize_pdf_url(url)

        if url and url not in result:
            result.append(url)

    return result


def _has_unresolved_pdf(cached):
    if not isinstance(cached, dict):
        return False

    for item in cached.get("data") or []:
        if not isinstance(item, dict):
            continue

        content = _safe_text(item.get("news_full_content"))

        if (
            ".pdf" in content.lower()
            and not _extract_pdf_urls(content)
        ):
            return True

    return False


def _filing_cache_is_fresh(cached):
    if not isinstance(cached, dict):
        return False

    if not isinstance(cached.get("data"), list):
        return False

    updated_at = _safe_text(cached.get("updated_at"))

    if not updated_at:
        return False

    try:
        updated = datetime.strptime(
            updated_at,
            "%Y-%m-%d %H:%M:%S",
        ).replace(tzinfo=VN_TZ)
    except ValueError:
        return False

    return (
        _now_vn() - updated
        < timedelta(hours=FILING_CACHE_TTL_HOURS)
    )


def _fetch_filings(symbol):
    """
    Lấy toàn bộ filing của doanh nghiệp.
    Không truyền doc_type => lấy tất cả.
    """

    cache_file = f"{symbol}_filings.json"
    cached = load_json(cache_file)

    if _filing_cache_is_fresh(cached):
        print(f"📄 Filings {symbol}: dùng cache")
        return cached["data"]

    try:
        _pace_upstream_request()

        print(
            f"📄 Fetching filings for {symbol}"
        )

        df = _call_with_hard_timeout(
            _vnstock_filing_call,
            symbol,
            timeout=NEWS_UPSTREAM_CALL_TIMEOUT_SECONDS,
        )

        if df is None or df.empty:
            print(
                f"ℹ️ Không có filing cho {symbol}"
            )
            return []

        print(
            f"✅ Filings {symbol}: "
            f"{len(df)} records"
        )

        records = [
            {
                "doc_url": _safe_text(row.get("doc_url")),
                "doc_title": _safe_text(row.get("doc_title")),
                "doc_name": _safe_text(row.get("doc_name")),
            }
            for _, row in df.iterrows()
        ]

        save_json(
            cache_file,
            {
                "symbol": symbol,
                "data": records,
                "updated_at": _now_vn().strftime(
                    "%Y-%m-%d %H:%M:%S"
                ),
                "cache_version": 1,
            },
        )

        return records

    except Exception as e:
        print(
            f"⚠️ Không lấy được filing "
            f"{symbol}: {e}"
        )

        if isinstance(cached, dict):
            return cached.get("data") or []

        return []


def _find_pdf_urls(
    title,
    content,
    filings,
):
    """
    1. Nếu news đã có URL PDF trực tiếp
       => dùng luôn.

    2. Nếu chưa có
       => match title news với doc_title/doc_name
          trong filing().
    """

    direct_urls = _extract_pdf_urls(
        content
    )

    if direct_urls:
        return direct_urls

    # Mot so nguon chi dua ten file vao noi dung thay vi URL day du.
    content_pdf_names = {
        _normalize_match_text(name)
        for name in re.findall(
            r"[^\s\"'<>/\\]+\.pdf",
            _safe_text(content),
            flags=re.IGNORECASE,
        )
    }

    for filing in filings:
        doc_url = _normalize_pdf_url(
            filing.get("doc_url")
        )

        if not doc_url:
            continue

        doc_filename = unquote(
            doc_url.split("?", 1)[0].rsplit("/", 1)[-1]
        )

        if (
            _normalize_match_text(doc_filename)
            in content_pdf_names
        ):
            return [doc_url]

    news_text = _normalize_match_text(
        title
    )

    if not news_text:
        return []

    news_years = set(
        re.findall(
            r"\b20\d{2}\b",
            news_text,
        )
    )

    best_url = ""
    best_score = 0.0

    for filing in filings:
        doc_url = _normalize_pdf_url(
            filing.get("doc_url")
        )

        if not doc_url:
            continue

        # Chỉ lấy PDF.
        if not (
            doc_url
            .lower()
            .split("?")[0]
            .endswith(".pdf")
        ):
            continue

        doc_title = (
            filing.get("doc_title")
            or filing.get("doc_name")
            or ""
        )

        doc_text = _normalize_match_text(
            doc_title
        )

        if not doc_text:
            continue

        # =========================
        # KHÔNG MATCH NHẦM NĂM
        # =========================

        doc_years = set(
            re.findall(
                r"\b20\d{2}\b",
                doc_text,
            )
        )

        if (
            news_years
            and doc_years
            and news_years.isdisjoint(
                doc_years
            )
        ):
            continue

        # =========================
        # TOKEN MATCH
        # =========================

        news_tokens = set(
            news_text.split()
        )

        doc_tokens = set(
            doc_text.split()
        )

        if not doc_tokens:
            continue

        common_tokens = (
            news_tokens
            & doc_tokens
        )

        coverage = (
            len(common_tokens)
            / len(doc_tokens)
        )

        similarity = SequenceMatcher(
            None,
            news_text,
            doc_text,
        ).ratio()

        score = (
            coverage * 0.65
            + similarity * 0.35
        )

        # Trường hợp rất gần nhau:
        #
        # News:
        # Báo cáo tình hình quản trị công ty
        # 06 tháng đầu năm 2026
        #
        # Filing:
        # Báo cáo tình hình quản trị
        # 6 tháng đầu năm 2026

        if doc_text in news_text:
            score += 0.1

        if score > best_score:
            best_score = score
            best_url = doc_url

    # Không đủ giống thì bỏ,
    # tránh gắn nhầm PDF.
    if (
        best_url
        and best_score >= 0.62
    ):
        return [best_url]

    return []


def _append_pdf_links(
    content,
    pdf_urls,
):
    content = _safe_text(content)

    if not pdf_urls:
        return content

    links = []

    for index, url in enumerate(
        pdf_urls,
        start=1,
    ):
        url = _normalize_pdf_url(
            url
        )

        if not url:
            continue

        # Nếu đã có link <a> thì không thêm lại.
        if (
            f'href="{url}"' in content
            or f"href='{url}'" in content
        ):
            continue

        label = (
            "Xem tài liệu PDF"
            if len(pdf_urls) == 1
            else f"Xem tài liệu PDF {index}"
        )

        links.append(
            '<p>'
            f'<a href="{url}" '
            'target="_blank" '
            'rel="noopener noreferrer">'
            f'📎 {label}'
            '</a>'
            '</p>'
        )

    if not links:
        return content

    pdf_block = (
        '<div class="news-pdf-attachments">'
        '<p><strong>'
        'Tài liệu đính kèm'
        '</strong></p>'
        + "".join(links)
        + "</div>"
    )

    if content:
        return (
            f"{content}\n\n"
            f"{pdf_block}"
        )

    return pdf_block


# =========================
# VNSTOCK DATA
# =========================

def _fetch_from_api(
    symbol: str,
    limit: int = NEWS_LIMIT,
):
    symbol = symbol.upper().strip()

    try:
        # =========================
        # FETCH NEWS
        # =========================

        _pace_upstream_request()

        print(
            f"📰 Fetching news from "
            f"vnstock_data for {symbol}"
        )

        upstream_started = time.perf_counter()

        df = _call_with_hard_timeout(
            _vnstock_news_call,
            symbol,
            limit,
            timeout=NEWS_UPSTREAM_CALL_TIMEOUT_SECONDS,
        )

        print(
            f"⏱️ vnstock_data.news {symbol}: "
            f"{time.perf_counter() - upstream_started:.2f}s"
        )

        if df is None or df.empty:
            print(
                f"⚠️ Không có dữ liệu news "
                f"cho {symbol}"
            )

            return {}

        print(
            f"✅ News {symbol}: "
            f"{len(df)} records | "
            f"columns={df.columns.tolist()}"
        )

        # =========================
        # FETCH PDF
        # =========================

        filings = []
        needs_filing = False

        for _, row in df.iterrows():
            candidate_content = " ".join(
                filter(
                    None,
                    (
                        _safe_text(row.get("title")),
                        _safe_text(row.get("summary")),
                        _safe_text(row.get("content")),
                    ),
                )
            )

            if (
                ".pdf" in candidate_content.lower()
                and not _extract_pdf_urls(candidate_content)
            ):
                needs_filing = True
                break

        if not needs_filing:
            print(
                f"ℹ️ News {symbol}: không cần gọi filing"
            )
        else:
            print(
                f"📎 News {symbol}: PDF sẽ được bổ sung nền"
            )

        # =========================
        # SORT MỚI NHẤT
        # =========================

        if "publish_time" in df.columns:
            df["_sort_date"] = (
                pd.to_datetime(
                    df["publish_time"],
                    errors="coerce",
                )
            )

            df = df.sort_values(
                "_sort_date",
                ascending=False,
                na_position="last",
            )

        # Giới hạn pool theo NEWS_LIMIT; bài cũ vẫn được giữ trong NestJS DB.
        df = df.head(limit)

        # =========================
        # MAP SCHEMA
        # =========================

        records = []

        for _, row in df.iterrows():
            news_id = _safe_text(
                row.get("id")
            )

            title = _safe_text(
                row.get("title")
            )

            summary = _safe_text(
                row.get("summary")
            )

            content = _safe_text(
                row.get("content")
            )

            image_url = _safe_text(
                row.get("image_url")
            )

            source_url = _safe_text(
                row.get("url")
            )

            source = _safe_text(
                row.get("source")
            )

            category = _safe_text(
                row.get("category")
            )

            public_date = _safe_date(
                row.get("publish_time")
            )

            # =========================
            # FALLBACK CONTENT
            # =========================

            final_summary = (
                summary
                or content
                or title
            )

            final_content = (
                content
                or summary
                or title
            )

            # =========================
            # PDF
            # =========================

            pdf_urls = _find_pdf_urls(
                title=title,
                content=final_content,
                filings=filings,
            )

            final_content = (
                _append_pdf_links(
                    final_content,
                    pdf_urls,
                )
            )

            if pdf_urls:
                print(
                    f"📎 {symbol} "
                    f"{news_id}: "
                    f"{len(pdf_urls)} PDF"
                )

                for pdf_url in pdf_urls:
                    print(
                        f"   ↳ {pdf_url}"
                    )

            # =========================
            # SLUG
            # =========================

            raw_slug = slugify(
                title
            )

            if raw_slug:
                if news_id:
                    combined = (
                        f"{news_id}-"
                        f"{raw_slug}"
                    )
                else:
                    combined = raw_slug

            else:
                combined = (
                    f"news-{news_id}"
                    if news_id
                    else "news"
                )

            slug = (
                combined[
                    :MAX_SLUG_LEN
                ]
                .rstrip("-")
            )

            # =========================
            # GIỮ SCHEMA CŨ
            # =========================

            records.append({
                "news_id":
                    news_id,

                "news_title":
                    title,

                "news_sub_title":
                    final_summary,

                "news_short_content":
                    final_summary,

                "news_full_content":
                    final_content,

                "news_image_url":
                    image_url,

                "news_source_link":
                    source_url,

                "public_date":
                    public_date,

                "slug":
                    slug,

                "source":
                    source,

                "category":
                    category,
            })

        data = {
            "symbol":
                symbol,

            "count":
                len(records),

            "data":
                records,

            "updated_at":
                _now_vn().strftime(
                    "%Y-%m-%d %H:%M:%S"
                ),

            "cache_version":
                CACHE_VERSION,

            "pdf_resolution_version":
                2,

            "pdf_status":
                "pending" if needs_filing else "ready",
        }

        print(
            f"✅ Lấy thành công "
            f"{len(records)} bài "
            f"cho {symbol}"
        )

        return data

    except Exception as e:
        print(
            f"❌ Lỗi fetch_news"
            f"({symbol}): {e}"
        )

        traceback.print_exc()

        return {}


def _set_pdf_status(cache_file, status):
    cached = load_json(cache_file)

    if not isinstance(cached, dict):
        return

    cached["pdf_status"] = status
    cached["pdf_resolution_version"] = 2
    save_json(cache_file, cached)


def _run_pdf_enrichment(symbol, cache_file):
    acquired_slot = False

    try:
        # Đây là worker nền: request News đã trả về trước khi worker chờ slot.
        acquired_slot = _upstream_slots.acquire()
        filings = _fetch_filings(symbol)
        symbol_lock = _get_symbol_lock(symbol)

        with symbol_lock:
            cached = load_json(cache_file)

            if not isinstance(cached, dict):
                return

            matched_count = 0

            for item in cached.get("data") or []:
                if not isinstance(item, dict):
                    continue

                content = _safe_text(
                    item.get("news_full_content")
                )

                if (
                    ".pdf" not in content.lower()
                    or _extract_pdf_urls(content)
                ):
                    continue

                pdf_urls = _find_pdf_urls(
                    title=item.get("news_title"),
                    content=content,
                    filings=filings,
                )

                if not pdf_urls:
                    continue

                item["news_full_content"] = _append_pdf_links(
                    content,
                    pdf_urls,
                )
                matched_count += 1

            cached["pdf_status"] = (
                "ready"
                if not _has_unresolved_pdf(cached)
                else "unavailable"
            )
            cached["pdf_resolution_version"] = 2
            save_json(cache_file, cached)

            print(
                f"📎 PDF enrichment {symbol}: "
                f"{matched_count} bài được bổ sung URL"
            )
    except Exception as exc:
        print(f"⚠️ PDF enrichment {symbol} lỗi: {exc}")
        _set_pdf_status(cache_file, "error")
    finally:
        if acquired_slot:
            _upstream_slots.release()

        with _pdf_flights_guard:
            _pdf_flights.discard(symbol)


def _schedule_pdf_enrichment(symbol, cache_file, data):
    if not isinstance(data, dict) or not _has_unresolved_pdf(data):
        return data

    if data.get("pdf_status") in {"ready", "unavailable"}:
        return data

    response_data = dict(data)
    response_data["pdf_status"] = "pending"

    with _pdf_flights_guard:
        if symbol in _pdf_flights:
            return response_data

        _pdf_flights.add(symbol)

    threading.Thread(
        target=_run_pdf_enrichment,
        args=(symbol, cache_file),
        name=f"news-pdf-{symbol}",
        daemon=True,
    ).start()

    return response_data


# =========================
# PUBLIC FUNCTION
# =========================

def _run_refresh_flight(symbol, cache_file, fallback, flight):
    """Fetch một symbol ở background và đánh thức mọi request đang chờ."""
    acquired_slot = False

    try:
        acquired_slot = _upstream_slots.acquire(
            timeout=NEWS_SLOT_TIMEOUT_SECONDS
        )

        if not acquired_slot:
            print(
                f"⏱️ Hết thời gian chờ upstream slot cho {symbol}"
            )
            flight["result"] = fallback or {}
            return

        data = _fetch_from_api(symbol)

        if data and data.get("data"):
            save_json(cache_file, data)
            flight["result"] = _schedule_pdf_enrichment(
                symbol,
                cache_file,
                data,
            )
        else:
            print(
                f"⚠️ API lỗi/rỗng {symbol} "
                "→ fallback cache cũ"
            )
            flight["result"] = fallback or {}
    except Exception as exc:
        print(f"❌ Refresh news {symbol} lỗi: {exc}")
        traceback.print_exc()
        flight["result"] = fallback or {}
    finally:
        if acquired_slot:
            _upstream_slots.release()

        flight["event"].set()

        symbol_lock = _get_symbol_lock(symbol)
        with symbol_lock:
            if _symbol_flights.get(symbol) is flight:
                _symbol_flights.pop(symbol, None)

def fetch_news(symbol: str):
    """
    Cache:
    data/news/<SYMBOL>_news.json

    Rule:
    - Cache hợp lệ -> trả ngay.
    - Cache cũ -> chỉ 1 request được fetch.
    - Request khác chờ request đầu xong rồi dùng cache mới.
    - Sang ngày mới chỉ refresh sau 17h giờ Việt Nam.
    - API lỗi -> fallback cache cũ.

    Pagination 10 bài/lần do NestJS/frontend xử lý.
    """

    symbol = symbol.upper().strip()

    cache_file = f"{symbol}_news.json"

    # =========================
    # FAST CACHE
    # =========================

    cached = load_json(
        cache_file
    )

    if not _need_refresh(cached):
        print(
            f"📦 Dùng cache {symbol}: "
            f"{cached.get('count', 0)} bài"
        )

        return _schedule_pdf_enrichment(
            symbol,
            cache_file,
            cached,
        )

    # Single-flight theo symbol: hai request cùng mã dùng chung một lần fetch,
    # nhưng các mã khác không còn khóa lẫn nhau.
    symbol_lock = _get_symbol_lock(symbol)

    with symbol_lock:
        cached = load_json(cache_file)

        if not _need_refresh(cached):
            print(
                f"📦 Request khác vừa update "
                f"{symbol} → dùng cache mới"
            )
            return _schedule_pdf_enrichment(
                symbol,
                cache_file,
                cached,
            )

        flight = _symbol_flights.get(symbol)

        if flight is None:
            if not cached:
                print(f"🆕 Không có cache cho {symbol}")
            else:
                print(f"🔄 Cache cũ {symbol} → fetch lại")

            flight = {
                "event": threading.Event(),
                "result": None,
            }
            _symbol_flights[symbol] = flight

            threading.Thread(
                target=_run_refresh_flight,
                args=(symbol, cache_file, cached, flight),
                name=f"news-refresh-{symbol}",
                daemon=True,
            ).start()
        else:
            print(f"⏳ {symbol} đang fetch → dùng chung request")

    # Stale-while-revalidate: cache đúng schema dù đã đến hạn vẫn được trả ngay.
    # Worker phía trên tiếp tục refresh nền, nên việc mở trang không phải chờ
    # vnstock_data thêm 30-45 giây.
    if _cache_is_usable(cached):
        print(f"📦 Trả cache cũ {symbol}, đang refresh nền")
        return _schedule_pdf_enrichment(
            symbol,
            cache_file,
            cached,
        )

    # Chỉ request đầu tiên của một mã hoàn toàn chưa có cache mới phải chờ.
    if flight["event"].wait(NEWS_REQUEST_TIMEOUT_SECONDS):
        return flight["result"] or cached or {}

    # Không giữ Flask request vô hạn khi vnstock_data bị treo. Worker daemon
    # vẫn hoàn thành cache nếu upstream trả về sau đó.
    print(
        f"⏱️ Fetch news {symbol} quá "
        f"{NEWS_REQUEST_TIMEOUT_SECONDS:g}s → trả cache cũ"
    )

    if cached:
        return _schedule_pdf_enrichment(
            symbol,
            cache_file,
            cached,
        )

    raise NewsFetchTimeoutError(
        f"Fetch news {symbol} quá thời gian cho phép"
    )
