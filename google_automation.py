"""
Google One automation using Selenium.

Logs into a Gmail account, navigates to Google One, detects the
12-month free Gemini Pro offer, and returns the activation / payment link.
Supports interactive CAPTCHA and 2FA resolution directly via Telegram.
"""

import logging
import time
import re
from urllib.parse import urlparse
from typing import Optional, Callable

from selenium import webdriver
from selenium.common.exceptions import (
    NoSuchElementException,
    TimeoutException,
    WebDriverException,
)
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait

import config
from device_simulator import DeviceProfile

logger = logging.getLogger(__name__)


# ── Driver factory ────────────────────────────────────────────────────────────

def _build_driver(profile: DeviceProfile) -> webdriver.Chrome:
    """Return a headless Chrome WebDriver configured for the device profile with anti-detection."""
    options = Options()

    if config.HEADLESS:
        options.add_argument("--headless=new")

    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--disable-gpu")
    options.add_argument("--disable-extensions")
    options.add_argument("--disable-infobars")
    options.add_argument("--disable-notifications")
    options.add_argument("--window-size=440,920")  # Pixel 10 Pro screen size
    options.add_argument("--window-position=60,60")
    options.add_argument(f"--user-agent={profile.user_agent}")

    if getattr(config, "PROXY", None):
        logger.info("Using proxy: %s", config.PROXY)
        options.add_argument(f"--proxy-server={config.PROXY}")

    # Mobile emulation – Pixel 10 Pro viewport
    mobile_emulation = {
        "deviceMetrics": {"width": 390, "height": 844, "pixelRatio": 3.0},
        "userAgent": profile.user_agent,
    }
    options.add_experimental_option("mobileEmulation", mobile_emulation)

    # Suppress automation flags
    options.add_experimental_option("excludeSwitches", ["enable-automation"])
    options.add_experimental_option("useAutomationExtension", False)
    options.add_argument("--disable-blink-features=AutomationControlled")

    service = Service()
    driver = webdriver.Chrome(service=service, options=options)

    # Stealth script injection to mask automation detection
    try:
        driver.execute_cdp_cmd(
            "Page.addScriptToEvaluateOnNewDocument",
            {
                "source": """
                    Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
                    window.chrome = {
                        runtime: {},
                        loadTimes: function() {},
                        csi: function() {},
                        app: {}
                    };
                """
            }
        )
    except Exception as e:
        logger.warning("Failed to inject CDP stealth script: %s", e)

    driver.implicitly_wait(config.IMPLICIT_WAIT)
    driver.set_page_load_timeout(config.PAGE_LOAD_TIMEOUT)
    return driver


# ── Login helper ──────────────────────────────────────────────────────────────

def _wait_for(driver: webdriver.Chrome, by: str, value: str,
               timeout: int = config.WEBDRIVER_TIMEOUT) -> object:
    """Return element after waiting for it to be clickable."""
    return WebDriverWait(driver, timeout).until(
        EC.element_to_be_clickable((by, value))
    )


def _try_solve_recaptcha_checkbox(driver: webdriver.Chrome) -> bool:
    """Detect and automatically click the 'I'm not a robot' reCAPTCHA checkbox and Next."""
    try:
        frames = driver.find_elements(By.CSS_SELECTOR, 'iframe[src*="recaptcha"], iframe[title*="reCAPTCHA"]')
        if not frames:
            return False

        logger.info("Found %d reCAPTCHA iframe(s)", len(frames))
        for frame in frames:
            try:
                driver.switch_to.frame(frame)
                checkboxes = driver.find_elements(By.CSS_SELECTOR, '#recaptcha-anchor, .recaptcha-checkbox')
                if checkboxes and checkboxes[0].is_displayed():
                    logger.info("Clicking 'I am not a robot' checkbox...")
                    driver.execute_script("arguments[0].click();", checkboxes[0])
                    driver.switch_to.default_content()
                    time.sleep(2.5)

                    # If visual puzzle opened, do not click Next
                    if _is_bframe_active(driver):
                        logger.info("Visual puzzle opened after checkbox click.")
                        return True

                    # Otherwise, click Next button on main page if enabled
                    next_buttons = driver.find_elements(
                        By.CSS_SELECTOR, '#identifierNext, button[jsname="LgbsSe"], button[type="button"]'
                    )
                    for btn in next_buttons:
                        if btn.is_displayed() and "next" in btn.text.lower():
                            logger.info("Clicking Next button after reCAPTCHA checkbox")
                            btn.click()
                            time.sleep(3)
                            return True
                    return True
                driver.switch_to.default_content()
            except Exception as e:
                logger.warning("Error checking frame: %s", e)
                driver.switch_to.default_content()
    except Exception as e:
        logger.warning("Error in _try_solve_recaptcha_checkbox: %s", e)
        driver.switch_to.default_content()
    return False


