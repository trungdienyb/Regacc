# Cài đặt trên Termux

`DrissionPage` phụ thuộc `psutil`. Bản `psutil` trên PyPI không build trực tiếp trên Android, nên cần cài `python-psutil` bằng `pkg` trước khi chạy `pip install`.

## Cài package hệ thống

```bash
pkg update
pkg install x11-repo
pkg install python python-pip clang ffmpeg dbus chromium python-psutil python-lxml termux-x11-nightly
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
apt -o Acquire::Retries=5 install python python-pip clang ffmpeg python-psutil python-lxml
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

Nếu Chromium tải xong nhưng cấu hình lỗi ở `lv2.postinst` với thông báo `pip3: not found`, tạo alias `pip3` rồi sửa trạng thái package:

```bash
apt install python-pip
ln -sf "$(command -v pip)" "$PREFIX/bin/pip3"
dpkg --configure -a
apt --fix-broken install
```

## Cài nhanh

```bash
git pull
bash install_termux.sh
```

Installer sẽ tự:

- trỏ X11 repo sang mirror Grimler;
- chạy apt với retry/timeout dài hơn;
- sửa trạng thái `dpkg` nếu Chromium/LV2/PipeWire đang cài dở;
- cài `python-pip` và tạo `pip3` nếu Termux thiếu;
- cài Chromium và Python dependencies theo cách tránh build lại `psutil`/`lxml` từ PyPI.

## Cài thủ công

Kiểm tra `psutil` đã được Termux nhận chưa:

```bash
python -c "import psutil; print(psutil.__version__)"
```

Không chạy `pip install DrissionPage` trực tiếp trên Termux. Hãy cài dependency trước, sau đó cài `DrissionPage` bằng `--no-deps` để pip không tự build lại `psutil` từ PyPI:

```bash
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

## Chạy bằng Termux:X11

Termux:X11 cần đủ 2 phần:

- Android app Termux:X11 APK.
- Package trong Termux: `termux-x11-nightly`.

Cài package Termux:

```bash
pkg install x11-repo
pkg install termux-x11-nightly
```

Nếu chạy `termux-x11 :0` báo `Termux:X11 application is not found`, nghĩa là Android APK companion chưa được cài hoặc không cùng nguồn/chữ ký với Termux. Cài APK mới nhất từ GitHub Termux:X11 releases, chọn `app-arm64-v8a-debug.apk` hoặc `app-universal-debug.apk`, sau đó mở app Termux:X11 một lần.

Nếu đang dùng Termux:X11, cần chạy tool trong shell có biến `DISPLAY`. Ví dụ:

```bash
termux-x11 :0 &
export DISPLAY=:0
export DBUS_SESSION_BUS_ADDRESS="$(dbus-daemon --session --fork --print-address)"
```

Test Chromium có GUI:

```bash
chromium-browser --no-sandbox --user-data-dir=/tmp/chrome-test https://example.com
```

Nếu Chromium mở cửa sổ trong app Termux:X11, chạy tool ở chế độ GUI:

```bash
python reg_accTTC.py --mobile --gui -t 1 --browser-path "$(which chromium-browser)"
```

Nếu log vẫn hiện `headless=True`, nghĩa là shell chạy tool chưa có `DISPLAY` hoặc bạn chưa pull bản mới.

Các warning `xkbcomp` thường không fatal. Các warning DBus của Chromium sẽ giảm khi đã export `DBUS_SESSION_BUS_ADDRESS`; nếu Chromium vẫn mở cửa sổ được thì có thể bỏ qua.

Chọn preset mobile hoặc PC:

```bash
python reg_accTTC.py --mobile -t 1 --browser-path "$(which chromium-browser)"
python reg_accTTC.py --pc -t 3 --browser-path "$(which chromium-browser)"
```

Log ngoại lệ được ghi vào:

```bash
tail -f reg_accTTC.log
```

Nếu log có `Audio CAPTCHA không khả dụng` hoặc `Google did not provide a reCAPTCHA audio source`, nghĩa là reCAPTCHA trên Chromium headless/Termux không cung cấp audio challenge. Tool sẽ tự chờ một khoảng rồi reset session thay vì retry liên tục.

Khi test Chromium headless, các warning kiểu `Failed to connect to the bus` hoặc `inotify/max_user_watches` thường là log môi trường Termux và không nhất thiết là lỗi nếu Chromium vẫn trả HTML:

```bash
chromium-browser --headless=new --no-sandbox --disable-dev-shm-usage --dump-dom https://example.com | head
```

Muốn ẩn warning và chỉ xem HTML:

```bash
chromium-browser --headless=new --no-sandbox --disable-dev-shm-usage --dump-dom https://example.com 2>/dev/null | head
```

Nếu `git pull` báo lỗi `safe.directory`, chạy đúng đường dẫn repo hiện tại:

```bash
git config --global --add safe.directory "$(pwd)"
```
