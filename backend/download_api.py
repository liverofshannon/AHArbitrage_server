"""搜索 & 下载模块"""

import os
import re
import tempfile
import zipfile
from datetime import datetime, timedelta

from flask import Blueprint, request, jsonify, session, send_file

from auth import require_auth
from config import ROOT_DIR
from logger import log

download_bp = Blueprint("download", __name__)


@download_bp.route("/search_csv", methods=["GET"])
@require_auth
def search_csv():
    date_str = request.args.get("date", "").strip()
    code = request.args.get("code", "").strip()
    username = session.get("username", "unknown")

    # 日期范围 → 打包下载
    if re.match(r"^\d{8}-\d{8}$", date_str) and re.match(r"^\d{6}$", code):
        start_str, end_str = date_str.split("-")
        try:
            start_date = datetime.strptime(start_str, "%Y%m%d")
            end_date = datetime.strptime(end_str, "%Y%m%d")
        except ValueError:
            return jsonify({"code": 400, "msg": "日期格式错误"}), 400
        if start_date > end_date:
            return jsonify({"code": 400, "msg": "开始日期不能晚于结束日期"}), 400

        total_days = (end_date - start_date).days + 1
        log.debug(f"批量搜索: code={code}, {start_str}-{end_str}, 共 {total_days} 天")
        found_files = {}
        skipped = 0
        d = start_date
        while d <= end_date:
            ds = d.strftime("%Y%m%d")
            search_dir = os.path.join(ROOT_DIR, f"{d.strftime('%Y')}_ah比价", f"{ds}_ah比价")
            if os.path.isdir(search_dir):
                for f in os.listdir(search_dir):
                    if f.startswith(code) and f.endswith(".csv") and not f.startswith("."):
                        found_files.setdefault(ds, []).append((os.path.join(search_dir, f), f))
            else:
                skipped += 1
            d += timedelta(days=1)

        log.debug(f"批量搜索完成: 命中 {len(found_files)} 天, 跳过 {skipped} 天(目录不存在)")
        if not found_files:
            log.info(f"批量搜索无结果: {start_str}-{end_str}, code={code}")
            return jsonify({"code": 404, "msg": "未找到匹配的文件"}), 404

        tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".zip")
        try:
            with zipfile.ZipFile(tmp.name, "w", zipfile.ZIP_DEFLATED) as zf:
                for ds, files in sorted(found_files.items()):
                    for full_path, filename in files:
                        zf.write(full_path, f"{ds}/{filename}")
            tmp.close()
            total = sum(len(v) for v in found_files.values())
            zip_size = os.path.getsize(tmp.name)
            log.info(f"批量打包: {start_str}-{end_str}, code={code}, {total} 个文件, zip {zip_size}B")
            return send_file(tmp.name, as_attachment=True,
                             download_name=f"{code}_{start_str}_{end_str}.zip")
        except Exception as e:
            log.error(f"打包下载失败: {e}")
            if os.path.exists(tmp.name):
                os.remove(tmp.name)
            return jsonify({"code": 500, "msg": f"打包失败: {e}"}), 500

    # 单日期 → 文件列表
    if not re.match(r"^\d{8}$", date_str) or not re.match(r"^\d{6}$", code):
        return jsonify({"code": 400, "msg": "日期格式 yyyyMMdd 或 yyyyMMdd-yyyyMMdd"}), 400

    search_dir = os.path.join(ROOT_DIR, f"{date_str[:4]}_ah比价", f"{date_str}_ah比价")
    if not os.path.isdir(search_dir):
        log.debug(f"单日搜索目录不存在: {search_dir}")
        return jsonify({"code": 0, "data": {"dir": search_dir, "files": []}})

    files = sorted([f for f in os.listdir(search_dir)
                    if f.startswith(code) and f.endswith(".csv") and not f.startswith(".")])
    log.info(f"单日搜索: {search_dir}, code={code}, 结果 {len(files)} 个")
    return jsonify({"code": 0, "data": {"dir": search_dir, "files": files}})


@download_bp.route("/download_file", methods=["GET"])
@require_auth
def download_file():
    dir_path = request.args.get("dir", "")
    filename = request.args.get("file", "")
    if ".." in dir_path or ".." in filename or "/" in filename or "\\" in filename:
        log.warning(f"非法下载路径: dir={dir_path}, file={filename}")
        return jsonify({"code": 400, "msg": "非法路径"}), 400
    filepath = os.path.join(dir_path, filename)
    if not os.path.isfile(filepath):
        log.warning(f"下载文件不存在: {filepath}")
        return jsonify({"code": 404, "msg": "文件不存在"}), 404
    log.info(f"单文件下载: {filepath} ({os.path.getsize(filepath)}B)")
    return send_file(filepath, as_attachment=True, download_name=filename)
