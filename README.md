# 📱 Pixel 10 Pro Google One Gemini Bot

> Automatically simulate a **Google Pixel 10 Pro (Android 16)** device, log into Google One, and claim/extract the **12-month free Gemini Pro (Google One AI Premium)** offer link — controllable entirely from **Telegram on your mobile phone**!

---

## 📑 Table of Contents
1. [How It Works](#-how-it-works)
2. [What to Set Up (Before You Start)](#-what-to-set-up-before-you-start)
3. [How to Install & Run (Step-by-Step)](#-how-to-install--run-step-by-step)
4. [Telegram Commands & What They Do](#-telegram-commands--what-they-do)
5. [How the Mobile in-Chat CAPTCHA Solver Works](#-how-the-mobile-in-chat-captcha-solver-works)
6. [Regional Eligibility & India RDP Guide](#-regional-eligibility--india-rdp-guide)
7. [Configuration File (`.env`) Reference](#-configuration-file-env-reference)
8. [Troubleshooting & FAQ](#-troubleshooting--faq)

---

## 🧠 How It Works

Here is the exact step-by-step flow of what happens under the hood:

```text
 ┌────────────────┐         ┌────────────────────┐         ┌───────────────────────┐
 │  Telegram Bot  │ ──────> │ Headless Chrome    │ ──────> │ Google One / Accounts │
 │  (Mobile/PC)   │         │ (Pixel 10 Pro Sim) │         │ (one.google.com)      │
 └────────────────┘         └────────────────────┘         └───────────────────────┘
         ▲                            │                                │
         │                            ▼                                │
         │                  [reCAPTCHA Triggered]                      │
         │                            │                                │
         │   Auto-crops puzzle image  │                                │
         │   Injects badges [1]..[9]  │                                │
         │ <──────────────────────────┤                                │
         │                                                             │
   User taps [1] [5] [Verify]                                          │
         │ ──────────────────────────> Headless Chrome Clicks          │
         │                             & Solves Puzzle                 │
         │                                    │                        │
         │                                    ▼                        │
         │                             Logs into Google One            │
         │                             Scans AI Premium Plans <────────┘
         │                                    │
         │ <──────────────────────────────────┴── Returns Gemini Pro Link!
         │                                        & Saves to gemini_offers.txt
```

1. **You send `/login` and `/check_offer`** in Telegram from your phone or PC.
2. **The bot launches a background (headless) Chrome browser** configured with genuine Pixel 10 Pro hardware characteristics (Android 16 user-agent, mobile viewport `390x844`, CDP anti-detection flags).
3. **If Google asks for a reCAPTCHA visual puzzle**, the bot extracts the challenge box, places clear numbered badges (`1` to `9` or `16`) over each picture, and sends it directly to your Telegram chat.
4. **You tap the matching numbers on the Telegram button grid** (`[ 1 ]`, `[ 2 ]`, etc.) and tap `[ ✅ Verify ]`.
5. **The bot clicks the tiles in Chrome**, verifies with Google, navigates to Google One, grabs the Gemini Pro offer link, displays it in chat, and appends it to `gemini_offers.txt`.

---

## ⚙️ What to Set Up (Before You Start)

You only need **two things**:

### 1. Python 3.10 or newer
- **Windows:** Download from [python.org](https://www.python.org/downloads/). During installation, make sure to check the box:  
  ✅ **"Add Python to PATH"**.
- **Linux/RDP:** Run `sudo apt update && sudo apt install python3 python3-pip python3-venv -y`.

### 2. A Free Telegram Bot Token
1. Open Telegram and search for [@BotFather](https://t.me/BotFather).
2. Send the message `/newbot`.
3. Choose a display name (e.g. `My Pixel Bot`) and a username ending in `bot` (e.g. `mypixel_gemini_bot`).
4. BotFather will give you a token that looks like:  
   `12564782:abcsddsgh`
5. Keep this token handy — you will paste it when the terminal asks for it!

---

## 💻 How to Install & Run (Step-by-Step)

### Option A: Windows (One-Click Auto-Setup)

1. **Download or clone the repository:**
   ```powershell
   git clone https://github.com/noyonbee-cmd/pixel-gemini.git
   cd pixel-gemini
   ```
2. **Double-click [`start_bot.bat`].**
3. **Automatic Installation:** The script automatically:
   - Checks your Python version.
   - Creates the virtual environment (`venv`).
   - Automatically installs all required packages (`python-telegram-bot`, `selenium`, `Pillow`, etc.).
   - Prompts you for your Telegram Bot Token if you haven't set it yet:
     ```text
     👉 Enter your Telegram Bot Token: 
     ```
   - Saves it to `.env` and immediately starts your bot!

---

### Option B: Linux / VPS / India RDP (One-Click)

1. **Clone the repository:**
   ```bash
   git clone https://github.com/noyonbee-cmd/pixel-gemini.git
   cd pixel-gemini
   ```
2. **Make the start script executable and run:**
   ```bash
   chmod +x start_bot.sh
   ./start_bot.sh
   ```
3. Enter your Telegram Bot Token when prompted. That's it!

---

### Option C: Manual Setup

1. Create a virtual environment and activate it:
   ```bash
   # Windows:
   python -m venv venv
   venv\Scripts\activate

   # Linux/macOS:
   python3 -m venv venv
   source venv/bin/activate
   ```
2. Install the packages:
   ```bash
   pip install -r requirements.txt
   ```
3. Run the bot:
   ```bash
   python main.py
   ```
   *(If `.env` is missing, the terminal will ask for your Telegram Token interactively and create `.env` for you).*

---

## 🤖 Telegram Commands & What They Do

| Command | What It Does | Example Usage |
|---|---|---|
| `/start` | Shows the welcome menu and list of all available commands. | `/start` |
| `/login` | Starts a secure 2-step prompt asking for your Gmail email and password. Passwords are held in memory only for the active session. | `/login` |
| `/check_offer` | Launches Pixel 10 Pro simulation, logs into Google One, prompts for CAPTCHA if needed, and searches for Gemini Pro. | `/check_offer` |
| `/proxy` | Tests your network connection and displays your current public IP, country, and promotion eligibility status. | `/proxy` |
| `/set_proxy <url>` | Dynamically connects through an HTTP or SOCKS5 proxy (useful if you are in an unsupported region). | `/set_proxy http://123.45.67.89:8080`<br>`/set_proxy socks5://ip:port` |
| `/clear_proxy` | Removes any active proxy and reverts to your direct network connection (ideal when running on an India RDP). | `/clear_proxy` |
| `/headless on\|off` | Toggles background headless mode. When `on`, Chrome runs silently without desktop popups (ideal for mobile use). | `/headless on`<br>`/headless off` |
| `/get_link` | Shows the last successfully captured Gemini Pro offer link. | `/get_link` |
| `/saved_links` | Reads and displays all captured links saved in `gemini_offers.txt`. | `/saved_links` |
| `/status` | Displays your active session info, credentials state, and simulated Pixel 10 Pro device specs (IMEI, Android ID). | `/status` |
| `/cancel` | Cancels any ongoing login conversation. | `/cancel` |

---

## 📱 How the Mobile in-Chat CAPTCHA Solver Works

When Google asks to verify you're not a robot, **you never need to open a desktop browser**:

```
+───────────────────────────────────────────────────────────+
│  🧩 reCAPTCHA Image Puzzle                                │
│  Instructions: Select all squares with traffic lights     │
│                                                           │
│  [Photo with badges: 1, 2, 3 on top row, 4, 5, 6, etc.]   │
│                                                           │
│   [ 1 ]         [ 🟢 2 ]       [ 3 ]                      │
│   [ 4 ]         [ 5 ]          [ 🟢 6 ]                   │
│   [ 7 ]         [ 8 ]          [ 9 ]                      │
│   [🔄 New Puzzle]  [📸 Refresh]  [✅ Verify]              │
+───────────────────────────────────────────────────────────+
```

1. **Auto-Cropped Image:** The bot captures only the reCAPTCHA box, so on your phone screen the puzzle is **large, crisp, and easy to see**.
2. **Numbered Badges:** Every tile is numbered (`1`, `2`, `3`...).
3. **Tap Buttons:**
   - Tap matching tile numbers (e.g. `2` and `6`): they turn green (`🟢 2`, `🟢 6`).
   - Tap **`[ 📸 Refresh ]`** if new replacement tiles fade in.
   - Tap **`[ 🔄 New Puzzle ]`** to reload a fresh puzzle if the current one is unclear.
   - Tap **`[ ✅ Verify ]`** when finished. The bot submits the challenge and proceeds to Google One!

---

## 🌐 Regional Eligibility & India RDP Guide

Google One's official promotional terms for the 12-month Gemini Advanced Pixel promotion officially cover:

> **Eligible Countries:** Australia, Austria, Belgium, Canada, Czechia, Denmark, Estonia, Finland, France, Germany, Hungary, **India 🇮🇳**, Ireland, Italy, Latvia, Lithuania, Malaysia, Mexico, Netherlands, Norway, Poland, Portugal, Romania, Singapore, Slovakia, Slovenia, Spain, Sweden, Switzerland, Taiwan, United Kingdom, and the **United States 🇺🇸**.

### 🇮🇳 Why Running on an India RDP is Best:
- **India is an officially eligible launch country.**
- If you host this bot on your **India RDP**, your network IP is already recognized by Google as India.
- **You do NOT need any external VPN or proxy on an India RDP!**
- Run `/proxy` in chat to confirm:
  ```text
  • Public IP: 103.xxx.xxx.xxx
  • Detected Country: 🇮🇳 India
  • Promotion Status: ✅ Eligible Region!
  ```

### 🌍 Running Outside Supported Countries (e.g., Bangladesh):
- Google will detect your region and only show local offers (like YouTube Premium Lite).
- To solve this, connect your host to a US/India VPN, or set a proxy in Telegram:
  ```text
  /set_proxy http://your-us-proxy:port
  ```

---

## 📁 Configuration File (`.env`) Reference

Your settings are stored in `.env` in the root folder:

```env
# Your Telegram Bot Token from @BotFather (Required)
TELEGRAM_BOT_TOKEN=123456789:ABCdefGhIJKlmNoPQRsTUVwxyZ

# Run Chrome silently in the background (Default: true)
# Set to 'true' for mobile & RDP usage (no desktop window popup)
# Set to 'false' if you want to watch the live Chrome window on desktop
HEADLESS=true

# Optional: HTTP or SOCKS5 proxy (e.g. http://ip:port or socks5://ip:port)
PROXY=
```

---

## ❓ Troubleshooting & FAQ

### Q1: The bot says "Conflict: terminated by other getUpdates request"
- **Cause:** You have two instances of the bot running with the same token at the same time.
- **Fix:** Close any other running terminal/CMD window running `main.py` or `start_bot.bat`. Only run one instance.

### Q2: Why did I get a YouTube Premium link instead of Gemini Pro?
- **Cause:** Your account region or IP address is detected in an unsupported country (e.g. Bangladesh `:BD:`).
- **Fix:** Use an India RDP (where India is officially eligible) or use `/set_proxy` with a US/India proxy, and ensure your Google account region supports Google One AI Premium.

### Q3: Can I run this bot 24/7 on an RDP or VPS?
- **Yes!** Because `HEADLESS=true` is enabled by default, the bot requires no monitor or screen. You can leave `start_bot.bat` or `./start_bot.sh` running in the background and control everything from Telegram on your phone.

---

## 🔒 Privacy Notice

- **In-Memory Only:** Passwords are held in memory only for the duration of the login request and are never written to disk or logged.
- **No Token Leaks:** The `.env` file and `gemini_offers.txt` are included in `.gitignore` to prevent any accidental credentials leak when pushing code to GitHub.

---

## 📄 License
This project is open-source and licensed under the [MIT License](LICENSE).
