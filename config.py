import os
from dotenv import load_dotenv

load_dotenv()

BOT_TOKEN: str = os.environ["BOT_TOKEN"]
DATABASE_URL: str = os.environ["DATABASE_URL"]
ADMIN_CHANNEL_ID: int = int(os.environ["ADMIN_CHANNEL_ID"])
SUPPORT_GROUP_ID: int = int(os.environ["SUPPORT_GROUP_ID"])
ADMIN_USERNAME: str = os.environ.get("ADMIN_USERNAME", "admin")

# Deposit / payment settings
DEPOSIT_EXPIRY_MINUTES: int = int(os.environ.get("DEPOSIT_EXPIRY_MINUTES", "60"))
PAYMENT_EXPIRY_MINUTES: int = int(os.environ.get("PAYMENT_EXPIRY_MINUTES", "30"))
DEPOSIT_ADDRESS: str = os.environ.get("DEPOSIT_ADDRESS", "YOUR_SOL_ADDRESS")

# Watcher poll interval (seconds)
WATCHER_INTERVAL: int = int(os.environ.get("WATCHER_INTERVAL", "30"))

# Telegram WebApp URL for wallet connect mini-app.
# If not set, the bot falls back to the text-based challenge flow.
# Must be a publicly accessible HTTPS URL, e.g. https://yourdomain.com/wallet
WEBAPP_URL: str = os.environ.get("WEBAPP_URL", "")
