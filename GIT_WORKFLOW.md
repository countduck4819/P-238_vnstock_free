# QUY TRÌNH QUẢN LÝ MÃ NGUỒN VÀ LÀM VIỆC VỚI GIT (PROJECT COUNTDUCK - FIREANT TRADING AI)

**Official Repository:** `https://github.com/AI20K-Build-Phase-Cohort-3/P-238`

Tài liệu này quy định quy chuẩn làm việc Git cho 4 thành viên nhóm Countduck: **Đinh Hồng Đăng (Lead)**, **Hoàng Hải Dương (Backend)**, **Nguyễn Hoàng Sơn (Frontend & AI RAG)**, **Vũ Thành Khang (AI & DevOps)**.

---

## 1. QUY ƯỚC NHÁNH (BRANCHING CONVENTION)

- **`main`**: Nhánh Production. Chỉ được merge từ `develop` khi có phiên bản ổn định (Releases/Demos).
- **`develop`**: Nhánh phát triển chính. Tất cả tính năng mới được merge vào đây sau khi review.
- **`feature/<mã-tác-vụ>-<tên-ngắn>`**: Nhánh tính năng cá nhân.
  - Ví dụ: `feature/T-004-init-nextjs-ui`, `feature/T-032-rag-citation-modal`, `feature/T-035-auth-api`
- **`fix/<mã-lỗi>-<tên-ngắn>`**: Nhánh sửa lỗi.
  - Ví dụ: `fix/BUG-001-chat-accent-vietnamese`

---

## 2. QUY ƯỚC COMMIT MESSAGE (CONVENTIONAL COMMITS)

Cú pháp: `<type>(<scope>): <mô tả ngắn bằng tiếng Việt hoặc tiếng Anh>`

Các type hợp lệ:
- `feat`: Thêm tính năng mới (ví dụ: `feat(ui): thêm citation modal cho AI Chat`)
- `fix`: Sửa lỗi (ví dụ: `fix(rag): sửa lỗi parse chunk metadata`)
- `docs`: Cập nhật tài liệu (ví dụ: `docs(git): bổ sung git workflow guidelines`)
- `refactor`: Tối ưu code không làm thay đổi tính năng
- `style`: Thay đổi định dạng UI/CSS, không ảnh hưởng logic
- `test`: Bổ sung test cases

---

## 3. QUY TRÌNH PULL REQUEST (PR)

1. Tạo nhánh từ `develop`:
   ```bash
   git checkout develop
   git pull origin develop
   git checkout -b feature/T-xxx-name
   ```
2. Commit và đẩy nhánh lên GitHub repo chính (`https://github.com/AI20K-Build-Phase-Cohort-3/P-238`):
   ```bash
   git add .
   git commit -m "feat(module): mô tả công việc"
   git push origin feature/T-xxx-name
   ```
3. Tạo Pull Request trên GitHub hướng về nhánh `develop`.
4. Yêu cầu **ít nhất 1 thành viên** trong nhóm review trước khi Merge.
