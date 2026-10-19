#!/bin/sh
# Khởi động python_data với vnstock bản Cộng đồng mới nhất.
set -e

if [ "${VNSTOCK_AUTO_UPGRADE:-1}" != "0" ]; then
    echo "Kiểm tra bản vnstock mới nhất..."
    pip install --no-cache-dir --upgrade \
        --extra-index-url https://vnstocks.com/api/packages \
        --extra-index-url https://vnstocks.com/api/simple \
        vnstock \
        || echo "Không nâng cấp được vnstock, dùng bản đã cài."
fi

# API key miễn phí (bản Cộng đồng) nâng giới hạn từ 20 lên 60 request/phút.
if [ -n "${VNSTOCK_API_KEY:-}" ]; then
    python register_api_key.py \
        || echo "Không đăng ký được VNSTOCK_API_KEY, chạy ở chế độ khách."
fi

python -c "import vnstock; print('vnstock', getattr(vnstock, '__version__', 'unknown'))" || true

exec python server.py
