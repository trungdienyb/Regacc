import os
import urllib.request
import random
import tempfile
import logging
import pydub
import speech_recognition
import time
from pathlib import Path
from typing import Optional
from DrissionPage import ChromiumPage

logger = logging.getLogger("reg_accTTC.recaptcha")
DEBUG_DIR = Path(os.getenv("RECAPTCHA_DEBUG_DIR", "recaptcha_debug"))

class RecaptchaSolverError(Exception):
    """Raised when a reCAPTCHA solving stage fails with preserved root cause."""

def driver_context(driver: ChromiumPage) -> str:
    context = []
    try:
        context.append(f"url={driver.url}")
    except Exception:
        context.append("url=<unavailable>")
    try:
        context.append(f"title={driver.title}")
    except Exception:
        context.append("title=<unavailable>")
    return ", ".join(context)

def frame_context(frame) -> str:
    context = []
    for name in ("title", "src", "name"):
        try:
            context.append(f"{name}={frame.attr(name)}")
        except Exception:
            context.append(f"{name}=<unavailable>")
    return ", ".join(context)

def check_recaptcha_success(driver, timeout=10):
    """
    Hàm theo dõi trạng thái DOM của iframe reCAPTCHA.
    Trả về True nếu aria-checked="true", False nếu hết thời gian chờ.
    """
    logger.info("Đang giám sát trạng thái reCAPTCHA. %s", driver_context(driver))
    
    try:
        # 1. Bắt đúng iframe chứa checkbox (anchor)
        # Sử dụng selector đối sánh chuỗi (bắt đầu bằng URL của API)
        anchor_frame = driver.get_frame('@src^https://www.google.com/recaptcha/api2/anchor')
        
        if not anchor_frame:
            logger.warning("Không tìm thấy iframe reCAPTCHA trên trang. %s", driver_context(driver))
            return False

        # 2. Vòng lặp giám sát sự thay đổi của DOM
        end_time = time.time() + timeout
        while time.time() < end_time:
            checkbox = anchor_frame.ele('#recaptcha-anchor')
            
            # Đọc thuộc tính aria-checked theo thời gian thực
            if checkbox and checkbox.attr('aria-checked') == 'true':
                return True
                
            time.sleep(0.5) # Giãn cách request để tối ưu CPU

        return False # Hết thời gian timeout

    except Exception:
        logger.exception("Quá trình giám sát DOM reCAPTCHA bị lỗi. %s", driver_context(driver))
        return False

