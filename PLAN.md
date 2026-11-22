# Kế hoạch triển khai

## Mục tiêu
Đưa hành vi ôn quiz và flashcard khớp SPEC.md và các quyết định đã chốt trong hội thoại, đồng thời xử lý ba lỗi kỹ thuật đã thống nhất. Không sửa SPEC.md.

## Quy tắc đã chốt
- Từ mới lần đầu (`repetition_level = 0`, `practice_count = 0`) trong flashcard tự hiện mặt sau ngay, không cần thao tác lật; đây là ngoại lệ so với thẻ thường.
- Flashcard từ mới có bốn lựa chọn: nhớ đúng +2, nhớ tương đối +1, nhớ sai +0, đã biết lên mức 8. Trả lời sai vẫn lên lịch ôn sau 1 giờ.
- Flashcard từ mới không tự timeout: chờ người học chọn kết quả; vẫn ghi nhận một lần ôn khi thẻ hiển thị.
- Hai nút “Đã biết” ở quiz và flashcard dùng chung quy tắc: chỉ hợp lệ nếu hoàn tất trong tối đa 3 giây tính từ lúc câu/thẻ được hiển thị.
- Không thay đổi các quy tắc lịch ôn, ưu tiên từ cũ, ngưỡng từ khó hoặc cách chấm các trường hợp khác đã khớp SPEC.

## Các bước
1. **Tách trạng thái từ mới khỏi trạng thái ôn thường ở backend.** Dùng practice_count trước khi tăng làm dữ kiện ổn định (không suy ra bằng `practice_count - 1` cho mọi tình huống); trả thông tin cần thiết trong dữ liệu thẻ. Khi chấm flashcard, áp dụng đúng các thay đổi mức riêng cho từ mới và lịch 1 giờ ở mức 0. Giữ tính nguyên tử của tăng số lần ôn và lưu kết quả.
2. **Đồng bộ giao diện flashcard.** Với từ mới, hiện ngay mặt sau, bật bốn nút kết quả mà không yêu cầu lật, và không khởi chạy timeout tự động. Với thẻ thường, giữ luồng lật và thời hạn hiện có. Chỉ cho “Đã biết” khi thời gian từ lúc hiển thị đến lúc bấm không quá 3 giây.
3. **Đồng bộ nút “Đã biết” giữa quiz và flashcard.** Gửi thời gian phản hồi cho quiz completion; backend xác nhận round hiện hành, đúng từ/câu đã hiện và câu trả lời đúng, đồng thời xác minh mốc 3 giây. Áp dụng cùng giới hạn thời gian đến lúc xác nhận cho flashcard. Đảm bảo một request lặp lại không làm hỏng kết quả đã lưu.
4. **Gia cố chống trùng khi ghi đồng thời.** Duy trì kiểm tra trùng thân thiện ở tầng ứng dụng, nhưng dựa vào ràng buộc/index duy nhất phù hợp ở SQLite và xử lý xung đột ghi thành HTTP 409. Giữ quy tắc chuẩn hóa chữ hoa/thường hiện có và kiểm tra cả lúc thêm lẫn sửa.
5. **Thêm regression tests.** Bao phủ: flashcard từ mới tự mở và đủ bốn lựa chọn; các mức +2/+1/+0/8 cùng lịch 1 giờ; không timeout tự động; thẻ thường vẫn giữ hành vi cũ; quy tắc 3 giây đồng nhất ở quiz/flashcard; chặn hoàn thành quiz cho từ khác/chưa hiện; và xung đột thêm/sửa đồng thời.
6. **Chạy kiểm chứng.** Chạy toàn bộ unittest và `node tests/test_frontend.js`; xem lại diff để đảm bảo chỉ thay đổi gắn với các mục trên và không sửa SPEC.md.

## Ngoài phạm vi
- Không đổi thiết kế giao diện ngoài các trạng thái bắt buộc của flashcard từ mới.
- Không thêm thư viện hoặc framework.
- Không sửa nội dung SPEC.md.
