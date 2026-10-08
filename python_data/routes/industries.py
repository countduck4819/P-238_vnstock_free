from flask import Blueprint, jsonify
from core.fetchers import fetch_industries

industries_bp = Blueprint("industries_bp", __name__)

@industries_bp.route("/api/industries")
def get_industries():
    data = fetch_industries()
    if not data:
        return jsonify({"error": "Không lấy được danh sách ngành"}), 500
    return jsonify(data)
