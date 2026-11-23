# Learn Vocab

Ứng dụng web hỗ trợ học tiếng Anh qua cụm từ, cụm từ đồng nghĩa và từ vựng, kèm nghĩa tiếng Việt.

- **Quản lý nội dung học:** Thêm, sửa, xóa, tìm kiếm, lọc và sắp xếp các mục trong từng danh sách.
- **Luyện tập:** Ôn bằng trắc nghiệm hoặc thẻ ghi nhớ, theo cả hai chiều Anh–Việt và Việt–Anh; cụm từ đồng nghĩa có thể luyện theo mẫu cụm từ.
- **Ôn tập cá nhân hóa:** Theo dõi tiến độ và lịch ôn cách quãng dựa trên kết quả luyện tập.
- **Thống kê:** Xem tổng quan tiến độ riêng cho từng danh sách.
- **Nhập dữ liệu:** Hỗ trợ nhập hàng loạt nội dung học từ tệp để xây dựng danh sách cá nhân.

## Cài đặt và chạy

Cần Python 3.10 trở lên. Ứng dụng lưu dữ liệu trong SQLite tại `instance/vocabulary.sqlite3`; không cần cài hoặc chạy server cơ sở dữ liệu. Các lệnh dưới đây chạy tại thư mục dự án.

### Windows (PowerShell)

```powershell
py -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
Copy-Item config.example.json config.json
```

Nếu PowerShell chặn kích hoạt môi trường ảo, chạy `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned` một lần rồi mở lại PowerShell.

### Linux

```bash
sudo apt update
sudo apt install -y python3 python3-venv
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
cp config.example.json config.json
```

### Android (Termux)

Cài Termux từ F-Droid hoặc GitHub, mở Termux rồi chạy:

```bash
pkg update
pkg install -y python git
```

Vào thư mục dự án (hoặc clone repo), sau đó:

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
cp config.example.json config.json
```

### Cấu hình và khởi chạy (cả ba môi trường)

Nếu cần, sửa `VOCAB_HOST`/`VOCAB_PORT` trong `config.json` để chọn địa chỉ và cổng lắng nghe. Không cần cấu hình database; ứng dụng tự tạo hoặc dùng lại `instance/vocabulary.sqlite3`.

Trong môi trường ảo đã kích hoạt, khởi chạy:

```bash
python app.py
```

Mở <http://127.0.0.1:5000> trên thiết bị.
