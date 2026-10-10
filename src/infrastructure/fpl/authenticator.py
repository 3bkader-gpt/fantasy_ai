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
        browser = playwright.chromium.launch(
            headless=True,
            args=[
                "--disable-blink-features=AutomationControlled",
                "--no-sandbox",
                "--disable-setuid-sandbox",
                "--disable-infobars"
            ]
        )
        context = browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36",
            viewport={"width": 1280, "height": 800}
        )
        page = context.new_page()
        page.add_init_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")

        # 1. Navigate to FPL Homepage
        page.goto("https://fantasy.premierleague.com/en/", wait_until="commit", timeout=35000)
        time.sleep(3)

        # 2. Accept Cookie Consent Banner if present
        try:
            page.locator("#onetrust-accept-btn-handler, button:has-text('Accept All Cookies')").first.click(timeout=5000)
            time.sleep(1)
        except Exception:
            pass

        # 3. Click Log In button
        try:
            page.locator("button:has-text('Log in'), a:has-text('Sign In'), a[href*='login']").first.click(timeout=8000)
        except Exception:
            page.goto("https://fantasy.premierleague.com/en/", wait_until="commit")
            time.sleep(2)
            page.locator("button:has-text('Log in'), a:has-text('Sign In'), a[href*='login']").first.click(timeout=8000)

        # 4. Wait for redirect to account.premierleague.com OAuth authorization
        page.wait_for_url(lambda u: "account.premierleague.com" in u, timeout=25000)
        u_input = page.locator("input[type='email'], input[name='login'], #username, #email").first
        u_input.wait_for(state="visible", timeout=15000)
        p_input = page.locator("input[type='password'], #password").first

        u_input.fill(self.email)
        time.sleep(0.3)
        p_input.fill(self.password)
        time.sleep(0.3)

        submit_btn = page.locator("button:has-text('Sign In'), button:has-text('Sign in'), button[type='submit']").first
        submit_btn.click()

        # 5. Wait for redirect back to authenticated FPL
        page.wait_for_url(lambda u: "fantasy.premierleague.com" in u and "account." not in u, timeout=35000)
        time.sleep(3)
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
