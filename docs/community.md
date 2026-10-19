# Cộng đồng: đăng bài và nhắn tin realtime

Trang `/cong-dong` là mạng xã hội cho nhà đầu tư, kiểu FireAnt: thành viên đăng
nhận định, thả tim, lưu, bình luận và nhắn tin riêng với nhau. Mọi thay đổi được
đẩy tới các trình duyệt đang mở qua Socket.IO, không cần tải lại trang.

## Chức năng

| Chức năng | Ai dùng được |
| --- | --- |
| Xem bảng tin, lọc theo chủ đề, ngành, mã CP, từ khoá | Mọi người (khách cũng xem được) |
| Đăng bài (gắn mã, Mua/Bán/Quan sát, giá mục tiêu, cắt lỗ) | Thành viên đã đăng nhập |
| Thả tim, lưu bài, bình luận | Thành viên đã đăng nhập |
| Xoá bài / bình luận | Tác giả hoặc admin |
| Nhắn tin 1-1, tìm thành viên, “đang soạn tin”, “Đã xem”, trạng thái online | Thành viên đã đăng nhập |

Trang tin nhắn: `/cong-dong/tin-nhan`. Nút “Nhắn tin” trên mỗi bài viết mở
`/cong-dong/tin-nhan?userId=<id tác giả>`, nút “Tin nhắn” ở đầu trang Cộng đồng
hiện số tin chưa đọc.

Danh tính người đăng, người bình luận, người nhắn luôn lấy từ access token
(JWT). API không nhận `userId`, `authorName`, `role`… từ client, nên không ai
đăng hay xoá bài thay người khác được.

## Backend (NestJS, `api/src/modules/Community`)

| File | Vai trò |
| --- | --- |
| `community.controller.ts` | REST API dưới `/api/community` |
| `community.service.ts` | Bài viết, thích, lưu, bình luận |
| `community-messages.service.ts` | Hội thoại, tin nhắn, đã đọc, tìm thành viên |
| `community.gateway.ts` | Socket.IO namespace `/community`, xác thực bằng JWT |
| `community-realtime.service.ts` | Phát sự kiện tới mọi người hoặc tới từng user, đếm online |
| `community.events.ts` | Tên sự kiện, namespace và path socket (web dùng bản sao ở `web/src/utils/communitySocket.ts`) |
| `community.entities.ts` | Bảng `community_posts`, `community_comments`, `community_likes`, `community_saves`, `community_conversations`, `community_messages` |

Bảng được TypeORM tạo tự động (`synchronize: true`), không cần migration.

### REST API

| Method | Đường dẫn | Ghi chú |
| --- | --- | --- |
| GET | `/api/community/posts` | Công khai. Query: `page`, `limit`, `category` (`all`, `hot`, `signal`, `technical`, `fundamental`, `qa`, `saved`), `sector`, `symbol`, `keyword`, `authorId`. Có token thì trả thêm `isLiked`, `isSaved` |
| POST | `/api/community/posts` | Đăng bài |
| DELETE | `/api/community/posts/:id` | Tác giả hoặc admin |
| POST | `/api/community/posts/:id/like` | Bật/tắt thích |
| POST | `/api/community/posts/:id/save` | Bật/tắt lưu |
| POST | `/api/community/posts/:id/comments` | Bình luận |
| DELETE | `/api/community/comments/:id` | Tác giả hoặc admin |
| GET | `/api/community/members?keyword=` | Tìm thành viên để nhắn tin |
| GET | `/api/community/members/:id` | Hồ sơ công khai (công khai) |
| GET | `/api/community/conversations` | Danh sách hội thoại kèm số tin chưa đọc |
| POST | `/api/community/conversations` | `{ recipientId }`, mở hoặc tạo hội thoại |
| GET | `/api/community/conversations/:id/messages` | `beforeId`, `limit` để tải tin cũ hơn |
| POST | `/api/community/conversations/:id/messages` | `{ content }`, dự phòng khi socket chưa kết nối |
| POST | `/api/community/conversations/:id/read` | Đánh dấu đã đọc |

### Socket.IO

Kết nối: namespace `/community`, path `/api/socket.io`,
`auth: { token: <accessToken> }`. Không có token vẫn kết nối được để nhận bảng
tin realtime, nhưng không nhắn tin được.

Server gửi: `post:created`, `post:deleted`, `post:likes`, `comment:created`,
`comment:deleted`, `message:new`, `conversation:read`, `typing`,
`presence:snapshot`, `presence:update`.

Client gửi (có ack `{ ok, data | error }`): `message:send`
`{ conversationId, content }`, `conversation:read` `{ conversationId }`,
`typing` `{ conversationId, typing }`.

## Frontend (Next.js)

- `app/(client)/(no-auth)/cong-dong/layout.tsx` bọc mọi trang Cộng đồng bằng
  `CommunityRealtimeProvider`: mở một socket dùng chung, đổ sự kiện vào Redux,
  gửi tin qua socket và tự chuyển sang REST khi mất kết nối.
- `cong-dong/page.tsx`: bảng tin. `cong-dong/tin-nhan/page.tsx`: hộp thư.
- Redux: `store/community` (bài viết) và `store/community-chat` (hội thoại,
  tin nhắn, online, đang soạn tin).

## Chạy và triển khai

- `docker compose up` là đủ: socket chạy chung cổng 8000 với API, trình duyệt
  nối vào `/api/socket.io` cùng domain với web và Next.js chuyển tiếp sang API
  (cả WebSocket). Lệnh khởi động container tự `npm ci` lại khi
  `package-lock.json` thay đổi, nên gói `socket.io` mới được cài tự động.
- Production qua nginx: `file.nginx` có `location /api/socket.io` với header
  `Upgrade`/`Connection` để giữ kết nối WebSocket. Nhớ `nginx -t && nginx -s reload`
  sau khi cập nhật.
- Biến môi trường tuỳ chọn: `NEXT_PUBLIC_SOCKET_URL` (web, khi socket ở domain
  khác), `CORS_ORIGINS` (api, thêm origin được phép, ngăn cách bằng dấu phẩy).
