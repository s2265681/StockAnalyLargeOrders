#!/usr/bin/env python3
"""创建 / 提升超级管理员账号（role=admin，不受会员限制）。

用法（在 backend 目录下，用项目 venv 执行）：
    ./venv/bin/python scripts/create_admin.py <用户名> [密码]

说明：
  - 用户不存在   -> 新建，role=admin
  - 用户已存在   -> 就地提升为 admin（可同时重置密码，若提供了密码）
  - admin 账号由后端 /api/user/profile 返回永不过期 VIP，
    因此 web 与小程序的会员限制自动全部解除，无需改前端。
"""
import sys
import os

# 允许从 backend/ 直接运行时导入项目模块
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from werkzeug.security import generate_password_hash
from utils.db import execute_query, execute_write, execute_insert


def main():
    if len(sys.argv) < 2:
        print('用法: python scripts/create_admin.py <用户名> [密码]')
        sys.exit(1)

    username = sys.argv[1].strip()
    password = sys.argv[2] if len(sys.argv) > 2 else None

    existing = execute_query(
        'SELECT id, role FROM users WHERE username = %s', (username,)
    )

    if existing:
        uid = existing[0]['id']
        if password:
            pw_hash = generate_password_hash(password, method='pbkdf2:sha256')
            execute_write(
                'UPDATE users SET role = %s, password_hash = %s WHERE id = %s',
                ('admin', pw_hash, uid),
            )
            print(f'✅ 已将用户 {username}(id={uid}) 提升为 admin，并重置密码')
        else:
            execute_write(
                'UPDATE users SET role = %s WHERE id = %s', ('admin', uid)
            )
            print(f'✅ 已将用户 {username}(id={uid}) 提升为 admin（密码未改动）')
        return

    if not password:
        print('❌ 新建账号必须提供密码：python scripts/create_admin.py <用户名> <密码>')
        sys.exit(1)
    if len(password) < 6:
        print('❌ 密码至少 6 个字符')
        sys.exit(1)

    pw_hash = generate_password_hash(password, method='pbkdf2:sha256')
    uid = execute_insert(
        'INSERT INTO users (username, password_hash, role) VALUES (%s, %s, %s)',
        (username, pw_hash, 'admin'),
    )
    print(f'✅ 已创建超级管理员 {username}(id={uid})，可用账号密码登录，无会员限制')


if __name__ == '__main__':
    main()
