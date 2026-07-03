import os
import urllib.request
import random
import tempfile
import pydub
import speech_recognition
import time
from typing import Optional
from DrissionPage import ChromiumPage

def check_recaptcha_success(driver, timeout=10):
    """
    Hàm theo dõi trạng thái DOM của iframe reCAPTCHA.
    Trả về True nếu aria-checked="true", False nếu hết thời gian chờ.
    """
    print("[HỆ THỐNG] Đang giám sát trạng thái reCAPTCHA...")
    
    try:
        # 1. Bắt đúng iframe chứa checkbox (anchor)
        # Sử dụng selector đối sánh chuỗi (bắt đầu bằng URL của API)
        anchor_frame = driver.get_frame('@src^https://www.google.com/recaptcha/api2/anchor')
        
        if not anchor_frame:
            print("[LỖI] Không tìm thấy iframe reCAPTCHA trên trang.")
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

    except Exception as e:
        print(f"[NGOẠI LỆ] Quá trình giám sát DOM bị lỗi: {e}")
        return False

class RecaptchaSolver:
    """A class to solve reCAPTCHA challenges using audio recognition."""

    # Constants
    TEMP_DIR = tempfile.gettempdir()
    TIMEOUT_STANDARD = 7
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
            return
        if check_recaptcha_success(self.driver):
            return
        # Handle audio challenge
        iframe = self.driver("xpath://iframe[contains(@title, 'recaptcha')]")
        iframe.wait.ele_displayed(
            "#recaptcha-audio-button", timeout=self.TIMEOUT_STANDARD
        )
        iframe("#recaptcha-audio-button", timeout=self.TIMEOUT_SHORT).click()
        time.sleep(0.3)

        if self.is_detected():

            raise Exception("Captcha detected bot behavior")

        # Download and process audio
        try:
            iframe.wait.ele_displayed("#audio-source", timeout=self.TIMEOUT_STANDARD)
            src = iframe("#audio-source").attrs["src"]
        except:
            if check_recaptcha_success(self.driver):
                return

        try:
            text_response = self._process_audio_challenge(src)
            iframe("#audio-response").input(text_response.lower())
            iframe("#recaptcha-verify-button").click()
            time.sleep(0.4)

            if not self.is_solved():
                if check_recaptcha_success(self.driver):
                    return
                raise Exception("Failed to solve the captcha")

        except Exception as e:
            if check_recaptcha_success(self.driver):
                return
            raise Exception(f"Audio challenge failed: {str(e)}")

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
            urllib.request.urlretrieve(audio_url, mp3_path)
            sound = pydub.AudioSegment.from_mp3(mp3_path)
            sound.export(wav_path, format="wav")

            recognizer = speech_recognition.Recognizer()
            with speech_recognition.AudioFile(wav_path) as source:
                audio = recognizer.record(source)

            return recognizer.recognize_google(audio)

        finally:
            for path in (mp3_path, wav_path):
                if os.path.exists(path):
                    try:
                        os.remove(path)
                    except OSError:
                        pass

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
            return False

    def get_token(self) -> Optional[str]:
        """Get the reCAPTCHA token if available."""
        try:
            return self.driver.ele("#recaptcha-token").attrs["value"]
        except Exception:
            return None
