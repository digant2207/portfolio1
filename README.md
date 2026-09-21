# 📈 Smart Money 200 DMA Automated Paper Trading

An automated paper trading bot for Indian equities (NSE/BSE) that tracks 200 DMA breakout triggers, executes simulated trades with a ₹1,00,000 portfolio, applies strict risk management (2% Stop-Loss, 5% Target), and sends daily email performance reports.

**Runs 100% in the cloud via GitHub Actions — zero PC uptime required!**

---

## ⚡ Cloud Automation via GitHub Actions

Once pushed to GitHub, the included workflow (`.github/workflows/paper_trading_automation.yml`) runs automatically in the cloud on the following schedule:

| Schedule (IST) | Trigger | Automated Cloud Action |
| :--- | :--- | :--- |
| **6:00 PM & 6:30 PM** | Daily | Connects to your Gmail, extracts the *"Daily smart money finder report"*, parses stocks and sets 200 DMA + 1% buy triggers. |
| **9:15 AM - 3:30 PM** | Mon - Fri | Runs every 15 mins during market hours to evaluate live NSE/BSE quotes, execute paper buys, and check Stop-Loss (-2%) / Target (+5%) exits. |
| **3:45 PM** | Mon - Fri | Compiles and emails your daily portfolio performance summary to your inbox. |
| **Anytime** | Manual | Can be triggered manually via GitHub's **"Run workflow"** button from your phone or browser! |

---

## 🚀 How to Connect to GitHub (3 Easy Steps)

### Step 1: Create a Repository on GitHub
1. Go to **[github.com/new](https://github.com/new)**.
2. Name it **`portfolio1`** (make it **Private** so your trading data remains private).
3. Do NOT initialize with a README (this project already has one).
4. Click **Create repository**.

### Step 2: Push Your Local Code to GitHub
Run these commands in your PowerShell terminal inside `portfolio1`:

```powershell
# Set main branch
git branch -M main

# Add your GitHub repository as origin (replace with your GitHub username)
git remote add origin https://github.com/YOUR_GITHUB_USERNAME/portfolio1.git

# Push the project to GitHub
git push -u origin main
```

---

### Step 3: Add Your Gmail Secrets to GitHub (One-Time Setup)

To allow GitHub Actions to securely read your Gmail and send reports:
1. Open your repository on GitHub.
2. Go to **Settings** > **Secrets and variables** > **Actions**.
3. Click **New repository secret** and add these 2 secrets:

| Secret Name | Value |
| :--- | :--- |
| `GMAIL_USER` | `your.email@gmail.com` |
| `GMAIL_APP_PASSWORD` | `abcdefghijklmnop` *(Your 16-character Google App Password)* |
| `NOTIFICATION_RECIPIENT` | *(Optional)* Email where daily summaries should be sent. |
| `TELEGRAM_BOT_TOKEN` | *(Optional)* Bot Token from `@BotFather` for instant trade alerts. |
| `TELEGRAM_CHAT_ID` | *(Optional)* Your Telegram user ID or group ID. |

> 🔒 **Security**: GitHub Secrets are encrypted and never exposed in code or public logs.

---

## 🧪 Triggering a Cloud Run Manually Anytime

You don't need to wait for scheduled times:
1. Go to your GitHub repository > **Actions** tab.
2. Click **"Paper Trading Automation Engine"** on the left.
3. Click **Run workflow** and pick any task:
   - `fetch-mail` (Fetch & parse Gmail report right now)
   - `trade-cycle` (Check market prices and trigger orders)
   - `daily-report` (Email yourself a portfolio summary right now)
   - `all` (Automatic time-based execution)

---

## 💻 Optional: Running Local Web Dashboard on PC

If you ever want to view the live dark-mode dashboard on your local PC:
```powershell
.\.venv\Scripts\python.exe run.py
```
Open **[http://127.0.0.1:8000](http://127.0.0.1:8000)** in your browser.
