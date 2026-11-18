# Học từ vựng

Ứng dụng web localhost tối giản để quản lý và ôn từ vựng Anh–Việt. Khi thêm từ, có thể đánh dấu hoàn thành ngay; từ hoàn thành có thể được đặt lại mốc 1 để học lại sau khi xác nhận.

## Chạy ứng dụng

```powershell
python -m pip install -r requirements.txt
# Chỉ cần khi chưa có config.json; không ghi đè cấu hình đang dùng.
Copy-Item config.example.json config.json
python app.py
```

Mở http://127.0.0.1:5000. Cơ sở dữ liệu SQLite được tạo tự động tại `instance/vocabulary.sqlite3`.
Host và port được đọc từ `config.json`; cấu hình ban đầu là `127.0.0.1:5000`.

### Mở trên điện thoại cùng mạng Wi-Fi

Trong `config.json`, đổi host thành `0.0.0.0` và đặt port muốn dùng, ví dụ:

```json
{
  "VOCAB_HOST": "0.0.0.0",
  "VOCAB_PORT": 5000
}
```

Khởi động lại bằng `python app.py`. Chạy `ipconfig` để tìm địa chỉ IPv4 của máy tính, rồi mở `http://<địa-chỉ-IPv4>:<VOCAB_PORT>` trên điện thoại đang dùng cùng Wi-Fi. Nếu Windows Firewall hỏi, chỉ cho phép truy cập trên mạng riêng (Private). Để quay lại chỉ truy cập trên máy tính, đặt host thành `127.0.0.1`.

Ứng dụng chưa có đăng nhập; chỉ dùng trên mạng tin cậy và không cấu hình router để mở cổng này ra Internet.

Có thể thêm từ trong giao diện. Nếu nạp dữ liệu trực tiếp vào SQLite, bảng `vocabulary` gồm `english`, `english_key`, `vietnamese`, `repetition_count` và `next_review_at`. `english_key` phải là `english.casefold()` để ngăn từ tiếng Anh trùng nhau; từ mới có `repetition_count = 0` và `next_review_at` là giờ địa phương theo định dạng `YYYY-MM-DDTHH:MM:SS`. Từ `Hoàn thành` có `repetition_count = 8` và `next_review_at = NULL`.

Khi khởi động ứng dụng, schema cũ dùng cột `stage` được tự động nâng cấp sang `repetition_count` và giữ lịch ôn hiện tại. Để viết thường các từ đã lưu trước đây, chạy một lần:

```powershell
python migrate_lowercase.py
```

Để nạp [input_vocab.txt](./input_vocab.txt) vào SQLite, chạy:

```powershell
python import_vocab.py
```

Importer cũ ghép các dòng không rỗng theo cặp (tiếng Anh rồi nghĩa tiếng Việt), bỏ khoảng trắng đầu/cuối, lưu chữ thường và đặt từ mới đến hạn ngay. Chạy lại bỏ qua từ đã có mà không ghi đè tiến độ. Script này vẫn được giữ để nhập không qua AI.

Ví dụ thêm một từ mới bằng SQL:

```sql
INSERT INTO vocabulary (english, english_key, vietnamese, repetition_count, next_review_at)
VALUES ('apple', 'apple', 'quả táo', 0, strftime('%Y-%m-%dT%H:%M:%S', 'now', 'localtime'));
```

## Kiểm thử

```powershell
python -m unittest discover -s tests -v
```