def _is_bframe_active(driver: webdriver.Chrome) -> bool:
    """Check if the reCAPTCHA visual puzzle popup iframe is active and displayed."""
    try:
        frames = driver.find_elements(By.CSS_SELECTOR, 'iframe[src*="bframe"], iframe[title*="recaptcha challenge"]')
        for f in frames:
            if f.is_displayed():
                return True
    except Exception:
        pass
    return False


def _inject_captcha_badges(driver: webdriver.Chrome) -> tuple:
    """
    Inject visible numbered badge overlays (1, 2, 3...) onto each reCAPTCHA tile
    inside the active bframe, and return (num_tiles, instructions).
    """
    try:
        frames = driver.find_elements(By.CSS_SELECTOR, 'iframe[src*="bframe"], iframe[title*="recaptcha challenge"]')
        active_frame = None
        for f in frames:
            if f.is_displayed():
                active_frame = f
                break
        if not active_frame:
            return 0, ""

        driver.switch_to.frame(active_frame)

        desc_el = driver.find_elements(By.CSS_SELECTOR, ".rc-imageselect-desc-wrapper, .rc-imageselect-desc, strong")
        instructions = desc_el[0].text.strip() if desc_el else "Select matching tiles"

        tiles = driver.find_elements(By.CSS_SELECTOR, "td.rc-imageselect-tile, .rc-image-tile-target, .rc-imageselect-table td")
        num_tiles = len(tiles) if len(tiles) in (9, 16) else 9

        # Inject styled badge overlays onto tiles
        driver.execute_script("""
            const tiles = document.querySelectorAll('td.rc-imageselect-tile, .rc-image-tile-target, .rc-imageselect-table td');
            tiles.forEach((tile, index) => {
                let badge = tile.querySelector('.captcha-tile-badge');
                if (!badge) {
                    badge = document.createElement('div');
                    badge.className = 'captcha-tile-badge';
                    badge.style.position = 'absolute';
                    badge.style.top = '6px';
                    badge.style.left = '6px';
                    badge.style.backgroundColor = 'rgba(0, 0, 0, 0.85)';
                    badge.style.color = '#ffffff';
                    badge.style.fontWeight = 'bold';
                    badge.style.fontSize = '17px';
                    badge.style.padding = '2px 8px';
                    badge.style.borderRadius = '8px';
                    badge.style.border = '2px solid #ffffff';
                    badge.style.zIndex = '999999';
                    badge.style.pointerEvents = 'none';
                    badge.style.boxShadow = '0 2px 4px rgba(0,0,0,0.6)';
                    tile.style.position = 'relative';
                    tile.appendChild(badge);
                }
                badge.innerText = (index + 1).toString();
            });
        """)

        driver.switch_to.default_content()
        return num_tiles, instructions
    except Exception as e:
        logger.warning("Error injecting captcha badges: %s", e)
        driver.switch_to.default_content()
        return 0, ""


