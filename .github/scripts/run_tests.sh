#!/usr/bin/env bash
# Chạy pytest trên các file test được truyền vào, chỉ lấy những file có trong nhánh.
# Dùng trong CI: nhánh chưa có test của một phần thì bước đó bỏ qua thay vì báo lỗi.
#   bash .github/scripts/run_tests.sh tests/test_a.py tests/test_b*.py
set -u

files=()
for pattern in "$@"; do
    for f in $pattern; do
        [ -f "$f" ] && files+=("$f")
    done
done

if [ ${#files[@]} -eq 0 ]; then
    echo "Không có file test nào trong số: $*"
    exit 0
fi

echo "Chạy: ${files[*]}"
python -m pytest -q -rs "${files[@]}"
code=$?
# Mã 5 = file có nhưng chưa có hàm test nào (file khung); không tính là lỗi
if [ "$code" -eq 5 ]; then
    echo "Các file test chưa có hàm test nào"
    exit 0
fi
exit "$code"
