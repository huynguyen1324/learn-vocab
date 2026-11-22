import re

INPUT_FILE = r"C:\Users\huy01\OneDrive\Desktop\Projects\learn-vocab\tools\toeic_vocab.md"
OUTPUT_FILE = r"C:\Users\huy01\OneDrive\Desktop\Projects\learn-vocab\tools\toeic_vocab.md"

# Header cố định
SECTION_HEADER = "Từ vựng Phiên âm Dịch nghĩa"

# Pattern: vị trí trong dòng có một entry mới bắt đầu (khoảng trắng + từ tiếng Anh + ( hoặc /)
ENTRY_START_MIDLINE = re.compile(r'\s+(?=[A-Z][a-zA-Z\s\-]+[\(/])')


def has_phonetic_no_meaning(entry: str) -> bool:
    """Kiểm tra entry có phiên âm /.../ nhưng chưa có nghĩa Việt ở cuối."""
    stripped = entry.strip()
    matches = list(re.finditer(r'/[^/]+/', stripped))
    if not matches:
        return False
    last_match = matches[-1]
    after = stripped[last_match.end():].strip()
    return after == ''


def is_new_entry(stripped: str, prev_entry: str | None = None) -> bool:
    """Kiểm tra xem dòng có phải là bắt đầu một entry mới hay không."""
    if not stripped:
        return False

    # Rule 1: Header cố định
    if stripped == SECTION_HEADER:
        return True

    # Rule 2: Category header pattern: "... (English)" (ví dụ: "Tiếp thị (Marketing)")
    # Không chứa ';' (dấu phân cách nghĩa) và không chứa '/' (phiên âm)
    if ';' not in stripped and '/' not in stripped:
        if re.match(r'.+\s*\([A-Za-z][A-Za-z\s]*\)\s*$', stripped):
            return True

    # Rule 3: Bắt đầu bằng một từ tiếng Anh và là entry start hợp lệ
    # 3a: Có phiên âm /.../
    if '/' in stripped:
        return True

    # 3b: Kết thúc bằng ( hoặc , (bịt bỏ, sẽ được tiếp tục ở dòng sau)
    if stripped.endswith('(') or stripped.endswith(','):
        return True

    # 3c: Chỉ là từ tiếng Anh (chỉ ký tự ASCII, không có dấu ngoặc)
    if re.match(r'^[A-Z][a-zA-Z\s\-]+$', stripped):
        # Nếu entry trước có phiên âm nhưng chưa có nghĩa -> dòng này là nghĩa Việt, nối vào trước
        if prev_entry is not None and has_phonetic_no_meaning(prev_entry):
            return False
        return True

    return False


def split_merged_entries(line: str) -> list[str]:
    """Tách một dòng chứa nhiều entry thành các entry riêng lẻ."""
    stripped = line.strip()
    if not stripped:
        return []

    matches = list(ENTRY_START_MIDLINE.finditer(stripped))

    if not matches:
        return [stripped]

    parts = []
    prev_end = 0
    for m in matches:
        start = m.start()
        parts.append(stripped[prev_end:start].strip())
        prev_end = start + 1  # bỏ qua khoảng trắng

    parts.append(stripped[prev_end:].strip())

    return [p for p in parts if p]


def fix_phonetic_spaces(text: str) -> str:
    """Loại bỏ khoảng trắng lẻ trong các đoạn phiên âm /.../ (ví dụ: 'n t/' -> 'nt/', 'mə nt/' -> 'mənt/')."""
    def fix_one(m: re.Match) -> str:
        ph = m.group(0)
        # Xóa khoảng trắng trước 1 ký tự đơn rồi slash đóng: ' X/' -> 'X/'
        ph = re.sub(r' (\S)/', r'\1/', ph)
        # Xóa khoảng trắng trước đoạn 'nt/' (tên loại phổ biến bị tách): ' nt/' -> 'nt/'
        ph = ph.replace(' nt/', 'nt/')
        return ph
    return re.sub(r'/[^/]+/', fix_one, text)


def fix_file():
    with open(INPUT_FILE, "r", encoding="utf-8") as f:
        lines = f.readlines()

    # Bước 1: Tách các entry bị gộp trong cùng một dòng
    raw_entries = []
    for line in lines:
        stripped = line.strip()
        if not stripped:
            continue
        parts = split_merged_entries(stripped)
        raw_entries.extend(parts)

    print(f"Sau khi tách merged entries: {len(raw_entries)} entries")

    # Bước 2: Ghép các dòng liên tiếp (continuation) vào entry trước
    entries = []
    current = None
    prev_entry = None

    for entry in raw_entries:
        if is_new_entry(entry, prev_entry):
            if current is not None:
                entries.append(current)
            current = entry
        else:
            if current is not None:
                current += " " + entry
            else:
                current = entry
        prev_entry = entry

    if current is not None:
        entries.append(current)

    print(f"Sau khi ghép continuation: {len(entries)} entries")

    # Bước 3: Post-processing - xóa phiên âm, thay bằng dấu hai chấm
    fixed_entries = []
    for entry in entries:
        # Thay tat ca cac doan /.../ boi dau hai chấm
        entry = re.sub(r'\s*/[^/]+/', ':', entry)
        # Lam sach cac truong hop co hai phien am lien nhau
        entry = entry.replace(': :', ':').replace(': ;', ';').replace('; :', ';')
        # Chuan hoa khoang trang xung quanh dau hai chấm
        entry = re.sub(r'\s+:\s+', ': ', entry)
        # Chuan hoa khoang trang (nhieu khoang trang -> 1)
        entry = re.sub(r' +', ' ', entry)
        entry = entry.strip()
        fixed_entries.append(entry)

    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        for entry in fixed_entries:
            f.write(entry + "\n")

    print(f"Tổng số entry cuối: {len(fixed_entries)}")
    print(f"Đã ghi file: {OUTPUT_FILE}")


if __name__ == "__main__":
    fix_file()