def _get_captcha_screenshot(driver: webdriver.Chrome) -> bytes:
    """Capture cropped screenshot of the reCAPTCHA challenge box for mobile Telegram."""
    try:
        frames = driver.find_elements(By.CSS_SELECTOR, 'iframe[src*="bframe"], iframe[title*="recaptcha challenge"]')
        for f in frames:
            if f.is_displayed():
                return f.screenshot_as_png
    except Exception as e:
        logger.debug("Failed to take element screenshot: %s", e)
    return driver.get_screenshot_as_png()


def _handle_interactive_recaptcha(driver: webdriver.Chrome, prompt_callback: Callable):
    """Bridge the reCAPTCHA visual puzzle to the Telegram interactive UI."""
    try:
        num_tiles, instructions = _inject_captcha_badges(driver)
        if num_tiles == 0:
            return

        shot = _get_captcha_screenshot(driver)

        prompt_callback(
            f"🧩 <b>reCAPTCHA Image Puzzle</b>\n\n"
            f"<b>Instructions:</b> {instructions}\n\n"
            f"<i>Tap the matching tile numbers below (they match the numbered badges on the image), then tap Verify:</i>",
            photo_bytes=shot,
            wait_for_reply=True,
            custom_type="recaptcha_grid",
            extra_data={
                "driver": driver,
                "num_tiles": num_tiles,
                "instructions": instructions,
            }
        )
    except Exception as e:
        logger.warning("Error in _handle_interactive_recaptcha: %s", e)
        driver.switch_to.default_content()




