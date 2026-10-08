# Báo cáo tuần

## 1. Tóm tắt công việc tuần vừa qua

Tuần này nhóm đã tập trung hoàn thiện hai phần chính:

- Xây dựng giao diện người dùng (UI) cho dự án, bao gồm các màn hình chính để hiển thị kết quả phân tích kỹ thuật và giao diện tương tác với trợ lý AI.
- Thu thập dữ liệu phục vụ cho mô hình, gồm dữ liệu giá lịch sử, khối lượng giao dịch và các chỉ báo kỹ thuật ban đầu.

## 2. Những gì đã hoàn thành

### 2.1. Giao diện người dùng

- Xây dựng cấu trúc frontend trong `web/` dựa trên Next.js.
- Hoàn thiện trang dashboard hiển thị các chỉ báo chứng khoán và danh sách cổ phiếu tiềm năng.
- Thiết kế giao diện chat / tra cứu để người dùng có thể tương tác với trợ lý AI phân tích báo cáo tài chính.
- Bổ sung các thành phần trình bày biểu đồ, bảng số liệu và các bộ lọc cơ bản.

### 2.2. Thu thập dữ liệu

- Thu thập dữ liệu giá lịch sử và khối lượng giao dịch cho tập cổ phiếu mục tiêu.
- Tổng hợp các chỉ báo kỹ thuật cơ bản như MA, EMA, RSI, MACD.
- Chuẩn bị dữ liệu thô và xác định cấu trúc dữ liệu đầu vào để sẵn sàng huấn luyện mô hình.

## 3. Cấu trúc hệ thống hiện tại

### 3.1. Backend

- `src/main.py`: entrypoint ứng dụng FastAPI.
- `src/api/`: chứa định nghĩa route và API.
- `src/models/`: chứa schema dữ liệu Pydantic.
- `src/services/`: nơi dự kiến chứa logic xử lý dữ liệu và mô hình.
- `src/agents/`: các định nghĩa cho LangGraph agent, bao gồm `graph.py`, `state.py`, và các node/tool.

### 3.2. Frontend

- `web/`: ứng dụng Next.js quản lý giao diện.
- `web/src/app/`: cấu trúc trang và các route chính.
- `web/src/lib/api.ts`: kết nối tới backend.

### 3.3. Tài liệu và vận hành

- `docs/Brief.md`: mô tả mục tiêu và phạm vi giải pháp.
- `docs/PRD.md`: yêu cầu sản phẩm và tính năng cốt lõi.
- `README.md`: hướng dẫn cài đặt, cấu trúc dự án và thông tin nhanh.

## 4. Các chức năng chính hiện có

- Hiển thị dashboard phân tích chứng khoán.
- Giao diện nhập liệu và tương tác với trợ lý AI.
- Thu thập dữ liệu giá lịch sử và chỉ báo kỹ thuật cơ bản.
- Kết nối frontend với backend thông qua API cơ bản.

## 5. Kế hoạch tuần sau

### 5.1. Train model

- Sử dụng dữ liệu đã thu thập để bắt đầu huấn luyện mô hình phân tích kỹ thuật.
- Xây dựng pipeline tiền xử lý dữ liệu, chuẩn hóa, và tạo feature từ chỉ báo kỹ thuật.
- Thử nghiệm các mô hình ML/Deep Learning cơ bản để phát hiện xu hướng tăng và dự báo giá.

### 5.2. Hoàn thiện dữ liệu và tích hợp

- Hoàn thiện bộ dữ liệu thu thập, đảm bảo dữ liệu sạch và nhất quán.
- Hoàn thiện luồng dữ liệu đầu vào cho backend và xác thực dữ liệu trước khi huấn luyện.
- Tích hợp kết quả mô hình vào giao diện để hiển thị gợi ý cổ phiếu và chỉ số dự báo.

### 5.3. Mục tiêu bổ sung

- Bắt đầu xây dựng mô-đun phân tích báo cáo tài chính cho trợ lý AI.
- Thiết lập đánh giá ban đầu cho kết quả huấn luyện bằng các chỉ số như RMSE/MAPE.
- Đảm bảo mô hình có thể chạy trên dữ liệu thu thập được và trả về kết quả trong giao diện.

## 6. Ghi chú

Dự án đang đi đúng hướng với trọng tâm tuần này là hoàn thiện UI và chuẩn bị dữ liệu. Tuần sau sẽ chuyển sang giai đoạn huấn luyện mô hình và kết nối kết quả với trải nghiệm người dùng.
