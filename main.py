import os
import time
import yaml
import requests
from playwright.sync_api import sync_playwright
from concurrent.futures import ThreadPoolExecutor

# --- 配置区 ---
# 你提供的一样的 API KEY
COMMON_API_KEY = "da2-u4ksf3gspnhyjcokxzugo3mqr4"
GRAPHQL_URL = "https://attendix.apu.edu.my/graphql"

def take_attendance(name, token, otp):
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
    except Exception as e:
        return {"error": str(e)}

def process_single_account(acc, otp):
    print(f"🎬 Starting process for: {acc['name']}")
    with sync_playwright() as p:
        try:
            # 模拟 iPhone 环境，绕过一些基础的机器人检测
            browser = p.chromium.launch(headless=True, args=["--no-sandbox"])
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

            # 1. 访问 APSpace
            page.goto("https://apspace.apu.edu.my/login", wait_until="networkidle")
            
            # 2. 点击 Log In 按钮
            try:
                page.wait_for_selector('text="Log In"', timeout=5000)
                page.click('text="Log In"')
            except: pass

            # 3. 处理微软登录逻辑
            full_email = f"{acc['username']}@mail.apu.edu.my"
            
            # 检查是否有“Pick an account”
            try:
                account_selector = f"text='{full_email}'"
                page.wait_for_selector('body', timeout=10000)
                if page.is_visible(account_selector):
                    page.click(account_selector)
                else:
                    page.fill('input[type="email"]', full_email)
                    page.click('input[type="submit"]')
            except:
                # 兜底：直接尝试填表
                page.fill('input[type="email"]', full_email)
                page.click('input[type="submit"]')

            # 4. 填密码
            page.wait_for_selector('input[type="password"]', timeout=15000)
            page.fill('input[type="password"]', acc['password'])
            page.click('input[type="submit"]')
            
            # 确认“Stay signed in?”
            try:
                page.wait_for_selector('#idSIButton9', timeout=5000)
                page.click('#idSIButton9')
            except: pass

            # 5. 模拟进入 Dashboard 并触发 Token
            print(f"🛰️ {acc['name']} logged in, navigating to Attendix...")
            page.wait_for_url("**/tabs/dashboard", timeout=20000)
            page.goto("https://apspace.apu.edu.my/attendix/update")

            # 6. 截获 Token 并签到
            for _ in range(30):
                if token_container:
                    token = token_container[-1] # 取最新的 token
                    result = take_attendance(acc['name'], token, otp)
                    print(f"🔥 {acc['name']} SUCCESS: {result}")
                    browser.close()
                    return True
                time.sleep(0.5)
            
            print(f"⚠️ {acc['name']} failed to capture token.")
            browser.close()
            return False
        except Exception as e:
            print(f"❌ {acc['name']} Error: {str(e)}")
            return False

if __name__ == "__main__":
    accounts_raw = os.getenv("ACCOUNTS_YAML")
    otp = os.getenv("OTP_CODE")
    
    if not accounts_raw or not otp:
        print("Missing ACCOUNTS_YAML or OTP_CODE")
        exit(1)

    accounts = yaml.safe_load(accounts_raw)
    print(f"🚀 Launching attendance for {len(accounts)} accounts with OTP: {otp}")

    with ThreadPoolExecutor(max_workers=len(accounts)) as executor:
        executor.map(lambda acc: process_single_account(acc, otp), accounts)
