- Dán dữ liệu thô các từ vựng vào file input_vocab.txt
- Chạy transform_vocab.py với input_vocab.txt, đầu ra là output_vocab.txt và incorrect_input_vocab.txt
    + Tách các dòng, mỗi 2 dòng tạo thành 1 cặp english:vietnamese
    + Xét từng cặp:
        -- Nếu dòng english chứa ký tự khác ngoài chữ cái, dấu () thì không hợp lệ
        -- Nếu dòng vietnamese chỉ chứa chữ cái, dấu ",", dấu "/" thì không hợp lệ
        -- Với từ hợp lệ, tách phần đầu tiên trước dấu "," hoặc dấu "/" ra, rồi ghép english với phần tách của vietnamese lại, rồi ghép vào output_vocab.txt.
        -- Với từ ko hợp lệ, ghép english với vietnamese lại, bỏ vào input_vocab_error.txt
        -- Ví dụ: 
            advancement / advance (n)
            sự tiến bộ, bước tiến
            Thì bỏ vào input_vocab_error.txt dòng "advancement / advance (n) : sự tiến bộ, bước tiến"
            anticipate (v)
            mong đợi, đón chờ
            Thì ghép vào output_vocab.txt dòng "anticipate : mong đợi"
- Chạy transform_incorrect_vocab.py với incorrect_input_vocab.txt
    + Gọi AI đọc toàn bộ file biến đổi theo 1 quy tắc cụ thể, rồi ghép vào output_vocab.txt
    Ví dụ: 
        "advancement / advance (n) : sự tiến bộ, bước tiến" thì kỳ vọng AI biến đổi thành 2 dòng "advancement : sự tiến bộ" và "advance : sự tiến bộ"
        "distribute (v) / distribution (n) : phân phát / sự phân phối, cấp phát" thì kỳ vọng AI biến đổi thành 2 dòng "distribute : phân phát" và "distribution : sự phân phát"
        Rồi ghép 4 dòng đó vào output_vocab.txt
- Chạy sort_output_vocab.py, sắp xếp lại các dòng theo thứ tự từ điển bằng thuật toán sắp xếp chèn. Bởi vì sau này khi số lượng vocab rất lớn, nếu thêm 1 vài output_vocab mới vào rồi sắp xếp lại, dùng sắp xếp chèn sẽ nhanh nhất.
- Chạy analyze_output_vocab.py, tạo ra analyze_output_vocab.txt, thống kê các từ và tần suất xuất hiện, xếp theo thứ tự tần suất giảm dần. Mục đích để xem thủ công vocab nào xuất hiện nhiều lần trong output_vocab.txt, nếu thấy có nghĩa tiếng việt lặp lại thì xoá bớt, nghĩa tiếng việt khác nhau thì giữ lại. Bởi vì 1 từ tiếng anh có thể có nhiều nghĩa tiếng việt


