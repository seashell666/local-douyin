# -*- coding: utf-8 -*-
"""
A/B 测试框架
- 创建A/B测试（两个算法版本）
- 基于user_id哈希确定性分配变量
- 提供当前用户的活动变量
- 指标对比复用 metrics.compare_algorithms
"""
import hashlib
import json
import time
from typing import Optional, Tuple

AB_TEST_KEY = "active_ab_test"


def _get_conn(db_path: str):
    import sqlite3
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    return conn


def _ensure_table(conn):
    conn.execute("""CREATE TABLE IF NOT EXISTS ab_tests (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL,
        version_a TEXT NOT NULL,
        version_b TEXT NOT NULL,
        status TEXT DEFAULT 'running',
        created_at INTEGER,
        ended_at INTEGER
    )""")
    conn.commit()


def create_ab_test(db_path: str, name: str, version_a: str, version_b: str) -> dict:
    """创建A/B测试"""
    conn = _get_conn(db_path)
    _ensure_table(conn)
    now = int(time.time())
    # 结束之前运行的测试
    conn.execute("UPDATE ab_tests SET status='ended', ended_at=? WHERE status='running'", (now,))
    conn.execute(
        "INSERT INTO ab_tests (name, version_a, version_b, status, created_at) VALUES (?,?,?,'running',?)",
        (name, version_a, version_b, now)
    )
    conn.commit()
    test_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
    conn.close()
    return {"id": test_id, "name": name, "version_a": version_a, "version_b": version_b, "status": "running"}


def get_active_ab_test(db_path: str) -> Optional[dict]:
    """获取当前运行的A/B测试"""
    conn = _get_conn(db_path)
    _ensure_table(conn)
    row = conn.execute("SELECT * FROM ab_tests WHERE status='running' ORDER BY id DESC LIMIT 1").fetchone()
    conn.close()
    if row:
        return dict(row)
    return None


def assign_variant(user_id: str, version_a: str, version_b: str) -> Tuple[str, str]:
    """基于user_id哈希确定性分配变量，返回 (variant_name, version)"""
    h = int(hashlib.md5(user_id.encode()).hexdigest(), 16)
    if h % 2 == 0:
        return ("A", version_a)
    else:
        return ("B", version_b)


def get_user_variant(db_path: str, user_id: str = "local") -> Optional[dict]:
    """获取当前用户在活动A/B测试中的分配"""
    test = get_active_ab_test(db_path)
    if not test:
        return None
    variant, version = assign_variant(user_id, test["version_a"], test["version_b"])
    return {"test_id": test["id"], "test_name": test["name"],
            "variant": variant, "assigned_version": version,
            "version_a": test["version_a"], "version_b": test["version_b"]}


def end_ab_test(db_path: str, test_id: int) -> dict:
    """结束A/B测试"""
    conn = _get_conn(db_path)
    _ensure_table(conn)
    now = int(time.time())
    conn.execute("UPDATE ab_tests SET status='ended', ended_at=? WHERE id=?", (now, test_id))
    conn.commit()
    conn.close()
    return {"id": test_id, "status": "ended"}


def list_ab_tests(db_path: str, limit: int = 20) -> list:
    """列出A/B测试历史"""
    conn = _get_conn(db_path)
    _ensure_table(conn)
    rows = conn.execute("SELECT * FROM ab_tests ORDER BY id DESC LIMIT ?", (limit,)).fetchall()
    conn.close()
    return [dict(r) for r in rows]
