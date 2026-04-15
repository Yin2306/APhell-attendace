import os
import time
import yaml
import requests
from playwright.sync_api import sync_playwright
from concurrent.futures import ThreadPoolExecutor

# --- 配置区 ---
# APU Attendix 通用 API KEY
COMMON_API_KEY = "da2-u4ksf3gspnhyjcokxzugo3mqr4"
GRAPHQL_URL = "https://attendix.apu.edu.my/graphql"

def take_attendance(name, token, otp):
    """直接向 GraphQL 发送签到请求"""
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
            # --- 极速改动 1: 禁用图片、GPU 和插件，减轻 CPU 压力 ---
            browser = p.chromium.launch(headless=True, args=[
                "--no-sandbox",
                "--disable-gpu",
                "--disable-dev-shm-usage",
                "--blink-settings=imagesEnabled=false"  # 不加载图片，速度提升 20%
            ])
            context = browser.new_context(
                user_agent="Mozilla/5.0 (iPhone; CPU iPhone OS 16_6 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.6 Mobile/15E148 Safari/604.1"
            )
            page = context.new_page()
            
            token_container = []
            def handle_request(request):
                # 只要抓到 Authorization 立即存入
                auth = request.headers.get("authorization")
                if auth and "Bearer" in auth:
                    token_container.append(auth.replace("Bearer ", ""))

            page.on("request", handle_request)

            # --- 2. 直达微软 (保持原有稳定逻辑) ---
            login_url = "https://login.microsoftonline.com/0fed03a3-402d-4633-a8cd-8b308822253e/oauth2/v2.0/authorize?client_id=e96b418c-3f97-4b0f-b124-1cb3b347a06e&response_type=code&redirect_uri=https%3A%2F%2Fauth.apu.edu.my%2Fauth_token&scope=Group.Read.All+GroupMember.Read.All+User.Read+offline_access+openid+profile&state=%7B%22origin%22%3A+%22https%3A%2F%2Fapspace.apu.edu.my%22%2C+%22endpoint%22%3A+%22%2Flogin%22%2C+%22app_id%22%3A+%22apspace%22%7D"
            page.goto(login_url, wait_until="domcontentloaded", timeout=45000)

            # --- 3. 极速填表 ---
            full_email = f"{acc['username']}@mail.apu.edu.my"
            page.wait_for_selector('input[type="email"], [role="listitem"]', timeout=15000)
            
            if page.get_by_text(full_email).is_visible():
                page.get_by_text(full_email).click()
            else:
                page.fill('input[type="email"]', full_email)
                page.click('input[type="submit"]')

            page.wait_for_selector('input[type="password"]', timeout=15000)
            page.fill('input[type="password"]', acc['password'])
            # 这里点击完立刻开启高频监听，不等页面跳转完
            page.click('input[type="submit"]')
            
            # --- 极速改动 2: 高频轮询 (0.1s 检查一次) ---
            for _ in range(100): # 最多等 10 秒
                if token_container:
                    token = token_container[-1]
                    result = take_attendance(acc['name'], token, otp)
                    print(f"🔥 {acc['name']} 反馈: {result}")
                    # 抓到就闪人，不等其他请求
                    context.close()
                    browser.close()
                    return True
                time.sleep(0.1) 
            
            browser.close()
            return False
        except Exception as e:
            print(f"❌ {acc['name']} Error: {str(e)}")
            return False
            
if __name__ == "__main__":
    import time
    start_time = time.time()
    
    accounts_raw = os.getenv("ACCOUNTS_YAML")
    otp = os.getenv("OTP_CODE")
    
    if not accounts_raw or not otp:
        print("Missing ACCOUNTS_YAML or OTP_CODE")
        exit(1)

    accounts = yaml.safe_load(accounts_raw)
    
  # 设置为 6。
    # 11 个人分两组：第一批 6 个，第二批 5 个。
    # 这比 3 个一组（跑 4 轮）快了一倍！
    num_workers = 6 
    
    with ThreadPoolExecutor(max_workers=num_workers) as executor:
        list(executor.map(lambda acc: process_single_account(acc, otp), accounts))
