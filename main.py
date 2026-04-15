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
    """单个账号的登录及 Token 抓取流程"""
    print(f"🎬 Starting process for: {acc['name']}")
    with sync_playwright() as p:
        try:
            # 启动无头浏览器
            browser = p.chromium.launch(headless=True, args=["--no-sandbox"])
            context = browser.new_context(
                user_agent="Mozilla/5.0 (iPhone; CPU iPhone OS 16_6 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.6 Mobile/15E148 Safari/604.1",
                viewport={'width': 390, 'height': 844}
            )
            page = context.new_page()
            
            # 用于存储拦截到的 Bearer Token
            token_container = []
            def handle_request(request):
                auth = request.headers.get("authorization")
                if auth and "Bearer" in auth:
                    token_container.append(auth.replace("Bearer ", ""))

            page.on("request", handle_request)

            # 1. 直达微软登录页 (跳过 APSpace 首页提升稳定性)
            login_url = "https://login.microsoftonline.com/0fed03a3-402d-4633-a8cd-8b308822253e/oauth2/v2.0/authorize?client_id=e96b418c-3f97-4b0f-b124-1cb3b347a06e&response_type=code&redirect_uri=https%3A%2F%2Fauth.apu.edu.my%2Fauth_token&scope=Group.Read.All+GroupMember.Read.All+User.Read+offline_access+openid+profile&state=%7B%22origin%22%3A+%22https%3A%2F%2Fapspace.apu.edu.my%22%2C+%22endpoint%22%3A+%22%2Flogin%22%2C+%22app_id%22%3A+%22apspace%22%7D"
            
            print(f"📡 {acc['name']} 正在直达微软登录页...")
            page.goto(login_url, wait_until="networkidle", timeout=60000)
            
            # 2. 识别账号 (处理直接输入或点击头像)
            full_email = f"{acc['username']}@mail.apu.edu.my"
            try:
                # 等待页面加载出账号列表或输入框
                page.wait_for_selector('input[type="email"], [role="listitem"], text="Pick an account"', timeout=20000)
                
                if page.get_by_text(full_email).is_visible():
                    print(f"✅ {acc['name']} 发现已有账号，点击头像登录...")
                    page.get_by_text(full_email).click()
                else:
                    print(f"📝 {acc['name']} 手动输入 TP 号...")
                    page.fill('input[type="email"]', full_email)
                    page.click('input[type="submit"]')
            except:
                print(f"⚠️ {acc['name']} 尝试保底填表...")
                page.fill('input[type="email"]', full_email)
                page.click('input[type="submit"]')

            # 3. 输入密码
            print(f"🔑 {acc['name']} 正在输入密码...")
            page.wait_for_selector('input[type="password"]', timeout=20000)
            page.fill('input[type="password"]', acc['password'])
            page.click('input[type="submit"]')
            
            # 处理“保持登录”弹窗
            try:
                page.wait_for_selector('#idSIButton9', timeout=5000)
                page.click('#idSIButton9')
            except: pass

            # 4. 守株待兔抓取 Token
            print(f"🛰️ {acc['name']} 已登录，正在监听 Token 响应...")
            
            # 循环检查是否拦截到 Token
            for _ in range(150): # 0.1s * 150 = 15秒总等待
                if token_container:
                    token = token_container[-1]
                    # 拿到 Token 立刻执行，不回传页面
                    result = take_attendance(acc['name'], token, otp)
                    print(f"🔥 {acc['name']} SUCCESS: {result}")
                    
                    # 强制立刻关闭，不等待任何后续加载
                    context.close()
                    browser.close()
                    return True
                time.sleep(0.1) # 极速轮询
            
            print(f"⚠️ {acc['name']} 抓取 Token 超时")
            browser.close()
            return False
        except Exception as e:
            print(f"❌ {acc['name']} 运行出错: {str(e)}")
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
    
    # --- 极限加速配置 ---
    # 5 个并发是 GitHub Actions 的性能甜点位
    # 11 个人分三批跑，比 3 个并发快很多，又不会像 11 个并发那样直接卡死
    num_workers = 7
    
    print(f"🚀 极速模式启动 | 线程数: {num_workers} | 目标人数: {len(accounts)} | OTP: {otp}")

    with ThreadPoolExecutor(max_workers=num_workers) as executor:
        # 使用 list() 强制执行 map，确保所有线程立即启动
        list(executor.map(lambda acc: process_single_account(acc, otp), accounts))

    end_time = time.time()
    print(f"🏁 全部签到任务完成！总耗时: {int(end_time - start_time)} 秒")
