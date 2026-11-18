# Kế hoạch chuyển từ học từ riêng lẻ sang học câu ví dụ

## Trạng thái và quyết định chính

- Đã gỡ toàn bộ triển khai sinh/chuyển đổi example theo yêu cầu người dùng. Các nội dung bên dưới chỉ là bản ghi yêu cầu cũ, không phải chức năng đang có hoặc kế hoạch tiếp tục triển khai.
- Không thay đổi hoặc khôi phục DB trong lượt gỡ chức năng.

- Đã làm rõ và xác nhận: đơn vị học mới là **một câu ví dụ tiếng Anh và bản dịch tiếng Việt**, không phải một collocation verb + noun cho mỗi từ.
- AI ưu tiên kết hợp các từ có sẵn trong DB vào một câu tự nhiên; các mục nguồn cùng câu được hợp nhất thành một mục học.
- **Chấp nhận bỏ toàn bộ tiến trình học cũ. Mọi câu sau chuyển đổi bắt đầu ở `repetition_count = 0` (0/8) và đến hạn ngay**, kể cả khi nguồn là từ đã hoàn thành hoặc câu chỉ dùng một mục nguồn.
- Giữ giải pháp nhỏ, phù hợp ứng dụng cá nhân; không tối ưu ghép từ toàn cục, không xử lý dùng web/chỉnh sửa DB đồng thời khi chuyển đổi.

## 1. Lật thẻ: giới hạn nút “Đã biết”

- Đo từ lúc hiện mặt trước đến lúc lật thẻ, không đo đến lúc bấm nút đánh giá.
- Lật trong **≤ 2 giây** thì được chọn “Đã biết”; đây cũng là ngưỡng cộng 2 `repetition_count` nếu chọn “Nhớ đúng”.
- Lật sau 2 giây thì không được chọn “Đã biết”.
- Lật trong ngưỡng hợp lệ thì nút vẫn được phép chọn sau khi đọc mặt sau.
- Không thay đổi các quy tắc chấm flashcard khác.

## 2. Đơn vị học và cách sinh câu

- Dùng lại các trường hiện có: `english` lưu câu tiếng Anh, `vietnamese` lưu bản dịch toàn câu; `english_key` chống trùng câu theo cách chuẩn hóa hiện tại.
- Danh sách, flashcard và trắc nghiệm dùng câu thay cho từ. Không thêm bảng example, không giữ các thẻ từ riêng đã được hợp nhất.
- AI chọn nhóm mục nguồn phù hợp và sinh **một câu chung cho nhóm**, thay vì sinh độc lập cho từng từ rồi chờ trùng câu.
- Mỗi mục nguồn thuộc một nhóm trong một lượt chuyển đổi; không xử lý lại mục đã được bao phủ bởi câu đã sinh thành công.
- Ưu tiên tận dụng từ/cụm có sẵn trong DB, nhưng không ép nhét nhiều từ và không cần tối đa hóa số từ ghép vào câu.
- Câu ngắn, tự nhiên, đúng ngữ pháp; có thể là S + V, S + V + O, S + V + O + trạng ngữ. Đây là ví dụ, không phải khuôn cứng.
- Được thêm từ bổ trợ, từ nối và biến đổi ngữ pháp/chia động từ để câu tự nhiên.
- Dựa vào nghĩa tiếng Việt đầu vào để dùng đúng nghĩa. Nếu mục có nhiều nghĩa, chọn một nghĩa phù hợp trong số đó; không tự đổi sang nghĩa ngoài đầu vào.
- Ưu tiên ngôn ngữ/ngữ cảnh thông dụng, phù hợp IELTS/TOEIC; không khẳng định câu từng xuất hiện trong đề thật nếu không có nguồn kiểm chứng.
- Không ghép được với mục khác thì tạo câu riêng. Nếu không tạo được câu phù hợp thì đánh dấu cần xem lại, không cố sinh câu gượng ép.

Ví dụ:

```text
Nguồn:
- employee / nhân viên
- submit / nộp
- report / báo cáo

Một mục học sau chuyển đổi:
The employee submits the report.
Nhân viên nộp báo cáo.
repetition_count = 0, đến hạn ngay
```

Ba mục nguồn được thay bằng một mục câu; tiến độ cũ không được giữ lại.

## 3. Cấu hình và kiểm tra API AI

- Các script tự gọi API tương thích OpenAI.
- Đọc `BASE_URL`, `API_KEY`, `MODEL` từ `config.json`, bên cạnh cấu hình host/port hiện có.
- Không in API key ra log, không đưa cấu hình chứa key thật lên Git.
- Thêm `check_models.py`: dùng `BASE_URL`, `API_KEY` gọi endpoint danh sách model và hiển thị ID model; báo rõ nếu nhà cung cấp không hỗ trợ endpoint này.
- Thêm `test_prompt.py`: dùng cả ba giá trị cấu hình để gửi lời nhắn `Hello`, in phản hồi hoặc lỗi.
- Hai script kiểm tra API không chạm DB.

