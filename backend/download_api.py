"""搜索 & 下载模块，支持 .tar.gz 自动解压"""

import os
import re
import shutil
import tarfile
import tempfile
import zipfile
from datetime import datetime, timedelta

from flask import Blueprint, request, jsonify, session, send_file

from auth import require_auth
from config import ROOT_DIR
from logger import log

download_bp = Blueprint("download", __name__)


def _find_files(code, start_date, end_date):
    """遍历日期区间，返回 [(date_str, full_path, display_name)], .tar.gz 已解压列出内部 CSV"""
    results = []
    d = start_date
    while d <= end_date:
        ds = d.strftime("%Y%m%d")
        search_dir = os.path.join(ROOT_DIR, f"{d.strftime('%Y')}_ah比价", f"{ds}_ah比价")
        if not os.path.isdir(search_dir):
            d += timedelta(days=1)
            continue
        for fn in sorted(os.listdir(search_dir)):
            if fn.startswith(".") or not fn.startswith(code):
                continue
            full = os.path.join(search_dir, fn)
            if fn.endswith(".csv"):
                results.append((ds, full, fn))
            elif fn.endswith(".tar.gz") or fn.endswith(".tgz"):
                try:
                    tmp = tempfile.mkdtemp(prefix=f"dl_{code}_")
                    with tarfile.open(full, "r:gz") as tf:
                        tf.extractall(tmp)
                    for root, _, efiles in os.walk(tmp):
                        for ef in sorted(efiles):
                            if ef.endswith(".csv") and not ef.startswith("."):
                                results.append((ds, os.path.join(root, ef), ef))
                except Exception as e:
                    log.warning(f"解压失败 {full}: {e}")
        d += timedelta(days=1)
    return results


@download_bp.route("/search_csv", methods=["GET"])
@require_auth
def search_csv():
    date_str = request.args.get("date", "").strip()
    code = request.args.get("code", "").strip()
    username = session.get("username", "unknown")

    # ── 日期范围 → 打包下载 ──
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
        file_list = _find_files(code, start_date, end_date)
        log.debug(f"批量搜索完成: 找到 {len(file_list)} 个文件(含解压)")

        if not file_list:
            log.info(f"批量搜索无结果: {start_str}-{end_str}, code={code}")
            return jsonify({"code": 404, "msg": "未找到匹配的文件"}), 404

        tmp_dirs = set()
        tmp_zip = tempfile.NamedTemporaryFile(delete=False, suffix=".zip")
        try:
            with zipfile.ZipFile(tmp_zip.name, "w", zipfile.ZIP_DEFLATED) as zf:
                for ds, full_path, disp_name in file_list:
                    arcname = f"{ds}/{disp_name}"
                    zf.write(full_path, arcname)
                    dname = os.path.dirname(full_path)
                    if "_ah比价" not in dname:  # 解压出的临时目录
                        tmp_dirs.add(dname)
            tmp_zip.close()
            total = len(file_list)
            zip_size = os.path.getsize(tmp_zip.name)
            log.info(f"批量打包: {start_str}-{end_str}, code={code}, {total} 个文件, zip {zip_size}B")
            return send_file(tmp_zip.name, as_attachment=True,
                             download_name=f"{code}_{start_str}_{end_str}.zip")
        except Exception as e:
            log.error(f"打包失败: {e}")
            if os.path.exists(tmp_zip.name):
                os.remove(tmp_zip.name)
            return jsonify({"code": 500, "msg": f"打包失败: {e}"}), 500
        finally:
            for td in tmp_dirs:
                shutil.rmtree(td, ignore_errors=True)

    # ── 单日期 → 文件列表 ──
    if not re.match(r"^\d{8}$", date_str) or not re.match(r"^\d{6}$", code):
        return jsonify({"code": 400, "msg": "日期格式 yyyyMMdd 或 yyyyMMdd-yyyyMMdd"}), 400

    start_date = datetime.strptime(date_str, "%Y%m%d")
    file_list = _find_files(code, start_date, start_date)
    search_dir = os.path.join(ROOT_DIR, f"{date_str[:4]}_ah比价", f"{date_str}_ah比价")

    # 清理临时目录（提取自 tar.gz 的）
    for _, full_path, _ in file_list:
        dname = os.path.dirname(full_path)
        if "_ah比价" not in dname:
            shutil.rmtree(dname, ignore_errors=True)

    disp_files = [fn for _, _, fn in file_list]
    log.info(f"单日搜索: {search_dir}, code={code}, 结果 {len(disp_files)} 个")
    return jsonify({"code": 0, "data": {"dir": search_dir, "files": disp_files}})


@download_bp.route("/download_file", methods=["GET"])
@require_auth
def download_file():
    dir_path = request.args.get("dir", "")
    filename = request.args.get("file", "")

    if ".." in dir_path or ".." in filename or "/" in filename or "\\" in filename:
        log.warning(f"非法下载路径: dir={dir_path}, file={filename}")
        return jsonify({"code": 400, "msg": "非法路径"}), 400

    # 直接文件
    direct = os.path.join(dir_path, filename)
    if os.path.isfile(direct):
        log.info(f"单文件下载: {direct} ({os.path.getsize(direct)}B)")
        return send_file(direct, as_attachment=True, download_name=filename)

    # 可能是 tar.gz 内的文件，尝试解压并返回
    for fn in os.listdir(dir_path):
        if fn.startswith("."):
            continue
        full = os.path.join(dir_path, fn)
        if (fn.endswith(".tar.gz") or fn.endswith(".tgz")) and os.path.isfile(full):
            try:
                tmp = tempfile.mkdtemp(prefix="dl_single_")
                with tarfile.open(full, "r:gz") as tf:
                    tf.extractall(tmp)
                for root, _, efiles in os.walk(tmp):
                    for ef in efiles:
                        if ef == filename:
                            extracted = os.path.join(root, ef)
                            log.info(f"从压缩包解压下载: {extracted}")
                            resp = send_file(extracted, as_attachment=True, download_name=filename)
                            # 没法在响应后清理，留到下次或手动
                            return resp
            except Exception as e:
                log.warning(f"解压下载失败 {full}: {e}")

    log.warning(f"下载文件不存在: {direct}")
    return jsonify({"code": 404, "msg": "文件不存在"}), 404
