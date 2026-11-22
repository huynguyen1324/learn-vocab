(Cấm AI sửa file SPEC.md)

Các mức thông thạo repetition:
- Để đạt mức 1: Ôn ngay được
- Để đạt mức 2: Ôn sau 1 giờ từ lúc đạt mức 1
- Để đạt mức 3: Ôn sau 1 ngày từ lúc đạt mức 2
- Để đạt mức 4: Ôn sau 3 ngày từ lúc đạt mức 3
- Để đạt mức 5: Ôn sau 1 tuần từ lúc đạt mức 4
- Để đạt mức 6: Ôn sau 1 tháng từ lúc đạt mức 5
- Để đạt mức 7: Ôn sau 3 tháng từ lúc đạt mức 6
- Để đạt mức hoàn thành: Ôn sau 1 năm từ lúc đạt mức 7

Ôn trắc nghiệm và ôn lật thẻ đều dùng chung cơ chế đếm giờ.
- Với từ có repetition_level > 0 (từ đã nhớ cần ôn lại)
    + Trả lời (nhớ) đúng trong <= 5s thì cộng 1 repetition_level
    + Trả lời (nhớ) trong <= 10s cộng 0 repetition_level (đã ôn nhiều lần mà vẫn mất > 5s để nhớ đúng thì cần phải duy trì tần suất ôn)
    + Sau 10s thì coi như không nhớ vì đi thi thời gian có hạn. Sau 10s hoặc trả lời (nhớ) sai thì ngừng đếm giờ và -1 repetition_level (đã ôn nhiều lần mà vẫn không nhớ hoặc nhớ sai thì phải đẩy mạnh tần suất ôn)
- Với từ có repetition_level = 0 và practice_count = 0 (từ ôn lần đầu)
    + Trả lời (nhớ) đúng trong <= 5s cộng 2 repetition_level (từ dễ, nhưng không đến mức quá dễ để chọn "Đã biết")
    + Trả lời (nhớ) trong <= 10s cộng 1 repetition_level
    + Sau 10s hoặc trả lời (nhớ) sai thì ngừng đếm giờ và giữ nguyên repetition_level
- Với từ có repetition_level = 0 và practice_count > 0 (từ có nguy cơ khó ôn)
    + Trả lời (nhớ) đúng trong <= 10s cộng 1 repetition_level
    + Sau 10s hoặc trả lời (nhớ) sai thì ngừng đếm giờ và giữ nguyên repetition_level
- Ưu tiên chọn từ các từ có practice_count > 0 và đến hạn để ôn, rồi mới chọn đến các từ mới toanh có practice_count = 0, tránh việc từ cũ chưa thạo đã ôm thêm từ mới

Ôn lật thẻ:
- Nếu nhớ đúng trong <= 3s thì mở khoá quyền chọn "Đã biết", còn không thì khoá lại
- Nếu nhớ tương đối thì chọn "Nhớ tương đối" giữ nguyên repetition_level. 
- Nếu từ quá dễ thì chọn "Đã biết" để không phải ôn nữa

Đánh dấu cụm từ khó ôn:
- Từ nào có practice_count - repetition_level >= 3 thì đánh dấu đỏ cho từ