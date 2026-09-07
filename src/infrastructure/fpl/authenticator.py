import logging
import json
import time
from typing import Dict, List, Any, Optional
from playwright.sync_api import sync_playwright

logger = logging.getLogger("FPLAuthenticator")


class PlaywrightFPLAuthenticator:
    """Fully autonomous browser-based authenticator and API executor for FPL."""

    def __init__(self, email: str, password: str):
        self.email = email
        self.password = password

    def _login_and_get_page(self, playwright):
        browser = playwright.chromium.launch(headless=True)
        context = browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
        )
        page = context.new_page()
        page.goto("https://fantasy.premierleague.com/", wait_until="domcontentloaded", timeout=40000)
        time.sleep(2)
        try:
            page.locator("#onetrust-accept-btn-handler").click()
        except Exception:
            pass
        time.sleep(2)

        try:
            page.locator("text='تسجيل الدخول'").first.click(timeout=8000)
        except Exception:
            page.locator("text=/Sign in|Log in/i").first.click(timeout=8000)
        user_input = page.locator("#username").first
        user_input.wait_for(state="visible", timeout=15000)
        pass_input = page.locator("#password").first

        user_input.fill(self.email)
        time.sleep(0.3)
        pass_input.fill(self.password)
        time.sleep(0.3)
        pass_input.press("Enter")

        page.wait_for_url(lambda u: "fantasy.premierleague.com" in u and "account." not in u, timeout=30000)
        time.sleep(5)
        return browser, page

    def get_my_team_live(self, team_id: int) -> Dict[str, Any]:
        with sync_playwright() as p:
            browser, page = self._login_and_get_page(p)
            try:
                res = page.evaluate(f"""async () => {{
                    const r = await fetch('/api/my-team/{team_id}/');
                    return await r.json();
                }}""")
                return res
            finally:
                browser.close()

    def submit_lineup_live(self, team_id: int, picks_payload: List[Dict[str, Any]], chip: Optional[str] = None) -> Dict[str, Any]:
        payload_str = json.dumps({"chip": chip, "picks": picks_payload})
        with sync_playwright() as p:
            browser, page = self._login_and_get_page(p)
            try:
                res = page.evaluate(f"""async () => {{
                    const r = await fetch('/api/my-team/{team_id}/', {{
                        method: 'POST',
                        headers: {{
                            'Content-Type': 'application/json; charset=UTF-8',
                            'X-Requested-With': 'XMLHttpRequest'
                        }},
                        body: JSON.stringify({payload_str})
                    }});
                    return {{ status: r.status }};
                }}""")
                return {"status": "success" if res.get("status") in [200, 201] else "error", "code": res.get("status")}
            finally:
                browser.close()

    def submit_transfers_live(self, team_id: int, payload: Dict[str, Any]) -> Dict[str, Any]:
        payload_str = json.dumps(payload)
        with sync_playwright() as p:
            browser, page = self._login_and_get_page(p)
            try:
                res = page.evaluate(f"""async () => {{
                    const r = await fetch('/api/transfers/', {{
                        method: 'POST',
                        headers: {{
                            'Content-Type': 'application/json; charset=UTF-8',
                            'X-Requested-With': 'XMLHttpRequest'
                        }},
                        body: JSON.stringify({payload_str})
                    }});
                    return {{ status: r.status }};
                }}""")
                return {"status": "success" if res.get("status") in [200, 201] else "error", "code": res.get("status")}
            finally:
                browser.close()
