#!/usr/bin/env python3
"""AHarbitrage Chart 公共模块 —— 枚举、数据采集、字体、聚合等共享逻辑。"""

import csv
import sys
from datetime import datetime
from enum import StrEnum
from pathlib import Path

import matplotlib
import matplotlib.font_manager as fm


# ═══════════════════════════════════════════════════════════════════════
# 枚举 & 映射
# ═══════════════════════════════════════════════════════════════════════

class CsvColumn(StrEnum):
    """CSV 列名枚举，用于 -c 参数传参或代码中引用。"""

    STOCK_NAME = "stock_name"       # 股票名称
    A_COD = "a_cod"                 # A 股代码
    A_PRICE = "a_price"             # A 股价格
    H_COD = "h_cod"                 # H 股代码
    H_PRICE = "h_price"             # H 股价格
    AH_RATE = "a/h_rate"            # AH 溢价率
    A_HIGH = "a_high"               # A 股最高价
    A_LOW = "a_low"                 # A 股最低价
    H_HIGH = "h_high"               # H 股最高价
    H_LOW = "h_low"                 # H 股最低价

    @classmethod
    def label_of(cls, column: str) -> str:
        """返回列名对应的中文标签，未知列名返回原值。"""
        return _CSV_COLUMN_LABELS.get(column, column)

    @classmethod
    def color_of(cls, column: str) -> str:
        """返回列名对应的默认颜色，未知列名返回深灰。"""
        return _CSV_COLUMN_COLORS.get(column, "#555555")


_CSV_COLUMN_LABELS: dict[str, str] = {
    "stock_name": "股票名称",
    "a_cod": "A股代码",
    "a_price": "A股价格",
    "h_cod": "H股代码",
    "h_price": "H股价格",
    "a/h_rate": "AH溢价率",
    "a_high": "A股最高价",
    "a_low": "A股最低价",
    "h_high": "H股最高价",
    "h_low": "H股最低价",
}

_CSV_COLUMN_COLORS: dict[str, str] = {
    "a_price": "#000000",   # 黑色 — A 股价格
    "h_price": "#1f77b4",   # 蓝色 — H 股价格
    "a/h_rate": "#d62728",  # 红色 — AH 溢价率
    "a_high": "#000000",    # 黑色 — A 股最高价
    "a_low": "#000000",     # 黑色 — A 股最低价
    "h_high": "#1f77b4",    # 蓝色 — H 股最高价
    "h_low": "#1f77b4",     # 蓝色 — H 股最低价
}


# ═══════════════════════════════════════════════════════════════════════
# 中文字体
# ═══════════════════════════════════════════════════════════════════════

def setup_cjk_font() -> None:
    """自动检测并设置中文字体，避免图表中文乱码。"""
    cjk_candidates = [
        "PingFang SC", "PingFang HK", "PingFang TC",
        "Heiti SC", "Heiti TC", "STHeiti", "STHeiti Light",
        "Songti SC", "Songti TC", "STSong",
        "Kaiti SC", "Kaiti TC", "STKaiti",
        "Microsoft YaHei", "SimHei", "SimSun",
        "Noto Sans CJK SC", "Noto Sans CJK", "Noto Sans SC",
        "WenQuanYi Micro Hei", "WenQuanYi Zen Hei",
        "Arial Unicode MS",
    ]
    available = {f.name for f in fm.fontManager.ttflist}
    for font_name in cjk_candidates:
        if font_name in available:
            matplotlib.rcParams["font.family"] = font_name
            matplotlib.rcParams["font.sans-serif"] = [font_name]
            print(f"[字体] 使用中文字体: {font_name}")
            return
    print("[字体] 未找到中文字体，图表中文可能显示为方块。", file=sys.stderr)


# 模块加载时执行
setup_cjk_font()


# ═══════════════════════════════════════════════════════════════════════
# 文件系统工具
# ═══════════════════════════════════════════════════════════════════════

def is_date_dir(name: str) -> bool:
    """判断目录名是否为 8 位日期格式 (YYYYMMDD)。"""
    if len(name) != 8:
        return False
    try:
        datetime.strptime(name, "%Y%m%d")
        return True
    except ValueError:
        return False


def find_csv_in_dir(dir_path: Path) -> Path | None:
    """在目录中查找 CSV 文件（排除隐藏文件）。"""
    csv_files = sorted(dir_path.glob("*.csv"))
    csv_files = [f for f in csv_files if not f.name.startswith(".")]
    return csv_files[0] if csv_files else None


# ═══════════════════════════════════════════════════════════════════════
# 数据聚合
# ═══════════════════════════════════════════════════════════════════════

