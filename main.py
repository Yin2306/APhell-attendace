import os
import time
import yaml
import requests
from playwright.sync_api import sync_playwright
from concurrent.futures import ThreadPoolExecutor

def take_attendance(name, token, api_key, otp):
    url = "https://attendix.apu.edu.my/graphql"
    payload = {
        "operationName": "updateAttendance",
        "query": "mutation updateAttendance($otp: String!) {\n  updateAttendance(otp: $otp) {\n    id\n    attendance\n    __typename\n  }\n}\n",
        "variables": {"otp": otp},
    }
    headers = {
        "Authorization": f"Bearer {token}",
        "x-api-key": api_key,
        "Content-Type": "application/json"
    }
    try:
        res = requests.post(url, json=payload, headers=headers, timeout=5)
        return res.json()
    except:
        return None

def process_single_account(acc, otp):
    print(f"🚀 {acc['name']} is logging in...")
    with sync_playwright() as p:
        try:
            browser = p.chromium.launch(headless=True, args=["--no-sandbox"])
            context = browser.new_context()
            page = context.new_page()
            
            token_container = []
            def handle_request(request):
                auth = request.headers.get("authorization")
                if auth and "Bearer" in auth:
                    token_container.append(auth.replace("Bearer ", ""))

            page.on("request", handle_request)
            page.goto("https://apspace.apu.edu.my/login")
            
            # 自动填写
            page.fill('input[type="email"]', f"{acc['username']}@mail.apu.edu.my")
            page.click('input[type="submit"]')
            page.wait_for_selector('input[type="password"]', timeout=10000)
            page.fill('input[type="password"]', acc['password'])
            page.click('input[type="submit"]')
            
            # 抢跑逻辑：一旦抓到 Token，立刻发请求并关闭浏览器
            for _ in range(30):
                if token_container:
                    token = token_container[0]
                    result = take_attendance(acc['name'], token, acc['api_key'], otp)
                    print(f"✅ {acc['name']} Done: {result}")
                    browser.close()
                    return True
                time.sleep(0.5)
            
            browser.close()
            return False
        except Exception as e:
            print(f"❌ {acc['name']} Error: {str(e)}")
            return False

if __name__ == "__main__":
    accounts_raw = os.getenv("ACCOUNTS_YAML")
    otp = os.getenv("OTP_CODE")
    if not accounts_raw or not otp: exit(1)
    accounts = yaml.safe_load(accounts_raw)
    
    # 11人同时起步
    with ThreadPoolExecutor(max_workers=len(accounts)) as executor:
        executor.map(lambda acc: process_single_account(acc, otp), accounts)
