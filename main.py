import os
import time
import yaml
import requests
from playwright.sync_api import sync_playwright
from concurrent.futures import ThreadPoolExecutor

# 1. 签到函数
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
        res = requests.post(url, json=payload, headers=headers, timeout=10)
        return res.json()
    except Exception as e:
        return {"error": str(e)}

# 2. 单个账号的完整流程（登录 + 签到）
def process_single_account(acc, otp):
    username = acc['username']
    password = acc['password']
    name = acc['name']
    api_key = acc['api_key']
    
    print(f"🚀 Starting for {name}...")
    
    with sync_playwright() as p:
        try:
            # 启动浏览器
            browser = p.chromium.launch(headless=True, args=["--no-sandbox"])
            context = browser.new_context()
            page = context.new_page()
            token = None

            def handle_request(request):
                nonlocal token
                auth = request.headers.get("authorization")
                if auth and "Bearer" in auth:
                    token = auth.replace("Bearer ", "")

            page.on("request", handle_request)
            page.goto("https://apspace.apu.edu.my/login", timeout=60000)
            
            # 填写登录信息
            page.fill('input[type="email"]', f"{username}@mail.apu.edu.my")
            page.click('input[type="submit"]')
            page.wait_for_selector('input[type="password"]', timeout=20000)
            page.fill('input[type="password"]', password)
            page.click('input[type="submit"]')
            
            try:
                page.wait_for_selector('#idSIButton9', timeout=5000)
                page.click('#idSIButton9')
            except: pass

            # 等待 Token 抓取（只要抓到 Token 就立刻停止浏览器，节省时间）
            start_time = time.time()
            while not token and time.time() - start_time < 30:
                time.sleep(0.5)
            
            browser.close()

            if token:
                result = take_attendance(name, token, api_key, otp)
                print(f"✅ {name}: {result}")
                return True
            else:
                print(f"❌ {name}: Failed to get token")
                return False
        except Exception as e:
            print(f"⚠️ {name} Error: {str(e)}")
            return False

if __name__ == "__main__":
    accounts_raw = os.getenv("ACCOUNTS_YAML")
    otp = os.getenv("OTP_CODE")
    
    if not accounts_raw or not otp:
        exit(1)

    accounts = yaml.safe_load(accounts_raw)
    
    # --- 核心提速：使用多线程同时跑 11 个账号 ---
    print(f"⚡ Parallel processing started for {len(accounts)} accounts...")
    with ThreadPoolExecutor(max_workers=len(accounts)) as executor:
        executor.map(lambda acc: process_single_account(acc, otp), accounts)
    
    print("All done!")
