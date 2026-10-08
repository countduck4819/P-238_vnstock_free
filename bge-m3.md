Có. Khi deploy, BGE-M3 phải được chuẩn bị trên máy chủ vì FinSight dùng:

```python
SentenceTransformer(..., local_files_only=True)
```

Dockerfile không tải model tự động. Container chỉ chạy được nếu cache model đã tồn tại.

### Cần cấu hình

Model hiện tại:

```text
BAAI/bge-m3
Revision: 5617a9f61b028005a4858fdac845db406aefb181
Dimension: 1024
```

Compose đã có volume lưu cache:

```yaml
volumes:
  - finsight_hf_cache:/root/.cache/huggingface
```

Volume này giúp giữ model khi recreate container.

### Lần đầu deploy trên VPS

Sau khi build image, chạy một lần để tải model:

```bash
docker compose run --rm finsight_api \
  python -c "from sentence_transformers import SentenceTransformer; SentenceTransformer('BAAI/bge-m3', revision='5617a9f61b028005a4858fdac845db406aefb181', local_files_only=False)"
```

Lệnh này cần:

- Internet.
- Khoảng vài GB dung lượng.
- Khuyến nghị VPS tối thiểu 8 GB RAM.

Sau đó khởi động:

```bash
docker compose up -d finsight_api api web
```

### Kiểm tra model đã có

```bash
docker compose exec finsight_api \
  python -c "from sentence_transformers import SentenceTransformer; SentenceTransformer('BAAI/bge-m3', revision='5617a9f61b028005a4858fdac845db406aefb181', local_files_only=True); print('BGE-M3 OK')"
```

### Lưu ý

Không chạy:

```bash
docker compose down -v
```

vì `-v` sẽ xóa volume `finsight_hf_cache`, khiến model phải tải lại.

Qdrant Cloud chỉ lưu vector và dữ liệu; BGE-M3 vẫn cần tồn tại trên máy chạy FinSight để mã hóa câu hỏi thành vector 1024 chiều.