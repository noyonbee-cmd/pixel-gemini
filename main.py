"""
Telegram Bot entry point for the Pixel 10 Pro Google One Gemini Bot.

Commands:
  /start        – Show welcome message and available commands
  /login        – Begin credential capture flow (email → password)
  /check_offer  – Run Google One automation and look for Gemini Pro offer
  /get_link     – Show the last captured offer link
  /status       – Show current session status and device profile
"""

import asyncio
from datetime import datetime
import logging
import os
import sys
from typing import Dict, Optional, Set

from telegram import (
    Update,
    ReplyKeyboardMarkup,
    ReplyKeyboardRemove,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    InputMediaPhoto,
)
from telegram.ext import (
    Application,
    CommandHandler,
    ConversationHandler,
    MessageHandler,
    CallbackQueryHandler,
    ContextTypes,
    filters,
)
from selenium.webdriver.common.by import By

import config
from device_simulator import create_device_profile
from google_automation import GoogleAutomationError, check_gemini_offer

# ── Logging ───────────────────────────────────────────────────────────────────
logging.basicConfig(level=config.LOG_LEVEL, format=config.LOG_FORMAT)
logger = logging.getLogger(__name__)

# ── Conversation states ───────────────────────────────────────────────────────
AWAIT_EMAIL, AWAIT_PASSWORD = range(2)

# Pending user responses for CAPTCHA / 2FA verification (chat_id -> Future)
PENDING_INPUTS: Dict[int, asyncio.Future] = {}
CAPTCHA_SESSIONS: Dict[int, dict] = {}


def build_recaptcha_keyboard(num_tiles: int, selected: Set[int]) -> InlineKeyboardMarkup:
    """Build an interactive 3x3 or 4x4 inline button grid for reCAPTCHA puzzle."""
    cols = 4 if num_tiles == 16 else 3
    rows = []
    current_row = []
    for i in range(num_tiles):
        tile_num = i + 1
        label = f"🟢 {tile_num}" if i in selected else f"{tile_num}"
        current_row.append(InlineKeyboardButton(label, callback_data=f"tile_{i}"))
        if len(current_row) == cols:
            rows.append(current_row)
            current_row = []
    if current_row:
        rows.append(current_row)
    rows.append([
        InlineKeyboardButton("🔄 New Puzzle", callback_data="captcha_reload"),
        InlineKeyboardButton("📸 Refresh", callback_data="captcha_refresh"),
        InlineKeyboardButton("✅ Verify", callback_data="captcha_verify"),
    ])
    return InlineKeyboardMarkup(rows)


# ── Helpers ───────────────────────────────────────────────────────────────────

def _get_session(chat_id: int) -> dict:
    """Return (creating if absent) the session dict for *chat_id*."""
    if chat_id not in config.SESSION_STORE:
        config.SESSION_STORE[chat_id] = {}
    return config.SESSION_STORE[chat_id]


def save_offer_link(email: str, link: str) -> str:
    """Save captured Gemini Pro offer link to gemini_offers.txt."""
    filename = "gemini_offers.txt"
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    entry = f"[{timestamp}] Account: {email}\nOffer Link: {link}\n{'-'*50}\n"
    with open(filename, "a", encoding="utf-8") as f:
        f.write(entry)
    logger.info("Saved offer link to %s", filename)
    return filename


async def safe_reply(update_or_msg, text: str, **kwargs):
    """Safely send a reply, falling back to plain text if HTML/Markdown fails."""
    try:
        return await update_or_msg.reply_text(text, **kwargs)
    except Exception as e:
        logger.warning("Failed to send formatted text (%s), falling back to plain text", e)
        clean_text = text.replace("<b>", "").replace("</b>", "").replace("<i>", "").replace("</i>", "").replace("<code>", "").replace("</code>", "")
        return await update_or_msg.reply_text(clean_text, parse_mode=None)


