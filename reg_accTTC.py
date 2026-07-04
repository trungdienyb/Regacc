import argparse
import logging
import os, time, random, string, secrets
import shutil
import socket
import subprocess
import tempfile
import threading
import queue
import math
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
from GoogleRecaptchaBypass.RecaptchaSolver import (
    AudioChallengeUnavailableError,
    AudioDependencyError,
    RecaptchaSolver,
)
from DrissionPage import ChromiumPage, ChromiumOptions
from DrissionPage.errors import AlertExistsError
from pydub import AudioSegment
import pydub.utils

# Thư viện UI Console
from rich.console import Console
from rich.table import Table
from rich.live import Live
from rich.prompt import IntPrompt

# ======================================================================
# CẤU HÌNH TOÀN CỤC & BIẾN TRẠNG THÁI
# ======================================================================
BASE_DIR = Path(__file__).resolve().parent
ACCOUNTS_FILE = BASE_DIR / "acc_ttcReg.txt"
LOG_FILE = BASE_DIR / "reg_accTTC.log"
IS_TERMUX = bool(os.environ.get("TERMUX_VERSION")) or "com.termux" in os.environ.get("PREFIX", "")

IS_RUNNING = True  
account_queue = queue.Queue() 
console = Console()

# Biến lưu trữ cấu hình màn hình
SCREEN_WIDTH = 0
SCREEN_HEIGHT = 0
RUNTIME_CONFIG = {}
CAPTCHA_AUDIO_BACKOFF_SECONDS = 60 if IS_TERMUX else 20

logging.basicConfig(
    filename=LOG_FILE,
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] [%(threadName)s] [%(name)s] %(message)s",
    encoding="utf-8",
)
logger = logging.getLogger("reg_accTTC")

def log_exception(message: str):
    logger.exception(message)

def thread_exception_hook(args):
    logger.error(
        "Uncaught thread exception in %s",
        args.thread.name if args.thread else "unknown",
        exc_info=(args.exc_type, args.exc_value, args.exc_traceback),
    )

threading.excepthook = thread_exception_hook

def find_executable(env_names, candidates):
    for env_name in env_names:
        env_value = os.environ.get(env_name)
        if env_value and Path(env_value).exists():
            return env_value

    for candidate in candidates:
        found = shutil.which(candidate)
        if found:
            return found

    for candidate in candidates:
        candidate_path = Path(candidate)
        if candidate_path.exists():
            return str(candidate_path)

    return None

def configure_audio_tools():
    ffmpeg_path = find_executable(
        ("FFMPEG_BINARY", "FFMPEG_PATH"),
        ("ffmpeg", r"C:\ffmpeg\bin\ffmpeg.exe"),
    )
    ffprobe_path = find_executable(
        ("FFPROBE_BINARY", "FFPROBE_PATH"),
        ("ffprobe", r"C:\ffmpeg\bin\ffprobe.exe"),
    )

    if ffmpeg_path:
        AudioSegment.converter = ffmpeg_path
    if ffprobe_path:
        pydub.utils.get_prober_name = lambda: ffprobe_path

def resolve_runtime_temp_dir() -> Path:
    candidates = []
    tmpdir = os.environ.get("TMPDIR")
    if tmpdir:
        candidates.append(Path(tmpdir))
    candidates.append(Path(tempfile.gettempdir()))
    candidates.append(BASE_DIR / ".tmp")

    for candidate in candidates:
        try:
            candidate.mkdir(parents=True, exist_ok=True)
            test_file = candidate / ".write_test"
            test_file.write_text("ok", encoding="utf-8")
            test_file.unlink(missing_ok=True)
            return candidate
        except Exception:
            logger.debug("Khong dung duoc temp dir: %s", candidate, exc_info=True)

    raise RuntimeError("Khong tim thay thu muc temp co quyen ghi.")

def reserve_free_local_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        sock.listen(1)
        return sock.getsockname()[1]

def ensure_termux_dbus_session() -> str | None:
    session_bus = os.environ.get("DBUS_SESSION_BUS_ADDRESS")
    if session_bus:
        return session_bus

    dbus_daemon = shutil.which("dbus-daemon")
    if not dbus_daemon:
        logger.warning("Khong tim thay dbus-daemon trong Termux.")
        return None

    try:
        output = subprocess.check_output(
            [dbus_daemon, "--session", "--fork", "--print-address"],
            stderr=subprocess.STDOUT,
            text=True,
        ).strip()
    except Exception:
        log_exception("Khong khoi dong duoc DBus session cho Termux.")
        return None

    if output:
        os.environ["DBUS_SESSION_BUS_ADDRESS"] = output
        return output
    return None

