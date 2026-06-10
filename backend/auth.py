"""认证模块：登录、登出、会话检查、锁定、限流"""

import hashlib
import os
import secrets
import time
from functools import wraps

from flask import Blueprint, request, jsonify, session

from config import USERS_FILE, SESSION_DIR, MAX_ATTEMPTS, LOCKOUT_MINUTES, SESSION_GC_INTERVAL
from logger import log
import state

auth_bp = Blueprint("auth", __name__)
last_gc = time.time()


# ====== 用户加载 ======
def load_users():
    state.users.clear()
    state.unlock_code = None
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
                state.unlock_code = {"salt": parts[1], "hash": ":".join(parts[2:])}
            else:
                state.users[parts[0]] = {"salt": parts[1], "hash": ":".join(parts[2:])}


load_users()
log.info(f"已加载 {len(state.users)} 个用户: {', '.join(state.users.keys()) if state.users else '(无)'}")


# ====== 工具 ======
def hash_password(username, password, salt):
    return hashlib.sha256(f"{username}:{password}:{salt}".encode()).hexdigest()


def get_client_ip():
    xff = request.headers.get("X-Forwarded-For") or request.headers.get("X-Real-IP")
    if xff:
        return xff.split(",")[0].strip()
    return request.remote_addr or "127.0.0.1"


# ====== 会话文件操作 ======
def _session_path(username):
    return os.path.join(SESSION_DIR, f"{username}.session")


def _get_session(username):
    p = _session_path(username)
    if not os.path.exists(p):
        return None
    try:
        if time.time() - os.path.getmtime(p) > 86400:
            os.remove(p)
            return None
        with open(p, "r") as f:
            return f.read().strip()
    except Exception:
        return None


def _set_session(username, sid):
    os.makedirs(SESSION_DIR, exist_ok=True)
    with open(_session_path(username), "w") as f:
        f.write(sid)
    log.debug(f"session 写入: {username}")


def _del_session(username):
    p = _session_path(username)
    if os.path.exists(p):
        os.remove(p)
        log.debug(f"session 删除: {username}")


def gc_sessions():
    global last_gc
    now = time.time()
    if now - last_gc < SESSION_GC_INTERVAL:
        return
    last_gc = now
    if not os.path.isdir(SESSION_DIR):
        return
    removed = 0
    for fn in os.listdir(SESSION_DIR):
        p = os.path.join(SESSION_DIR, fn)
        if fn.endswith(".session") and now - os.path.getmtime(p) > 86400:
            try:
                os.remove(p)
                removed += 1
            except Exception:
                pass
    if removed:
        log.info(f"session GC: 清理了 {removed} 个过期会话")


# ====== 认证装饰器 ======
def require_auth(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        gc_sessions()
        username = session.get("username")
        sid = session.get("session_id")
        if not username or not sid:
            return jsonify({"code": 401, "msg": "请先登录"}), 401
        current_sid = _get_session(username)
        if not current_sid or current_sid != sid:
            session.clear()
            return jsonify({"code": 401, "msg": "该账号已在其他设备登录，当前会话已被踢出"}), 401
        return f(*args, **kwargs)
    return wrapper


def _do_login(username):
    sid = secrets.token_hex(32)
    session["username"] = username
    session["session_id"] = sid
    session.permanent = True
    _set_session(username, sid)
    return jsonify({"code": 0, "msg": "ok", "data": {"username": username}})


# ====== 路由 ======
@auth_bp.route("/login", methods=["POST"])
def login():
    data = request.get_json(silent=True) or {}
    username = (data.get("username") or "").strip()
    password = data.get("password") or ""
    ip = get_client_ip()
    now = time.time()
    log.debug(f"登录尝试: username={username or '(空)'}, ip={ip}")

    # IP 频率限制
    ip_info = state.ip_attempts.get(ip, {"count": 0, "first_time": now})
    if now - ip_info["first_time"] > 60:
        ip_info = {"count": 0, "first_time": now}
    ip_info["count"] += 1
    state.ip_attempts[ip] = ip_info
    if ip_info["count"] > 20:
        log.warning(f"IP {ip} 登录频率超限")
        return jsonify({"code": 429, "msg": "请求过于频繁，请稍后再试"}), 429

    # 紧急解锁
    if username == "_unlock":
        if not state.unlock_code:
            return jsonify({"code": 401, "msg": "用户名或密码错误"}), 401
        h = hash_password("_unlock", password, state.unlock_code["salt"])
        if h != state.unlock_code["hash"]:
            return jsonify({"code": 401, "msg": "用户名或密码错误"}), 401
        state.failed_attempts.clear()
        state.ip_attempts.pop(ip, None)
        log.warning(f"紧急解锁已使用，来源 IP: {ip}")
        return _do_login("_unlock")

    # 用户检查
    user_info = state.users.get(username)
    if not user_info:
        return jsonify({"code": 401, "msg": "用户名或密码错误"}), 401

    # 锁定检查
    fa = state.failed_attempts.get(username)
    if fa and fa.get("lockout_until") and now < fa["lockout_until"]:
        remaining = int(fa["lockout_until"] - now)
        mins, secs = divmod(remaining, 60)
        log.warning(f"登录拒绝: {username} 已锁定，剩余 {mins}分{secs}秒，IP: {ip}")
        return jsonify({"code": 423, "msg": f"账户已锁定，请 {mins} 分 {secs} 秒后重试"}), 423

    # 密码校验
    h = hash_password(username, password, user_info["salt"])
    if h != user_info["hash"]:
        if not fa or now - fa.get("first_time", 0) > LOCKOUT_MINUTES * 60:
            fa = {"count": 0, "first_time": now}
        fa["count"] += 1
        if fa["count"] >= MAX_ATTEMPTS:
            fa["lockout_until"] = now + LOCKOUT_MINUTES * 60
            log.warning(f"用户 {username} 连续 {fa['count']} 次登录失败，已锁定 {LOCKOUT_MINUTES} 分钟，来源 IP: {ip}")
        else:
            log.info(f"用户 {username} 登录失败（第 {fa['count']}/{MAX_ATTEMPTS} 次），来源 IP: {ip}")
        state.failed_attempts[username] = fa
        remaining = max(0, MAX_ATTEMPTS - fa["count"])
        return jsonify({"code": 401, "msg": f"用户名或密码错误，还剩 {remaining} 次尝试机会"}), 401

    # 登录成功
    state.failed_attempts.pop(username, None)
    state.ip_attempts.pop(ip, None)
    log.info(f"登录成功: {username}，来源 IP: {ip}")
    log.debug(f"当前活跃 session 数: {sum(1 for fn in os.listdir(SESSION_DIR) if fn.endswith('.session')) if os.path.isdir(SESSION_DIR) else 0}")
    return _do_login(username)


@auth_bp.route("/logout", methods=["POST"])
def logout():
    username = session.get("username")
    if username:
        _del_session(username)
        log.info(f"用户 {username} 已登出")
    session.clear()
    return jsonify({"code": 0, "msg": "ok"})


@auth_bp.route("/check_session", methods=["GET"])
def check_session():
    gc_sessions()
    username = session.get("username")
    sid = session.get("session_id")
    if not username or not sid:
        return jsonify({"code": 401, "msg": "未登录"}), 401
    current_sid = _get_session(username)
    if not current_sid or current_sid != sid:
        session.clear()
        log.info(f"用户 {username} 会话被踢出（新设备登录覆盖）")
        return jsonify({"code": 401, "msg": "该账号已在其他设备登录，当前会话已被踢出"}), 401
    return jsonify({"code": 0, "msg": "ok", "data": {"username": username}})
