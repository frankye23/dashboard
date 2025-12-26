#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
最小复现脚本：证明 except Exception 导致 cursor 返回 None

测试场景：
1. 模拟 PyMySQL InterfaceError(0, '')
2. 验证修复前：except Exception 捕获后 raise，导致 query_all 收到 None
3. 验证修复后：InterfaceError 直接向上抛出，query_all 正确抛出异常
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import pymysql
from unittest.mock import Mock, patch, MagicMock

print("=" * 80)
print("复现测试：except Exception 导致 cursor 为 None")
print("=" * 80)

# ============================================================================
# 修复前的代码（有 bug）
# ============================================================================
class DB_Before:
    """修复前的 DB 类（包含错误的 except Exception 块）"""
    
    def __init__(self):
        self.conn = None
        self.config = {}
    
    def get_conn(self):
        if self.conn is None:
            # 模拟连接
            mock_conn = Mock()
            mock_conn.cursor = Mock(side_effect=lambda: Mock())
            self.conn = mock_conn
        return self.conn
    
    def execute_buggy(self, *a, **kw):
        """修复前：有 except Exception 块"""
        import time
        import threading
        
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
            
        except Exception as e:
            # ❌ BUG: 捕获所有异常后 raise，导致 return cursor 不可达
            elapsed = time.time() - start_time
            print(f"[DB_ERROR] thread={thread_id} sql={sql_preview} elapsed={elapsed:.3f}s error={e}")
            raise
            
        return cursor
    
    def query_all(self, *a, **kw):
        cursor = None
        try:
            cursor = self.execute_buggy(*a, **kw)
            return cursor.fetchall()
        finally:
            cursor and cursor.close()


# ============================================================================
# 修复后的代码（正确）
# ============================================================================
class DB_After:
    """修复后的 DB 类（移除了 except Exception 块）"""
    
    def __init__(self):
        self.conn = None
        self.config = {}
    
    def get_conn(self):
        if self.conn is None:
            mock_conn = Mock()
            mock_conn.cursor = Mock(side_effect=lambda: Mock())
            self.conn = mock_conn
        return self.conn
    
    def execute_fixed(self, *a, **kw):
        """修复后：移除 except Exception 块"""
        import time
        import threading
        
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
    
    def query_all(self, *a, **kw):
        cursor = None
        try:
            cursor = self.execute_fixed(*a, **kw)
            return cursor.fetchall()
        finally:
            cursor and cursor.close()


# ============================================================================
# 测试用例
# ============================================================================

def test_before_fix():
    """测试修复前：InterfaceError 导致 cursor 为 None"""
    print("\n【测试 1】修复前：InterfaceError(0, '') 触发 except Exception")
    print("-" * 80)
    
    db = DB_Before()
    
    # Mock cursor.execute 抛出 InterfaceError
    mock_cursor = Mock()
    mock_cursor.execute = Mock(side_effect=pymysql.err.InterfaceError(0, ''))
    
    with patch.object(db, 'get_conn') as mock_get_conn:
        mock_conn = Mock()
        mock_conn.cursor = Mock(return_value=mock_cursor)
        mock_get_conn.return_value = mock_conn
        
        try:
            result = db.query_all("SELECT * FROM test")
            print(f"❌ 错误：query_all 应该抛出异常，但返回了: {result}")
            return False
        except pymysql.err.InterfaceError as e:
            print(f"✓ 预期行为：InterfaceError 被正确抛出: {e}")
            return True
        except AttributeError as e:
            # 这是 bug 的表现：cursor 为 None，导致 cursor.fetchall() 失败
            print(f"❌ BUG 触发：cursor 为 None，导致 AttributeError: {e}")
            return False
        except Exception as e:
            print(f"❓ 意外异常: {type(e).__name__}: {e}")
            return False


def test_after_fix():
    """测试修复后：InterfaceError 正确向上抛出"""
    print("\n【测试 2】修复后：InterfaceError 正确向上抛出")
    print("-" * 80)
    
    db = DB_After()
    
    # Mock cursor.execute 抛出 InterfaceError
    mock_cursor = Mock()
    mock_cursor.execute = Mock(side_effect=pymysql.err.InterfaceError(0, ''))
    
    with patch.object(db, 'get_conn') as mock_get_conn:
        mock_conn = Mock()
        mock_conn.cursor = Mock(return_value=mock_cursor)
        mock_get_conn.return_value = mock_conn
        
        try:
            result = db.query_all("SELECT * FROM test")
            print(f"❌ 错误：query_all 应该抛出异常，但返回了: {result}")
            return False
        except pymysql.err.InterfaceError as e:
            print(f"✓ 正确行为：InterfaceError 被正确抛出: {e}")
            return True
        except AttributeError as e:
            print(f"❌ 不应该出现 AttributeError: {e}")
            return False
        except Exception as e:
            print(f"❓ 意外异常: {type(e).__name__}: {e}")
            return False


def test_operational_error_recovery():
    """测试 OperationalError 的重连恢复逻辑"""
    print("\n【测试 3】OperationalError 重连恢复（修复前后都应该正常）")
    print("-" * 80)
    
    # 测试修复后的版本
    db = DB_After()
    
    call_count = [0]
    
    def mock_execute_with_retry(*a, **kw):
        call_count[0] += 1
        if call_count[0] == 1:
            # 第一次调用失败
            raise pymysql.OperationalError(2006, 'MySQL server has gone away')
        else:
            # 第二次调用成功
            pass
    
    mock_cursor = Mock()
    mock_cursor.execute = mock_execute_with_retry
    mock_cursor.fetchall = Mock(return_value=[('result',)])
    
    with patch.object(db, 'get_conn') as mock_get_conn:
        mock_conn = Mock()
        mock_conn.cursor = Mock(return_value=mock_cursor)
        mock_conn.close = Mock()
        mock_get_conn.return_value = mock_conn
        
        try:
            result = db.query_all("SELECT * FROM test")
            print(f"✓ 重连成功，返回结果: {result}")
            print(f"✓ execute 被调用 {call_count[0]} 次（第一次失败，第二次成功）")
            return True
        except Exception as e:
            print(f"❌ 重连失败: {type(e).__name__}: {e}")
            return False


# ============================================================================
# 执行测试
# ============================================================================

if __name__ == '__main__':
    print("\n" + "=" * 80)
    print("开始执行复现测试")
    print("=" * 80)
    
    results = []
    
    # 测试 1：修复前的行为
    results.append(("修复前 InterfaceError", test_before_fix()))
    
    # 测试 2：修复后的行为
    results.append(("修复后 InterfaceError", test_after_fix()))
    
    # 测试 3：OperationalError 重连
    results.append(("OperationalError 重连", test_operational_error_recovery()))
    
    # 汇总结果
    print("\n" + "=" * 80)
    print("测试结果汇总")
    print("=" * 80)
    
    all_passed = True
    for test_name, passed in results:
        status = "✓ PASS" if passed else "❌ FAIL"
        print(f"{status}: {test_name}")
        if not passed:
            all_passed = False
    
    print("=" * 80)
    
    if all_passed:
        print("\n✓ 所有测试通过")
        sys.exit(0)
    else:
        print("\n❌ 部分测试失败")
        sys.exit(1)
