"""图表生成 API —— 折线图 & 柱状图，支持 .tar.gz 压缩包"""

import csv
import io
import os
import re
import shutil
import tarfile
import tempfile
from datetime import datetime, timedelta

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
import numpy as np
from flask import Blueprint, request, jsonify, session, send_file

from chart_common import CsvColumn, aggregate_data, build_chart_meta
from logger import log

chart_bp = Blueprint("chart", __name__)

ROOT_DIR = os.environ.get("ROOT_DIR", "/home/harry")
FREQ_OPTIONS = {"hourly", "daily", "weekly"}
AVAILABLE_COLUMNS = list(CsvColumn)


def _iter_csv_files(code, start_date, end_date):
    """遍历时间区间内匹配的文件，返回 [(ts_date, csv_path, is_temp), ...]
    支持 .csv 和 .tar.gz，压缩包自动解压到临时目录"""
    files = []
    d = start_date
    while d <= end_date:
        ds = d.strftime("%Y%m%d")
        search_dir = os.path.join(ROOT_DIR, f"{d.strftime('%Y')}_ah比价", f"{ds}_ah比价")
        if not os.path.isdir(search_dir):
            d += timedelta(days=1)
            continue
        for fn in sorted(os.listdir(search_dir)):
            if fn.startswith("."):
                continue
            full_path = os.path.join(search_dir, fn)

            if fn.startswith(code) and fn.endswith(".csv"):
                files.append((d, full_path, False))

            elif fn.startswith(code) and (fn.endswith(".tar.gz") or fn.endswith(".tgz")):
                tmp_dir = tempfile.mkdtemp(prefix=f"chart_{code}_")
                try:
                    with tarfile.open(full_path, "r:gz") as tf:
                        tf.extractall(tmp_dir)
                    for root, _, extracted in os.walk(tmp_dir):
                        for ef in sorted(extracted):
                            if ef.endswith(".csv") and not ef.startswith("."):
                                files.append((d, os.path.join(root, ef), True))
                except Exception as e:
                    log.warning(f"解压失败 {full_path}: {e}")
                    shutil.rmtree(tmp_dir, ignore_errors=True)
        d += timedelta(days=1)
    return files


def _read_file(path, columns, collectors, stock_info):
    """读取单个 CSV，追加数据到 collectors"""
    try:
        with open(path, "r", encoding="utf-8-sig") as f:
            reader = csv.DictReader(f)
            for row in reader:
                if not stock_info:
                    stock_info["stock_name"] = row.get("stock_name", "").strip()
                    stock_info["a_cod"] = row.get("a_cod", "").strip()
                ts_str = row.get("ovral_timstmp", "").strip()
                if not ts_str:
                    continue
                try:
                    ts = datetime.strptime(ts_str, "%Y-%m-%d %H:%M:%S")
                except ValueError:
                    continue
                for col in columns:
                    val_str = row.get(col, "").strip()
                    if val_str:
                        if val_str.endswith("%"):
                            val_str = val_str[:-1]
                        try:
                            collectors[col][0].append(ts)
                            collectors[col][1].append(float(val_str))
                        except ValueError:
                            pass
    except Exception:
        pass


