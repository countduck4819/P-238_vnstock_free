from flask import Blueprint, jsonify
from core.fetchers import fetch_listing

listing_bp = Blueprint("listing_bp", __name__)

@listing_bp.route("/api/listing")
def get_listing():
    data = fetch_listing()
    if not data:
        return jsonify({"error": "Không lấy được danh sách mã"}), 500
    return jsonify(data)