## 4. Sinh kết quả, xem trước và chạy tiếp

- Tách **sinh kết quả** và **áp dụng kết quả đã duyệt**. Bước sinh không thay đổi DB; bước áp dụng dùng file đã duyệt, không gọi AI lại.
- Lưu bản xem trước JSON gồm các mục nguồn (ID DB nếu có, tiếng Anh/nghĩa gốc), câu tiếng Anh, bản dịch và trạng thái thành công/lỗi/cần xem lại/xung đột.
- Bản xem trước thể hiện rõ nhóm mục sẽ bị thay thế/xóa khi hợp nhất và việc reset tiến độ về 0/8.
- Người dùng có thể xem, chỉnh sửa trước khi áp dụng. Chỉ áp dụng nhóm đã duyệt và hợp lệ; mục lỗi/chưa được duyệt giữ nguyên trong DB, không âm thầm xóa hoặc reset.
- Xử lý tuần tự từng nhóm; lưu sau mỗi kết quả thành công, ghi nhận các mục nguồn đã dùng để chạy tiếp không bị lặp nhóm.
- Lỗi tạm thời thử lại tối đa 3 lần; vẫn lỗi thì ghi lỗi và tiếp tục.
- Chạy lại dùng kết quả thành công đã lưu, chỉ xử lý mục còn thiếu/lỗi để tránh gọi API tốn phí lặp lại.

## 5. Nhập dữ liệu mới

Tên script dự kiến: `transform_vocab_into_examples_and_import.py` (thay tên dự kiến chứa `collocation`, chưa tạo file).

- Đọc các cặp tiếng Anh / nghĩa tiếng Việt từ `input_vocab.txt`, đồng thời tham khảo các mục có sẵn trong DB để ghép câu.
- Được ghép từ mới với mục đang học trong DB. Bản xem trước phải chỉ rõ những mục DB bị ảnh hưởng.
- Nếu DB đã có câu phù hợp thì ưu tiên dùng lại câu đó, không viết lại tùy tiện.
- Khi áp dụng, nhóm nguồn được thay bằng một câu, bắt đầu ở 0/8 và đến hạn ngay, kể cả mục DB được dùng lại/hợp nhất.
- Không reset những mục DB không tham gia lượt nhập mới.
- **Giữ nguyên `import_vocab.py` cũ** để nhập không qua AI; người dùng có thể tự xóa sau.

## 6. Chuyển toàn bộ DB hiện có sang câu

Tên script dự kiến: `upgrade_db_vocab_to_examples.py` (thay tên dự kiến chứa `collocation`, chưa tạo file).

- Đưa tất cả các mục DB vào phạm vi chuyển đổi, kể cả mục đã hoàn thành.
- Nhóm các mục nguồn, sinh câu chung và bản dịch theo mục 2; tạo bản xem trước trước khi áp dụng.
- Mỗi nhóm được duyệt thay các mục nguồn bằng một mục câu. Không giữ thẻ từ riêng hay lịch/tiến độ học cũ của nhóm đó.
- Tất cả câu đầu ra có `repetition_count = 0`, `next_review_at` là thời điểm áp dụng; từ đã hoàn thành cũng bắt đầu học lại dưới dạng câu.
- Mục lỗi/chưa duyệt tạm giữ nguyên để xử lý tiếp; chỉ coi chuyển đổi toàn bộ hoàn tất khi không còn mục nguồn chưa xử lý.

## 7. Hợp nhất và câu trùng

- Nhóm nguồn có chung câu example được hợp nhất thành **một hàng câu duy nhất**. Không cần chọn theo tiến độ cũ vì mọi câu đều reset về 0/8.
- Chống trùng theo câu tiếng Anh đã chuẩn hóa khóa không phân biệt hoa thường, tương thích `english_key` hiện tại.
- Các nhóm sinh cùng câu và bản dịch tương đương được gộp; danh sách mục nguồn trong bản xem trước phải bao phủ các mục bị thay thế.
- Cùng câu nhưng bản dịch khác nghĩa thì đánh dấu xung đột để sửa/chọn trước khi áp dụng; không âm thầm bỏ một nghĩa.
- Không cần thêm cơ chế bảo tồn ID hay lịch sử tiến độ cũ; ưu tiên cách cập nhật/gộp đơn giản, không mất mục nguồn ngoài nhóm đã duyệt.

## 8. Áp dụng DB: bảo vệ tối giản

- Không dùng web/chỉnh sửa DB trong lúc chuyển đổi; đóng ứng dụng trước khi chuyển đổi, mở lại sau khi xong.
- Tự sao lưu DB trước mỗi lượt áp dụng.
- Ghi trong một transaction: thành công thì commit, lỗi ghi DB thì rollback toàn bộ lượt ghi.
- Không xây đối chiếu phiên bản, phát hiện chỉnh sửa đồng thời hay xử lý trường hợp vừa học vừa chuyển đổi.
- Báo cáo số mục nguồn được chuyển đổi, số câu đầu ra, số mục được hợp nhất, mục chưa duyệt/cần xem lại và lỗi.
