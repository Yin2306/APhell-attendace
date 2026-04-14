import os
import time
import yaml
import requests
from playwright.sync_api import sync_playwright

def take_attendance(name, token, api_key, otp):
    url = "https://attendix.apu.edu.my/graphql"
    payload = {
        "operationName": "updateAttendance",
        "query": "mutation updateAttendance($otp: String!) {\n  updateAttendance(otp: $otp) {\n    id\n    attendance\n    classcode\n    date\n    startTime\n    endTime\n    classType\n    __typename\n  }\n}\n",
        "variables": {"otp": otp},
    }
    headers = {
        "Authorization": f"Bearer {token}",
        "x-api-key": api_key,
        "Content-Type": "application/json"
    }
    try:
        response = requests.post(url, json=payload, headers=headers)
        return response.json()
    except Exception as e:
        return str(e)

def login_and_get_token(username, password):
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context()
        page = context.new_page()
        token = None

        def handle_request(request):
            nonlocal token
            auth = request.headers.get("authorization")
            if auth and "Bearer" in auth:
                token = auth.replace("Bearer ", "")

        page.on("request", handle_request)
        page.goto("https://apspace.apu.edu.my/login")
        
        page.fill('input[type="email"]', f"{username}@mail.apu.edu.my")
        page.click('input[type="submit"]')
        page.wait_for_selector('input[type="password"]')
        page.fill('input[type="password"]', password)
        page.click('input[type="submit"]')
        
        try:
            page.wait_for_selector('#idSIButton9', timeout=5000)
            page.click('#idSIButton9')
        except: pass

        page.wait_for_url("**/dashboard**", timeout=60000)
        time.sleep(5) 
        browser.close()
        return token

if __name__ == "__main__":
    accounts_raw = os.getenv("ACCOUNTS_YAML")
    otp = os.getenv("OTP_CODE")
    
    if not accounts_raw or not otp:
        print("Missing ACCOUNTS_YAML or OTP_CODE")
        exit(1)

    accounts = yaml.safe_load(accounts_raw)
    for acc in accounts:
        print(f"Logging in for {acc['name']}...")
        token = login_and_get_token(acc['username'], acc['password'])
        if token:
            print(f"✅ Token captured. Taking attendance...")
            res = take_attendance(acc['name'], token, acc['api_key'], otp)
            print(f"Result: {res}")
        else:
            print(f"❌ Failed to get token for {acc['name']}")
