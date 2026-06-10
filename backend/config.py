"""全局配置，全部从环境变量读取"""

import os

ROOT_DIR = os.environ.get("ROOT_DIR", "/home/harry")
CONFIG_DIR = os.path.join(ROOT_DIR, "config")
SESSION_DIR = os.path.join(ROOT_DIR, "sessions")

USERS_FILE = os.path.join(CONFIG_DIR, "users.txt")
STOCK_FILE = os.path.join(CONFIG_DIR, "ah_stock_map.csv")
PREMIUM_FILE = os.path.join(CONFIG_DIR, "ah_alarmRate.csv")

MAX_ATTEMPTS = 5
LOCKOUT_MINUTES = 30
SESSION_GC_INTERVAL = 300
