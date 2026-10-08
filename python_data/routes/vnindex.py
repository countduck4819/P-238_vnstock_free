from flask import Blueprint, jsonify
from core.fetchers import fetch_vnindex

vnindex_bp = Blueprint("vnindex_bp", __name__)

@vnindex_bp.route("/api/vnindex")
def get_vnindex():
    data = fetch_vnindex()
    if not data:
        return jsonify({"error": "Không lấy được dữ liệu VNINDEX"}), 500
    return jsonify(data)
