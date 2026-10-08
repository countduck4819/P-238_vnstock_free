from flask import Blueprint, jsonify
from core.fetchers import fetch_stocks_by_industries

stocks_by_industries_bp = Blueprint("stocks_by_industries_bp", __name__)

@stocks_by_industries_bp.route("/api/stocks-by-industries")
def get_industries():
    data = fetch_stocks_by_industries()
    if not data:
        return jsonify({"error": "Không lấy được danh sách ngành"}), 500
    return jsonify(data)
