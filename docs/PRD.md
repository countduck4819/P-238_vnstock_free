# Product Requirements Document (PRD)

## 1. Tổng quan sản phẩm

- Tên sản phẩm: Nền tảng AI phát hiện cổ phiếu có xu hướng tăng và trợ lý AI phân tích báo cáo tài chính.
- Mục tiêu: Hỗ trợ nhà đầu tư bằng hai mô-đun độc lập: phân tích kỹ thuật dự báo giá và trợ lý AI phân tích báo cáo tài chính.
- Người dùng mục tiêu: nhà đầu tư cá nhân, nhà đầu tư tổ chức nhỏ, người yêu thích chứng khoán, và các chuyên viên phân tích muốn có công cụ tham khảo.

## 2. Tính năng cốt lõi

### 2.1. Mô-đun phân tích kỹ thuật

- Thu thập dữ liệu giá lịch sử và khối lượng giao dịch.
- Tính toán các chỉ báo kỹ thuật: MA, EMA, RSI, MACD, Bollinger Bands, On-Balance Volume, ADX.
- Nhận diện xu hướng tăng nắm giữ dựa trên bộ tiêu chí kỹ thuật.
- Dự báo giá cổ phiếu ngắn hạn và trung hạn.
- Gợi ý danh sách cổ phiếu tiềm năng tăng danh mục.
- Hiển thị biểu đồ giá và các chỉ báo kỹ thuật liên quan.

### 2.2. Mô-đun trợ lý AI phân tích báo cáo tài chính

- Nhập liệu hoặc tải lên báo cáo tài chính doanh nghiệp.
- Phân tích các chỉ số tài chính: doanh thu, lợi nhuận sau thuế, ROE, ROA, EPS, P/E, P/B, dòng tiền, biên lợi nhuận, nợ vay, hệ số thanh toán.
- Giải thích ý nghĩa từng chỉ số và mức độ sức khỏe tài chính.
- So sánh hiệu quả tài chính giữa nhiều kỳ hoặc nhiều doanh nghiệp cùng nhóm ngành.
- Trả lời câu hỏi người dùng theo ngữ cảnh báo cáo tài chính.
- Đưa ra nhận xét cơ bản về tiềm năng tăng trưởng doanh nghiệp.

### 2.3. Tính năng tích hợp

- Cho phép người dùng tham khảo đồng thời kết quả phân tích kỹ thuật và đánh giá cơ bản.
- Kết nối giữa danh sách cổ phiếu xu hướng tăng và báo cáo tài chính tương ứng.
- Cung cấp tính năng lọc và sắp xếp theo mức độ phù hợp kỹ thuật và cơ bản.

## 3. Yêu cầu chức năng

- Hệ thống phải cung cấp giao diện truy vấn cổ phiếu và hiển thị kết quả rõ ràng.
- Hệ thống phải hỗ trợ xuất báo cáo định dạng PDF/CSV cho kết quả phân tích.
- Hệ thống phải lưu lại các phân tích đã thực hiện để người dùng tham khảo lại.
- Hệ thống AI Agent phải trả lời được câu hỏi bằng ngôn ngữ tự nhiên tiếng Việt.
- Hệ thống phải đánh dấu nguồn dữ liệu và mức độ độ tin cậy của câu trả lời khi phân tích báo cáo.

## 4. Yêu cầu phi chức năng

- Hiệu suất: trả về kết quả phân tích trong vòng 5–10 giây đối với tập dữ liệu chuẩn.
- Bảo mật: bảo mật dữ liệu người dùng và báo cáo tài chính doanh nghiệp.
- Khả năng mở rộng: hỗ trợ bổ sung thêm chỉ báo kỹ thuật và báo cáo tài chính mới.
- Tính tiện dụng: giao diện trực quan, dễ sử dụng, thân thiện với người dùng mới.
- Độ tin cậy: đảm bảo phân tích tài chính đúng định dạng, không gây hiểu nhầm thông tin.

## 5. Luồng người dùng chính

1. Người dùng đăng nhập/truy cập nền tảng.
2. Chọn chức năng phân tích kỹ thuật hoặc trợ lý AI.
3. Với phân tích kỹ thuật:
   - Chọn danh sách cổ phiếu hoặc tải dữ liệu giá.
   - Xem kết quả xu hướng và dự báo.
   - Lưu, xuất hoặc so sánh kết quả.
4. Với trợ lý AI:
   - Nhập hoặc tải báo cáo tài chính.
   - Đặt câu hỏi về doanh thu, lợi nhuận, chỉ số tài chính, dòng tiền, v.v.
   - Xem trả lời và giải thích chi tiết.
5. Người dùng có thể chuyển đổi giữa hai mô-đun để so sánh góc nhìn kỹ thuật và cơ bản.

## 6. Tiêu chí thành công

- Mô-đun kỹ thuật đưa ra danh sách cổ phiếu xu hướng tăng phù hợp với ít nhất 70% mẫu kiểm tra.
- Trợ lý AI trả lời chính xác và không mập mờ với ít nhất 80% các câu hỏi mẫu về báo cáo tài chính.
- Người dùng có thể hoàn thành quy trình phân tích trong ít nhất 3 bước cơ bản.
- Nền tảng cung cấp thông tin trực quan, dễ hiểu và giúp người dùng so sánh hai góc nhìn.

## 7. Phạm vi triển khai giai đoạn 1

- Cơ chế phân tích kỹ thuật đơn giản với dữ liệu giá lịch sử và các chỉ báo cơ bản.
- Trợ lý AI xử lý báo cáo tài chính đã được chuẩn hóa và trả lời câu hỏi thông dụng.
- Giao diện hiển thị kết quả phân tích và biểu đồ cơ bản.
- Tài liệu hướng dẫn sử dụng tính năng chính.

## 8. Gợi ý công nghệ

- Backend: Node.js / Python.
- AI: scikit-learn, TensorFlow/PyTorch, NLP transformer hoặc LLM.
- Cơ sở dữ liệu: PostgreSQL hoặc MongoDB.
- Frontend: React/Next.js.
- Triển khai: Docker, Docker Compose.

## 9. Rủi ro và biện pháp giảm thiểu

- Dữ liệu không nhất quán: làm sạch và chuẩn hóa dữ liệu trước khi phân tích.
- Mô hình dự báo chưa chính xác: thử nghiệm với nhiều mô hình và đánh giá theo chỉ số RMSE / MAPE.
- Trợ lý AI trả lời sai: xây dựng bộ câu hỏi mẫu, kiểm thử thủ công và thêm quy tắc kiểm tra ngữ cảnh.
- Nhu cầu người dùng phức tạp: tập trung giai đoạn đầu vào các tính năng cốt lõi và mở rộng dần.
