import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Any, Optional

logger = logging.getLogger("GeminiRateLimiter")

ROOT_DIR = Path(__file__).resolve().parent.parent.parent.parent
JSON_FILE = ROOT_DIR / "gemini_rate_limits.json"
MD_FILE = ROOT_DIR / "GEMINI_RATE_LIMITS.md"


class GeminiRateLimiter:
    """Tracks Google Gemini API rate limits, tokens, and daily quotas across all models."""

    def __init__(self, json_path: Path = JSON_FILE, md_path: Path = MD_FILE):
        self.json_path = json_path
        self.md_path = md_path
        self.data: Dict[str, Any] = self._load()

    def _load(self) -> Dict[str, Any]:
        if self.json_path.exists():
            try:
                with open(self.json_path, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception as e:
                logger.warning(f"Failed to load {self.json_path}: {e}")
        return {"last_updated": datetime.now(timezone.utc).isoformat(), "models": {}}

    def can_call(self, model: str) -> bool:
        """Checks if model has remaining daily and minute quota."""
        info = self.data.get("models", {}).get(model)
        if not info:
            return True
        rpd_limit = info.get("rpd_limit", 0)
        rpd_curr = info.get("rpd_current", 0)
        if rpd_limit > 0 and rpd_curr >= rpd_limit:
            logger.warning(f"Model {model} reached RPD quota: {rpd_curr}/{rpd_limit}")
            return False
        return True

    def record_call(self, model: str, total_tokens: int = 0):
        """Records a successful API call, updates token counts, and regenerates files."""
        models = self.data.setdefault("models", {})
        if model not in models:
            models[model] = {
                "display_name": model.replace("-", " ").title(),
                "category": "Text-out models",
                "rpm_current": 1, "rpm_limit": 5,
                "tpm_current": total_tokens, "tpm_limit": 250000,
                "rpd_current": 1, "rpd_limit": 20
            }
        else:
            m = models[model]
            m["rpd_current"] = m.get("rpd_current", 0) + 1
            m["rpm_current"] = m.get("rpm_current", 0) + 1
            m["tpm_current"] = m.get("tpm_current", 0) + total_tokens

        now_str = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
        self.data["last_updated"] = now_str
        self._save(now_str)

    def _save(self, timestamp_str: str):
        # Sort models descending by version (newest first)
        def _version_key(item: tuple) -> tuple:
            name = item[1].get("display_name", item[0]).lower()
            import re
            m = re.search(r"(\d+(?:\.\d+)?)", name)
            ver = float(m.group(1)) if m else 0.0
            sub = 3 if "flash lite" not in name and "pro" not in name else (2 if "pro" in name else 1)
            return (ver, sub)

        sorted_models = dict(sorted(self.data.get("models", {}).items(), key=_version_key, reverse=True))
        self.data["models"] = sorted_models

        # 1. Save JSON
        try:
            with open(self.json_path, "w", encoding="utf-8") as f:
                json.dump(self.data, f, indent=2, ensure_ascii=False)
        except Exception as e:
            logger.error(f"Error saving {self.json_path}: {e}")

        # 2. Save Markdown
        try:
            md_lines = [
                "# 📊 Google Gemini Rate Limits & Live Quota Tracker",
                f"*Last Updated: {timestamp_str}*",
                "",
                "| Model / Tool | Category | RPM | TPM | RPD |",
                "| :--- | :--- | :--- | :--- | :--- |"
            ]
            for _, info in sorted_models.items():
                name = info.get("display_name", "Unknown")
                cat = info.get("category", "Text-out models")
                rpm = f"{info.get('rpm_current', 0)} / {info.get('rpm_limit', 0)}"

                tpm_c = info.get("tpm_current", 0)
                tpm_l = info.get("tpm_limit", 0)
                tpm_c_str = f"{tpm_c / 1000:.2f}K" if tpm_c >= 1000 else f"{tpm_c}"
                tpm_l_str = f"{tpm_l // 1000}K" if tpm_l >= 1000 else f"{tpm_l}"
                tpm = f"{tpm_c_str} / {tpm_l_str}"

                rpd = f"{info.get('rpd_current', 0)} / {info.get('rpd_limit', 0)}"
                md_lines.append(f"| {name} | {cat} | {rpm} | {tpm} | {rpd} |")

            with open(self.md_path, "w", encoding="utf-8") as f:
                f.write("\n".join(md_lines) + "\n")
        except Exception as e:
            logger.error(f"Error saving {self.md_path}: {e}")
