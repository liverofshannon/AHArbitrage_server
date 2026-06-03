#!/usr/bin/env python3
"""生成用户密码行，追加到 users.txt 即可"""

import hashlib
import secrets
import sys

USERS_FILE = "users.txt"

def gen(user, password):
    salt = secrets.token_hex(16)
    h = hashlib.sha256(f"{user}:{password}:{salt}".encode()).hexdigest()
    return f"{user}:{salt}:{h}"

if __name__ == "__main__":
    if len(sys.argv) == 3:
        print(gen(sys.argv[1], sys.argv[2]))
    else:
        user = input("用户名: ").strip()
        password = input("密码: ").strip()
        if not user or not password:
            print("用户名和密码不能为空", file=sys.stderr)
            sys.exit(1)
        line = gen(user, password)
        print()
        print(line)
