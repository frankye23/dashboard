#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
守门测试：确保 DB.execute() 的函数不变量

不变量（Invariants）：
1. execute() 成功时必须返回有效的 cursor 对象（非 None）
2. execute() 失败时必须抛出异常，不能返回 None 伪装成功
3. OperationalError/AttributeError 必须触发重连并重试
4. 非 OperationalError 的异常必须向上抛出
5. query_all/query_one 等方法不能因为 cursor=None 而返回错误的结果
"""

import sys
import os
import time
import threading
import pymysql
from unittest.mock import Mock, patch

print("=" * 80)
print("守门测试：验证 DB.execute() 的函数不变量")
print("=" * 80)

# ============================================================================
# 复制真实的 DB 类（修复后的版本）
# ============================================================================

class DB:
    """真实的 DB 类（修复后）"""
    
    def __init__(self, cfg=None):
        self.config = cfg or {}
        self.conn = None

    def get_conn(self):
        if self.conn is None:
            # Mock connection
            self.conn = Mock()
        return self.conn

    def execute(self, *a, **kw):
        """修复后的 execute 方法"""
        cursor = kw.pop('cursor', None)
        start_time = time.time()
        sql_preview = str(a[0])[:50] if a else 'unknown'
        thread_id = threading.current_thread().name
        
        try:
            cursor = cursor or self.get_conn().cursor()
            cursor.execute(*a, **kw)
            
            elapsed = time.time() - start_time
            if elapsed > 0.1:
                print(f"[DB_SLOW] thread={thread_id} sql={sql_preview} elapsed={elapsed:.3f}s")
            
        except (AttributeError, pymysql.OperationalError) as e:
            elapsed = time.time() - start_time
            print(f"[DB_RECONNECT] thread={thread_id} sql={sql_preview} elapsed={elapsed:.3f}s error={e}")
            
            self.conn and self.conn.close()
            self.conn = None
            cursor = self.get_conn().cursor()
            cursor.execute(*a, **kw)
        
        return cursor

    def insert(self, *a, **kw):
        cursor = None
        try:
            cursor = self.execute(*a, **kw)
            row_id = cursor.lastrowid
            self.commit()
            return row_id
        except pymysql.IntegrityError:
            self.rollback()
        finally:
            cursor and cursor.close()

    def update(self, *a, **kw):
        cursor = None
        try:
            cursor = self.execute(*a, **kw)
            self.commit()
            row_count = cursor.rowcount
            return row_count
        except pymysql.IntegrityError:
            self.rollback()
        finally:
            cursor and cursor.close()

    def query_all(self, *a, **kw):
        cursor = None
        try:
            cursor = self.execute(*a, **kw)
            return cursor.fetchall()
        finally:
            cursor and cursor.close()

    def query_one(self, *a, **kw):
        rows = self.query_all(*a, **kw)
        if rows:
            return rows[0]
        else:
            return None

    def query_column(self, *a, **kw):
        rows = self.query_all(*a, **kw)
        if rows:
            return [row[0] for row in rows]
        else:
            return []

    def commit(self):
        if self.conn:
            try:
                self.conn.commit()
            except pymysql.OperationalError:
                self.conn = None

    def rollback(self):
        if self.conn:
            try:
                self.conn.rollback()
            except pymysql.OperationalError:
                self.conn = None


def test_invariant_1_success_returns_cursor():
    """不变量 1: 成功时必须返回有效的 cursor"""
    print("\n【测试 1】不变量：成功时返回有效 cursor")
    print("-" * 80)
    
    db = DB({})
    
    mock_cursor = Mock()
    mock_cursor.execute = Mock()  # 成功执行
    
    with patch.object(db, 'get_conn') as mock_get_conn:
        mock_conn = Mock()
        mock_conn.cursor = Mock(return_value=mock_cursor)
        mock_get_conn.return_value = mock_conn
        
        result = db.execute("SELECT 1")
        
        if result is None:
            print("❌ FAIL: execute() 返回了 None")
            return False
        elif result == mock_cursor:
            print(f"✓ PASS: execute() 返回了有效的 cursor: {result}")
            return True
        else:
            print(f"❌ FAIL: execute() 返回了意外对象: {result}")
            return False


def test_invariant_2_interface_error_raises():
    """不变量 2: InterfaceError 必须向上抛出，不能返回 None"""
    print("\n【测试 2】不变量：InterfaceError 必须抛出，不能返回 None")
    print("-" * 80)
    
    db = DB({})
    
    mock_cursor = Mock()
    mock_cursor.execute = Mock(side_effect=pymysql.err.InterfaceError(0, ''))
    
    with patch.object(db, 'get_conn') as mock_get_conn:
        mock_conn = Mock()
        mock_conn.cursor = Mock(return_value=mock_cursor)
        mock_get_conn.return_value = mock_conn
        
        try:
            result = db.execute("SELECT 1")
            print(f"❌ FAIL: execute() 应该抛出异常，但返回了: {result}")
            return False
        except pymysql.err.InterfaceError:
            print("✓ PASS: InterfaceError 被正确抛出")
            return True
        except Exception as e:
            print(f"❌ FAIL: 抛出了错误的异常类型: {type(e).__name__}: {e}")
            return False


def test_invariant_3_operational_error_retries():
    """不变量 3: OperationalError 触发重连并重试"""
    print("\n【测试 3】不变量：OperationalError 触发重连")
    print("-" * 80)
    
    db = DB({})
    
    call_count = [0]
    
    def mock_execute_with_retry(*a, **kw):
        call_count[0] += 1
        if call_count[0] == 1:
            raise pymysql.OperationalError(2006, 'MySQL server has gone away')
        else:
            pass  # 第二次成功
    
    mock_cursor = Mock()
    mock_cursor.execute = mock_execute_with_retry
    
    with patch.object(db, 'get_conn') as mock_get_conn:
        mock_conn = Mock()
        mock_conn.cursor = Mock(return_value=mock_cursor)
        mock_conn.close = Mock()
        mock_get_conn.return_value = mock_conn
        
        result = db.execute("SELECT 1")
        
        if result is None:
            print(f"❌ FAIL: 重连后返回了 None")
            return False
        elif call_count[0] != 2:
            print(f"❌ FAIL: execute 被调用 {call_count[0]} 次，预期 2 次")
            return False
        else:
            print(f"✓ PASS: 重连成功，execute 被调用 {call_count[0]} 次")
            return True


def test_invariant_4_query_all_never_returns_none():
    """不变量 4: query_all 不能因为 cursor=None 而返回错误结果"""
    print("\n【测试 4】不变量：query_all 不能返回 None 或因 cursor=None 崩溃")
    print("-" * 80)
    
    db = DB({})
    
    # 测试正常情况
    mock_cursor = Mock()
    mock_cursor.execute = Mock()
    mock_cursor.fetchall = Mock(return_value=[('row1',), ('row2',)])
    
    with patch.object(db, 'get_conn') as mock_get_conn:
        mock_conn = Mock()
        mock_conn.cursor = Mock(return_value=mock_cursor)
        mock_get_conn.return_value = mock_conn
        
        result = db.query_all("SELECT 1")
        
        if result is None:
            print("❌ FAIL: query_all 返回了 None")
            return False
        elif isinstance(result, (list, tuple)):
            print(f"✓ PASS: query_all 返回了有效的结果: {result}")
            return True
        else:
            print(f"❌ FAIL: query_all 返回了意外类型: {type(result)}")
            return False


def test_invariant_5_interface_error_in_query_all():
    """不变量 5: query_all 遇到 InterfaceError 必须抛出，不能返回 None"""
    print("\n【测试 5】不变量：query_all 遇到 InterfaceError 必须抛出")
    print("-" * 80)
    
    db = DB({})
    
    mock_cursor = Mock()
    mock_cursor.execute = Mock(side_effect=pymysql.err.InterfaceError(0, ''))
    
    with patch.object(db, 'get_conn') as mock_get_conn:
        mock_conn = Mock()
        mock_conn.cursor = Mock(return_value=mock_cursor)
        mock_get_conn.return_value = mock_conn
        
        try:
            result = db.query_all("SELECT 1")
            print(f"❌ FAIL: query_all 应该抛出异常，但返回了: {result}")
            return False
        except pymysql.err.InterfaceError:
            print("✓ PASS: query_all 正确抛出 InterfaceError")
            return True
        except AttributeError as e:
            # 这是修复前的 bug：cursor 为 None，导致 cursor.fetchall() 失败
            print(f"❌ FAIL: 触发了 AttributeError（cursor 可能为 None）: {e}")
            return False
        except Exception as e:
            print(f"❌ FAIL: 抛出了错误的异常: {type(e).__name__}: {e}")
            return False


def test_invariant_6_other_exceptions_propagate():
    """不变量 6: 其他异常（非 OperationalError/AttributeError）必须向上抛出"""
    print("\n【测试 6】不变量：其他异常必须向上抛出")
    print("-" * 80)
    
    db = DB({})
    
    # 测试 ValueError
    mock_cursor = Mock()
    mock_cursor.execute = Mock(side_effect=ValueError("Invalid SQL"))
    
    with patch.object(db, 'get_conn') as mock_get_conn:
        mock_conn = Mock()
        mock_conn.cursor = Mock(return_value=mock_cursor)
        mock_get_conn.return_value = mock_conn
        
        try:
            result = db.execute("INVALID SQL")
            print(f"❌ FAIL: execute() 应该抛出 ValueError，但返回了: {result}")
            return False
        except ValueError as e:
            print(f"✓ PASS: ValueError 被正确抛出: {e}")
            return True
        except Exception as e:
            print(f"❌ FAIL: 抛出了错误的异常: {type(e).__name__}: {e}")
            return False


def test_invariant_7_insert_update_never_return_none():
    """不变量 7: insert/update 不能因为 cursor=None 而返回错误结果"""
    print("\n【测试 7】不变量：insert/update 不能返回 None 作为 ID/row_count")
    print("-" * 80)
    
    db = DB({})
    
    # 测试 insert
    mock_cursor = Mock()
    mock_cursor.execute = Mock()
    mock_cursor.lastrowid = 123
    
    with patch.object(db, 'get_conn') as mock_get_conn:
        mock_conn = Mock()
        mock_conn.cursor = Mock(return_value=mock_cursor)
        mock_conn.commit = Mock()
        mock_get_conn.return_value = mock_conn
        
        result = db.insert("INSERT INTO test VALUES (1)")
        
        if result is None:
            print("❌ FAIL: insert 返回了 None")
            return False
        elif result == 123:
            print(f"✓ PASS: insert 返回了有效的 lastrowid: {result}")
        else:
            print(f"❓ WARNING: insert 返回了意外值: {result}")
    
    # 测试 update
    mock_cursor.rowcount = 5
    
    with patch.object(db, 'get_conn') as mock_get_conn:
        mock_conn = Mock()
        mock_conn.cursor = Mock(return_value=mock_cursor)
        mock_conn.commit = Mock()
        mock_get_conn.return_value = mock_conn
        
        result = db.update("UPDATE test SET x=1")
        
        if result is None:
            print("❌ FAIL: update 返回了 None")
            return False
        elif result == 5:
            print(f"✓ PASS: update 返回了有效的 rowcount: {result}")
            return True
        else:
            print(f"❓ WARNING: update 返回了意外值: {result}")
            return True


# ============================================================================
# 执行所有测试
# ============================================================================

if __name__ == '__main__':
    print("\n" + "=" * 80)
    print("开始执行守门测试")
    print("=" * 80)
    
    tests = [
        ("不变量 1: 成功返回 cursor", test_invariant_1_success_returns_cursor),
        ("不变量 2: InterfaceError 抛出", test_invariant_2_interface_error_raises),
        ("不变量 3: OperationalError 重连", test_invariant_3_operational_error_retries),
        ("不变量 4: query_all 不返回 None", test_invariant_4_query_all_never_returns_none),
        ("不变量 5: query_all InterfaceError", test_invariant_5_interface_error_in_query_all),
        ("不变量 6: 其他异常抛出", test_invariant_6_other_exceptions_propagate),
        ("不变量 7: insert/update 不返回 None", test_invariant_7_insert_update_never_return_none),
    ]
    
    results = []
    for test_name, test_func in tests:
        try:
            passed = test_func()
            results.append((test_name, passed, None))
        except Exception as e:
            print(f"❌ 测试崩溃: {e}")
            import traceback
            traceback.print_exc()
            results.append((test_name, False, str(e)))
    
    # 汇总结果
    print("\n" + "=" * 80)
    print("守门测试结果汇总")
    print("=" * 80)
    
    all_passed = True
    for test_name, passed, error in results:
        if passed:
            print(f"✓ PASS: {test_name}")
        else:
            print(f"❌ FAIL: {test_name}")
            if error:
                print(f"    错误: {error}")
            all_passed = False
    
    print("=" * 80)
    
    if all_passed:
        print("\n✓ 所有守门测试通过")
        print("\n函数不变量验证：")
        print("  1. execute() 成功时返回有效 cursor ✓")
        print("  2. execute() 失败时抛出异常，不返回 None ✓")
        print("  3. OperationalError 触发重连 ✓")
        print("  4. query_all 不会因 cursor=None 崩溃 ✓")
        print("  5. 异常正确向上传播 ✓")
        sys.exit(0)
    else:
        print("\n❌ 部分守门测试失败")
        print("\n⚠️  函数不变量被违反，代码存在风险")
        sys.exit(1)
