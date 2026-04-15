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

            # --- 1. 直接进入微软授权页面 (跳过 APSpace 首页) ---
            login_url = "https://login.microsoftonline.com/0fed03a3-402d-4633-a8cd-8b308822253e/oauth2/v2.0/authorize?client_id=e96b418c-3f97-4b0f-b124-1cb3b347a06e&response_type=code&redirect_uri=https%3A%2F%2Fauth.apu.edu.my%2Fauth_token&scope=Group.Read.All+GroupMember.Read.All+User.Read+offline_access+openid+profile&state=%7B%22origin%22%3A+%22https%3A%2F%2Fapspace.apu.edu.my%22%2C+%22endpoint%22%3A+%22%2Flogin%22%2C+%22app_id%22%3A+%22apspace%22%7D"
            
            print(f"📡 {acc['name']} 正在直达微软登录页...")
            page.goto(login_url, wait_until="networkidle", timeout=60000)
            
            # --- 2. 处理账号输入或选择 ---
            full_email = f"{acc['username']}@mail.apu.edu.my"
            
            try:
                # 这里的 selector 改得更通用一点，同时等“输入框”或“账号选择列表”
                page.wait_for_selector('input[type="email"], [role="listitem"]', timeout=20000)
                
                # 如果看到了你的 TP 号已经在那了，直接点
                if page.get_by_text(full_email).is_visible():
                    print(f"✅ {acc['name']} 发现已有账号，点击头像...")
                    page.get_by_text(full_email).click()
                else:
                    print(f"📝 {acc['name']} 手动输入账号...")
                    page.fill('input[type="email"]', full_email)
                    page.click('input[type="submit"]')
            except Exception as e:
                print(f"⚠️ {acc['name']} 账号页处理异常，尝试保底输入...")
                page.fill('input[type="email"]', full_email)
                page.click('input[type="submit"]')

            # --- 3. 填密码 ---
            print(f"🔑 {acc['name']} 正在输入密码...")
            page.wait_for_selector('input[type="password"]', timeout=20000)
            page.fill('input[type="password"]', acc['password'])
            page.click('input[type="submit"]')
            
            # 确认“Stay signed in?”
            try:
                page.wait_for_selector('#idSIButton9', timeout=5000)
                page.click('#idSIButton9')
            except: pass

            # --- 4. 模拟进入 Dashboard 并触发 Token ---
            print(f"🛰️ {acc['name']} logged in, waiting for token...")
            
            # 这里我们不需要 goto 了，因为登录完会自动跳回 APSpace
            # 我们只需要循环等 Token 出现即可
            for _ in range(60): # 增加到 30 秒总等待时间
                if token_container:
                    token = token_container[-1]
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

   # 第一次测试，务必用 1。成功了之后，下次再改回 3。
    with ThreadPoolExecutor(max_workers=1) as executor:
        executor.map(lambda acc: process_single_account(acc, otp), accounts)
