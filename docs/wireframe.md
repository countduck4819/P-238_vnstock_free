# Wireframe & UI Flow

Link Figma:
https://www.figma.com/make/OPkTrZwWc5qAaMbmp2HFJA/Dashboard-Wireframe-Design?code-node-id=0-9&p=f&fullscreen=1

Dựa trên cấu trúc và component hiện có trong dự án `web/`, wireframe sau đây đề xuất giao diện sát với layout dashboard Next.js và các tab đã có.

## 1. Trang chính (Client)

### Header

- Logo dự án.
- Menu chính: Dashboard, Phân tích kỹ thuật, Trợ lý AI, Tin tức, Hồ sơ.
- Nút đăng nhập/đăng ký hoặc avatar người dùng.

### Body

- Bố cục chính 2 cột trên desktop, 1 cột trên mobile.
- Cột trái: widget biểu đồ thị trường và tab gợi ý cổ phiếu.
- Cột phải: danh sách chỉ số thị trường, heatmap ngắn, biểu đồ TradingView.

### Component chính

- `LeftSidebar`: giữ form chọn tab hoặc chọn bộ lọc.
- `StockRecommendationTabs`: các tab chuyên gia, xu hướng ngắn hạn và xu hướng dài hạn + dự đoán giá.
- `TradingView widget`: hiển thị biểu đồ chỉ số thị trường.

## 2. UI hiện có trong code

### 2.1. Trang dashboard client hiện tại

- Dựa trên file `web/src/app/(client)/page.tsx`.
- Có `TradingView widget` hiển thị biểu đồ thị trường.
- Có `StockRecommendationTabs` với tab chuyên gia, xu hướng ngắn hạn và xu hướng dài hạn + dự đoán giá.
- `V6LongTermAdvisory` hiển thị chung xếp hạng dài hạn, dự đoán giá và biểu đồ của cùng một phiên dữ liệu.
- `ExpertRecommendations` hiển thị danh sách khuyến nghị chuyên gia.

### 2.2. Tính năng hiện có

- Bảng dài hạn hiển thị `Mã`, `Xác suất`, `Đồng thuận model`, `Giá dự đoán`, `Biểu đồ mini` và `Phiên dữ liệu`.
- Loading và empty state đã có trong component.
- Sidebar/left panel hiện có các tab chọn nguồn dữ liệu.

## 3. Phạm vi chức năng

### 3.1. Chức năng dự kiến triển khai

- Dashboard.
- AI phát hiện cổ phiếu có xu hướng tăng.
- AI dự báo giá cổ phiếu trong tương lai.
- AI Agent phân tích báo cáo tài chính.

### 3.2. Hướng phát triển

- Upload báo cáo PDF.
- Phân tích tin tức.
- Phân tích cảm xúc thị trường.
- Hệ thống chấm điểm cổ phiếu.
- Gợi ý danh mục đầu tư.

## 4. Gợi ý cấu trúc UI cụ thể

### 4.1. Dùng component hiện có

- `Input` và `Button` cho form tìm kiếm.
- `Tabs` để chuyển giữa chuyên gia, xu hướng ngắn hạn và xu hướng dài hạn + dự đoán giá.
- `TableCustom` để hiển thị bảng cổ phiếu gợi ý.
- `TradingView widget` hoặc `StockChart` để hiển thị biểu đồ giá.

### 4.2. Tông màu và phong cách

- Giữ phong cách gradient tím/xanh như hiện tại.
- Card trắng viền xám nhẹ để tương đồng với phần `StockRecommendationTabs`.
- Các thẻ thông tin dùng màu xanh lá, vàng, đỏ cho trạng thái thị trường.

## 5. Luồng người dùng đề xuất

1. Vào trang chính dashboard.
2. Chuyển sang tab xu hướng dài hạn + dự đoán giá để xem cùng một cohort và phiên dữ liệu.
3. Sang trang `Phân tích kỹ thuật` để xem chart chi tiết và danh sách cổ phiếu tiềm năng.
4. Sang trang Trợ lý AI để đặt câu hỏi về báo cáo tài chính doanh nghiệp.
5. Xem kết quả phân tích để tham khảo trước khi đưa ra quyết định đầu tư.
