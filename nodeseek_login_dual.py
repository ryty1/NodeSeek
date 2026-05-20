# nodeseek_login_dual.py - 支持双网站的登录模块
import os
import time
import json
from typing import Optional
from curl_cffi import requests
from dotenv import load_dotenv

# 加载配置
load_dotenv()

# 网站配置
SITES_CONFIG = {
    "ns": {
        "name": "NodeSeek",
        "domain": "www.nodeseek.com",
        "login_url": "https://www.nodeseek.com/signIn.html",
        "api_signin": "https://www.nodeseek.com/api/account/signIn",
        "attendance_url": "https://www.nodeseek.com/api/attendance",
        "sitekey": "0x4AAAAAAAaNy7leGjewpVyR"
    },
    "df": {
        "name": "DeepFlood", 
        "domain": "www.deepflood.com",
        "login_url": "https://www.deepflood.com/signIn.html",
        "api_signin": "https://www.deepflood.com/api/account/signIn",
        "attendance_url": "https://www.deepflood.com/api/attendance",
        "sitekey": "0x4AAAAAAAaNy7leGjewpVyR"  # 假设使用相同的 sitekey，实际可能不同
    }
}

IMPORTANT_COOKIES = ["session", "smac", "cf_clearance", "fog"]

FLARESOLVERR_URL = os.getenv("FLARESOLVERR_URL")
API_BASE_URL = os.getenv("API_BASE_URL")
CLIENT_KEY = os.getenv("CLIENT_KEY")


def mask(v: Optional[str], keep: int = 4) -> str:
    if not v:
        return "None"
    if len(v) <= keep:
        return "*" * len(v)
    return v[:keep] + "..." + v[-keep:]


def solve_turnstile_token(api_base_url: str, client_key: str, url: str, sitekey: str,
                          timeout=30, max_retries=20, retry_interval=6) -> Optional[str]:
    headers = {"Content-Type": "application/json"}
    create_payload = {
        "clientKey": client_key,
        "type": "Turnstile",
        "url": url,
        "siteKey": sitekey
    }
    try:
        print("🧩 正在创建 Turnstile 任务...")
        r = requests.post(f"{api_base_url}/createTask", data=json.dumps(create_payload), headers=headers, timeout=timeout)
        data = r.json()
        task_id = data.get("taskId")
        if not task_id:
            print("❌ createTask 响应无 taskId:", data)
            return None
    except Exception as e:
        print(f"❌ createTask 失败: {e}")
        return None

    result_payload = {"clientKey": client_key, "taskId": task_id}
    for i in range(1, max_retries + 1):
        try:
            print(f"⏳ 获取验证结果 {i}/{max_retries} ...")
            rr = requests.post(f"{api_base_url}/getTaskResult", data=json.dumps(result_payload), headers=headers, timeout=timeout)
            result = rr.json()
            if result.get("status") in ("completed", "ready"):
                token = (
                    result.get("solution", {}).get("token")
                    or result.get("result", {}).get("response", {}).get("token")
                )
                if token:
                    print("✅ Turnstile token 获取成功")
                    return token
                else:
                    print("❌ getTaskResult 没有 token:", result)
                    return None
        except Exception as e:
            print(f"⚠️ 轮询异常: {e}")
        time.sleep(retry_interval)
    print("❌ Turnstile token 获取超时")
    return None


def get_session():
    # 优先 chrome100，不支持就回退 chrome99
    try:
        s = requests.Session(impersonate="chrome100")
    except requests.exceptions.ImpersonateError:
        print("[WARN] chrome100 不支持，回退到 chrome99")
        s = requests.Session(impersonate="chrome99")
    return s


def cookie_string_from_session(s: requests.Session, important_only: bool = True) -> str:
    cookies = s.cookies.get_dict()
    if important_only:
        cookies = {k: v for k, v in cookies.items() if k in IMPORTANT_COOKIES}
    return "; ".join([f"{k}={v}" for k, v in cookies.items()])


