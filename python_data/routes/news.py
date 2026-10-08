from flask import Blueprint, jsonify

from core.fetchers import fetch_news
from core.fetchers.news_fetcher import NewsFetchTimeoutError


news_bp = Blueprint("news_bp", __name__)


@news_bp.route(
    "/api/news/<string:symbol>",
    methods=["GET"],
)
def get_news(symbol):
    symbol = symbol.strip().upper()

    if not symbol:
        return jsonify({
            "error": "Mã chứng khoán không hợp lệ",
        }), 400

    try:
        data = fetch_news(symbol)
    except NewsFetchTimeoutError as exc:
        return jsonify({
            "error": str(exc),
            "code": "NEWS_UPSTREAM_TIMEOUT",
        }), 504

    if not data:
        response = jsonify({
            "error": f"Tạm thời chưa lấy được tin tức cho {symbol}",
            "code": "NEWS_UPSTREAM_UNAVAILABLE",
        })
        response.headers["Retry-After"] = "2"
        return response, 503

    # Python chỉ báo cache đã sẵn sàng. NestJS đọc file JSON dùng chung và
    # thực hiện import/phân trang, tránh gửi cả pool news qua HTTP hai lần.
    return jsonify({
        "success": True,
        "symbol": symbol,
        "count": data.get("count", 0),
        "updated_at": data.get("updated_at"),
        "cache_version": data.get("cache_version"),
        "pdf_status": data.get("pdf_status", "ready"),
    })