def _collect_data(code, start_str, end_str, columns, resample):
    """采集数据，返回 (collectors, stock_info, temp_dirs)"""
    start_date = datetime.strptime(start_str, "%Y%m%d")
    end_date = datetime.strptime(end_str, "%Y%m%d")

    collectors = {col: ([], []) for col in columns}
    stock_info = {}
    temp_dirs = set()

    log.debug(f"开始采集数据: code={code}, {start_str}-{end_str}, resample={resample}, columns={columns}")
    file_list = _iter_csv_files(code, start_date, end_date)
    log.info(f"数据采集: 找到 {len(file_list)} 个匹配文件")

    for ts_date, path, is_temp in file_list:
        if is_temp:
            temp_dirs.add(os.path.dirname(path))
        _read_file(path, columns, collectors, stock_info)

    log.debug(f"数据读取完成, stock_info={stock_info.get('a_cod','?')}-{stock_info.get('stock_name','?')}, "
              f"各列数据点: " + ", ".join(f"{col}={len(collectors[col][0])}" for col in columns))

    for col in columns:
        if not collectors[col][0]:
            label = CsvColumn.label_of(col)
            # 清理临时目录
            for td in temp_dirs:
                shutil.rmtree(td, ignore_errors=True)
            raise ValueError(f"未提取到 {label} ({col}) 的数据")

    if resample and resample in FREQ_OPTIONS:
        collectors = aggregate_data(collectors, resample)
        log.debug(f"聚合后 ({resample}) 数据点: " +
                  ", ".join(f"{col}={len(collectors[col][0])}" for col in columns))

    return collectors, stock_info, temp_dirs


def _plot_lines(collectors, columns, title, figsize, dpi):
    """绘制折线图，返回 PNG bytes。日期不连续则按顺序连接无断点"""
    fig, ax = plt.subplots(figsize=figsize, dpi=dpi)
    for col in columns:
        ts_list, val_list = collectors[col]
        # 转数值坐标保证断点日期也能连续连接
        x_nums = mdates.date2num(ts_list)
        ax.plot(x_nums, val_list, linewidth=0.8, color=CsvColumn.color_of(col),
                label=CsvColumn.label_of(col), alpha=0.85)

    ax.xaxis.set_major_formatter(mdates.DateFormatter("%m-%d %H:%M"))
    ax.xaxis.set_major_locator(mdates.AutoDateLocator())
    fig.autofmt_xdate(rotation=30, ha="right")
    ax.set_xlabel("时间", fontsize=12)
    ax.set_ylabel("数值", fontsize=12)
    ax.set_title(title, fontsize=14, fontweight="bold")
    ax.legend(loc="best", fontsize=10)
    ax.grid(True, alpha=0.3)
    ax.set_xlim(auto=True)
    fig.tight_layout()

    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=dpi, bbox_inches="tight")
    plt.close(fig)
    buf.seek(0)
    return buf


def _plot_bars(collectors, title, figsize, dpi):
    """绘制 a/h_rate 柱状图，返回 PNG bytes。日期不连续柱间距自适应"""
    col = CsvColumn.AH_RATE
    ts_list, val_list = collectors[col]
    n = len(ts_list)

    fig, ax = plt.subplots(figsize=figsize, dpi=dpi)
    x_nums = mdates.date2num(ts_list)

    if n <= 1:
        bar_width = 0.5
    else:
        # 中位间距自适应，忽略日期跳跃
        bar_width = np.median(np.diff(x_nums)) * 0.75

    bars = ax.bar(x_nums, val_list, width=bar_width,
                  color=CsvColumn.color_of(col), alpha=0.85, label=CsvColumn.label_of(col))
    for bar, val in zip(bars, val_list):
        ax.text(bar.get_x() + bar.get_width() / 2, bar.get_height(),
                f"{val:.2f}%", ha="center", va="bottom", fontsize=8, color="#333333")

    ax.xaxis.set_major_formatter(mdates.DateFormatter("%m-%d %H:%M" if n > 10 else "%m-%d"))
    ax.xaxis.set_major_locator(mdates.AutoDateLocator())
    fig.autofmt_xdate(rotation=30, ha="right")
    ax.set_xlabel("时间", fontsize=12)
    ax.set_ylabel("溢价率 (%)", fontsize=12)
    ax.set_title(title, fontsize=14, fontweight="bold")
    ax.legend(loc="best", fontsize=10)
    ax.grid(True, alpha=0.3, axis="y")
    ax.axhline(y=0, color="#999999", linewidth=0.5, linestyle="--")
    ax.set_xlim(auto=True)
    fig.tight_layout()

    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=dpi, bbox_inches="tight")
    plt.close(fig)
    buf.seek(0)
    return buf