def aggregate_data(
    data: dict[str, tuple[list[datetime], list[float]]],
    mode: str,
) -> dict[str, tuple[list[datetime], list[float]]]:
    """将逐笔数据聚合为指定周期的最后一笔。

    mode: "hourly" / "daily" / "weekly"
    """

    def make_key(ts: datetime):
        if mode == "hourly":
            return (ts.year, ts.month, ts.day, ts.hour)
        elif mode == "weekly":
            iso = ts.isocalendar()
            return (iso.year, iso.week)
        else:  # daily
            return ts.date()

    result: dict[str, tuple[list[datetime], list[float]]] = {}
    for col, (ts_list, val_list) in data.items():
        groups: dict[object, tuple[datetime, float]] = {}
        for ts, val in zip(ts_list, val_list):
            groups[make_key(ts)] = (ts, val)
        sorted_keys = sorted(groups.keys())
        result[col] = (
            [groups[k][0] for k in sorted_keys],
            [groups[k][1] for k in sorted_keys],
        )
    return result


# ═══════════════════════════════════════════════════════════════════════
# 数据采集
# ═══════════════════════════════════════════════════════════════════════

def collect_data(
    base_dir: Path, columns: list[str], resample: str | None = None
) -> tuple[dict[str, tuple[list[datetime], list[float]]], dict[str, str]]:
    """遍历 base_dir 下所有日期子目录，读取 CSV，提取指定列的数据。

    返回:
        (data, stock_info)
        - data: {column_name: (timestamps, values), ...}
        - stock_info: {"stock_name": ..., "a_cod": ...}
    """
    collectors: dict[str, tuple[list[datetime], list[float]]] = {
        col: ([], []) for col in columns
    }

    stock_info: dict[str, str] = {}

    date_dirs = sorted(
        [d for d in base_dir.iterdir() if d.is_dir() and is_date_dir(d.name)],
        key=lambda d: d.name,
    )

    if not date_dirs:
        print(f"[错误] 在 {base_dir} 下未找到任何日期格式 (YYYYMMDD) 的子目录。", file=sys.stderr)
        sys.exit(1)

    print(f"找到 {len(date_dirs)} 个日期目录: {date_dirs[0].name} ~ {date_dirs[-1].name}")

    skipped = 0
    for date_dir in date_dirs:
        csv_path = find_csv_in_dir(date_dir)
        if csv_path is None:
            print(f"  [跳过] {date_dir.name}: 未找到 CSV 文件")
            skipped += 1
            continue

        try:
            with open(csv_path, "r", encoding="utf-8-sig") as f:
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
                                val = float(val_str)
                                collectors[col][0].append(ts)
                                collectors[col][1].append(val)
                            except ValueError:
                                pass
        except Exception as e:
            print(f"  [错误] 读取 {csv_path} 失败: {e}", file=sys.stderr)
            skipped += 1

    if skipped:
        print(f"共跳过 {skipped} 个目录。")

    if resample:
        collectors = aggregate_data(collectors, resample)
        labels = {"hourly": "小时", "daily": "个交易日", "weekly": "周"}
        label = labels.get(resample, resample)
        print(f"[{resample}] 已聚合为 {len(next(iter(collectors.values()))[0])} {label}数据")

    for col in columns:
        if not collectors[col][0]:
            print(f"[错误] 列 \"{col}\" 未提取到任何数据，请检查列名是否正确。", file=sys.stderr)
            sys.exit(1)

    for col in columns:
        ts_list, val_list = collectors[col]
        label = CsvColumn.label_of(col)
        print(f"列 \"{label}\" ({col}): {len(ts_list)} 个数据点, "
              f"时间范围 {min(ts_list)} ~ {max(ts_list)}, "
              f"数值范围 [{min(val_list):.4f}, {max(val_list):.4f}]")

    return collectors, stock_info


# ═══════════════════════════════════════════════════════════════════════
# 图表元信息（标题 / 文件名前缀）
# ═══════════════════════════════════════════════════════════════════════

def build_chart_meta(
    stock_info: dict[str, str],
    dir_name: str,
    columns: list[str],
    chart_type: str = "走势图",
) -> dict[str, str]:
    """根据股票信息和目录名构建标题前缀和文件名前缀。

    返回:
        {"chart_prefix": "000333-美的集团_20260501-20260610",     # 标题用
         "file_prefix":  "美的集团_20260501-20260610",            # 文件名用
         "col_part":     "A股价格、H股价格",                       # 列名中文部分
         "default_title": "000333-美的集团_20260501-20260610 — A股价格、H股价格 走势图",
         "default_output":"美的集团_20260501-20260610_A股价格、H股价格.png"}
    """
    a_cod = stock_info.get("a_cod", "")
    stock_name = stock_info.get("stock_name", "")

    if a_cod and stock_name and "_" in dir_name:
        date_range = dir_name.split("_", 1)[1]
        chart_prefix = f"{a_cod}-{stock_name}_{date_range}"
        file_prefix = f"{stock_name}_{date_range}"
    else:
        chart_prefix = dir_name
        file_prefix = dir_name

    col_labels = [CsvColumn.label_of(c) for c in columns]
    col_part = "、".join(col_labels)
    col_part_comma = ", ".join(col_labels)

    default_title = f"{chart_prefix} — {col_part_comma} {chart_type}"
    default_output = f"{file_prefix}_{col_part}.png"

    return {
        "chart_prefix": chart_prefix,
        "file_prefix": file_prefix,
        "col_part": col_part,
        "col_part_comma": col_part_comma,
        "default_title": default_title,
        "default_output": default_output,
    }
