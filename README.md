# 📱 Pixel 10 Pro Google One Gemini Bot

A high-performance Telegram bot that emulates a **Google Pixel 10 Pro (Android 16)** device to log into Google One and detect/extract the **12-month free Gemini Pro (Google One AI Premium)** offer link.

Featuring an **in-Telegram mobile reCAPTCHA solver**, background headless automation, auto-saving of captured links, and full proxy/regional support.

---

## ✨ Features

- **📱 Pixel 10 Pro (Android 16) Emulation:** Simulates real Pixel 10 Pro hardware characteristics (IMEI, Android ID, mobile viewport `390x844`, custom Chrome 124 UA) with Chrome DevTools Protocol (CDP) anti-detection.
- **🧩 In-Telegram Mobile reCAPTCHA Solver:** Solves reCAPTCHA visual tile puzzles directly inside Telegram on your phone! Challenge images are automatically cropped, numbered with badges (`1` to `9` or `16`), and paired with an interactive button grid. No desktop browser or monitor required.
- **🚀 100% Background / Headless Ready:** Runs completely silently in background mode (`HEADLESS=true`). Perfect for running on Linux servers, Windows RDPs, or local PCs while controlling everything from your mobile phone.
- **🌐 Regional Support & Proxy Manager:** Google's promotional terms officially support regions including **India 🇮🇳**, **United States 🇺🇸**, **United Kingdom 🇬🇧**, Canada, Australia, and more. Manage proxies on the fly with `/proxy`, `/set_proxy`, and `/clear_proxy`.
- **💾 Automatic Offer Storage:** Successfully captured promotion links are automatically timestamped and saved to `gemini_offers.txt`.
- **⚡ Interactive Terminal Setup:** When launched, the script automatically verifies and installs missing dependencies and prompts for your Telegram Bot Token if not yet configured.

---

## 🚀 Quick Start

### Option A: Windows (One-Click)

1. Clone or download this repository:
   ```bash
   git clone https://github.com/noyonbee-cmd/pixel-gemini.git
   cd pixel-gemini
   ```
2. Double-click **`start_bot.bat`**.
3. If this is your first time, the terminal will automatically create a virtual environment, install requirements, and prompt you:
   ```text
   👉 Enter your Telegram Bot Token: 
   ```
4. Paste your token from [@BotFather](https://t.me/BotFather). The bot will save it to `.env` and start immediately!

---

### Option B: Linux / VPS / RDP (One-Click)

1. Clone the repository:
   ```bash
   git clone https://github.com/noyonbee-cmd/pixel-gemini.git
   cd pixel-gemini
   ```
2. Make the script executable and run:
   ```bash
   chmod +x start_bot.sh
   ./start_bot.sh
   ```
3. Enter your Telegram Bot Token when prompted.

---

### Option C: Manual Setup

1. **Install dependencies:**
   ```bash
   pip install -r requirements.txt
   ```
2. **Configure `.env`:**
   Copy `.env.example` to `.env` or run `python main.py` to configure interactively:
   ```env
   TELEGRAM_BOT_TOKEN=your_token_from_botfather
   HEADLESS=true
   PROXY=
   ```
3. **Start the bot:**
   ```bash
   python main.py
   ```

---

## 🤖 Telegram Commands

| Command | Description |
|---|---|
| `/start` | Show welcome message, features, and command list |
| `/login` | Enter your Gmail email and password (two-step secure conversation) |
| `/check_offer` | Simulate Pixel 10 Pro, log into Google One, and scan for Gemini Pro |
| `/proxy` | Check current public IP, country, and promotion eligibility |
| `/set_proxy <url>` | Set an HTTP or SOCKS5 proxy (e.g. `/set_proxy http://ip:port`) |
| `/clear_proxy` | Revert to direct connection (ideal on India RDP) |
| `/headless on\|off` | Toggle background headless mode (default: `on`) |
| `/get_link` | Retrieve the last captured offer link |
| `/saved_links` | View all captured links saved in `gemini_offers.txt` |
| `/status` | View current session status and active device profile |
| `/cancel` | Cancel current ongoing conversation |

---

## 📱 In-Telegram Mobile reCAPTCHA Solver

When Google prompts for a security verification (reCAPTCHA puzzle), you don't need a desktop screen:

```
+───────────────────────────────────────────────────+
│       🧩 reCAPTCHA Image Puzzle                   │
│       Instructions: Select all squares with cars  │
│                                                   │
│       [ 1 ] [ 2 ] [ 3 ]                           │
│       [ 4 ] [ 5 ] [ 6 ]                           │
│       [ 7 ] [ 8 ] [ 9 ]                           │
│                                                   │
│   [ 1 ]       [ 🟢 2 ]     [ 3 ]                  │
│   [ 4 ]       [ 5 ]        [ 🟢 6 ]               │
│   [ 7 ]       [ 8 ]        [ 9 ]                  │
│   [🔄 New Puzzle] [📸 Refresh] [✅ Verify]        │
+───────────────────────────────────────────────────+
```

1. The bot sends a high-resolution, auto-cropped photo of the challenge box with numbered badges (`1` to `9`).
2. Tap the corresponding numbers on the inline button grid to select tiles (e.g., tap `2` -> turns to `🟢 2`).
3. Tap **`✅ Verify`** to finish the challenge.
4. If more images fade in, tap **`📸 Refresh`** to update the photo.

---

## 🌐 Regional Eligibility & India RDP Guide

Google One's official promotional terms for the Pixel 12-month Gemini Advanced offer officially include:
> **Australia, Austria, Belgium, Canada, Czechia, Denmark, Estonia, Finland, France, Germany, Hungary, India, Ireland, Italy, Latvia, Lithuania, Malaysia, Mexico, Netherlands, Norway, Poland, Portugal, Romania, Singapore, Slovakia, Slovenia, Spain, Sweden, Switzerland, Taiwan, United Kingdom, United States.**

### Running on an India RDP:
- If you host this bot on an **India RDP**, your network IP is already recognized as India (`IN`).
- India is an officially eligible country! **No external VPN or proxy is needed on an India RDP.**
- Use `/proxy` in chat to verify:
  ```
  • Public IP: 103.xxx.xxx.xxx
  • Detected Country: 🇮🇳 India
  • Promotion Status: ✅ Eligible Region!
  ```

### Running Outside Eligible Regions:
- If your native connection is in an unsupported country, use `/set_proxy http://us-ip:port` or connect your host machine to a US/India VPN before running `/check_offer`.

---

## 📁 Project Structure

```text
pixel-gemini/
├── main.py               # Telegram bot handlers & interactive CLI setup
├── google_automation.py  # Selenium automation, stealth script & CAPTCHA bridge
├── device_simulator.py   # Android 16 Pixel 10 Pro profile & hardware simulation
├── config.py             # Global settings, constants & country eligibility
├── requirements.txt      # Python package dependencies
├── start_bot.bat         # One-click Windows runner & auto-installer
├── start_bot.sh          # One-click Linux/VPS runner
├── .env.example          # Environment variables template
├── .gitignore            # Git exclusion rules (keeps credentials private)
└── README.md             # Documentation
```

---

## 🔒 Security & Privacy

- **In-Memory Credential Handling:** Passwords are held in memory only for the active session duration and are never saved to disk.
- **Git Safety:** `.env` and `gemini_offers.txt` are included in `.gitignore` to prevent accidental credential leaks.
- Always use a secondary or test account when performing automation.

---

## 📄 License

This project is licensed under the MIT License.
