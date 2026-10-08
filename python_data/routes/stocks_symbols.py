from flask import Blueprint, jsonify
from core.fetchers import fetch_stocks_symbols

stocks_symbols_bp = Blueprint("stocks_symbols_bp", __name__)

@stocks_symbols_bp.route("/api/stocks_symbols")
def get_stocks_symbols():
    data = fetch_stocks_symbols()
    if not data:
        return jsonify({"error": "Không lấy được danh sách mã cổ phiếu"}), 500

    return jsonify(data)
