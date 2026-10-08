--- Phần brief

# Xây dựng nền tảng AI phát hiện cổ phiếu có xu hướng tăng và trợ lý AI phân tích báo cáo tài chính

## 1. Mục tiêu đề tài

Đề tài hướng tới xây dựng một nền tảng AI hỗ trợ nhà đầu tư thông qua hai chức năng độc lập nhưng bổ trợ cho nhau.

- Chức năng 1: Hệ thống áp dụng các mô hình Machine Learning/Deep Learning để phân tích dữ liệu giá lịch sử, khối lượng giao dịch và các chỉ báo kỹ thuật nhằm phát hiện các cổ phiếu có xu hướng tăng và dự báo giá cổ phiếu trong tương lai.
- Chức năng 2: Hệ thống xây dựng một trợ lý AI (AI Agent) có khả năng phân tích báo cáo tài chính doanh nghiệp và trả lời các câu hỏi của người dùng dựa trên nội dung báo cáo và tìm kiếm cổ phiếu bền vững dựa theo báo cáo tài chính

Nền tảng cung cấp đồng thời hai công cụ hỗ trợ, giúp nhà đầu tư tham khảo cả góc nhìn phân tích kỹ thuật và phân tích cơ bản trước khi đưa ra quyết định đầu tư.

## 2. Phạm vi giải pháp

### 2.1. Phân tích kỹ thuật và dự báo cổ phiếu

- Thu thập và tiền xử lý dữ liệu giá lịch sử, khối lượng giao dịch và chỉ báo kỹ thuật.
- Xây dựng mô hình Machine Learning/Deep Learning để phát hiện cổ phiếu có xu hướng tăng.
- Dự báo giá cổ phiếu trong tương lai dựa trên dữ liệu quá khứ và các chỉ báo.
- Trình bày kết quả theo dạng báo cáo, biểu đồ xu hướng và tiêu chí lọc cổ phiếu.

### 2.2. Trợ lý AI phân tích báo cáo tài chính

- Thu thập và chuẩn hóa dữ liệu báo cáo tài chính của doanh nghiệp.
- Xây dựng AI Agent có khả năng đọc hiểu và phân tích các chỉ số tài chính chính yếu.
- Đánh giá các chỉ số như doanh thu, lợi nhuận, ROE, ROA, EPS, P/E, P/B, dòng tiền và các yếu tố tài chính khác.
- Giải thích ý nghĩa các chỉ số và hỗ trợ đánh giá tiềm năng tăng trưởng của doanh nghiệp.
- Trả lời câu hỏi của người dùng liên quan đến báo cáo tài chính và tình hình doanh nghiệp.

## 3. Các tính năng chính

- Tìm kiếm và gợi ý cổ phiếu có xu hướng tăng dựa trên mô hình phân tích kỹ thuật.
- Dự báo xu hướng giá trong ngắn hạn và trung hạn.
- Thống kê các chỉ báo kỹ thuật quan trọng.
- Trợ lý AI trả lời câu hỏi về báo cáo tài chính.
- Phân tích chỉ số tài chính và đưa ra nhận định cơ bản.
- Kết hợp hai góc nhìn phân tích kỹ thuật và phân tích cơ bản để hỗ trợ nhà đầu tư.

## 4. Kiến trúc giải pháp

### 4.1. Thành phần dữ liệu

- Dữ liệu giá cổ phiếu lịch sử
- Dữ liệu khối lượng giao dịch
- Các chỉ báo kỹ thuật (MA, RSI, MACD, Bollinger Bands, v.v.)
- Báo cáo tài chính doanh nghiệp
- Chỉ số tài chính định dạng chuẩn

### 4.2. Thành phần AI/ML

- Mô hình học máy/deep learning cho dự báo giá và phát hiện xu hướng.
- Mô hình xử lý ngôn ngữ tự nhiên (NLP) cho AI Agent đọc hiểu báo cáo tài chính.
- Cơ chế truy vấn ngữ nghĩa, phân tích câu hỏi và trả lời dựa trên nội dung báo cáo.

### 4.3. Giao diện và trải nghiệm người dùng

- Bảng điều khiển hiển thị kết quả phân tích kỹ thuật và các cổ phiếu đề xuất.
- Giao diện chat/tra cứu để tương tác với AI Agent phân tích báo cáo tài chính.
- Biểu đồ trực quan hóa xu hướng và số liệu tài chính.

## 5. Quy trình thực hiện chi tiết

1. Nghiên cứu và thu thập dữ liệu chứng khoán, báo cáo tài chính.
2. Tiền xử lý dữ liệu: làm sạch, chuẩn hóa, tạo chỉ báo kỹ thuật.
3. Xây dựng và huấn luyện mô hình phát hiện xu hướng và dự báo giá.
4. Xây dựng AI Agent phân tích báo cáo tài chính, triển khai NLP và kiến thức tài chính.
5. Tích hợp hai chức năng vào cùng nền tảng.
6. Kiểm thử và đánh giá kết quả: độ chính xác dự báo, chất lượng trả lời của trợ lý AI.
7. Hoàn thiện tài liệu, mô tả và hướng dẫn sử dụng.

## 6. Kết quả mong đợi

- Nền tảng AI có thể phát hiện và gợi ý cổ phiếu tiềm năng tăng giá dựa trên phân tích kỹ thuật.
- Trợ lý AI giải thích rõ ràng các chỉ số tài chính và cung cấp góc nhìn cơ bản về doanh nghiệp.
- Nhà đầu tư có thể sử dụng đồng thời hai công cụ để tham khảo, so sánh và ra quyết định đầu tư tốt hơn.

## 7. Tên đề tài

Xây dựng nền tảng AI phát hiện cổ phiếu có xu hướng tăng và trợ lý AI phân tích báo cáo tài chính

## 8. Gợi ý các bước tiếp theo

- Bước 1: Hoàn thiện định nghĩa dữ liệu và sơ đồ luồng xử lý.
- Bước 2: Xây dựng mô hình phân tích kỹ thuật và thử nghiệm với dữ liệu thực.
- Bước 3: Xây dựng AI Agent phân tích báo cáo tài chính.
- Bước 4: Triển khai giao diện và tích hợp hai công cụ.
- Bước 5: Kiểm tra, tinh chỉnh, và soạn thảo báo cáo hoàn chỉnh.