class RecaptchaSolver:
    """A class to solve reCAPTCHA challenges using audio recognition."""

    # Constants
    TEMP_DIR = tempfile.gettempdir()
    TIMEOUT_STANDARD = 7
    TIMEOUT_AUDIO_SOURCE = 20
    TIMEOUT_SHORT = 1
    TIMEOUT_DETECTION = 0.05

    def __init__(self, driver: ChromiumPage) -> None:
        """Initialize the solver with a ChromiumPage driver.

        Args:
            driver: ChromiumPage instance for browser interaction
        """
        self.driver = driver

    def solveCaptcha(self) -> None:
        """Attempt to solve the reCAPTCHA challenge.

        Raises:
            Exception: If captcha solving fails or bot is detected
        """
        
        try:
            logger.info("Bắt đầu solve reCAPTCHA. %s", driver_context(self.driver))
            # Handle main reCAPTCHA iframe
            self.driver.wait.ele_displayed(
                "@title=reCAPTCHA", timeout=self.TIMEOUT_STANDARD
            )
            time.sleep(0.1)
            iframe_inner = self.driver("@title=reCAPTCHA")

            # Click the checkbox
            iframe_inner.wait.ele_displayed(
                ".rc-anchor-content", timeout=self.TIMEOUT_STANDARD
            )
            iframe_inner(".rc-anchor-content", timeout=self.TIMEOUT_SHORT).click()

            # Check if solved by just clicking
            if self.is_solved():
                logger.info("reCAPTCHA solved bằng checkbox click.")
                return
            if check_recaptcha_success(self.driver):
                logger.info("reCAPTCHA solved sau khi giám sát checkbox.")
                return
            # Handle audio challenge
            iframe = self._get_challenge_frame("#recaptcha-audio-button")
            self._click_audio_button(iframe)

            if self.is_detected():
                raise RecaptchaSolverError("Captcha detected bot behavior")

            text_response = self._solve_audio_challenge(iframe)
            if text_response is None:
                logger.info("reCAPTCHA đã solve trước khi cần submit audio response.")
                return
            iframe("#audio-response").input(text_response.lower())
            iframe("#recaptcha-verify-button").click()
            time.sleep(0.4)

            if not self.is_solved():
                if check_recaptcha_success(self.driver):
                    logger.info("reCAPTCHA solved sau khi submit audio response.")
                    return
                raise RecaptchaSolverError("Audio response submitted but captcha was not solved")

        except RecaptchaSolverError:
            logger.exception("Solve reCAPTCHA thất bại. %s", driver_context(self.driver))
            raise
        except Exception as e:
            logger.exception("Solve reCAPTCHA lỗi ngoài dự kiến. %s", driver_context(self.driver))
            raise RecaptchaSolverError("Unexpected reCAPTCHA solver failure") from e

    def _click_audio_button(self, iframe):
        iframe.wait.ele_displayed("#recaptcha-audio-button", timeout=self.TIMEOUT_STANDARD)
        audio_button = iframe("#recaptcha-audio-button", timeout=self.TIMEOUT_SHORT)
        try:
            audio_button.click()
            logger.info("Đã click audio button bằng click thường. %s", frame_context(iframe))
        except Exception:
            logger.exception("Click thường audio button lỗi, thử click bằng JS. %s", frame_context(iframe))
            audio_button.click(by_js=True)

        time.sleep(1)
        if self._frame_has_audio_source(iframe):
            return

        try:
            audio_button = iframe("#recaptcha-audio-button", timeout=self.TIMEOUT_SHORT)
            audio_button.click(by_js=True)
            logger.info("Đã click audio button lần hai bằng JS fallback. %s", frame_context(iframe))
            time.sleep(1)
        except Exception:
            logger.exception("Click JS fallback audio button lỗi. %s", frame_context(iframe))

    def _get_challenge_frame(self, required_locator):
        frame_locators = (
            '@src^https://www.google.com/recaptcha/api2/bframe',
            'xpath://iframe[contains(@src, "/recaptcha/api2/bframe")]',
            'xpath://iframe[contains(@title, "challenge") or contains(@title, "recaptcha")]',
        )

        last_error = None
        for frame_locator in frame_locators:
            try:
                frame = self.driver.get_frame(frame_locator, timeout=self.TIMEOUT_SHORT)
                if not frame:
                    continue
                if frame.ele(required_locator, timeout=self.TIMEOUT_SHORT):
                    logger.info(
                        "Tìm thấy reCAPTCHA challenge frame bằng locator=%s. %s",
                        frame_locator,
                        frame_context(frame),
                    )
                    return frame
                logger.info(
                    "Frame locator=%s không có required_locator=%s. %s",
                    frame_locator,
                    required_locator,
                    frame_context(frame),
                )
            except Exception as e:
                last_error = e
                logger.debug(
                    "Không dùng được frame locator=%s cho required_locator=%s.",
                    frame_locator,
                    required_locator,
                    exc_info=True,
                )

        try:
            frames = self.driver.get_frames(timeout=self.TIMEOUT_SHORT)
            for index, frame in enumerate(frames, start=1):
                try:
                    if frame.ele(required_locator, timeout=self.TIMEOUT_SHORT):
                        logger.info(
                            "Tìm thấy reCAPTCHA challenge frame bằng fallback scan index=%s. %s",
                            index,
                            frame_context(frame),
                        )
                        return frame
                    logger.debug(
                        "Fallback frame index=%s không có required_locator=%s. %s",
                        index,
                        required_locator,
                        frame_context(frame),
                    )
                except Exception:
                    logger.debug(
                        "Không đọc được fallback frame index=%s. %s",
                        index,
                        frame_context(frame),
                        exc_info=True,
                    )
        except Exception as e:
            last_error = e
            logger.exception("Không lấy được danh sách iframe. %s", driver_context(self.driver))

        self._log_recaptcha_frames(required_locator)
        raise RecaptchaSolverError(f"Cannot find reCAPTCHA challenge frame containing {required_locator}") from last_error

    def _log_recaptcha_frames(self, required_locator):
        try:
            frames = self.driver.get_frames(timeout=self.TIMEOUT_SHORT)
            logger.error(
                "Không tìm thấy frame chứa %s. Tổng iframe/frame hiện có: %s. %s",
                required_locator,
                len(frames),
                driver_context(self.driver),
            )
            for index, frame in enumerate(frames, start=1):
                logger.error("Frame[%s]: %s", index, frame_context(frame))
        except Exception:
            logger.exception("Không log được danh sách iframe. %s", driver_context(self.driver))

    def _frame_has_audio_source(self, iframe) -> bool:
        try:
            audio_source = iframe("#audio-source", timeout=self.TIMEOUT_SHORT)
            return bool(audio_source and audio_source.attrs.get("src"))
        except Exception:
            return False

    def _frame_snapshot(self, iframe, limit=2000) -> str:
        try:
            html = iframe.html
            html = " ".join(str(html).split())
            if len(html) > limit:
                return html[:limit] + "...<truncated>"
            return html
        except Exception as e:
            return f"<snapshot unavailable: {e}>"

    def _write_frame_snapshot(self, iframe, reason: str) -> Optional[Path]:
        try:
            DEBUG_DIR.mkdir(parents=True, exist_ok=True)
            timestamp = time.strftime("%Y%m%d_%H%M%S")
            path = DEBUG_DIR / f"{timestamp}_{reason}_{random.randrange(1000, 9999)}.html"
            path.write_text(str(iframe.html), encoding="utf-8")
            return path
        except Exception:
            logger.exception("Không ghi được HTML snapshot của reCAPTCHA frame.")
            return None

    def _wait_for_audio_source(self, iframe) -> str:
        end_time = time.time() + self.TIMEOUT_AUDIO_SOURCE
        last_error = None

        while time.time() < end_time:
            try:
                audio_source = iframe("#audio-source", timeout=self.TIMEOUT_SHORT)
                src = audio_source.attrs.get("src") if audio_source else None
                if src:
                    logger.info("Tìm thấy audio source reCAPTCHA. %s", frame_context(iframe))
                    return src
            except Exception as e:
                last_error = e

            if check_recaptcha_success(self.driver):
                return ""
            if self.is_detected():
                raise RecaptchaSolverError("Captcha detected bot behavior while waiting for audio source")
            time.sleep(0.75)

        snapshot_path = self._write_frame_snapshot(iframe, "missing_audio_source")
        logger.error(
            "Hết thời gian chờ audio source. %s. snapshot_file=%s frame_snapshot=%s",
            frame_context(iframe),
            snapshot_path,
            self._frame_snapshot(iframe),
        )
        raise RecaptchaSolverError("Cannot find reCAPTCHA audio source after clicking audio button") from last_error

    def _solve_audio_challenge(self, iframe) -> Optional[str]:
        try:
            src = self._wait_for_audio_source(iframe)
            if not src:
                return None
        except RecaptchaSolverError:
            raise
        except Exception as e:
            if check_recaptcha_success(self.driver):
                return None
            logger.exception("Không lấy được audio source reCAPTCHA. %s", driver_context(self.driver))
            raise RecaptchaSolverError("Cannot find reCAPTCHA audio source") from e

        try:
            return self._process_audio_challenge(src)
        except RecaptchaSolverError:
            raise
        except Exception as e:
            if check_recaptcha_success(self.driver):
                return None
            logger.exception("Xử lý audio challenge thất bại. audio_url=%s, %s", src, driver_context(self.driver))
            raise RecaptchaSolverError("Audio challenge processing failed") from e

    def _process_audio_challenge(self, audio_url: str) -> str:
        """Process the audio challenge and return the recognized text.

        Args:
            audio_url: URL of the audio file to process

        Returns:
            str: Recognized text from the audio file
        """
        mp3_path = os.path.join(self.TEMP_DIR, f"{random.randrange(1,1000)}.mp3")
        wav_path = os.path.join(self.TEMP_DIR, f"{random.randrange(1,1000)}.wav")

        try:
            logger.info("Tải audio challenge: %s", audio_url)
            urllib.request.urlretrieve(audio_url, mp3_path)
            sound = pydub.AudioSegment.from_mp3(mp3_path)
            sound.export(wav_path, format="wav")

            recognizer = speech_recognition.Recognizer()
            with speech_recognition.AudioFile(wav_path) as source:
                audio = recognizer.record(source)
            text = recognizer.recognize_google(audio)
            logger.info("Nhận dạng audio challenge thành công.")
            return text

        finally:
            for path in (mp3_path, wav_path):
                if os.path.exists(path):
                    try:
                        os.remove(path)
                    except OSError:
                        logger.exception("Không xóa được file audio tạm: %s", path)

    def is_solved(self) -> bool:
        """Check if the captcha has been solved successfully."""
        try:
            return (
                "style"
                in self.driver.ele(
                    ".recaptcha-checkbox-checkmark", timeout=self.TIMEOUT_SHORT
                ).attrs
            )
        except Exception:
            logger.debug("Không xác định được trạng thái solved của reCAPTCHA.", exc_info=True)
            return False

    def is_detected(self) -> bool:
        """Check if the bot has been detected."""
        try:
            return (
                self.driver.ele("Try again later", timeout=self.TIMEOUT_DETECTION)
                .states()
                .is_displayed
            )
        except Exception:
            logger.debug("Không xác định được trạng thái bot-detected của reCAPTCHA.", exc_info=True)
            return False

    def get_token(self) -> Optional[str]:
        """Get the reCAPTCHA token if available."""
        try:
            return self.driver.ele("#recaptcha-token").attrs["value"]
        except Exception:
            logger.debug("Không lấy được token reCAPTCHA.", exc_info=True)
            return None