def _gmail_login(driver: webdriver.Chrome, email: str, password: str,
                 prompt_callback: Optional[Callable] = None) -> bool:
    """
    Perform Gmail / Google account login with support for interactive CAPTCHA and 2FA.
    """
    try:
        logger.info("Opening Google login page: %s", config.GMAIL_LOGIN_URL)
        driver.get(config.GMAIL_LOGIN_URL)
        time.sleep(2)

        # ── Email step ────────────────────────────────────────────────────────
        email_field = None
        for by, sel in [
            (By.ID, "identifierId"),
            (By.NAME, "identifier"),
            (By.CSS_SELECTOR, 'input[type="email"]'),
            (By.CSS_SELECTOR, 'input[type="text"]'),
        ]:
            try:
                email_field = WebDriverWait(driver, 5).until(
                    EC.element_to_be_clickable((by, sel))
                )
                if email_field:
                    break
            except TimeoutException:
                pass

        if not email_field:
            raise GoogleAutomationError("Could not find the Google email input field.")

        email_field.clear()
        email_field.send_keys(email)

        # Click identifier Next
        next_btn = None
        for by, sel in [
            (By.ID, "identifierNext"),
            (By.CSS_SELECTOR, 'button[jsname="LgbsSe"]'),
            (By.CSS_SELECTOR, 'button[type="button"]'),
        ]:
            try:
                next_btn = WebDriverWait(driver, 3).until(
                    EC.element_to_be_clickable((by, sel))
                )
                if next_btn:
                    break
            except TimeoutException:
                pass

        if next_btn:
            next_btn.click()
        time.sleep(3)

        # Check for immediate account not found error
        body_text = driver.find_element(By.TAG_NAME, "body").text
        if "Couldn't find your Google Account" in body_text or "Couldn’t find your Google Account" in body_text:
            raise GoogleAutomationError("Couldn't find your Google Account. Please verify your email.")

        # Check if CAPTCHA appears after email step
        ca_inputs = driver.find_elements(By.CSS_SELECTOR, 'input[name="ca"], input#ca, input[aria-label*="Type the text"]')
        if ca_inputs and ca_inputs[0].is_displayed():
            logger.info("CAPTCHA detected on email step")
            if prompt_callback:
                shot = driver.get_screenshot_as_png()
                ca_code = prompt_callback(
                    "🧩 *Google Security Check (CAPTCHA)*\n\n"
                    "Google has requested a CAPTCHA verification.\n"
                    "Please reply to this message with the characters shown in the image below:",
                    photo_bytes=shot,
                    wait_for_reply=True,
                )
                if ca_code:
                    ca_inputs[0].clear()
                    ca_inputs[0].send_keys(ca_code)
                    btn = driver.find_element(By.CSS_SELECTOR, '#identifierNext, button[jsname="LgbsSe"]')
                    btn.click()
                    time.sleep(3)

        # ── Password step ─────────────────────────────────────────────────────
        pw_field = None
        for by, sel in [
            (By.NAME, "Passwd"),
            (By.NAME, "password"),
            (By.CSS_SELECTOR, 'input[type="password"]'),
        ]:
            try:
                pw_field = WebDriverWait(driver, 8).until(
                    EC.element_to_be_clickable((by, sel))
                )
                if pw_field:
                    break
            except TimeoutException:
                pass

        if pw_field:
            pw_field.clear()
            pw_field.send_keys(password)

            pw_next = None
            for by, sel in [
                (By.ID, "passwordNext"),
                (By.CSS_SELECTOR, 'button[jsname="LgbsSe"]'),
                (By.CSS_SELECTOR, 'button[type="button"]'),
            ]:
                try:
                    pw_next = WebDriverWait(driver, 3).until(
                        EC.element_to_be_clickable((by, sel))
                    )
                    if pw_next:
                        break
                except TimeoutException:
                    pass

            if pw_next:
                pw_next.click()
            time.sleep(4)

        # ── Verification & 2FA Loop ───────────────────────────────────────────
        start_time = time.time()
        already_prompted_phone = False
        already_prompted_pin = False

        while time.time() - start_time < 120:
            current_url = driver.current_url
            parsed = urlparse(current_url)
            hostname = parsed.hostname or ""
            path = parsed.path or ""

            # Check if login is complete
            if (
                hostname == "myaccount.google.com"
                or (hostname.endswith(".google.com") and "/u/" in path)
                or ("one.google.com" in hostname and "/about" not in path and "/signin" not in path)
            ):
                logger.info("Login succeeded for %s (URL: %s)", email, current_url)
                return True

            # If still on accounts.google.com signin/challenge/v3 flow, we are not logged in yet
            if hostname == "accounts.google.com" and (
                "/signin" in path or "/challenge" in path or "/v3" in path or "/identifier" in path
            ):
                pass
            elif hostname != "accounts.google.com" and hostname != "":
                logger.info("Redirected away from Google Accounts (URL: %s)", current_url)
                return True

            # Check for incorrect password error
            try:
                error_el = driver.find_element(
                    By.CSS_SELECTOR, '[jsname="B34EJ"], [aria-live="assertive"]'
                )
                err_text = error_el.text.strip()
                if err_text and ("wrong password" in err_text.lower() or "incorrect" in err_text.lower()):
                    raise GoogleAutomationError(f"Incorrect password: {err_text}")
            except NoSuchElementException:
                pass

            body_text = driver.find_element(By.TAG_NAME, "body").text

            # Check for post-password CAPTCHA
            ca_inputs = driver.find_elements(By.CSS_SELECTOR, 'input[name="ca"], input#ca')
            if ca_inputs and ca_inputs[0].is_displayed():
                if prompt_callback:
                    shot = driver.get_screenshot_as_png()
                    ca_code = prompt_callback(
                        "🧩 *Google Security Verification*\n\n"
                        "Please reply with the characters shown in the image below:",
                        photo_bytes=shot,
                        wait_for_reply=True,
                    )
                    if ca_code:
                        ca_inputs[0].clear()
                        ca_inputs[0].send_keys(ca_code)
                        # Re-enter password if empty
                        try:
                            pws = driver.find_elements(By.CSS_SELECTOR, 'input[type="password"]')
                            if pws and not pws[0].get_attribute("value"):
                                pws[0].send_keys(password)
                        except Exception:
                            pass
                        btn = driver.find_element(By.CSS_SELECTOR, '#passwordNext, button[jsname="LgbsSe"]')
                        btn.click()
                        time.sleep(3)
                        continue

            # Check for 2FA PIN (SMS or Google Authenticator)
            pin_inputs = driver.find_elements(
                By.CSS_SELECTOR, 'input[type="tel"], input#idvPin, input[name="Pin"], input[id="totpPin"], input[name="code"]'
            )
            if pin_inputs and pin_inputs[0].is_displayed():
                if not already_prompted_pin and prompt_callback:
                    already_prompted_pin = True
                    shot = driver.get_screenshot_as_png()
                    pin_code = prompt_callback(
                        "🔑 *Google 2-Step Verification*\n\n"
                        "Google has sent a 2-Step verification code.\n"
                        "Please reply with the 6-digit code received on your phone or Authenticator app:",
                        photo_bytes=shot,
                        wait_for_reply=True,
                    )
                    if pin_code:
                        pin_inputs[0].clear()
                        pin_inputs[0].send_keys(pin_code)
                        btn = driver.find_element(
                            By.CSS_SELECTOR, 'button[type="button"], button[jsname="LgbsSe"], #idvPreregisteredPhoneNext'
                        )
                        btn.click()
                        time.sleep(4)
                        already_prompted_pin = False
                        continue

            # Check for reCAPTCHA challenge (checkbox or puzzle)
            if "challenge/recaptcha" in current_url or "confirm you're not a robot" in body_text.lower() or _is_bframe_active(driver):
                logger.info("reCAPTCHA challenge detected.")
                if _is_bframe_active(driver):
                    logger.info("reCAPTCHA visual puzzle (bframe) is active! Triggering interactive grid...")
                    if prompt_callback:
                        _handle_interactive_recaptcha(driver, prompt_callback)
                    time.sleep(3)
                else:
                    _try_solve_recaptcha_checkbox(driver)
                    time.sleep(3)
                    if _is_bframe_active(driver) and prompt_callback:
                        _handle_interactive_recaptcha(driver, prompt_callback)
                continue

            # Check for Google Prompt on Phone ("Tap Yes on your phone", number matching)
            phone_keywords = ["check your phone", "google sent a notification", "tap yes on your phone", "open the gmail app", "tap the number"]
            if any(kw in body_text.lower() for kw in phone_keywords):
                if not already_prompted_phone and prompt_callback:
                    already_prompted_phone = True
                    shot = driver.get_screenshot_as_png()
                    prompt_callback(
                        "📱 <b>Google 2-Step Verification (Phone Prompt)</b>\n\n"
                        "Google sent a prompt to your device.\n"
                        "Open your phone, tap <b>Yes</b>, and select the matching number shown in the image above to approve the login.",
                        photo_bytes=shot,
                        wait_for_reply=False,
                    )
                time.sleep(3)
                continue

            time.sleep(2)

        logger.warning("Login verification timed out after 120s: %s", driver.current_url)
        return False

    except TimeoutException as exc:
        logger.error("Timeout during login: %s", exc)
        return False
    except WebDriverException as exc:
        logger.error("WebDriver error during login: %s", exc)
        return False


