from flask import Blueprint, jsonify
from core.fetchers import fetch_industries_for_code

industries_for_code_bp = Blueprint("industries_for_code_bp", __name__)

@industries_for_code_bp.route("/api/industries-for-code")
def get_industries_for_code():
    data = fetch_industries_for_code()
    if not data:
        return jsonify({"error": "Không lấy được danh sách mã"}), 500
    return jsonify(data)
