# Cài đặt trên Termux

`DrissionPage` phụ thuộc `psutil`. Bản `psutil` trên PyPI không build trực tiếp trên Android, nên cần cài `python-psutil` bằng `pkg` trước khi chạy `pip install`.

## Cài package hệ thống

```bash
pkg update
pkg install x11-repo
pkg install python clang ffmpeg chromium python-psutil python-lxml
```

## Cài package Python

```bash
python -m pip install --upgrade pip setuptools wheel
pip install -r requirements.txt
```

Nếu `pip` vẫn cố build `psutil`, kiểm tra `psutil` đã được Termux nhận chưa:

```bash
python -c "import psutil; print(psutil.__version__)"
```

Sau đó chạy lại:

```bash
pip install -r requirements.txt
```

## Chạy tool

```bash
python reg_accTTC.py -t 1 --browser-path "$(which chromium)"
```

Nếu không dùng Termux:X11 hoặc không có biến `DISPLAY`, script sẽ tự chạy Chromium ở chế độ headless.
