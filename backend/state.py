"""全局内存状态，供各模块共享"""

users = {}           # username -> {salt, hash}
unlock_code = None   # {salt, hash}
failed_attempts = {}  # username -> {count, first_time, lockout_until}
ip_attempts = {}      # ip -> {count, first_time}
