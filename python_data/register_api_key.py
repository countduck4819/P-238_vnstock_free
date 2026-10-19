"""Đăng ký VNSTOCK_API_KEY cho vnstock (4.x và thế hệ 5)."""

import os
import sys

import vnstock

api_key = os.environ.get("VNSTOCK_API_KEY", "").strip()

if not api_key:
    sys.exit(0)

# 4.x dùng change_api_key(); thế hệ 5 giữ các hàm tương thích và cũng đọc
# trực tiếp biến môi trường VNSTOCK_API_KEY.
for name in ("change_api_key", "register_user"):
    register = getattr(vnstock, name, None)
    if callable(register):
        register(api_key)
        print(f"Đã đăng ký VNSTOCK_API_KEY qua vnstock.{name}().")
        break
else:
    print("vnstock tự đọc VNSTOCK_API_KEY từ biến môi trường.")
