- Thêm trường english_pattern, synonym_pattern cho bảng synonymous_pattern
- Chọc vào DB, với mỗi cặp english, synonym, nếu có chung chuỗi gì thì thay bằng dấu "..." rồi bỏ vào english_pattern, synonym_pattern
Ví dụ:
    english, synonym là take a bus là catch a bus thì english_pattern, synonym_pattern là take ..., catch ...
    english, synonym là have a problem with a credit card, a credit card is not working thì english_pattern, synonym_pattern là have a problem with ..., ... is not working
- Ôn trắc nghiệm, chỉ với synonymous_collocations thì dùng english_pattern, synonym_pattern, còn collocations và vocabulary thì giữ nguyên cơ chế