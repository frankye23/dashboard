#!/usr/bin/env python
#-*- coding:utf-8 -*-
"""
日志分析工具 - 分析增强日志找出 504 超时根因

使用方法：
    python analyze_logs.py /path/to/logfile.log
    或者直接传入最近的日志：
    tail -n 10000 /var/log/dashboard.log | python analyze_logs.py -
"""

import sys
import re
from datetime import datetime
from collections import defaultdict

class LogAnalyzer:
    def __init__(self):
        self.http_requests = {}  # request_id -> {start, end, elapsed, method, path}
        self.api_requests = {}   # id -> {start, end, elapsed, method, url, caller}
        self.slow_requests = []
        self.timeouts = []
        self.errors = []
        self.concurrent_peak = 0
        
    def parse_line(self, line):
        """解析日志行"""
        # 提取时间戳
        timestamp_match = re.match(r'(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})', line)
        if not timestamp_match:
            return None
        
        timestamp_str = timestamp_match.group(1)
        try:
            timestamp = datetime.strptime(timestamp_str, '%Y-%m-%d %H:%M:%S')
        except:
            return None
        
        return {
            'timestamp': timestamp,
            'line': line
        }
    
    def analyze_http_start(self, match, timestamp):
        """分析 HTTP 请求开始"""
        request_id = match.group(1)
        method = match.group(2)
        path = match.group(3)
        
        self.http_requests[request_id] = {
            'start': timestamp,
            'method': method,
            'path': path
        }
    
    def analyze_http_end(self, match, timestamp):
        """分析 HTTP 请求结束"""
        request_id = match.group(1)
        status = match.group(4)
        elapsed = float(match.group(5))
        
        if request_id in self.http_requests:
            self.http_requests[request_id]['end'] = timestamp
            self.http_requests[request_id]['status'] = status
            self.http_requests[request_id]['elapsed'] = elapsed
    
    def analyze_req_start(self, match, timestamp):
        """分析 API 请求开始"""
        req_id = match.group(1)
        method = match.group(2)
        url = match.group(3)
        caller = match.group(4)
        active_count = int(match.group(6))
        
        self.api_requests[req_id] = {
            'start': timestamp,
            'method': method,
            'url': url,
            'caller': caller,
            'active_count_start': active_count
        }
        
        # 更新并发峰值
        if active_count > self.concurrent_peak:
            self.concurrent_peak = active_count
    
    def analyze_req_end(self, match, timestamp):
        """分析 API 请求结束"""
        req_id = match.group(1)
        elapsed = float(match.group(2))
        
        if req_id in self.api_requests:
            self.api_requests[req_id]['end'] = timestamp
            self.api_requests[req_id]['elapsed'] = elapsed
    
    def analyze_slow(self, match, timestamp):
        """分析慢请求"""
        req_id = match.group(1)
        elapsed = float(match.group(4))
        caller = match.group(5)
        
        self.slow_requests.append({
            'req_id': req_id,
            'timestamp': timestamp,
            'elapsed': elapsed,
            'caller': caller
        })
    
    def analyze_timeout(self, match, timestamp):
        """分析超时"""
        req_id = match.group(1)
        url = match.group(3)
        elapsed = float(match.group(4))
        
        self.timeouts.append({
            'req_id': req_id,
            'timestamp': timestamp,
            'url': url,
            'elapsed': elapsed
        })
    
    def analyze_file(self, file_handle):
        """分析日志文件"""
        for line in file_handle:
            parsed = self.parse_line(line)
            if not parsed:
                continue
            
            timestamp = parsed['timestamp']
            line = parsed['line']
            
            # HTTP 请求开始
            match = re.search(r'\[HTTP_START\] request_id=(\S+) method=(\S+) path=(\S+)', line)
            if match:
                self.analyze_http_start(match, timestamp)
                continue
            
            # HTTP 请求结束
            match = re.search(r'\[HTTP_END\] request_id=(\S+) method=(\S+) path=(\S+) status=(\S+) elapsed=([\d.]+)s', line)
            if match:
                self.analyze_http_end(match, timestamp)
                continue
            
            # API 请求开始
            match = re.search(r'\[REQ_START\] id=(\d+) method=(\S+) url=(\S+) caller=(\S+) thread=(\S+) active_count=(\d+)', line)
            if match:
                self.analyze_req_start(match, timestamp)
                continue
            
            # API 请求结束
            match = re.search(r'\[REQ_END\] id=(\d+) elapsed=([\d.]+)s', line)
            if match:
                self.analyze_req_end(match, timestamp)
                continue
            
            # 慢请求
            match = re.search(r'\[REQ_SLOW\] id=(\d+) method=(\S+) url=(\S+) elapsed=([\d.]+)s caller=(\S+)', line)
            if match:
                self.analyze_slow(match, timestamp)
                continue
            
            # 超时
            match = re.search(r'\[REQ_TIMEOUT\] id=(\d+) method=(\S+) url=(\S+) elapsed=([\d.]+)s', line)
            if match:
                self.analyze_timeout(match, timestamp)
                continue
    
    def generate_report(self):
        """生成分析报告"""
        print("=" * 70)
        print("日志分析报告")
        print("=" * 70)
        
        # 1. 总体统计
        print("\n【1. 总体统计】")
        print("-" * 70)
        print("HTTP 请求总数: %d" % len(self.http_requests))
        print("API 调用总数: %d" % len(self.api_requests))
        print("慢请求数量: %d" % len(self.slow_requests))
        print("超时数量: %d" % len(self.timeouts))
        print("并发峰值: %d" % self.concurrent_peak)
        
        # 2. HTTP 响应时间分析
        print("\n【2. HTTP 响应时间分析】")
        print("-" * 70)
        http_elapsed = [req['elapsed'] for req in self.http_requests.values() if 'elapsed' in req]
        if http_elapsed:
            print("平均响应时间: %.3fs" % (sum(http_elapsed) / len(http_elapsed)))
            print("最大响应时间: %.3fs" % max(http_elapsed))
            print("最小响应时间: %.3fs" % min(http_elapsed))
            
            # 找出最慢的 HTTP 请求
            slow_http = sorted(
                [(req_id, req) for req_id, req in self.http_requests.items() if 'elapsed' in req],
                key=lambda x: x[1]['elapsed'],
                reverse=True
            )[:10]
            
            print("\n最慢的 10 个 HTTP 请求:")
            for req_id, req in slow_http:
                print("  %.3fs - %s %s (status=%s)" % (
                    req['elapsed'], req['method'], req['path'], req.get('status', 'unknown')
                ))
        
        # 3. API 调用分析
        print("\n【3. API 调用响应时间分析】")
        print("-" * 70)
        api_elapsed = [req['elapsed'] for req in self.api_requests.values() if 'elapsed' in req]
        if api_elapsed:
            print("API 调用平均时间: %.3fs" % (sum(api_elapsed) / len(api_elapsed)))
            print("API 调用最大时间: %.3fs" % max(api_elapsed))
            
            # 按 URL 分组统计
            url_stats = defaultdict(lambda: {'count': 0, 'total': 0, 'max': 0})
            for req in self.api_requests.values():
                if 'elapsed' in req:
                    url = req['url']
                    url_stats[url]['count'] += 1
                    url_stats[url]['total'] += req['elapsed']
                    url_stats[url]['max'] = max(url_stats[url]['max'], req['elapsed'])
            
            print("\n按 API 端点统计 (Top 10):")
            sorted_urls = sorted(
                url_stats.items(),
                key=lambda x: x[1]['total'],
                reverse=True
            )[:10]
            
            for url, stats in sorted_urls:
                avg = stats['total'] / stats['count']
                print("  %s" % url)
                print("    调用次数: %d, 平均: %.3fs, 最大: %.3fs, 总计: %.3fs" % (
                    stats['count'], avg, stats['max'], stats['total']
                ))
        
        # 4. 慢请求详情
        if self.slow_requests:
            print("\n【4. 慢请求详情 (>2s)】")
            print("-" * 70)
            for req in sorted(self.slow_requests, key=lambda x: x['elapsed'], reverse=True)[:20]:
                print("  [%s] 耗时: %.3fs" % (req['timestamp'].strftime('%H:%M:%S'), req['elapsed']))
                print("    调用者: %s" % req['caller'])
                if req['req_id'] in self.api_requests:
                    api_req = self.api_requests[req['req_id']]
                    print("    URL: %s" % api_req.get('url', 'unknown'))
                print()
        
        # 5. 超时详情
        if self.timeouts:
            print("\n【5. 超时详情】")
            print("-" * 70)
            for req in self.timeouts:
                print("  [%s] 超时 URL: %s (等待: %.3fs)" % (
                    req['timestamp'].strftime('%H:%M:%S'),
                    req['url'],
                    req['elapsed']
                ))
        
        # 6. 并发情况分析
        print("\n【6. 并发情况分析】")
        print("-" * 70)
        active_counts = [req['active_count_start'] for req in self.api_requests.values() 
                        if 'active_count_start' in req]
        if active_counts:
            print("平均并发: %.1f" % (sum(active_counts) / len(active_counts)))
            print("最大并发: %d" % max(active_counts))
            
            # 统计并发分布
            from collections import Counter
            count_dist = Counter(active_counts)
            print("\n并发分布:")
            for count in sorted(count_dist.keys()):
                print("  并发=%d: %d 次 (%s)" % (
                    count, 
                    count_dist[count],
                    '#' * min(50, count_dist[count] // 10)
                ))
        
        # 7. 关键发现
        print("\n【7. 关键发现与建议】")
        print("-" * 70)
        
        findings = []
        
        if self.timeouts:
            findings.append("⚠️  发现 %d 次超时，说明后端 API 无响应" % len(self.timeouts))
        
        if self.concurrent_peak > 5:
            findings.append("⚠️  并发峰值达到 %d，超过单线程处理能力" % self.concurrent_peak)
        
        if api_elapsed and max(api_elapsed) > 10:
            findings.append("⚠️  发现超长 API 调用 (%.3fs)，可能导致阻塞" % max(api_elapsed))
        
        slow_callers = defaultdict(int)
        for req in self.slow_requests:
            slow_callers[req['caller']] += 1
        if slow_callers:
            top_caller = max(slow_callers.items(), key=lambda x: x[1])
            findings.append("⚠️  最慢的调用点: %s (%d 次)" % top_caller)
        
        if findings:
            for finding in findings:
                print(finding)
        else:
            print("✓ 未发现明显异常")
        
        print("\n建议:")
        print("1. 如果看到大量超时，检查后端 API (127.0.0.1:31132) 的健康状态")
        print("2. 如果并发峰值 > 1，说明单线程无法处理，需要启用 threaded=True")
        print("3. 如果某个 API 调用特别慢，考虑加缓存或优化该接口")
        print("4. 添加 timeout 参数到所有 requests 调用，避免永久挂起")
        
        print("\n" + "=" * 70)


def main():
    if len(sys.argv) > 1 and sys.argv[1] != '-':
        # 从文件读取
        with open(sys.argv[1], 'r') as f:
            analyzer = LogAnalyzer()
            analyzer.analyze_file(f)
            analyzer.generate_report()
    else:
        # 从 stdin 读取
        analyzer = LogAnalyzer()
        analyzer.analyze_file(sys.stdin)
        analyzer.generate_report()


if __name__ == "__main__":
    main()
