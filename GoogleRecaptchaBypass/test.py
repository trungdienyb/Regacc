from DrissionPage import ChromiumPage, ChromiumOptions
from RecaptchaSolver import RecaptchaSolver
from pydub import AudioSegment
import pydub.utils
import time
import os

# ======================================================================
# 1. CẤU HÌNH FFMPEG (Giải quyết dứt điểm RuntimeWarning của Pydub)
# Yêu cầu: Tải ffmpeg và giải nén vào ổ C:\ffmpeg
# ======================================================================
AudioSegment.converter = r"C:\ffmpeg\bin\ffmpeg.exe"
pydub.utils.get_prober_name = lambda: r"C:\ffmpeg\bin\ffprobe.exe"

CHROME_ARGUMENTS = [
    "-no-first-run",
    "-force-color-profile=srgb",
    "-metrics-recording-only",
    "-password-store=basic",
    "-use-mock-keychain",
    "-export-tagged-pdf",
    "-no-default-browser-check",
    "-disable-background-mode",
    "-enable-features=NetworkService,NetworkServiceInProcess",
    "-disable-features=FlashDeprecationWarning",
    "-deny-permission-prompts",
    "-disable-gpu",
    "-accept-lang=en-US",
    "--disable-usage-stats",
    "--disable-crash-reporter",
    "--no-sandbox",
    "--disable-blink-features=AutomationControlled" # BỔ SUNG: Cờ chí mạng để bypass bot detection
]

options = ChromiumOptions()

# ======================================================================
# 2. CẤU HÌNH ĐƯỜNG DẪN TRÌNH DUYỆT (Giải quyết FileNotFoundError)
# Yêu cầu: Đảm bảo đường dẫn này trỏ đúng đến file chrome.exe trên máy bạn
# ======================================================================
chrome_path = r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"
if not os.path.exists(chrome_path):
    # Fallback thử đường dẫn x86 nếu không tìm thấy bản 64-bit
    chrome_path = r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"
options.set_browser_path(chrome_path)

for argument in CHROME_ARGUMENTS:
    options.set_argument(argument)
    
driver = ChromiumPage(addr_or_opts=options)
recaptchaSolver = RecaptchaSolver(driver)

try:
    # Truy cập mục tiêu
    driver.get("https://traodoisub.com/")
    
    # Khuyến nghị: Đợi một chút để iframe reCAPTCHA tải hoàn tất trước khi gọi hàm
    time.sleep(2) 
    register_btn = driver.ele("xpath://button[contains(text(), 'Đăng Ký Ngay!')]", timeout=15)

    if register_btn:
        # Thực thi click bằng JavaScript để xuyên thủng lớp bảo vệ của Cloudflare
        register_btn.click(by_js=True)
    else:
        print("[LỖI] Không tìm thấy nút Đăng Ký Ngay! sau 15 giây chờ.")
    time.sleep(3)  # Đợi 1 giây để iframe reCAPTCHA xuất hiện
    os._exit(0)
    print("Đang tiến hành giải reCAPTCHA...")
    t0 = time.time()
    
    recaptchaSolver.solveCaptcha()
    
    print(f"[THÀNH CÔNG] Thời gian giải: {time.time()-t0:.2f} giây")

    print("Vui lòng tự cập nhật selector cho nút Submit phù hợp với tuongtaccheo.com")

    # Dừng script 5 giây để bạn quan sát kết quả trước khi đóng
    time.sleep(5)

except Exception as e:
    print(f"[THẤT BẠI] Đã xảy ra lỗi trong quá trình thực thi: {e}")
finally:
    # Luôn đóng trình duyệt để giải phóng RAM dù script có lỗi hay không
    driver.close()