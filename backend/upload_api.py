"""文件上传模块"""

import os
from datetime import datetime

from flask import Blueprint, request, jsonify, session

from auth import require_auth
from config import STOCK_FILE, PREMIUM_FILE
from logger import log

upload_bp = Blueprint("upload", __name__)


def _detect_and_convert_to_utf8(raw_bytes):
    if raw_bytes[:3] == b"\xef\xbb\xbf":
        return raw_bytes.decode("utf-8-sig").encode("utf-8")
    for enc in ["utf-8", "gbk", "gb2312", "gb18030", "latin-1"]:
        try:
            return raw_bytes.decode(enc).encode("utf-8")
        except (UnicodeDecodeError, UnicodeError):
            continue
    return raw_bytes


def _save_file(target_path):
    username = session.get("username", "unknown")
    body = request.get_data()
    if not body:
        log.warning(f"用户 {username} 上传文件到 {target_path} 失败：请求体为空")
        return jsonify({"code": 400, "msg": "请求体为空"}), 400
    try:
        orig_size = len(body)
        body = _detect_and_convert_to_utf8(body)
        log.debug(f"编码转换: {target_path} 原始 {orig_size}B -> UTF-8 {len(body)}B")
        os.makedirs(os.path.dirname(target_path), exist_ok=True)
        with open(target_path, "wb") as f:
            f.write(body)
        stat = os.stat(target_path)
        log.info(f"用户 {username} 上传文件到 {target_path}，大小 {stat.st_size} 字节")
    except Exception as e:
        log.error(f"用户 {username} 上传文件到 {target_path} 写入失败: {e}")
        return jsonify({"code": 500, "msg": f"文件写入失败: {e}"}), 500
    return jsonify({
        "code": 0, "msg": "ok",
        "data": {
            "file": target_path,
            "size": stat.st_size,
            "modified": datetime.fromtimestamp(stat.st_mtime).strftime("%Y-%m-%d %H:%M:%S")
        }
    })


@upload_bp.route("/update_ah_rate", methods=["POST"])
@require_auth
def update_ah_rate():
    return _save_file(STOCK_FILE)


@upload_bp.route("/premium_update", methods=["POST"])
@require_auth
def premium_update():
    return _save_file(PREMIUM_FILE)
