import os, time, random, string, secrets
import threading
import queue
import math
import ctypes
import shutil
from concurrent.futures import ThreadPoolExecutor
from GoogleRecaptchaBypass.RecaptchaSolver import RecaptchaSolver
from DrissionPage import ChromiumPage, ChromiumOptions
from pydub import AudioSegment
import pydub.utils

# Thư viện UI Console
from rich.console import Console
from rich.table import Table
from rich.live import Live
from rich.prompt import IntPrompt

# ======================================================================
# 1. CẤU HÌNH TOÀN CỤC & BIẾN TRẠNG THÁI
# ======================================================================
AudioSegment.converter = r"C:\ffmpeg\bin\ffmpeg.exe"
pydub.utils.get_prober_name = lambda: r"C:\ffmpeg\bin\ffprobe.exe"

IS_RUNNING = True  
account_queue = queue.Queue() 
console = Console()

SCREEN_WIDTH = 0
SCREEN_HEIGHT = 0

# ======================================================================
# 2. HÀM XỬ LÝ GIAO DIỆN CONSOLE (RICH UI)
# ======================================================================
def generate_ui_table(thread_states) -> Table:
    table = Table(
        title="[bold magenta]🚀 HỆ THỐNG AUTO REG ĐA LUỒNG (SIÊU ỔN ĐỊNH) 🚀[/]",
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
# 3. THUẬT TOÁN TÍNH TỌA ĐỘ CỬA SỔ (WINDOW TILING)
# ======================================================================
def init_screen_metrics():
    global SCREEN_WIDTH, SCREEN_HEIGHT
    try:
        user32 = ctypes.windll.user32
        user32.SetProcessDPIAware() 
        SCREEN_WIDTH = user32.GetSystemMetrics(0)
        SCREEN_HEIGHT = user32.GetSystemMetrics(1) - 40 
    except Exception:
        SCREEN_WIDTH = 1920
        SCREEN_HEIGHT = 1040 

def get_window_bounds(worker_id: int, total_threads: int):
    cols = math.ceil(math.sqrt(total_threads))
    rows = math.ceil(total_threads / cols)

    win_width = SCREEN_WIDTH // cols
    win_height = SCREEN_HEIGHT // rows

    index = worker_id - 1
    col_idx = index % cols
    row_idx = index // cols

    return col_idx * win_width, row_idx * win_height, win_width, win_height

# ======================================================================
# 4. LUỒNG THƯ KÝ: GHI FILE TỪ HÀNG ĐỢI
# ======================================================================
def file_writer_worker():
    with open("accounts.txt", "a", encoding="utf-8") as f:
        while IS_RUNNING or not account_queue.empty():
            try:
                data = account_queue.get(timeout=1)
                f.write(data + "\n")
                f.flush() 
                account_queue.task_done()
            except queue.Empty:
                continue
            except Exception:
                pass

# ======================================================================
# 5. CÁC HÀM XỬ LÝ LÕI (CORE LOGIC)
# ======================================================================
def generate_secure_username() -> str:
    alphabet = string.ascii_lowercase + string.digits
    return ''.join(secrets.choice(alphabet) for _ in range(secrets.choice(range(8, 15))))

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
    except:
        return False

# ======================================================================
# 6. LUỒNG LÀM VIỆC ĐỘC LẬP (TỰ ĐỘNG PHỤC HỒI & CÔ LẬP CACHE)
# ======================================================================
def worker_task(worker_id: int, total_threads: int, thread_states: dict):
    chrome_path = r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"
    BATCH_LIMIT = 5 
    profile_path = os.path.abspath(f"./tmp_profile_{worker_id}")
    
    args = [
        "-no-first-run", "-password-store=basic", "-use-mock-keychain",
        "--disable-usage-stats", "--disable-crash-reporter", "--no-sandbox",
        "--disable-blink-features=AutomationControlled", "--mute-audio",
        "--disable-dev-shm-usage", "--disable-gpu", "--disable-software-rasterizer"
    ]

    while IS_RUNNING:
        current_port = random.randint(9000, 9999)
        thread_states[worker_id]["port"] = current_port
        driver = None
        
        try:
            update_state(thread_states, worker_id, "Đang Reset luồng...", "cyan")
            
            # Xóa triệt để rác của profile cũ để trình duyệt khởi sinh sạch sẽ 100%
            if os.path.exists(profile_path):
                try:
                    shutil.rmtree(profile_path)
                except:
                    pass

            options = ChromiumOptions()
            options.set_local_port(current_port)
            options.set_browser_path(chrome_path)
            options.set_user_data_path(profile_path) # Cô lập hoàn toàn tiến trình
            options.incognito() 
            for arg in args: options.set_argument(arg)

            driver = ChromiumPage(addr_or_opts=options)
            x, y, w, h = get_window_bounds(worker_id, total_threads)
            driver.set.window.size(w, h)
            driver.set.window.location(x, y)
            
            recaptchaSolver = RecaptchaSolver(driver)
            
            # Vòng lặp chạy theo lô (Batch Processing)
            for i in range(BATCH_LIMIT):
                if not IS_RUNNING: break
                
                try:
                    update_state(thread_states, worker_id, f"Lô {i+1}/{BATCH_LIMIT} - Chuẩn bị...", "yellow")
                    try:
                        driver.cookies.clear()
                        driver.run_js("localStorage.clear(); sessionStorage.clear();")
                    except: pass
                    
                    driver.get("https://traodoisub.com/")
                    
                    username = generate_secure_username()
                    password = generate_secure_username() + "A1!"
                    
                    time.sleep(2) 
                    register_btn = driver.ele("xpath://button[contains(text(), 'Đăng Ký Ngay!')]", timeout=10)

                    if register_btn:
                        register_btn.click(by_js=True) 
                    else:
                        raise Exception("Không tải được form đăng ký")

                    update_state(thread_states, worker_id, "Đang giải mã reCAPTCHA...", "magenta")
                    recaptchaSolver.solveCaptcha()
                    
                    if check_recaptcha_success(driver, timeout=20):
                        update_state(thread_states, worker_id, "CAPTCHA OK! Điền form...", "green")
                        driver.ele('#dkusername').input(username)
                        time.sleep(0.3)
                        driver.ele('#dkpassword').input(password)
                        time.sleep(0.3)
                        driver.ele('#rdkpassword').input(password)
                        time.sleep(0.5)
                        driver.ele('#register').click()
                        time.sleep(3) 
                        
                        account_queue.put(f"{username}|{password}")
                        update_state(thread_states, worker_id, f"Lưu thành công: {username}", "bold green", add_success=True)
                    else:
                        raise Exception("Giải CAPTCHA thất bại")

                except Exception as inner_e:
                    # Bẻ gãy vòng lặp con ngay lập tức nếu gặp lỗi, ép trình duyệt khởi động lại
                    update_state(thread_states, worker_id, f"Lỗi vòng {i+1}, Hủy lô để Reset...", "red")
                    time.sleep(2)
                    break 

        except Exception as e:
            update_state(thread_states, worker_id, "Lỗi kết nối Port, đang xả...", "red")
            time.sleep(2)
            
        finally:
            update_state(thread_states, worker_id, "Đang xả RAM & Đóng Port...", "yellow")
            try:
                if driver: driver.quit()
            except: pass
            
            # Thời gian vàng để Windows giải phóng Port và xóa thư mục Profile
            time.sleep(4) 

# ======================================================================
# 7. BỘ QUẢN LÝ TIẾN TRÌNH & MAIN
# ======================================================================
if __name__ == "__main__":
    os.system('cls' if os.name == 'nt' else 'clear')
    console.print("[bold cyan]=== KHỞI ĐỘNG HỆ THỐNG AUTO REG ===[/]")
    
    init_screen_metrics()
    
    num_threads = IntPrompt.ask(
        "\n[bold yellow]Nhập số lượng luồng chạy đồng thời (Khuyên dùng: 2 - 6)[/]", 
        default=3
    )
    
    thread_states = {
        i: {"port": 0, "status": "Chờ lệnh...", "success": 0, "color": "cyan"} 
        for i in range(1, num_threads + 1)
    }
    
    os.system('cls' if os.name == 'nt' else 'clear')
    
    # Bật luồng ghi I/O
    writer_thread = threading.Thread(target=file_writer_worker)
    writer_thread.start()
    
    # Khởi chạy các trình duyệt
    executor = ThreadPoolExecutor(max_workers=num_threads)
    for i in range(1, num_threads + 1):
        executor.submit(worker_task, i, num_threads, thread_states)
        time.sleep(1.5) # Giãn cách để chống nghẽn CPU lúc khởi động
        
    try:
        # Chạy giao diện Live Console
        with Live(generate_ui_table(thread_states), refresh_per_second=4, console=console) as live:
            while True:
                live.update(generate_ui_table(thread_states))
                time.sleep(0.25)
                
    except KeyboardInterrupt:
        IS_RUNNING = False 
        console.print("\n[bold red]⚠️ NHẬN LỆNH DỪNG TỪ NGƯỜI DÙNG ⚠️[/]")
        console.print("[yellow]1/3: Đang chờ các luồng xả Port an toàn...[/]")
        executor.shutdown(wait=True) 
        
        console.print("[yellow]2/3: Đang chờ ghi nốt dữ liệu còn tồn trong Queue...[/]")
        writer_thread.join() 
        
        console.print("[bold green]3/3: Toàn bộ Port và File đã đóng. Dọn dẹp thư mục tạm...[/]")
        
        # Xóa các thư mục tmp_profile còn sót lại khi tắt chương trình
        for i in range(1, num_threads + 1):
            p_path = os.path.abspath(f"./tmp_profile_{i}")
            if os.path.exists(p_path):
                try: shutil.rmtree(p_path)
                except: pass
                
        console.print("[bold green]Hệ thống tắt an toàn.[/]")
        os._exit(0)