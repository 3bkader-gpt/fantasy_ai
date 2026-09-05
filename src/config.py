import os
from pathlib import Path
from dataclasses import dataclass
from dotenv import load_dotenv

# Root Directory
ROOT_DIR = Path(__file__).resolve().parent.parent
load_dotenv(ROOT_DIR / ".env")


@dataclass(frozen=True)
class AppConfig:
    """Immutable application settings loaded from environment."""
    # Google Gemini
    gemini_api_key: str = os.getenv("GEMINI_API_KEY", "")
    gemini_model: str = os.getenv("GEMINI_MODEL", "gemini-3.6-flash")

    # FPL Credentials
    fpl_email: str = os.getenv("FPL_EMAIL", "")
    fpl_password: str = os.getenv("FPL_PASSWORD", "")
    fpl_cookie: str = os.getenv("FPL_COOKIE", "")
    fpl_team_id: int = int(os.getenv("FPL_TEAM_ID", "0")) if os.getenv("FPL_TEAM_ID", "0").isdigit() else 0

    # Strategy & Safety
    dry_run: bool = os.getenv("DRY_RUN", "True").strip().lower() in ("true", "1", "yes")
    max_allowed_hits: int = int(os.getenv("MAX_ALLOWED_HITS", "1"))
    horizon_weeks: int = int(os.getenv("HORIZON_WEEKS", "3"))
    horizon_decay: float = float(os.getenv("HORIZON_DECAY", "0.85"))
    min_starter_chance: int = int(os.getenv("MIN_STARTER_CHANCE", "75"))
    final_safety_check_mins: int = int(os.getenv("FINAL_SAFETY_CHECK_MINS", "20"))

    # Telegram Notifications
    telegram_bot_token: str = os.getenv("TELEGRAM_BOT_TOKEN", "")
    telegram_chat_id: str = os.getenv("TELEGRAM_CHAT_ID", "")

    # Endpoints
    fpl_base_url: str = "https://fantasy.premierleague.com/api"
    fpl_login_url: str = "https://users.premierleague.com/accounts/login/"
    fpl_bootstrap_url: str = "https://fantasy.premierleague.com/api/bootstrap-static/"
    fpl_fixtures_url: str = "https://fantasy.premierleague.com/api/fixtures/"
    fpl_my_team_url: str = "https://fantasy.premierleague.com/api/my-team"
    fpl_transfers_url: str = "https://fantasy.premierleague.com/api/transfers/"
    data_cache_dir: Path = ROOT_DIR / "data_cache"


config = AppConfig()
