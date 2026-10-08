import sys

from flask import Flask, json
from flask_cors import CORS
from routes import blueprints
from scheduler import start_scheduler

app = Flask(__name__)
CORS(app, resources={r"/api/*": {"origins": "*"}})

@app.route("/")
def index():
    return json.dumps({
        "service": "FinSight Python Data & AI Service",
        "status": "online",
        "web_ui": "http://localhost:3000",
        "api_endpoints": [
            "/api/stock/<symbol>",
            "/api/listing",
            "/api/vnindex",
            "/api/finance/<symbol>",
            "/api/news",
            "/api/wave-h120/latest",
            "/api/wave-v6/latest",
            "/health"
        ]
    }), 200, {"Content-Type": "application/json"}

@app.route("/health")
@app.route("/api/health")
def health():
    return json.dumps({"status": "ok"}), 200, {"Content-Type": "application/json"}

# Cấu hình toàn cục để Flask JSON không escape unicode
app.config['JSON_AS_ASCII'] = False

# Đảm bảo provider JSON mới của Flask (>=2.3) cũng dùng UTF-8
json.provider.DefaultJSONProvider.ensure_ascii = False

# (Tuỳ chọn, nhưng nên có) đảm bảo output console UTF-8
sys.stdout.reconfigure(encoding='utf-8')

# Đăng ký blueprint cho các route
for bp in blueprints:
    app.register_blueprint(bp)


# Khởi động scheduler chạy nền (auto update mỗi 1 tiếng)
start_scheduler()

if __name__ == "__main__":
    app.run(
        host="0.0.0.0",
        port=6060,
        debug=False,
        use_reloader=False,
    )
