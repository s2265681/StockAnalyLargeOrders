"""
MySQL 数据库连接管理
"""
import os
import logging
import pymysql

from utils.env import load_env, getenv

load_env()

logger = logging.getLogger(__name__)

DB_CONFIG = {
    "host": getenv("MYSQL_HOST", "127.0.0.1"),
    "port": int(getenv("MYSQL_PORT", "3306")),
    "user": getenv("MYSQL_USER", "root"),
    "password": getenv("MYSQL_PASSWORD", "123456"),
    "database": getenv("MYSQL_DATABASE", "stock"),
    "charset": "utf8mb4",
    "cursorclass": pymysql.cursors.DictCursor,
}


def get_connection():
    """获取一个新的数据库连接（短连接模式，用完即关）"""
    return pymysql.connect(**DB_CONFIG)


def execute_query(sql, params=None):
    """执行查询，返回结果列表"""
    conn = get_connection()
    try:
        with conn.cursor() as cursor:
            cursor.execute(sql, params)
            return cursor.fetchall()
    finally:
        conn.close()


def execute_write(sql, params=None):
    """执行写入（INSERT/UPDATE/DELETE），返回 affected rows"""
    conn = get_connection()
    try:
        with conn.cursor() as cursor:
            result = cursor.execute(sql, params)
            conn.commit()
            return result
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def execute_insert(sql, params=None):
    """执行 INSERT，返回 lastrowid"""
    conn = get_connection()
    try:
        with conn.cursor() as cursor:
            cursor.execute(sql, params)
            conn.commit()
            return cursor.lastrowid
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def execute_many(sql, params_list):
    """批量写入"""
    if not params_list:
        return 0
    conn = get_connection()
    try:
        with conn.cursor() as cursor:
            result = cursor.executemany(sql, params_list)
            conn.commit()
            return result
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()