# ── Handlers ──────────────────────────────────────────────────────────────────

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Send welcome message with command menu."""
    await safe_reply(
        update.message,
        "🤖 <b>Pixel 10 Pro Google One Bot</b>\n\n"
        "This bot simulates a Google Pixel 10 Pro (Android 16) device, "
        "logs into your Google account, and retrieves the <b>12-month free "
        "Gemini Pro</b> offer link from Google One.\n\n"
        "📋 <b>Available Commands:</b>\n"
        "• /login – Enter your Gmail credentials\n"
        "• /check_offer – Detect the Gemini Pro offer\n"
        "• /proxy – Check current IP, country & eligibility\n"
        "• /set_proxy &lt;url&gt; – Set an HTTP/SOCKS5 proxy\n"
        "• /clear_proxy – Use direct connection (ideal on India RDP)\n"
        "• /headless on|off – Toggle background headless mode\n"
        "• /get_link – Show last captured offer link\n"
        "• /saved_links – View all captured links saved to file\n"
        "• /status – View current session & device info\n\n"
        "📱 <b>Mobile / RDP Ready:</b>\n"
        "• Chrome runs silently in background (no popup windows).\n"
        "• reCAPTCHAs are solved 100% inside Telegram with interactive button tiles!\n"
        "• Eligible countries include: <b>India</b> 🇮🇳, <b>United States</b> 🇺🇸, UK, Canada, etc.\n\n"
        "⚠️ <i>Privacy Note:</i> Credentials are held in memory only for the "
        "duration of the session and never stored persistently.",
        parse_mode="HTML",
    )


# ── /login conversation ───────────────────────────────────────────────────────

async def login_start(update: Update,
                      context: ContextTypes.DEFAULT_TYPE) -> int:
    """Begin the login conversation – ask for email."""
    await update.message.reply_text(
        "📧 Please enter your Gmail address:",
        reply_markup=ReplyKeyboardRemove(),
    )
    return AWAIT_EMAIL


async def login_email(update: Update,
                      context: ContextTypes.DEFAULT_TYPE) -> int:
    """Store the email and ask for password."""
    email = update.message.text.strip()
    context.user_data["pending_email"] = email
    await safe_reply(
        update.message,
        f"✅ Email received: <code>{email}</code>\n\n🔒 Now enter your password:",
        parse_mode="HTML",
    )
    return AWAIT_PASSWORD


async def login_password(update: Update,
                         context: ContextTypes.DEFAULT_TYPE) -> int:
    """Store credentials, generate a new device profile, and finish."""
    chat_id = update.effective_chat.id
    password = update.message.text.strip()
    email = context.user_data.pop("pending_email", "")

    session = _get_session(chat_id)
    session["email"] = email
    session["password"] = password
    session["device"] = create_device_profile()
    session["offer_link"] = None

    # Delete the message containing the password for security
    try:
        await update.message.delete()
    except Exception:
        pass

    summary_text = (
        "✅ <b>Credentials saved</b> and a new Pixel 10 Pro device profile has "
        "been created for this session.\n\n"
        f"📱 <b>Device Profile</b>\n"
        f"Model: {session['device'].model}\n"
        f"Android: {session['device'].android_version}\n"
        f"IMEI: <code>{session['device'].imei}</code>\n"
        f"Android ID: <code>{session['device'].android_id}</code>\n"
        f"Session: <code>{session['device'].session_id[:8]}…</code>\n\n"
        "Use /check_offer to search for the Gemini Pro offer."
    )
    try:
        await context.bot.send_message(chat_id=chat_id, text=summary_text, parse_mode="HTML")
    except Exception:
        await context.bot.send_message(chat_id=chat_id, text=summary_text, parse_mode=None)

    return ConversationHandler.END


async def login_cancel(update: Update,
                       context: ContextTypes.DEFAULT_TYPE) -> int:
    """Cancel the login conversation."""
    chat_id = update.effective_chat.id
    if chat_id in PENDING_INPUTS and not PENDING_INPUTS[chat_id].done():
        PENDING_INPUTS[chat_id].cancel()
        PENDING_INPUTS.pop(chat_id, None)
    context.user_data.pop("pending_email", None)
    await update.message.reply_text(
        "❌ Action cancelled.",
        reply_markup=ReplyKeyboardRemove(),
    )
    return ConversationHandler.END


async def _watch_desktop_captcha(chat_id: int, driver, future: asyncio.Future, msg):
    """Watches if the user solves or verifies the reCAPTCHA directly on the live desktop window."""
    from google_automation import _is_bframe_active
    while not future.done():
        await asyncio.sleep(2.0)
        try:
            if not _is_bframe_active(driver):
                await asyncio.sleep(1.0)
                if not _is_bframe_active(driver) and not future.done():
                    logger.info("reCAPTCHA solved on live desktop window for chat %d", chat_id)
                    try:
                        next_btns = driver.find_elements(
                            By.CSS_SELECTOR, '#identifierNext, button[jsname="LgbsSe"], button[type="button"]'
                        )
                        for b in next_btns:
                            if b.is_displayed() and "next" in b.text.lower():
                                b.click()
                                break
                    except Exception:
                        pass

                    try:
                        await msg.edit_caption(
                            caption="✅ <b>reCAPTCHA Solved on live window! Proceeding…</b>",
                            parse_mode="HTML"
                        )
                    except Exception:
                        pass

                    future.set_result("solved_on_screen")
                    break
        except Exception:
            pass


# ── /check_offer ──────────────────────────────────────────────────────────────

async def check_offer(update: Update,
                      context: ContextTypes.DEFAULT_TYPE) -> None:
    """Run Google One automation with interactive Telegram verification support."""
    chat_id = update.effective_chat.id
    session = _get_session(chat_id)

    if not session.get("email") or not session.get("password"):
        await update.message.reply_text(
            "⚠️ No credentials found. Please use /login first."
        )
        return

    device = session.get("device")
    if not device:
        device = create_device_profile()
        session["device"] = device

    await safe_reply(
        update.message,
        "⏳ <b>Launching Pixel 10 Pro simulator and logging in…</b>\n\n"
        "💡 <i>Note:</i> If Google asks for a CAPTCHA or 2-Step Verification, "
        "I will send the prompt/image directly to this chat for you to confirm!",
        parse_mode="HTML"
    )

    loop = asyncio.get_running_loop()


    def prompt_callback(
        text: str,
        photo_bytes: Optional[bytes] = None,
        wait_for_reply: bool = True,
        custom_type: Optional[str] = None,
        extra_data: Optional[dict] = None,
    ) -> Optional[str]:
        """Threadsafe callback called from the Selenium automation thread."""
        async def _coro():
            if custom_type == "recaptcha_grid" and extra_data:
                driver = extra_data["driver"]
                num_tiles = extra_data.get("num_tiles", 9)
                instructions = extra_data.get("instructions", "")
                selected: Set[int] = set()

                future = loop.create_future()
                CAPTCHA_SESSIONS[chat_id] = {
                    "driver": driver,
                    "num_tiles": num_tiles,
                    "selected": selected,
                    "future": future,
                    "instructions": instructions,
                }

                keyboard = build_recaptcha_keyboard(num_tiles, selected)
                msg = await context.bot.send_photo(
                    chat_id=chat_id,
                    photo=photo_bytes,
                    caption=text,
                    reply_markup=keyboard,
                    parse_mode="HTML",
                )
                CAPTCHA_SESSIONS[chat_id]["message_id"] = msg.message_id

                watcher_task = asyncio.create_task(_watch_desktop_captcha(chat_id, driver, future, msg))

                try:
                    res = await asyncio.wait_for(future, timeout=240.0)
                    return res
                except asyncio.TimeoutError:
                    await context.bot.send_message(
                        chat_id=chat_id,
                        text="⏰ reCAPTCHA verification timed out. Please run /check_offer again."
                    )
                    return None
                finally:
                    watcher_task.cancel()
                    CAPTCHA_SESSIONS.pop(chat_id, None)

            clean_text = text.replace("<b>", "").replace("</b>", "").replace("<i>", "").replace("</i>", "").replace("<code>", "").replace("</code>", "").replace("*", "")
            try:
                if photo_bytes:
                    await context.bot.send_photo(chat_id=chat_id, photo=photo_bytes, caption=text, parse_mode="HTML")
                else:
                    await context.bot.send_message(chat_id=chat_id, text=text, parse_mode="HTML")
            except Exception:
                if photo_bytes:
                    await context.bot.send_photo(chat_id=chat_id, photo=photo_bytes, caption=clean_text)
                else:
                    await context.bot.send_message(chat_id=chat_id, text=clean_text)

            if wait_for_reply:
                future = loop.create_future()
                PENDING_INPUTS[chat_id] = future
                try:
                    user_reply = await asyncio.wait_for(future, timeout=180.0)
                    return user_reply
                except asyncio.TimeoutError:
                    await context.bot.send_message(
                        chat_id=chat_id,
                        text="⏰ Verification timed out. Please run /check_offer again."
                    )
                    return None
                finally:
                    PENDING_INPUTS.pop(chat_id, None)
            return None

        fut = asyncio.run_coroutine_threadsafe(_coro(), loop)
        return fut.result(timeout=250.0)

    try:
        offer_type, offer_link = await asyncio.to_thread(
            check_gemini_offer,
            session["email"],
            session["password"],
            device,
            prompt_callback,
        )
    except GoogleAutomationError as exc:
        await safe_reply(update.message, f"❌ <b>Error:</b> {exc}", parse_mode="HTML")
        return
    except Exception as exc:
        logger.exception("Unexpected error in check_offer for chat %s", chat_id)
        await safe_reply(update.message, f"❌ An unexpected error occurred: {exc}")
        return

    if offer_type == "gemini" and offer_link:
        session["offer_link"] = offer_link
        save_offer_link(session.get("email", "unknown"), f"[GEMINI PRO 12-MONTH] {offer_link}")
        success_msg = (
            "🎉 <b>Gemini Pro (Google One AI Premium) Offer Found!</b>\n\n"
            "Click the link below to activate your 12-month free Gemini Pro:\n\n"
            f"🔗 {offer_link}\n\n"
            "💾 <i>Saved to <code>gemini_offers.txt</code></i>\n"
            "<i>Use /get_link or /saved_links to view captured links.</i>"
        )
        await safe_reply(update.message, success_msg, parse_mode="HTML")
    elif offer_type == "other" and offer_link:
        session["offer_link"] = offer_link
        save_offer_link(session.get("email", "unknown"), f"[OTHER BENEFIT] {offer_link}")
        msg = (
            "⚠️ <b>No Gemini Pro Offer Available for this Account/Region</b>\n\n"
            "Google One was checked, but the 12-month free Gemini Pro promotion was <b>not granted</b> to this account.\n\n"
            f"🎁 <b>Google One Benefit Detected Instead:</b>\n"
            f"🔗 <code>{offer_link}</code>\n\n"
            "ℹ️ <b>Why is Gemini Pro missing?</b>\n"
            "• <b>Region Restriction:</b> The detected link contains <code>:BD:</code> (Bangladesh). Google's 12-month Gemini promotion is officially restricted to eligible launch regions (US, UK, etc.).\n"
            "• <b>Hardware Validation:</b> Google requires the official Google One app on an eligible Pixel device or a US account/IP.\n\n"
            "💡 <i>Tip: You can set a US proxy in your <code>.env</code> file (<code>PROXY=http://ip:port</code>) or connect through a US VPN to test a US region!</i>"
        )
        await safe_reply(update.message, msg, parse_mode="HTML")
    else:
        await safe_reply(
            update.message,
            "😔 No active Gemini Pro offer was detected on your Google One "
            "account at this time.\n\n"
            "The offer may not be available for your account region or may "
            "have already been activated. Try again later."
        )


# ── Interactive Message Input Handler ─────────────────────────────────────────

async def handle_user_input(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle text responses for CAPTCHA or 2FA codes."""
    chat_id = update.effective_chat.id
    text = (update.message.text or "").strip()

    if chat_id in PENDING_INPUTS and not PENDING_INPUTS[chat_id].done():
        PENDING_INPUTS[chat_id].set_result(text)
        await update.message.reply_text("✅ Verification received. Processing…")
        return


