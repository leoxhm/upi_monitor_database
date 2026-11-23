"""提供 SQLite 数据库连接。"""

import sqlite3
from contextlib import contextmanager
from pathlib import Path


# 数据库文件路径。运行时自动创建文件，无需先安装数据库服务。
DB_PATH = Path(__file__).with_name("demo.db")

@contextmanager
def get_connection(db_path=DB_PATH):
    """提供连接，正常结束提交事务，异常时回滚，最后关闭连接。"""
    conn = sqlite3.connect(db_path, timeout=30)
    conn.row_factory = sqlite3.Row
    try:
        conn.execute("PRAGMA foreign_keys = ON")
        with conn:
            yield conn
    finally:
        conn.close()
