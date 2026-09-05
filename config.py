"""Backwards compatibility shim for config."""
from src.config import config, AppConfig, ROOT_DIR as BASE_DIR

# Expose legacy variables
GEMINI_API_KEY = config.gemini_api_key
GEMINI_MODEL = config.gemini_model
FPL_EMAIL = config.fpl_email
FPL_PASSWORD = config.fpl_password
FPL_COOKIE = config.fpl_cookie
FPL_TEAM_ID = config.fpl_team_id
DRY_RUN = config.dry_run
MAX_ALLOWED_HITS = config.max_allowed_hits
HORIZON_WEEKS = config.horizon_weeks
HORIZON_DECAY = config.horizon_decay
TELEGRAM_BOT_TOKEN = config.telegram_bot_token
TELEGRAM_CHAT_ID = config.telegram_chat_id
FPL_BASE_URL = config.fpl_base_url
FPL_LOGIN_URL = config.fpl_login_url
FPL_BOOTSTRAP_URL = config.fpl_bootstrap_url
FPL_FIXTURES_URL = config.fpl_fixtures_url
FPL_MY_TEAM_URL = config.fpl_my_team_url
FPL_TRANSFERS_URL = config.fpl_transfers_url