# ── /get_link ─────────────────────────────────────────────────────────────────

async def get_link(update: Update,
                   context: ContextTypes.DEFAULT_TYPE) -> None:
    """Return the last captured offer link for this session."""
    chat_id = update.effective_chat.id
    session = _get_session(chat_id)
    link = session.get("offer_link")

    if link:
        await safe_reply(
            update.message,
            f"🔗 <b>Last captured offer link:</b>\n\n{link}\n\n💾 <i>All offers are saved in <code>gemini_offers.txt</code>. Use /saved_links to view all.</i>",
            parse_mode="HTML",
        )
    else:
        await safe_reply(
            update.message,
            "ℹ️ No offer link has been captured yet. "
            "Use /check_offer to search for the Gemini Pro offer."
        )


# ── /saved_links ──────────────────────────────────────────────────────────────

async def saved_links(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Display all saved offer links from gemini_offers.txt."""
    filename = "gemini_offers.txt"
    if not os.path.exists(filename):
        await update.message.reply_text("ℹ️ No saved offers file found yet. Run /check_offer to detect and save offers.")
        return

    with open(filename, "r", encoding="utf-8") as f:
        content = f.read().strip()

    if not content:
        await update.message.reply_text("ℹ️ The saved offers file is currently empty.")
        return

    # If content is very long, send last 3500 chars to avoid Telegram length limit
    if len(content) > 3500:
        content = "...[truncated]...\n" + content[-3500:]

    await safe_reply(
        update.message,
        f"📋 <b>Saved Gemini Pro Offers (from gemini_offers.txt):</b>\n\n<code>{content}</code>",
        parse_mode="HTML"
    )



# ── /status ───────────────────────────────────────────────────────────────────

async def status(update: Update,
                 context: ContextTypes.DEFAULT_TYPE) -> None:
    """Show current session and device profile summary."""
    chat_id = update.effective_chat.id
    session = _get_session(chat_id)

    if not session:
        await update.message.reply_text(
            "ℹ️ No active session. Use /login to get started."
        )
        return

    email = session.get("email", "—")
    has_creds = bool(session.get("email") and session.get("password"))
    offer_link = session.get("offer_link")
    device = session.get("device")

    lines = [
        "📊 <b>Session Status</b>\n",
        f"Account: <code>{email}</code>",
        f"Credentials loaded: {'✅' if has_creds else '❌'}",
        f"Offer link captured: {'✅' if offer_link else '❌'}",
    ]

    if device:
        lines.append(
            f"\n📱 <b>Device Profile</b>\n"
            f"Model: {device.model}\n"
            f"Android: {device.android_version}\n"
            f"IMEI: <code>{device.imei}</code>\n"
            f"Android ID: <code>{device.android_id}</code>\n"
            f"Session: <code>{device.session_id[:8]}…</code>"
        )

    await safe_reply(
        update.message,
        "\n".join(lines),
        parse_mode="HTML",
    )


async def handle_captcha_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle interactive tile selections, reload, and verify for reCAPTCHA grid."""
    query = update.callback_query
    await query.answer()
    chat_id = update.effective_chat.id

    if chat_id not in CAPTCHA_SESSIONS:
        await safe_reply(query.message, "ℹ️ No active reCAPTCHA session.")
        return

    session = CAPTCHA_SESSIONS[chat_id]
    driver = session["driver"]
    num_tiles = session["num_tiles"]
    selected = session["selected"]
    data = query.data

    if data.startswith("tile_"):
        tile_idx = int(data.split("_")[1])
        if tile_idx in selected:
            selected.remove(tile_idx)
        else:
            selected.add(tile_idx)

        # Click the tile in Selenium iframe
        try:
            frames = driver.find_elements(By.CSS_SELECTOR, 'iframe[src*="bframe"], iframe[title*="recaptcha challenge"]')
            for f in frames:
                if f.is_displayed():
                    driver.switch_to.frame(f)
                    tiles = driver.find_elements(By.CSS_SELECTOR, "td.rc-imageselect-tile, .rc-image-tile-target, .rc-imageselect-table td")
                    if tile_idx < len(tiles):
                        driver.execute_script("arguments[0].click();", tiles[tile_idx])
                    driver.switch_to.default_content()
                    break
        except Exception as e:
            logger.warning("Error clicking tile %d: %s", tile_idx, e)
            driver.switch_to.default_content()

        # Update keyboard with checkmarks
        new_keyboard = build_recaptcha_keyboard(num_tiles, selected)
        try:
            await query.edit_message_reply_markup(reply_markup=new_keyboard)
        except Exception:
            pass

    elif data == "captcha_refresh":
        from google_automation import _inject_captcha_badges, _get_captcha_screenshot
        _inject_captcha_badges(driver)
        shot = _get_captcha_screenshot(driver)
        keyboard = build_recaptcha_keyboard(num_tiles, selected)
        try:
            await query.edit_message_media(
                media=InputMediaPhoto(
                    media=shot,
                    caption=f"🧩 <b>reCAPTCHA Image Puzzle</b>\n\n<b>Instructions:</b> {session.get('instructions', '')}\n\n<i>Tap the tile numbers below that match the instruction, then tap Verify:</i>",
                    parse_mode="HTML"
                ),
                reply_markup=keyboard
            )
        except Exception:
            try:
                await query.edit_message_reply_markup(reply_markup=keyboard)
            except Exception:
                pass

    elif data == "captcha_verify":
        # Click verify button in Selenium
        try:
            frames = driver.find_elements(By.CSS_SELECTOR, 'iframe[src*="bframe"], iframe[title*="recaptcha challenge"]')
            for f in frames:
                if f.is_displayed():
                    driver.switch_to.frame(f)
                    btn = driver.find_element(By.ID, "recaptcha-verify-button")
                    driver.execute_script("arguments[0].click();", btn)
                    driver.switch_to.default_content()
                    break
        except Exception as e:
            logger.warning("Error clicking verify: %s", e)
            driver.switch_to.default_content()

        await asyncio.sleep(2.5)

        # Check if challenge is solved
        from google_automation import _is_bframe_active, _inject_captcha_badges, _get_captcha_screenshot
        is_still_open = _is_bframe_active(driver)

        if not is_still_open:
            # Challenge solved! Click Next button on Google login page
            try:
                next_btns = driver.find_elements(By.CSS_SELECTOR, '#identifierNext, button[jsname="LgbsSe"], button[type="button"]')
                for b in next_btns:
                    if b.is_displayed() and "next" in b.text.lower():
                        b.click()
                        break
            except Exception:
                pass

            try:
                await query.edit_message_caption(caption="✅ <b>reCAPTCHA Verified Successfully! Proceeding…</b>", parse_mode="HTML")
            except Exception:
                pass
            if not session["future"].done():
                session["future"].set_result("verified")
        else:
            # More images appeared or second challenge
            num_tiles, instructions = _inject_captcha_badges(driver)
            if num_tiles:
                session["num_tiles"] = num_tiles
                session["instructions"] = instructions
            selected.clear()
            shot = _get_captcha_screenshot(driver)
            keyboard = build_recaptcha_keyboard(session["num_tiles"], selected)
            try:
                await query.edit_message_media(
                    media=InputMediaPhoto(
                        media=shot,
                        caption=f"🧩 <b>reCAPTCHA Update</b>\n\n<b>Instructions:</b> {session.get('instructions', '')}\n\n<i>Select any newly appeared matching tiles and tap Verify:</i>",
                        parse_mode="HTML"
                    ),
                    reply_markup=keyboard
                )
            except Exception:
                try:
                    await query.edit_message_reply_markup(reply_markup=keyboard)
                except Exception:
                    pass

    elif data == "captcha_reload":
        try:
            frames = driver.find_elements(By.CSS_SELECTOR, 'iframe[src*="bframe"], iframe[title*="recaptcha challenge"]')
            for f in frames:
                if f.is_displayed():
                    driver.switch_to.frame(f)
                    reload_btn = driver.find_element(By.ID, "recaptcha-reload-button")
                    driver.execute_script("arguments[0].click();", reload_btn)
                    driver.switch_to.default_content()
                    break
        except Exception:
            driver.switch_to.default_content()

        await asyncio.sleep(2.0)
        from google_automation import _inject_captcha_badges, _get_captcha_screenshot
        num_tiles, instructions = _inject_captcha_badges(driver)
        if num_tiles:
            session["num_tiles"] = num_tiles
            session["instructions"] = instructions
        selected.clear()
        shot = _get_captcha_screenshot(driver)
        keyboard = build_recaptcha_keyboard(session["num_tiles"], selected)
        try:
            await query.edit_message_media(
                media=InputMediaPhoto(
                    media=shot,
                    caption=f"🔄 <b>reCAPTCHA Reloaded</b>\n\n<b>Instructions:</b> {instructions}\n\n<i>Tap matching tiles below and tap Verify:</i>",
                    parse_mode="HTML"
                ),
                reply_markup=keyboard
            )
        except Exception:
            try:
                await query.edit_message_reply_markup(reply_markup=keyboard)
            except Exception:
                pass


# ── Proxy & Region Commands ───────────────────────────────────────────────────

async def proxy_status(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Show current proxy and detected region/eligibility status."""
    import urllib.request, json

    cur_proxy = config.PROXY or "None (Direct Connection)"
    msg = await safe_reply(update.message, "🔄 <i>Testing network connection and checking region…</i>", parse_mode="HTML")

    try:
        handlers = []
        if config.PROXY:
            handlers.append(urllib.request.ProxyHandler({'http': config.PROXY, 'https': config.PROXY}))
        opener = urllib.request.build_opener(*handlers)
        req = urllib.request.Request("http://ip-api.com/json", headers={"User-Agent": "Mozilla/5.0"})
        with opener.open(req, timeout=8) as resp:
            data = json.loads(resp.read().decode())
    except Exception as exc:
        data = {"error": str(exc)}

    if "error" in data:
        text = (
            f"🌐 <b>Proxy & Network Status</b>\n\n"
            f"<b>Current Proxy:</b> <code>{cur_proxy}</code>\n"
            f"❌ <b>Connection Error:</b> {data['error']}\n\n"
            f"💡 Use <code>/set_proxy &lt;proxy_url&gt;</code> to configure a proxy."
        )
    else:
        ip = data.get("query", "Unknown")
        country = data.get("country", "Unknown")
        country_code = data.get("countryCode", "")
        city = data.get("city", "")

        is_eligible = country in config.ELIGIBLE_COUNTRIES

        flag = f"{country} ({country_code})"
        if country_code == "IN":
            flag = f"🇮🇳 {country} (India)"
        elif country_code == "US":
            flag = f"🇺🇸 {country} (United States)"
        elif country_code == "GB":
            flag = f"🇬🇧 {country} (United Kingdom)"
        elif country_code == "BD":
            flag = f"🇧🇩 {country} (Bangladesh)"

        eligibility_badge = "✅ <b>Eligible Region!</b> (Google lists this country as supported)" if is_eligible else "⚠️ <b>Not Officially Supported Country</b> (Use India RDP or US Proxy)"

        text = (
            f"🌐 <b>Proxy & Regional Eligibility</b>\n\n"
            f"• <b>Public IP:</b> <code>{ip}</code>\n"
            f"• <b>Detected Country:</b> {flag} ({city})\n"
            f"• <b>Current Proxy:</b> <code>{cur_proxy}</code>\n"
            f"• <b>Promotion Status:</b> {eligibility_badge}\n\n"
            f"📋 <b>Commands:</b>\n"
            f"• <code>/set_proxy &lt;url&gt;</code> – Set proxy (e.g. <code>/set_proxy http://ip:port</code>)\n"
            f"• <code>/clear_proxy</code> – Revert to direct connection (ideal on India RDP)\n"
            f"• <code>/headless on|off</code> – Toggle background headless mode"
        )

    await msg.edit_text(text, parse_mode="HTML")


async def set_proxy(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Set the proxy URL dynamically for the bot session."""
    import urllib.request, json
    args = context.args
    if not args:
        await safe_reply(
            update.message,
            "ℹ️ <b>Usage:</b> <code>/set_proxy &lt;proxy_url&gt;</code>\n\n"
            "<b>Examples:</b>\n"
            "• <code>/set_proxy http://123.45.67.89:8080</code>\n"
            "• <code>/set_proxy http://user:pass@123.45.67.89:8080</code>\n"
            "• <code>/set_proxy socks5://123.45.67.89:1080</code>\n\n"
            "Use /clear_proxy to reset back to direct connection.",
            parse_mode="HTML"
        )
        return

    new_proxy = args[0].strip()
    status_msg = await safe_reply(update.message, "🔄 <i>Testing proxy connection…</i>", parse_mode="HTML")

    try:
        handlers = [urllib.request.ProxyHandler({'http': new_proxy, 'https': new_proxy})]
        opener = urllib.request.build_opener(*handlers)
        req = urllib.request.Request("http://ip-api.com/json", headers={"User-Agent": "Mozilla/5.0"})
        with opener.open(req, timeout=10) as resp:
            data = json.loads(resp.read().decode())
    except Exception as exc:
        await status_msg.edit_text(
            f"❌ <b>Proxy Connection Failed!</b>\n\n<code>{exc}</code>\n\n"
            "The proxy was not saved. Please verify the host, port, and credentials.",
            parse_mode="HTML"
        )
        return

    config.PROXY = new_proxy
    ip = data.get("query", "Unknown")
    country = data.get("country", "Unknown")
    is_eligible = country in config.ELIGIBLE_COUNTRIES

    badge = "✅ <b>Eligible Region!</b>" if is_eligible else "⚠️ <b>Country not on Google's list</b>"

    await status_msg.edit_text(
        f"✅ <b>Proxy Connected & Saved!</b>\n\n"
        f"• <b>New IP:</b> <code>{ip}</code>\n"
        f"• <b>Country:</b> {country}\n"
        f"• <b>Status:</b> {badge}\n\n"
        f"Future /check_offer runs will route through this proxy.",
        parse_mode="HTML"
    )


async def clear_proxy(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Clear the active proxy and use direct connection."""
    config.PROXY = ""
    await safe_reply(
        update.message,
        "✅ <b>Proxy Cleared!</b>\n\nThe bot is now using direct connection (ideal if running on India RDP).\nUse /proxy to check your IP.",
        parse_mode="HTML"
    )


async def headless_mode(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Toggle or show headless Chrome mode (no window on desktop, mobile-ready)."""
    args = context.args
    if not args:
        state = "ENABLED (Background / Mobile Mode – No Desktop Window)" if config.HEADLESS else "DISABLED (Desktop Window Visible)"
        await safe_reply(
            update.message,
            f"🤖 <b>Headless Mode:</b> {state}\n\n"
            f"• <code>/headless on</code> – Chrome runs silently in background (perfect for mobile/RDP)\n"
            f"• <code>/headless off</code> – Opens visible Chrome window on desktop",
            parse_mode="HTML"
        )
        return

    choice = args[0].lower()
    if choice in ("on", "1", "true", "yes", "enable"):
        config.HEADLESS = True
        await safe_reply(update.message, "✅ <b>Headless Mode ENABLED</b>\nChrome will run silently in background without opening any desktop windows. Perfect for mobile Telegram!", parse_mode="HTML")
    elif choice in ("off", "0", "false", "no", "disable"):
        config.HEADLESS = False
        await safe_reply(update.message, "✅ <b>Headless Mode DISABLED</b>\nA visible Chrome window will open on desktop when running automation.", parse_mode="HTML")
    else:
        await safe_reply(update.message, "Usage: <code>/headless on</code> or <code>/headless off</code>", parse_mode="HTML")


# ── Application setup ─────────────────────────────────────────────────────────

async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Log exceptions and notify user."""
    logger.error("Exception while handling an update:", exc_info=context.error)
    if isinstance(update, Update) and update.effective_message:
        try:
            await update.effective_message.reply_text(
                f"⚠️ Error: {context.error}"
            )
        except Exception:
            pass


def ensure_dependencies() -> None:
    """Check required packages and auto-install any that are missing."""
    import subprocess
    required = [
        ("telegram", "python-telegram-bot>=21.4"),
        ("selenium", "selenium>=4.21.0"),
        ("webdriver_manager", "webdriver-manager>=4.0.1"),
        ("dotenv", "python-dotenv>=1.0.0"),
        ("PIL", "Pillow>=10.0.0"),
    ]
    missing = []
    for mod, pkg in required:
        try:
            __import__(mod)
        except ImportError:
            missing.append(pkg)

    if missing:
        print(f"\n📦 Installing required dependencies: {', '.join(missing)}...")
        try:
            subprocess.check_call([sys.executable, "-m", "pip", "install", *missing])
            print("✅ Dependencies installed successfully!\n")
        except Exception as exc:
            print(f"⚠️ Warning: Auto-install failed ({exc}). Please run: pip install -r requirements.txt\n")


def ensure_bot_token() -> str:
    """
    Ensure TELEGRAM_BOT_TOKEN is available.
    If missing, prompt interactively in the terminal and save to .env.
    """
    token = (config.TELEGRAM_BOT_TOKEN or os.environ.get("TELEGRAM_BOT_TOKEN", "")).strip()
    if token:
        return token

    print("\n" + "=" * 60)
    print("      🤖 Pixel 10 Pro Google One Gemini Bot - Setup")
    print("=" * 60)
    print("No Telegram Bot Token was detected.")
    print("How to get one:")
    print(" 1. Open Telegram and message @BotFather")
    print(" 2. Send /newbot, choose a name and username")
    print(" 3. Copy the HTTP API token provided")
    print("-" * 60)

    while not token:
        try:
            user_input = input("👉 Enter your Telegram Bot Token: ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nSetup cancelled.")
            sys.exit(1)

        if ":" in user_input and len(user_input) > 20:
            token = user_input
        else:
            print("❌ Invalid token format! It should look like: 123456789:ABCdefGhIJKlmNoPQRsTUVwxyZ\n")

    # Save to .env
    env_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")
    lines = []
    token_written = False
    if os.path.exists(env_path):
        with open(env_path, "r", encoding="utf-8") as f:
            for line in f:
                if line.startswith("TELEGRAM_BOT_TOKEN="):
                    lines.append(f"TELEGRAM_BOT_TOKEN={token}\n")
                    token_written = True
                else:
                    lines.append(line)
    if not token_written:
        lines.append(f"TELEGRAM_BOT_TOKEN={token}\n")
        if not any(l.startswith("HEADLESS=") for l in lines):
            lines.append("HEADLESS=true\n")
        if not any(l.startswith("PROXY=") for l in lines):
            lines.append("PROXY=\n")

    with open(env_path, "w", encoding="utf-8") as f:
        f.writelines(lines)

    config.TELEGRAM_BOT_TOKEN = token
    print("✅ Telegram Bot Token saved to .env!")
    print("=" * 60 + "\n")
    return token


def main() -> None:
    ensure_dependencies()
    token = ensure_bot_token()

    app = Application.builder().token(token).build()

    # /login conversation
    login_conv = ConversationHandler(
        entry_points=[CommandHandler("login", login_start)],
        states={
            AWAIT_EMAIL: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, login_email)
            ],
            AWAIT_PASSWORD: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, login_password)
            ],
        },
        fallbacks=[CommandHandler("cancel", login_cancel)],
    )

    app.add_handler(CommandHandler("start", start))
    app.add_handler(login_conv)
    app.add_handler(CommandHandler("check_offer", check_offer))
    app.add_handler(CommandHandler("proxy", proxy_status))
    app.add_handler(CommandHandler("set_proxy", set_proxy))
    app.add_handler(CommandHandler("clear_proxy", clear_proxy))
    app.add_handler(CommandHandler("headless", headless_mode))
    app.add_handler(CommandHandler("get_link", get_link))
    app.add_handler(CommandHandler("saved_links", saved_links))
    app.add_handler(CommandHandler("status", status))
    app.add_handler(CommandHandler("cancel", login_cancel))
    # Handles interactive reCAPTCHA button grid clicks
    app.add_handler(CallbackQueryHandler(handle_captcha_callback))
    # Handles user text replies when answering text CAPTCHA or 2FA codes
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_user_input))
    app.add_error_handler(error_handler)

    logger.info("Bot is running. Press Ctrl-C to stop.")
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
