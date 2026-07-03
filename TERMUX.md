# Cài đặt trên Termux

`DrissionPage` phụ thuộc `psutil`. Bản `psutil` trên PyPI không build trực tiếp trên Android, nên cần cài `python-psutil` bằng `pkg` trước khi chạy `pip install`.

## Cài package hệ thống

```bash
pkg update
pkg install x11-repo
pkg install python clang ffmpeg chromium python-psutil python-lxml
```

Nếu cài `chromium` bị timeout, đổi mirror trước. Trong `termux-change-repo`, màn hình đầu tiên chọn repository cần đổi, hãy tick `Main repository` và `X11 repository`, sau đó mới chọn mirror kiểu `Single mirror`:

```bash
termux-change-repo
```

Chọn mirror khác, ví dụ mirror official/Grimler nếu có, rồi chạy lại với retry:

```bash
pkg clean
apt update
apt -o Acquire::Retries=5 -o Acquire::http::Timeout=60 -o Acquire::https::Timeout=60 install chromium
```

Nếu vẫn timeout, cài các gói nhỏ trước rồi cài riêng `chromium` sau:

```bash
apt -o Acquire::Retries=5 install python clang ffmpeg python-psutil python-lxml
apt -o Acquire::Retries=5 install chromium
```

Nếu menu chỉ thấy lựa chọn `Mirror group` và `Single mirror`, chọn `Single mirror`. Nếu vẫn timeout, có thể trỏ thẳng X11 repo sang Grimler:

```bash
mkdir -p $PREFIX/etc/apt/sources.list.d
cat > $PREFIX/etc/apt/sources.list.d/x11.list <<'EOF'
deb https://www.grimler.se/termux-x11 x11 main
EOF
apt update
apt -o Acquire::Retries=10 -o Acquire::http::Timeout=120 -o Acquire::https::Timeout=120 install chromium
```

## Cài nhanh

```bash
bash install_termux.sh
```

## Cài thủ công

Kiểm tra `psutil` đã được Termux nhận chưa:

```bash
python -c "import psutil; print(psutil.__version__)"
```

Không chạy `pip install DrissionPage` trực tiếp trên Termux. Hãy cài dependency trước, sau đó cài `DrissionPage` bằng `--no-deps` để pip không tự build lại `psutil` từ PyPI:

```bash
python -m pip install --upgrade pip setuptools wheel
pip install -r requirements-termux.txt
pip install DrissionPage --no-deps
```

Kiểm tra import:

```bash
python -c "import psutil, lxml, DrissionPage, pydub, speech_recognition; print('OK')"
```

## Chạy tool

```bash
python reg_accTTC.py -t 1 --browser-path "$(which chromium)"
```

Nếu không dùng Termux:X11 hoặc không có biến `DISPLAY`, script sẽ tự chạy Chromium ở chế độ headless.