# ── Offer detection ───────────────────────────────────────────────────────────

def _extract_payment_link(driver: webdriver.Chrome) -> tuple[Optional[str], Optional[str]]:
    """
    Scan the current page specifically for a Gemini Pro / AI Premium offer link.
    Returns (offer_type, url) where offer_type is "gemini", "other", or (None, None).
    """
    gemini_indicators = (
        "gemini",
        "ai-premium",
        "ai_premium",
        "gemini_advanced",
        "gemini-advanced",
        "gemini pro",
        "ai premium",
        "2 tb ai",
    )
    excluded_indicators = ("youtube", "play_pass", "play pass", "photo", "nest", "vpn")

    all_links = driver.find_elements(By.TAG_NAME, "a")

    # 1. Primary check: Exact Gemini / AI Premium links
    for link in all_links:
        try:
            href = (link.get_attribute("href") or "").strip()
            if not href or href.startswith("javascript:"):
                continue
            text = (link.text + " " + (link.get_attribute("aria-label") or "")).lower()

            # URL contains gemini / ai-premium
            if any(kw in href.lower() for kw in ("gemini", "ai-premium", "ai_premium", "ai_plan")):
                logger.info("Found Gemini offer link via URL: %s", href)
                return "gemini", href

            # Anchor text contains Gemini keywords
            if any(kw in text for kw in gemini_indicators) and not any(ex in text for ex in excluded_indicators):
                logger.info("Found Gemini offer link via text '%s': %s", text[:40], href)
                return "gemini", href
        except Exception:
            continue

    # 2. Check for button / CTA for Gemini
    buttons = driver.find_elements(By.CSS_SELECTOR, "button, [role='button']")
    for btn in buttons:
        try:
            text = btn.text.lower()
            if any(kw in text for kw in gemini_indicators) and not any(ex in text for ex in excluded_indicators):
                try:
                    parent_link = btn.find_element(By.XPATH, "ancestor::a")
                    href = parent_link.get_attribute("href") or ""
                    if href:
                        return "gemini", href
                except NoSuchElementException:
                    pass
                return "gemini", driver.current_url
        except Exception:
            continue

    # 3. Secondary check: Collect other Google One benefit links if present
    for link in all_links:
        try:
            href = (link.get_attribute("href") or "").strip()
            if "one.google.com/benefits/" in href and not href.startswith("javascript:"):
                return "other", href
        except Exception:
            continue

    return None, None


