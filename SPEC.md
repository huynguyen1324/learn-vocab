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

Ôn trắc nghiệm và ôn lật thẻ đều dùng chung cơ chế đếm giờ
- Trả lời (nhớ) đúng trong <= 3s cộng 2 repetition_level
- Trả lời (nhớ) đúng trong <= 7s cộng 1 repetition_level
- Trả lời (nhớ) trong <= 15s cộng 0 repetition_level
- Sau 15s hoặc trả lời (nhớ) sai thì ngừng đếm giờ và -1 repetition_level

Ôn lật thẻ, nếu nhớ tương đối thì giữ nguyên repetition_level

Đánh dấu cụm từ khó:
- Từ nào có practice_count - repetition_level >= 3 thì đánh dấu đỏ cho từ