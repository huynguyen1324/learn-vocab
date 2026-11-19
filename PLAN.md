# Các việc còn cần làm

> Tuân thủ SPEC.md; AI không được sửa SPEC.md. Chỉ dùng tên repetition_level, giữ thang 0–8 và dữ liệu học hiện có; không chuyển đổi sang thang 0–7.

## 1. Nhóm ôn tập trung tối đa 100 từ

- Mục đích: khi có hàng trăm từ đến hạn, tập trung vào một nhóm vừa sức thay vì ôn lan man. Đây là giới hạn nhóm đang giữ, không phải tổng số từ được phép học trong ngày.
- Thay cache RAM hiện tại bằng nhóm ID lưu trong SQLite hiện có, dùng chung cho trắc nghiệm và lật thẻ; không lưu song song bằng file JSON hoặc cache RAM.
- Lưu ngày của nhóm theo giờ máy chạy server. Restart trong cùng ngày giữ nguyên nhóm; ở request ôn đầu tiên khi sang ngày mới thì reset nhóm cũ.
- Chỉ sau khi lưu kết quả ôn thành công: nếu lịch tiếp theo vẫn trong ngày thì thêm/giữ ID trong nhóm; nếu sang ngày khác hoặc đã hoàn thành thì bỏ ID. Cập nhật kết quả và nhóm trong cùng giao dịch.
- Ưu tiên từ trong nhóm đã đến hạn; không ôn trước hạn. Nếu nhóm chưa đủ 100 ID, lấy thêm từ đến hạn ngoài nhóm, tối đa bằng số chỗ trống.
- Nếu nhóm đủ 100 ID nhưng chưa từ nào đến hạn thì chờ, không lấy thêm từ ngoài nhóm.
- Mỗi lượt chỉ lấy các từ trong nhóm đã đến hạn và số từ ngoài nhóm không vượt số chỗ trống lúc bắt đầu. Có thêm chỗ trống thì bắt đầu lượt tiếp theo để nhận thêm từ, không tải sẵn hàng trăm từ ngoài nhóm.
- Chỉ một lượt ôn hoạt động trên toàn app: bắt đầu quiz hoặc flashcard mới thay thế lượt cũ, kể cả ở tab khác; lượt cũ không được tiếp tục ghi kết quả.
- Xóa từ hoặc đánh dấu hoàn thành phải loại ID khỏi nhóm; không để ID không còn hợp lệ chiếm chỗ.

## 2. Hoàn tất việc bỏ tùy chọn hoàn thành ngay khi thêm từ

- Checkbox đã được bỏ khỏi HTML nhưng JavaScript vẫn truy cập #complete-option-label và #complete-option, gây lỗi khi mở form Thêm/Sửa. Xóa các tham chiếu còn sót để form hoạt động lại.
- Từ mới luôn có repetition_level = 0, practice_count = 0 và đến hạn ngay; không cho đánh dấu hoàn thành ngay trong form thêm từ.

## 3. Đồng bộ luật ôn với SPEC.md

### Mức thông thạo và lịch ôn

- Giữ repetition_level trong khoảng 0–8; mức 8 là hoàn thành và không còn lịch ôn. Không thay đổi hàng loạt mức, số lần ôn hoặc lịch đang lưu trong database.
- Sau mỗi kết quả ôn được lưu, tính lịch tiếp theo từ thời điểm trả lời theo repetition_level sau khi chấm, bất kể đúng, sai, hết giờ hay nhớ tương đối:

| repetition_level sau khi chấm | Lịch tiếp theo |
| --- | --- |
| 0 | Sau 1 giờ |
| 1 | Sau 1 giờ |
| 2 | Sau 1 ngày |
| 3 | Sau 3 ngày |
| 4 | Sau 1 tuần |
| 5 | Sau 1 tháng |
| 6 | Sau 3 tháng |
| 7 | Sau 1 năm |
| 8 | Hoàn thành, không có lịch tiếp theo |

- Ngoại lệ: repetition_level = 0 và practice_count = 0 là từ chưa từng ôn, phải đến hạn ngay, không bắt chờ 1 giờ.

### Đếm giờ và chấm kết quả chung cho quiz/flashcard

- Bắt đầu đo khi câu hỏi/thẻ sẵn sàng tương tác, không tính thời gian chờ API chuẩn bị câu hỏi.
- Quiz đo đến lúc chọn đáp án; flashcard đo đến lúc lật thẻ, sau đó người học tự đánh giá.
- Đúng trong <= 3 giây: +2 mức; đúng trong > 3 đến <= 7 giây: +1; đúng trong > 7 đến <= 15 giây: giữ mức.
- Sai hoặc quá 15 giây: dừng giờ và -1 mức. Giới hạn kết quả trong khoảng 0–8.
- Quá 15 giây: quiz tự hiện đáp án, flashcard tự lật; ghi kết quả hết giờ, không cho đổi thành đúng hoặc nhớ tương đối. Chỉ cho chuyển tiếp sau khi lưu thành công.
- Giữ nút Nhớ tương đối: không đổi repetition_level nhưng vẫn tính lại lịch theo bảng trên; chỉ chọn được sau khi tự lật thẻ trong thời hạn.
- Giữ nút Đã biết: chỉ cho chọn nếu lật thẻ trong <= 2 giây; đánh dấu mức 8, bỏ lịch ôn và loại khỏi nhóm.

## 4. Kiểm tra sau khi sửa

- Kiểm tra form Thêm/Sửa mở và lưu được, không còn phụ thuộc checkbox đã xóa.
- Kiểm tra nhóm dùng chung, đủ/chưa đủ 100 ID, thêm/bỏ sau trả lời, không vượt giới hạn, lượt cũ bị thay thế và ID bị xóa/hoàn thành.
- Kiểm tra restart cùng ngày giữ nhóm và chuyển ngày reset nhóm theo giờ server.
- Kiểm tra các biên thời gian 3, 7, 15 giây; đúng/sai/hết giờ/nhớ tương đối; giới hạn mức 0–8 và ngoại lệ từ chưa học.
- Giữ hành vi đã đúng theo SPEC.md: đánh dấu đỏ khi practice_count - repetition_level >= 3; kiểm tra lại để tránh hồi quy.