# ═══════════════════════════════════════════════
# 路由
# ═══════════════════════════════════════════════

@chart_bp.route("/chart_lines", methods=["GET"])
def chart_lines():
    """折线图：多列可选"""
    date_range = request.args.get("date", "").strip()
    code = request.args.get("code", "").strip()
    freq = request.args.get("freq", "daily").strip()
    cols_str = request.args.get("columns", "a_price").strip()

    if not re.match(r"^\d{8}-\d{8}$", date_range) or not re.match(r"^\d{6}$", code):
        return jsonify({"code": 400, "msg": "日期格式yyyyMMdd-yyyyMMdd"}), 400
    if freq not in FREQ_OPTIONS:
        return jsonify({"code": 400, "msg": f"频率仅支持: {', '.join(FREQ_OPTIONS)}"}), 400

    columns = [c.strip() for c in cols_str.split(",") if c.strip() in AVAILABLE_COLUMNS]
    if not columns:
        return jsonify({"code": 400, "msg": f"请至少选择一个有效列: {', '.join(AVAILABLE_COLUMNS)}"}), 400

    start_str, end_str = date_range.split("-")
    try:
        collectors, stock_info, temp_dirs = _collect_data(code, start_str, end_str, columns, freq)
    except ValueError as e:
        log.warning(f"折线图数据采集失败: {e}")
        return jsonify({"code": 404, "msg": str(e)}), 404

    dir_name = f"{code}_{start_str}-{end_str}"
    meta = build_chart_meta(stock_info, dir_name, columns, chart_type="走势图")
    log.debug(f"开始绘制折线图: {meta['default_title']}")
    buf = _plot_lines(collectors, columns, meta["default_title"], (16, 8), 150)
    log.info(f"折线图生成: code={code}, {date_range}, freq={freq}, columns={cols_str}, "
             f"size={buf.getbuffer().nbytes}B")

    for td in temp_dirs:
        shutil.rmtree(td, ignore_errors=True)

    return send_file(buf, mimetype="image/png", as_attachment=True,
                     download_name=f"{code}_{start_str}_{end_str}_{freq}_走势图.png")


@chart_bp.route("/chart_bars", methods=["GET"])
def chart_bars():
    """AH 溢价率柱状图"""
    date_range = request.args.get("date", "").strip()
    code = request.args.get("code", "").strip()
    freq = request.args.get("freq", "daily").strip()

    if not re.match(r"^\d{8}-\d{8}$", date_range) or not re.match(r"^\d{6}$", code):
        return jsonify({"code": 400, "msg": "日期格式yyyyMMdd-yyyyMMdd"}), 400
    if freq not in FREQ_OPTIONS:
        return jsonify({"code": 400, "msg": f"频率仅支持: {', '.join(FREQ_OPTIONS)}"}), 400

    start_str, end_str = date_range.split("-")
    columns = [CsvColumn.AH_RATE]

    try:
        collectors, stock_info, temp_dirs = _collect_data(code, start_str, end_str, columns, freq)
    except ValueError as e:
        log.warning(f"柱状图数据采集失败: {e}")
        return jsonify({"code": 404, "msg": str(e)}), 404

    dir_name = f"{code}_{start_str}-{end_str}"
    meta = build_chart_meta(stock_info, dir_name, columns, chart_type="柱状图")
    log.debug(f"开始绘制柱状图: {meta['default_title']}")
    buf = _plot_bars(collectors, meta["default_title"], (16, 8), 150)
    log.info(f"柱状图生成: code={code}, {date_range}, freq={freq}, "
             f"size={buf.getbuffer().nbytes}B")

    for td in temp_dirs:
        shutil.rmtree(td, ignore_errors=True)

    return send_file(buf, mimetype="image/png", as_attachment=True,
                     download_name=f"{code}_{start_str}_{end_str}_{freq}_柱状图.png")
