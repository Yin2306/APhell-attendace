import os
import time
import yaml
import requests
from playwright.sync_api import sync_playwright
from concurrent.futures import ThreadPoolExecutor

# --- Configuration ---
COMMON_API_KEY = "da2-u4ksf3gspnhyjcokxzugo3mqr4"
GRAPHQL_URL = "https://attendix.apu.edu.my/graphql"

def take_attendance(name, token, otp):
    """Send attendance request directly to GraphQL"""
    payload = {
        "operationName": "updateAttendance",
        "query": "mutation updateAttendance($otp: String!) {\n  updateAttendance(otp: $otp) {\n    id\n    attendance\n    __typename\n  }\n}\n",
        "variables": {"otp": str(otp)},
    }
    headers = {
        "Authorization": f"Bearer {token}",
        "x-api-key": COMMON_API_KEY,
        "Content-Type": "application/json",
        "User-Agent": "Mozilla/5.0 (iPhone; CPU iPhone OS 16_6 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.6 Mobile/15E148 Safari/604.1"
    }
    try:
        res = requests.post(GRAPHQL_URL, json=payload, headers=headers, timeout=10)
        return res.json()
    except Exception:
        return {"error": "request failed"}

def process_single_account(acc, otp):
    """Login and capture token for a single account"""
    print(f"🎬 Starting process for: {acc['name']}")
    with sync_playwright() as p:
        browser = None
        try:
            browser = p.chromium.launch(headless=True, args=[
                "--no-sandbox", "--disable-setuid-sandbox", "--disable-dev-shm-usage", 
                "--disable-gpu", "--blink-settings=imagesEnabled=false"
            ])
            context = browser.new_context(
                user_agent="Mozilla/5.0 (iPhone; CPU iPhone OS 16_6 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.6 Mobile/15E148 Safari/604.1",
                viewport={'width': 390, 'height': 844}
            )
            page = context.new_page()
            
            token_container = []
            def handle_request(request):
                auth = request.headers.get("authorization")
                if auth and "Bearer" in auth:
                    token_container.append(auth.replace("Bearer ", ""))
            page.on("request", handle_request)

            login_url = "https://login.microsoftonline.com/0fed03a3-402d-4633-a8cd-8b308822253e/oauth2/v2.0/authorize?client_id=e96b418c-3f97-4b0f-b124-1cb3b347a06e&response_type=code&redirect_uri=https%3A%2F%2Fauth.apu.edu.my%2Fauth_token&scope=Group.Read.All+GroupMember.Read.All+User.Read+offline_access+openid+profile&state=%7B%22origin%22%3A+%22https%3A%2F%2Fapspace.apu.edu.my%22%2C+%22endpoint%22%3A+%22%2Flogin%22%2C+%22app_id%22%3A+%22apspace%22%7D"
            page.goto(login_url, wait_until="networkidle", timeout=60000)
            
            full_email = f"{acc['username']}@mail.apu.edu.my"
            page.wait_for_selector('input[type="email"], [role="listitem"]', timeout=20000)
            
            if page.get_by_text(full_email, exact=False).is_visible():
                page.get_by_text(full_email, exact=False).click()
            else:
                page.fill('input[type="email"]', full_email)
                page.click('input[id="idSIButton9"]')

            page.wait_for_selector('input[type="password"]', timeout=20000)
            page.fill('input[type="password"]', acc['password'])
            page.click('input[id="idSIButton9"]')
            
            try:
                page.wait_for_selector('#idSIButton9', timeout=5000)
                page.click('#idSIButton9')
            except:
                pass

            # Capture token
            for _ in range(150):
                if token_container:
                    token = token_container[-1]
                    result = take_attendance(acc['name'], token, otp)
                    
                    if browser:
                        browser.close()

                    if result.get("data") and result["data"].get("updateAttendance"):
                        return f"✅ {acc['name']}: Success"
                    else:
                        # Simplified error: do not show detailed reason
                        return f"❌ {acc['name']}: Failed"
                time.sleep(0.1)
            
            if browser:
                browser.close()
            return f"❌ {acc['name']}: Failed"
            
        except Exception:
            if browser:
                browser.close()
            return f"❌ {acc['name']}: Failed"

if __name__ == "__main__":
    start_time = time.time()
    
    accounts_raw = os.getenv("ACCOUNTS_YAML")
    otp = os.getenv("OTP_CODE")
    
    if not accounts_raw or not otp:
        print("Missing ACCOUNTS_YAML or OTP_CODE")
        exit(1)

    accounts = yaml.safe_load(accounts_raw)
    # Set to 4 threads for best stability
    num_workers = 4
    
    print(f"🚀 Starting batch mode | Threads: {num_workers} | Total accounts: {len(accounts)}")

    with ThreadPoolExecutor(max_workers=num_workers) as executor:
        final_reports = list(executor.map(lambda acc: process_single_account(acc, otp), accounts))

    end_time = time.time()
    report_text = f"🏁 Attendance task completed | Time taken: {int(end_time - start_time)}s\n\n" + "\n".join(final_reports)
    
    with open("result.txt", "w", encoding="utf-8") as f:
        f.write(report_text)
    
    print(report_text)
