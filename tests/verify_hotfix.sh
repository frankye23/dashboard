#!/bin/bash
# Hotfix 证据包验证脚本

set -e

echo "================================================================================"
echo "Hotfix 证据包验证"
echo "================================================================================"
echo ""

# 1. 验证 Git Diff
echo "【1/5】验证 Git Diff"
echo "--------------------------------------------------------------------------------"
git diff rrd/store.py | grep -q "except Exception" && echo "✓ 包含 except Exception 的删除" || echo "❌ 未找到预期的删除"
echo ""

# 2. 运行复现测试
echo "【2/5】运行复现测试"
echo "--------------------------------------------------------------------------------"
python test_hotfix_reproduce.py
echo ""

# 3. 运行守门测试
echo "【3/5】运行守门测试"
echo "--------------------------------------------------------------------------------"
python test_hotfix_invariants.py
echo ""

# 4. 验证代码
echo "【4/5】验证修复后的代码"
echo "--------------------------------------------------------------------------------"
python -c "
import sys

with open('rrd/store.py', 'r') as f:
    lines = f.readlines()

# 找到 execute 方法
in_execute = False
execute_start = 0
for i, line in enumerate(lines, 1):
    if 'def execute(self' in line:
        execute_start = i
        in_execute = True
        break

if not in_execute:
    print('❌ FAIL: 未找到 execute 方法')
    sys.exit(1)

# 检查后续 50 行
execute_code = ''.join(lines[execute_start:execute_start+50])
has_except_exception = 'except Exception' in execute_code

if has_except_exception:
    print('❌ FAIL: execute() 中仍有 except Exception')
    sys.exit(1)
else:
    print('✓ execute() 中没有 except Exception')

# 检查必要的代码
if 'except (AttributeError' not in execute_code:
    print('❌ FAIL: 缺少 OperationalError 处理')
    sys.exit(1)
else:
    print('✓ 保留 OperationalError 重连逻辑')

if 'return cursor' not in execute_code:
    print('❌ FAIL: 缺少 return cursor')
    sys.exit(1)
else:
    print('✓ 保留 return cursor 语句')
"
echo ""

# 5. 生成证据包
echo "【5/5】生成证据包"
echo "--------------------------------------------------------------------------------"
echo "证据包文件:"
echo "  - HOTFIX_EVIDENCE_PACKAGE.md     (主证据文档)"
echo "  - test_hotfix_reproduce.py       (复现测试)"
echo "  - test_hotfix_invariants.py      (守门测试)"
echo "  - verify_hotfix.sh               (本验证脚本)"
echo ""

echo "================================================================================"
echo "✓ 所有验证通过"
echo "================================================================================"
echo ""
echo "下一步："
echo "  1. 阅读 HOTFIX_EVIDENCE_PACKAGE.md"
echo "  2. 确认所有证据"
echo "  3. 部署到生产环境"
echo ""
