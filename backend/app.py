import os
import re
import hashlib
import secrets
import time
from datetime import datetime
from functools import wraps
from flask import Flask, request, jsonify, session, send_file
from logger import log

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", secrets.token_hex(32))

# ====== 配置 ======
ROOT_DIR = os.environ.get("ROOT_DIR", "/home/harry/data/config")
USERS_FILE = os.path.join(ROOT_DIR, "users.txt")
STOCK_FILE = os.path.join(ROOT_DIR, "ah_stock_map.csv")
PREMIUM_FILE = os.path.join(ROOT_DIR, "premium_monitor.csv")
MAX_ATTEMPTS = 5
LOCKOUT_MINUTES = 30
BASE_DELAY_SECONDS = 1
SESSION_GC_INTERVAL = 300  # 5 分钟清理一次过期 session

# ====== 内存状态 ======
users = {}           # username -> {salt, hash}
unlock_code = None   # {salt, hash}
active_sessions = {}  # username -> {session_id, login_time}
failed_attempts = {}  # username -> {count, first_time, lockout_until}
ip_attempts = {}      # ip -> {count, first_time}
last_gc = time.time()

# ====== 加载用户文件 ======
def load_users():
    global users, unlock_code
    users = {}
    unlock_code = None
    if not os.path.exists(USERS_FILE):
        return
    with open(USERS_FILE, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            parts = line.split(":")
            if len(parts) < 3:
                continue
            if parts[0] == "!unlock":
                unlock_code = {"salt": parts[1], "hash": ":".join(parts[2:])}
            else:
                users[parts[0]] = {"salt": parts[1], "hash": ":".join(parts[2:])}

load_users()
log.info(f"Flask 启动完成，已加载 {len(users)} 个用户")

# ====== 工具函数 ======
def hash_password(username, password, salt):
    return hashlib.sha256(f"{username}:{password}:{salt}".encode()).hexdigest()

def get_client_ip():
    xff = request.headers.get("X-Forwarded-For") or request.headers.get("X-Real-IP")
    if xff:
        return xff.split(",")[0].strip()
    return request.remote_addr or "127.0.0.1"

def gc_sessions():
    global last_gc
    now = time.time()
    if now - last_gc < SESSION_GC_INTERVAL:
        return
    last_gc = now
    expired = [u for u, s in active_sessions.items() if now - s["login_time"] > 86400]
    for u in expired:
        del active_sessions[u]

# ====== 认证装饰器 ======
def require_auth(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        gc_sessions()
        username = session.get("username")
        sid = session.get("session_id")
        if not username or not sid:
            return jsonify({"code": 401, "msg": "请先登录"}), 401
        current = active_sessions.get(username)
        if not current or current["session_id"] != sid:
            session.clear()
            return jsonify({"code": 401, "msg": "该账号已在其他设备登录，当前会话已被踢出"}), 401
        return f(*args, **kwargs)
    return wrapper

# ====== API ======

@app.route("/login", methods=["POST"])
def login():
    data = request.get_json(silent=True) or {}
    username = (data.get("username") or "").strip()
    password = data.get("password") or ""
    ip = get_client_ip()
    now = time.time()

    # IP 频率限制
    ip_info = ip_attempts.get(ip, {"count": 0, "first_time": now})
    if now - ip_info["first_time"] > 60:
        ip_info = {"count": 0, "first_time": now}
    ip_info["count"] += 1
    ip_attempts[ip] = ip_info
    if ip_info["count"] > 20:
        log.warning(f"IP {ip} 登录频率超限")
        return jsonify({"code": 429, "msg": "请求过于频繁，请稍后再试"}), 429

    # 紧急解锁
    if username == "_unlock":
        if not unlock_code:
            return jsonify({"code": 401, "msg": "用户名或密码错误"}), 401
        h = hash_password("_unlock", password, unlock_code["salt"])
        if h != unlock_code["hash"]:
            return jsonify({"code": 401, "msg": "用户名或密码错误"}), 401
        # 清除所有锁定
        failed_attempts.clear()
        ip_attempts.pop(ip, None)
        log.warning(f"紧急解锁已使用，来源 IP: {ip}")
        return _do_login("_unlock")

    # 检查用户是否存在
    user_info = users.get(username)
    if not user_info:
        # 统一提示，防止用户名枚举
        return jsonify({"code": 401, "msg": "用户名或密码错误"}), 401

    # 检查锁定
    fa = failed_attempts.get(username)
    if fa and fa.get("lockout_until") and now < fa["lockout_until"]:
        remaining = int(fa["lockout_until"] - now)
        mins, secs = divmod(remaining, 60)
        log.warning(f"用户 {username} 尝试登录但账户已被锁定，来源 IP: {ip}")
        return jsonify({"code": 423, "msg": f"账户已锁定，请 {mins} 分 {secs} 秒后重试"}), 423

    # 校验密码
    h = hash_password(username, password, user_info["salt"])
    if h != user_info["hash"]:
        # 记录失败
        if not fa or now - fa.get("first_time", 0) > LOCKOUT_MINUTES * 60:
            fa = {"count": 0, "first_time": now}
        fa["count"] += 1
        if fa["count"] >= MAX_ATTEMPTS:
            fa["lockout_until"] = now + LOCKOUT_MINUTES * 60
            log.warning(f"用户 {username} 连续 {fa['count']} 次登录失败，已锁定 {LOCKOUT_MINUTES} 分钟，来源 IP: {ip}")
        else:
            log.info(f"用户 {username} 登录失败（第 {fa['count']}/{MAX_ATTEMPTS} 次），来源 IP: {ip}")
        failed_attempts[username] = fa
        remaining = max(0, MAX_ATTEMPTS - fa["count"])
        return jsonify({"code": 401, "msg": f"用户名或密码错误，还剩 {remaining} 次尝试机会"}), 401

    # 登录成功，清除失败记录
    failed_attempts.pop(username, None)
    ip_attempts.pop(ip, None)
    log.info(f"用户 {username} 登录成功，来源 IP: {ip}")
    return _do_login(username)


def _do_login(username):
    sid = secrets.token_hex(32)
    session["username"] = username
    session["session_id"] = sid
    session.permanent = True
    # 覆盖旧 session（实现单 session 互踢）
    active_sessions[username] = {"session_id": sid, "login_time": time.time()}
    return jsonify({"code": 0, "msg": "ok", "data": {"username": username}})


@app.route("/logout", methods=["POST"])
def logout():
    username = session.get("username")
    if username:
        if username in active_sessions and active_sessions[username]["session_id"] == session.get("session_id"):
            del active_sessions[username]
        log.info(f"用户 {username} 已登出")
    session.clear()
    return jsonify({"code": 0, "msg": "ok"})


@app.route("/check_session", methods=["GET"])
def check_session():
    gc_sessions()
    username = session.get("username")
    sid = session.get("session_id")
    if not username or not sid:
        return jsonify({"code": 401, "msg": "未登录"}), 401
    current = active_sessions.get(username)
    if not current or current["session_id"] != sid:
        session.clear()
        log.info(f"用户 {username} 会话被踢出（新设备登录覆盖）")
        return jsonify({"code": 401, "msg": "该账号已在其他设备登录，当前会话已被踢出"}), 401
    return jsonify({"code": 0, "msg": "ok", "data": {"username": username}})


@app.route("/update_ah_rate", methods=["POST"])
@require_auth
def update_ah_rate():
    return _save_file(STOCK_FILE)


@app.route("/premium_update", methods=["POST"])
@require_auth
def premium_update():
    return _save_file(PREMIUM_FILE)


@app.route("/search_csv", methods=["GET"])
@require_auth
def search_csv():
    date_str = request.args.get("date", "").strip()
    code = request.args.get("code", "").strip()
    if not re.match(r"^\d{8}$", date_str) or not re.match(r"^\d{6}$", code):
        return jsonify({"code": 400, "msg": "日期格式yyyyMMdd，代码格式XXXXXX"}), 400

    yyyy = date_str[:4]
    search_dir = os.path.join(ROOT_DIR, "data", f"{yyyy}_ah比价", f"{date_str}_ah比价")
    if not os.path.isdir(search_dir):
        return jsonify({"code": 0, "data": {"dir": search_dir, "files": []}})

    files = sorted([f for f in os.listdir(search_dir) if f.startswith(code) and f.endswith(".csv")])
    username = session.get("username", "unknown")
    log.info(f"用户 {username} 搜索文件，目录: {search_dir}，代码: {code}，结果: {len(files)} 个")
    return jsonify({"code": 0, "data": {"dir": search_dir, "files": files}})


@app.route("/download_file", methods=["GET"])
@require_auth
def download_file():
    dir_path = request.args.get("dir", "")
    filename = request.args.get("file", "")
    if ".." in dir_path or ".." in filename or "/" in filename or "\\" in filename:
        return jsonify({"code": 400, "msg": "非法路径"}), 400
    filepath = os.path.join(dir_path, filename)
    if not os.path.isfile(filepath):
        return jsonify({"code": 404, "msg": "文件不存在"}), 404
    username = session.get("username", "unknown")
    log.info(f"用户 {username} 下载文件: {filepath}")
    return send_file(filepath, as_attachment=True, download_name=filename)


def _save_file(target_path):
    body = request.get_data()
    username = session.get("username", "unknown")
    if not body:
        log.warning(f"用户 {username} 上传文件到 {target_path} 失败：请求体为空")
        return jsonify({"code": 400, "msg": "请求体为空"}), 400
    os.makedirs(os.path.dirname(target_path), exist_ok=True)
    with open(target_path, "wb") as f:
        f.write(body)
    stat = os.stat(target_path)
    log.info(f"用户 {username} 上传文件到 {target_path}，大小 {stat.st_size} 字节")
    return jsonify({
        "code": 0,
        "msg": "ok",
        "data": {
            "file": target_path,
            "size": stat.st_size,
            "modified": datetime.fromtimestamp(stat.st_mtime).strftime("%Y-%m-%d %H:%M:%S")
        }
    })


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8000, debug=False)