def _navigate_google_one(driver: webdriver.Chrome) -> tuple[Optional[str], Optional[str]]:
    """
    Navigate through Google One pages looking for the Gemini Pro offer.
    Returns (offer_type, link).
    """
    target_urls = [
        "https://one.google.com/explore-plan/ai-premium",
        "https://one.google.com/benefits",
        "https://one.google.com/about/plans",
        "https://one.google.com/",
    ]
    other_offer = None

    for url in target_urls:
        try:
            logger.info("Navigating to %s", url)
            driver.get(url)
            time.sleep(3)

            # Dismiss cookie/consent banners if present
            for selector in (
                '[aria-label="Accept all"]',
                'button[jsname="higCR"]',
                '[data-action="accept"]',
            ):
                try:
                    btn = driver.find_element(By.CSS_SELECTOR, selector)
                    btn.click()
                    time.sleep(1)
                    break
                except NoSuchElementException:
                    pass

            offer_type, link = _extract_payment_link(driver)
            if offer_type == "gemini":
                return "gemini", link
            elif offer_type == "other" and not other_offer:
                other_offer = link

        except (TimeoutException, WebDriverException) as exc:
            logger.warning("Error accessing %s: %s", url, exc)

    if other_offer:
        return "other", other_offer
    return None, None


# ── Public API ────────────────────────────────────────────────────────────────

class GoogleAutomationError(Exception):
    """Raised when automation encounters an unrecoverable error."""


def check_gemini_offer(email: str, password: str,
                       device: DeviceProfile,
                       prompt_callback: Optional[Callable] = None) -> tuple[Optional[str], Optional[str]]:
    """
    Main entry point.

    Logs into *email* / *password* using the supplied *device* profile,
    navigates to Google One, and returns (offer_type, offer_link).
    Supports interactive CAPTCHA & 2FA callback to Telegram.
    """
    driver: Optional[webdriver.Chrome] = None
    try:
        logger.info("Starting WebDriver for session %s (Pixel 10 Pro simulation)", device.session_id)
        driver = _build_driver(device)

        logged_in = _gmail_login(driver, email, password, prompt_callback=prompt_callback)
        if not logged_in:
            raise GoogleAutomationError(
                "Login failed. Please check your credentials or complete the verification."
            )

        offer_type, offer_link = _navigate_google_one(driver)
        return offer_type, offer_link

    finally:
        if driver:
            try:
                driver.quit()
            except Exception:
                pass