def start_termux_x11_companion_app() -> None:
    am_command = shutil.which("am")
    if not am_command:
        logger.warning("Khong tim thay lenh am de mo app Termux:X11 companion.")
        return

    try:
        subprocess.run(
            [am_command, "start", "-n", "com.termux.x11/com.termux.x11.MainActivity"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=False,
        )
    except Exception:
        log_exception("Khong mo duoc app Termux:X11 companion bang am start.")

def wait_for_termux_x11_ready(display: str, timeout: int = 12) -> None:
    display_number = display.lstrip(":").split(".")[0] or "0"
    candidate_dirs = []
    for raw_dir in (os.environ.get("TMPDIR"), tempfile.gettempdir(), "/tmp"):
        if raw_dir:
            candidate_dirs.append(Path(raw_dir) / ".X11-unix")

    deadline = time.time() + timeout
    while time.time() < deadline:
        for candidate_dir in candidate_dirs:
            socket_path = candidate_dir / f"X{display_number}"
            if socket_path.exists():
                logger.info("Termux:X11 san sang. socket=%s", socket_path)
                return
        time.sleep(0.5)

    logger.warning(
        "Khong xac nhan duoc X11 socket cho display=%s sau %ss, tiep tuc khoi tao Chromium theo best effort.",
        display,
        timeout,
    )

def ensure_termux_x11_server() -> str:
    display = os.environ.get("DISPLAY") or ":0"
    os.environ["DISPLAY"] = display

    termux_x11 = shutil.which("termux-x11")
    if not termux_x11:
        raise RuntimeError("Khong tim thay lenh termux-x11. Hay cai package termux-x11-nightly.")

    start_termux_x11_companion_app()
    time.sleep(1)

    try:
        process = subprocess.Popen(
            [termux_x11, display],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
        )
    except Exception as e:
        raise RuntimeError(f"Khong the khoi dong termux-x11: {e}") from e

    time.sleep(2)
    return_code = process.poll()
    if return_code not in (None, 0):
        raise RuntimeError(
            "termux-x11 thoat som. Kiem tra companion app Termux:X11 da cai va da mo tren Android chua."
        )

    wait_for_termux_x11_ready(display)
    return display

def resolve_browser_path(cli_browser_path=None):
    if cli_browser_path:
        return cli_browser_path

    candidates = (
        "chromium",
        "chromium-browser",
        "google-chrome",
        "google-chrome-stable",
        "chrome",
        "msedge",
        r"C:\Program Files\Google\Chrome\Application\chrome.exe",
        r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
    )
    return find_executable(("CHROME_PATH", "CHROMIUM_PATH", "BROWSER_PATH"), candidates)

def parse_args():
    parser = argparse.ArgumentParser(description="Auto reg TTC đa luồng.")
    parser.add_argument("-t", "--threads", type=int, help="Số luồng chạy đồng thời.")
    parser.add_argument("--browser-path", help="Đường dẫn Chromium/Chrome/Edge.")
    parser.add_argument("--headless", action="store_true", help="Chạy Chromium ở chế độ headless.")
    parser.add_argument(
        "--gui",
        action="store_true",
        help="Ép chạy có giao diện, dùng cho Termux:X11/desktop.",
    )
    parser.add_argument(
        "--no-window-tiling",
        action="store_true",
        help="Không resize/sắp xếp cửa sổ trình duyệt.",
    )
    parser.add_argument(
        "--mobile",
        action="store_true",
        help="Áp dụng preset mobile/Termux khi chọn số luồng.",
    )
    parser.add_argument(
        "--pc",
        action="store_true",
        help="Áp dụng preset PC khi chọn số luồng.",
    )
    return parser.parse_args()

def choose_thread_count(args) -> int:
    if args.mobile and args.pc:
        console.print("[bold red]Chỉ được chọn một trong --mobile hoặc --pc.[/]")
        raise SystemExit(1)

    is_mobile_mode = args.mobile or (IS_TERMUX and not args.pc)
    default_threads = 1 if is_mobile_mode else 3
    recommendation = "Mobile/Termux: 1 - 2" if is_mobile_mode else "PC: 2 - 6"

    if args.threads is not None:
        num_threads = args.threads
    else:
        num_threads = IntPrompt.ask(
            f"\n[bold yellow]Nhập số lượng luồng chạy đồng thời ({recommendation})[/]",
            default=default_threads,
        )

    if num_threads < 1:
        console.print("[bold red]Số luồng phải lớn hơn hoặc bằng 1.[/]")
        raise SystemExit(1)

    if is_mobile_mode and num_threads > 2:
        logger.warning("Mobile/Termux đang chạy %s luồng, có thể quá tải RAM/CPU.", num_threads)
        console.print("[yellow]Cảnh báo: Mobile/Termux nên chạy 1 - 2 luồng để ổn định hơn.[/]")

    return num_threads

# ======================================================================
# HÀM XỬ LÝ GIAO DIỆN CONSOLE
# ======================================================================
def generate_ui_table(thread_states) -> Table:
    table = Table(
        title="[bold magenta]🚀 HỆ THỐNG AUTO REG ĐA LUỒNG (QUEUE I/O) 🚀[/]",
        show_header=True, 
        header_style="bold white on blue",
        expand=True
    )
    table.add_column("Luồng", justify="center", style="bold cyan", width=10)
    table.add_column("Port", justify="center", style="yellow", width=8)
    table.add_column("Trạng thái", style="white")
    table.add_column("Thành công", justify="center", style="bold green", width=12)

    for worker_id, state in thread_states.items():
        table.add_row(
            f"Thread-{worker_id}",
            str(state["port"]),
            f"[{state['color']}]{state['status']}[/]",
            str(state["success"])
        )
    return table

def update_state(thread_states, worker_id: int, status: str, color: str = "cyan", add_success: bool = False):
    thread_states[worker_id]["status"] = status
    thread_states[worker_id]["color"] = color
    if add_success:
        thread_states[worker_id]["success"] += 1

# ======================================================================
# THUẬT TOÁN TÍNH TỌA ĐỘ CỬA SỔ (WINDOW TILING)
# ======================================================================
def init_screen_metrics():
    """Lấy kích thước màn hình, ưu tiên API Windows và fallback theo terminal."""
    global SCREEN_WIDTH, SCREEN_HEIGHT
    try:
        if os.name == "nt":
            import ctypes

            user32 = ctypes.windll.user32
            user32.SetProcessDPIAware() 
            SCREEN_WIDTH = user32.GetSystemMetrics(0)
            SCREEN_HEIGHT = user32.GetSystemMetrics(1) - 40
        else:
            terminal_size = shutil.get_terminal_size(fallback=(120, 40))
            SCREEN_WIDTH = max(terminal_size.columns * 8, 800)
            SCREEN_HEIGHT = max(terminal_size.lines * 18, 600)
    except Exception:
        log_exception("Không lấy được kích thước màn hình, dùng fallback.")
        SCREEN_WIDTH = 1280
        SCREEN_HEIGHT = 720 

def get_window_bounds(worker_id: int, total_threads: int):
    """
    Tính toán tọa độ (X, Y) và Kích thước (Width, Height) chia đều màn hình.
    """
    # Tính toán số cột và số hàng hợp lý để lưới gần với hình vuông nhất
    cols = math.ceil(math.sqrt(total_threads))
    rows = math.ceil(total_threads / cols)

    win_width = SCREEN_WIDTH // cols
    win_height = SCREEN_HEIGHT // rows

    # Đưa worker_id về index 0 (0-based)
    index = worker_id - 1
    
    col_idx = index % cols
    row_idx = index // cols

    x_pos = col_idx * win_width
    y_pos = row_idx * win_height

    return x_pos, y_pos, win_width, win_height

# ======================================================================
# LUỒNG THƯ KÝ: GHI FILE TỪ HÀNG ĐỢI
# ======================================================================
def file_writer_worker():
    with open(ACCOUNTS_FILE, "a", encoding="utf-8") as f:
        while IS_RUNNING or not account_queue.empty():
            try:
                data = account_queue.get(timeout=1)
                f.write(data + "\n")
                f.flush() 
                account_queue.task_done()
            except queue.Empty:
                continue
            except Exception:
                log_exception("Lỗi ghi tài khoản vào file.")

# ======================================================================
# CÁC HÀM XỬ LÝ LÕI (CORE LOGIC)
# ======================================================================
def generate_secure_username() -> str:
    alphabet = string.ascii_lowercase + string.digits
    return ''.join(secrets.choice(alphabet) for _ in range(secrets.choice(range(6, 10))))

def check_recaptcha_success(driver, timeout=30) -> bool:
    try:
        anchor_frame = driver.get_frame('@src^https://www.google.com/recaptcha/api2/anchor')
        if not anchor_frame: return False
        
        end_time = time.time() + timeout
        while time.time() < end_time and IS_RUNNING:
            checkbox = anchor_frame.ele('#recaptcha-anchor')
            if checkbox and checkbox.attr('aria-checked') == 'true':
                return True
            time.sleep(0.5)
        return False
    except Exception:
        log_exception("Lỗi kiểm tra trạng thái reCAPTCHA.")
        return False

def clear_browser_state(driver, worker_id: int):
    try:
        driver.run_cdp("Network.clearBrowserCookies")
        driver.run_cdp("Network.clearBrowserCache")
    except Exception:
        log_exception(f"Thread-{worker_id}: lỗi xóa cookies/cache bằng CDP.")

    try:
        driver.run_js("localStorage.clear(); sessionStorage.clear();")
    except Exception:
        log_exception(f"Thread-{worker_id}: lỗi xóa localStorage/sessionStorage.")

# ======================================================================
# LUỒNG LÀM VIỆC ĐỘC LẬP (GIỮ BROWSER MỞ)
# ======================================================================
def worker_task(worker_id: int, total_threads: int, thread_states: dict):
    chrome_path = RUNTIME_CONFIG.get("browser_path")
    current_port = reserve_free_local_port()
    thread_states[worker_id]["port"] = current_port
    
    driver = None
    user_data_path = None
    try:
        update_state(thread_states, worker_id, "Đang khởi tạo trình duyệt...", "cyan")
        options = ChromiumOptions()
        options.set_local_port(current_port)
        if chrome_path:
            options.set_browser_path(chrome_path)
        options.incognito() # Quan trọng để cách ly session khi chạy đa luồng
        
        args = [
            "-no-first-run", "-password-store=basic", "-use-mock-keychain",
            "--disable-usage-stats", "--disable-crash-reporter", "--no-sandbox",
            "--disable-dev-shm-usage", "--disable-gpu", "--disable-software-rasterizer",
            "--disable-extensions", "--disable-background-networking",
            "--disable-features=UseDBus,MediaRouter",
            "--disable-logging", "--log-level=3",
            "--disable-blink-features=AutomationControlled",
            "--remote-allow-origins=*",
            "--mute-audio" # Tắt tiếng trình duyệt để đỡ ồn khi chạy nhiều luồng
        ]
        if IS_TERMUX and not RUNTIME_CONFIG.get("headless"):
            args.extend([
                "--ozone-platform=x11",
                "--enable-features=UseOzonePlatform",
            ])
        for arg in args:
            options.set_argument(arg)
        if RUNTIME_CONFIG.get("headless"):
            options.headless()
            options.set_user_agent(
                "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
                "(KHTML, like Gecko) Chrome/149.0.0.0 Safari/537.36"
            )
            options.set_argument("--window-size=1280,720")

        user_data_base = Path(RUNTIME_CONFIG.get("temp_dir", resolve_runtime_temp_dir()))
        user_data_path = user_data_base / f"ttc_chromium_{worker_id}_{current_port}"
        options.set_user_data_path(str(user_data_path))

        # Mở trình duyệt
        last_error = None
        startup_attempts = 3 if IS_TERMUX else 1
        for attempt in range(1, startup_attempts + 1):
            try:
                driver = ChromiumPage(addr_or_opts=options)
                break
            except Exception as e:
                last_error = e
                logger.warning(
                    "Thread-%s: khoi tao Chromium that bai lan %s/%s. port=%s profile=%s",
                    worker_id,
                    attempt,
                    startup_attempts,
                    current_port,
                    user_data_path,
                    exc_info=True,
                )
                if attempt == startup_attempts:
                    raise
                time.sleep(2 + attempt)
        if driver is None and last_error is not None:
            raise last_error
        
        if not RUNTIME_CONFIG.get("no_window_tiling"):
            try:
                x, y, w, h = get_window_bounds(worker_id, total_threads)
                driver.set.window.size(w, h)
                driver.set.window.location(x, y)
            except Exception:
                log_exception(f"Thread-{worker_id}: không thể sắp xếp/resize cửa sổ.")
                update_state(thread_states, worker_id, "Bỏ qua sắp xếp cửa sổ trên môi trường hiện tại.", "yellow")
        
        recaptchaSolver = RecaptchaSolver(driver)
        
    except Exception as e:
        log_exception(f"Thread-{worker_id}: lỗi khởi tạo trình duyệt.")
        update_state(thread_states, worker_id, f"Lỗi khởi tạo: {e}", "red")
        if user_data_path:
            shutil.rmtree(user_data_path, ignore_errors=True)
        return

    # Vòng lặp Xử lý Tài khoản
    while IS_RUNNING:
        try:
            update_state(thread_states, worker_id, "Làm sạch Session...", "cyan")
            try:
                driver.handle_alert(accept=True, timeout=0.2)
            except Exception:
                pass
            clear_browser_state(driver, worker_id)
            
            update_state(thread_states, worker_id, "Truy cập mục tiêu...", "yellow")
            driver.get("https://tuongtaccheo.com")
            
            username = generate_secure_username()
            password = generate_secure_username() + "A1!"
            
            time.sleep(2) 
            driver.ele('#dkn').click()
            time.sleep(2)

            update_state(thread_states, worker_id, "Đang giải mã âm thanh reCAPTCHA...", "magenta")
            try:
                recaptchaSolver.solveCaptcha()
            except AudioDependencyError as e:
                logger.error(
                    "Thread-%s: thieu dependency xu ly audio. %s",
                    worker_id,
                    e,
                    exc_info=True,
                )
                update_state(thread_states, worker_id, f"Thiếu dependency audio: {e}", "red")
                break
            except AudioChallengeUnavailableError:
                logger.warning(
                    "Thread-%s: Google không cung cấp audio source reCAPTCHA; chờ %s giây rồi reset session.",
                    worker_id,
                    CAPTCHA_AUDIO_BACKOFF_SECONDS,
                    exc_info=True,
                )
                update_state(
                    thread_states,
                    worker_id,
                    f"Audio CAPTCHA không khả dụng, chờ {CAPTCHA_AUDIO_BACKOFF_SECONDS}s...",
                    "yellow",
                )
                time.sleep(CAPTCHA_AUDIO_BACKOFF_SECONDS)
                continue
            
            if check_recaptcha_success(driver, timeout=25):
                update_state(thread_states, worker_id, "CAPTCHA thành công! Đang điền form...", "green")
                driver.ele('#dkusername').input(username)
                time.sleep(0.3)
                driver.ele('#dkpassword').input(password)
                time.sleep(0.3)
                driver.ele('#rdkpassword').input(password)
                time.sleep(0.5)
                driver.ele('#dksubmit').click()
                time.sleep(3) 
                
                account_queue.put(f"{username}|{password}")
                update_state(thread_states, worker_id, f"Lưu thành công: {username}", "bold green", add_success=True)
            else:
                update_state(thread_states, worker_id, "Giải CAPTCHA thất bại. Bỏ qua...", "red")

        except Exception as e:
            if not IS_RUNNING:
                logger.info(
                    "Thread-%s dừng khi tool đang shutdown, bỏ qua lỗi do page/browser disconnect.",
                    worker_id,
                    exc_info=True,
                )
                break
            log_exception(f"Thread-{worker_id}: lỗi vòng lặp xử lý tài khoản.")
            update_state(thread_states, worker_id, "Lỗi ngoại lệ, reset vòng lặp...", "red")
            
        finally:
            time.sleep(1.5)

    # Đóng Port an toàn khi tắt tool
    update_state(thread_states, worker_id, "Đang dọn dẹp và đóng Port...", "yellow")
    try:
        if driver: 
            driver.quit()
    except Exception:
        log_exception(f"Thread-{worker_id}: lỗi đóng trình duyệt.")
    try:
        if user_data_path:
            shutil.rmtree(user_data_path, ignore_errors=True)
    except Exception:
        log_exception(f"Thread-{worker_id}: lỗi xóa thư mục profile tạm.")


# ======================================================================
# BỘ QUẢN LÝ TIẾN TRÌNH & MAIN
# ======================================================================
if __name__ == "__main__":
    args = parse_args()
    logger.info("Khởi động tool. Log file: %s", LOG_FILE)
    configure_audio_tools()
    if args.gui and args.headless:
        console.print("[bold red]Chỉ được chọn một trong --gui hoặc --headless.[/]")
        raise SystemExit(1)

    if IS_TERMUX and args.gui:
        try:
            display = ensure_termux_x11_server()
            dbus_session = ensure_termux_dbus_session()
            logger.info(
                "Da khoi dong Termux:X11 tu dong. display=%s, dbus=%s",
                display,
                dbus_session or "<unavailable>",
            )
        except Exception as e:
            console.print(f"[bold red]Khong the tu dong khoi dong Termux:X11: {e}[/]")
            raise SystemExit(1)
    else:
        display = os.environ.get("DISPLAY")
    auto_headless = IS_TERMUX and not display and not args.gui
    if args.gui and not display:
        console.print("[bold red]Bạn chọn --gui nhưng chưa có DISPLAY. Hãy export DISPLAY=:0 trước khi chạy.[/]")
        raise SystemExit(1)

    RUNTIME_CONFIG = {
        "browser_path": resolve_browser_path(args.browser_path),
        "headless": False if args.gui else (args.headless or auto_headless),
        "no_window_tiling": args.no_window_tiling or IS_TERMUX,
        "temp_dir": resolve_runtime_temp_dir(),
    }

    os.system('cls' if os.name == 'nt' else 'clear')
    console.print("[bold cyan]=== KHỞI ĐỘNG HỆ THỐNG AUTO REG ===[/]")
    if IS_TERMUX:
        console.print("[yellow]Phát hiện Termux: tự tắt sắp xếp cửa sổ desktop.[/]")
    if display:
        console.print(f"[green]DISPLAY={display}; có thể chạy Chromium qua Termux:X11.[/]")
    if auto_headless:
        console.print("[yellow]Không thấy DISPLAY trong Termux: tự bật chế độ headless.[/]")
    if not RUNTIME_CONFIG["browser_path"]:
        console.print("[bold red]Không tìm thấy Chromium/Chrome. Cài chromium hoặc truyền --browser-path.[/]")
        raise SystemExit(1)
    
    # Lấy thông số màn hình
    init_screen_metrics()
    
    # 1. Yêu cầu người dùng nhập số lượng luồng
    num_threads = choose_thread_count(args)
    if IS_TERMUX and num_threads > 2:
        logger.warning("Termux requested %s threads; clamping to 2 for stability.", num_threads)
        console.print("[yellow]Termux se tu gioi han toi da 2 luong de tranh page disconnect.[/]")
        num_threads = 2
    logger.info(
        "Cấu hình chạy: threads=%s, browser_path=%s, headless=%s, no_window_tiling=%s, termux=%s, display=%s, temp_dir=%s",
        num_threads,
        RUNTIME_CONFIG["browser_path"],
        RUNTIME_CONFIG["headless"],
        RUNTIME_CONFIG["no_window_tiling"],
        IS_TERMUX,
        display,
        RUNTIME_CONFIG["temp_dir"],
    )
    
    # Khởi tạo bộ nhớ UI State
    thread_states = {
        i: {"port": 0, "status": "Chờ lệnh...", "success": 0, "color": "cyan"} 
        for i in range(1, num_threads + 1)
    }
    
    os.system('cls' if os.name == 'nt' else 'clear')
    
    # 2. Khởi chạy luồng Thư ký (Ghi file)
    writer_thread = threading.Thread(target=file_writer_worker)
    writer_thread.start()
    
    # 3. Khởi tạo ThreadPool cho trình duyệt
    executor = ThreadPoolExecutor(max_workers=num_threads)
    for i in range(1, num_threads + 1):
        # Truyền num_threads vào để worker tính toán tọa độ lưới
        executor.submit(worker_task, i, num_threads, thread_states)
        time.sleep(1) # Chống nghẽn CPU
        
    try:
        # Chạy giao diện Live Console
        with Live(generate_ui_table(thread_states), refresh_per_second=4, console=console) as live:
            while True:
                live.update(generate_ui_table(thread_states))
                time.sleep(0.25)
                
    except KeyboardInterrupt:
        IS_RUNNING = False 
        logger.info("Người dùng dừng tool bằng KeyboardInterrupt.")
        console.print("\n[bold red]⚠️ NHẬN LỆNH DỪNG TỪ NGƯỜI DÙNG ⚠️[/]")
        console.print("[yellow]1/3: Đang chờ các luồng xả Port an toàn...[/]")
        executor.shutdown(wait=True) 
        
        console.print("[yellow]2/3: Đang chờ ghi nốt dữ liệu còn tồn trong Queue...[/]")
        writer_thread.join() 
        
        console.print("[bold green]3/3: Toàn bộ Port và File đã đóng. Hệ thống tắt an toàn.[/]")
        os._exit(0)