def get_cookies_from_flaresolverr(url: str, flaresolverr_url: str = FLARESOLVERR_URL) -> dict:
    payload = {
        "cmd": "request.get",
        "url": url,
        "maxTimeout": 120000
    }
    try:
        print(f"🌐 FlareSolverr 渲染页面: {url}")
        r = requests.post(flaresolverr_url, json=payload, timeout=60)
        j = r.json()

        cookies = {c["name"]: c["value"] for c in j.get("solution", {}).get("cookies", [])}
        if not cookies:
            print("❌ FlareSolverr 没有返回 cookies")
        else:
            print("✅ FlareSolverr 获取到 cookies:", cookies)
        return cookies
    except Exception as e:
        print(f"❌ FlareSolverr 获取 cookies 失败: {e}")
        return {}


def login_and_get_cookie(user: str, password: str, site_type: str = "ns") -> Optional[str]:
    """
    登录并获取 Cookie
    
    Args:
        user: 用户名或邮箱
        password: 密码
        site_type: 网站类型 ("ns" 或 "df")
    
    Returns:
        Cookie 字符串或 None
    """
    if site_type not in SITES_CONFIG:
        print(f"❌ 不支持的网站类型: {site_type}")
        return None
    
    config = SITES_CONFIG[site_type]
    print(f"🔐 开始登录 {config['name']} ({config['domain']})...")
    
    # 1. 先尝试 FlareSolverr
    flare_cookies = get_cookies_from_flaresolverr(config["login_url"])

    # 2. 获取 Turnstile token
    token = solve_turnstile_token(API_BASE_URL, CLIENT_KEY, config["login_url"], config["sitekey"])
    if not token:
        return None

    # 3. 初始化 session 并注入 cookies
    s = get_session()
    
    # 先访问登录页面
    try:
        s.get(config["login_url"], timeout=15)
    except Exception as e:
        print(f"[WARN] 初始访问 {config['name']} 登录页失败: {e}")
    
    # 注入 FlareSolverr 获取的 cookies
    for k, v in flare_cookies.items():
        s.cookies.set(k, v)

    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/134.0.0.0 Safari/537.36",
        "Origin": f"https://{config['domain']}",
        "Referer": config["login_url"],
        "Content-Type": "application/json",
    }
    
    payload = {
        "password": password,
        "token": token,
        "source": "turnstile",
    }
    
    if "@" in user:
        payload["email"] = user
    else:
        payload["username"] = user

    # 4. 登录请求
    try:
        print(f"📤 发送登录请求到 {config['name']}...")
        resp = s.post(config["api_signin"], json=payload, headers=headers, timeout=30)
        j = resp.json()
    except Exception as e:
        print(f"❌ {config['name']} 登录异常:", e)
        return None

    if j.get("success"):
        print(f"✅ {config['name']} 登录成功，获取完整 cookies...")
        try:
            # 访问主页和用户资料页面以获取完整 cookies
            s.get(f"https://{config['domain']}/", headers=headers, timeout=30)
            s.get(f"https://{config['domain']}/user/profile", headers=headers, timeout=30)
        except Exception as e:
            print(f"[WARN] 拉取 {config['name']} 用户信息时失败: {e}")
        
        cookies = cookie_string_from_session(s, important_only=False)
        print(f"🍪 {config['name']} Cookie 获取成功")
        return cookies
    else:
        print(f"❌ {config['name']} 登录失败：", j)
        return None


def cookie_valid(ns_cookie: str, site_type: str = "ns") -> bool:
    """
    验证 Cookie 是否有效
    
    Args:
        ns_cookie: Cookie 字符串
        site_type: 网站类型 ("ns" 或 "df")
    
    Returns:
        是否有效
    """
    if site_type not in SITES_CONFIG:
        return False
    
    config = SITES_CONFIG[site_type]
    
    try:
        r = requests.get(config["attendance_url"], headers={"Cookie": ns_cookie}, timeout=20)
        return r.status_code not in (401, 403)
    except Exception:
        return False


# 兼容性函数，保持与原版的接口一致
def login_and_get_cookie_legacy(user: str, password: str) -> Optional[str]:
    """兼容原版接口，默认使用 NodeSeek"""
    return login_and_get_cookie(user, password, "ns")