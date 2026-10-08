from core.fetchers import fetch_finance
from flask import (
    Blueprint,
    jsonify,
    request,
)

finance_bp = Blueprint(
    "finance_bp",
    __name__,
)


@finance_bp.route(
    "/api/finance/<string:symbol>",
    methods=["GET"],
)
def get_finance_summary(symbol):
    symbol = (
        symbol
        .strip()
        .upper()
    )

    if not symbol:
        return (
            jsonify(
                {
                    "error": (
                        "Mã chứng khoán "
                        "không hợp lệ."
                    )
                }
            ),
            400,
        )

    period = (
        request.args
        .get(
            "period",
            "quarter",
        )
        .strip()
        .lower()
    )

    # Hiện tại frontend dùng quarter.
    # Cho phép year để dùng sau này.
    if period not in {
        "quarter",
        "year",
    }:
        return (
            jsonify(
                {
                    "error": (
                        "Period chỉ hỗ trợ "
                        "'quarter' hoặc 'year'."
                    )
                }
            ),
            400,
        )

    data = fetch_finance(
        symbol,
        period=period,
    )

    if not data:
        return (
            jsonify(
                {
                    "error": (
                        f"Không lấy được dữ liệu "
                        f"cho {symbol}"
                    )
                }
            ),
            500,
        )

    return jsonify(data)
