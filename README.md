# Learn Vocab

Ứng dụng web học cụm từ tiếng Anh – Việt.

- **Quản lý cụm từ:** Thêm, sửa, xóa và chống trùng để xây dựng kho từ cá nhân.
- **Tìm, lọc và sắp xếp:** Tra cứu Anh/Việt,` lọc lịch ôn, sắp theo mức thông thạo hoặc số lần ôn để chọn từ cần học.
- **Trắc nghiệm hai chiều:** Chọn 1 trong 8 đáp án Anh–Việt hoặc Việt–Anh để kiểm tra khả năng nhớ nghĩa.
- **Lật thẻ hai chiều:** Tự đánh giá mức nhớ trong 10 giây để luyện phản xạ và điều chỉnh mức thông thạo theo tốc độ trả lời.
- **Ôn cách quãng:** Tự lên lịch ôn theo kết quả và mức thông thạo 0–8 để củng cố trí nhớ dài hạn.
- **Ưu tiên ôn từ cũ:** Từ đã ôn và đến hạn được đưa lên trước từ mới để tránh học lan man khi còn từ cũ chưa ôn xong.
- **Theo dõi tiến độ:** Hiển thị mức thông thạo, số lần ôn và lịch ôn tiếp theo để nắm tình trạng từng cụm từ.
- **Hoàn thành và học lại:** Đánh dấu từ đã biết hoặc khởi động lại từ đã hoàn thành để chủ động quản lý việc ôn.
- **AI tạo cụm từ (script):** Chuyển danh sách từ thành cụm từ kèm nghĩa Việt, theo hồ sơ cá nhân để học sát nhu cầu.
- **Nhập hàng loạt (script):** Nạp các cặp Anh–Việt từ tệp văn bản, bỏ qua từ trùng để bổ sung kho học nhanh.
- **Xuất dữ liệu cũ (script):** Xuất bảng vocabulary cũ ra văn bản để chuyển sang quy trình học cụm từ.

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
