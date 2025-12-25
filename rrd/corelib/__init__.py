#-*- coding:utf-8 -*-
# Copyright 2017 Xiaomi, Inc.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.


import requests
import json
import time
import logging
import threading

# 用于追踪活跃请求
_active_requests = {}
_active_requests_lock = threading.Lock()
_request_counter = 0
_request_counter_lock = threading.Lock()

def auth_requests(method, *args, **kwargs):
    from flask import g
    import time
    import traceback

    # 生成请求ID
    global _request_counter
    with _request_counter_lock:
        _request_counter += 1
        request_id = _request_counter

    # 获取调用栈信息
    stack = traceback.extract_stack()
    caller = "unknown"
    for frame in reversed(stack[:-1]):  # 倒序找调用者
        if 'rrd/' in frame.filename and '__init__.py' not in frame.filename:
            caller = "%s:%s:%s" % (frame.filename.split('rrd/')[-1], frame.lineno, frame.name)
            break

    # 记录请求开始
    start_time = time.time()
    url = args[0] if args else kwargs.get('url', 'unknown')

    with _active_requests_lock:
        active_count = len(_active_requests)
        _active_requests[request_id] = {
            'method': method,
            'url': url,
            'start': start_time,
            'caller': caller,
            'thread': threading.current_thread().name
        }

    logging.warning(
        "[REQ_START] id=%d method=%s url=%s caller=%s thread=%s active_count=%d",
        request_id, method, url, caller, threading.current_thread().name, active_count
    )

    if not g.user_token:
        logging.error("[REQ_ERROR] id=%d error=no_api_token", request_id)
        raise Exception("no api token")

    headers = {
        "Apitoken": json.dumps({"name":g.user_token.name, "sig":g.user_token.sig})
    }

    if not kwargs:
        kwargs = {}

    if "headers" in kwargs:
        headers.update(kwargs["headers"])
        del kwargs["headers"]

    # 执行请求
    response = None
    try:
        if method == "POST":
            response = requests.post(*args, headers=headers, **kwargs)
        elif method == "GET":
            response = requests.get(*args, headers=headers, **kwargs)
        elif method == "PUT":
            response = requests.put(*args, headers=headers, **kwargs)
        elif method == "DELETE":
            response = requests.delete(*args, headers=headers, **kwargs)
        else:
            raise Exception("invalid http method")

        # 记录响应
        elapsed = time.time() - start_time
        logging.warning(
            "[REQ_SUCCESS] id=%d method=%s url=%s status=%d elapsed=%.3fs",
            request_id, method, url, response.status_code, elapsed
        )

        if elapsed > 2.0:
            logging.error(
                "[REQ_SLOW] id=%d method=%s url=%s elapsed=%.3fs caller=%s",
                request_id, method, url, elapsed, caller
            )

        return response

    except requests.exceptions.Timeout as e:
        elapsed = time.time() - start_time
        logging.error(
            "[REQ_TIMEOUT] id=%d method=%s url=%s elapsed=%.3fs caller=%s error=%s",
            request_id, method, url, elapsed, caller, str(e)
        )
        raise

    except requests.exceptions.ConnectionError as e:
        elapsed = time.time() - start_time
        logging.error(
            "[REQ_CONN_ERROR] id=%d method=%s url=%s elapsed=%.3fs caller=%s error=%s",
            request_id, method, url, elapsed, caller, str(e)
        )
        raise

    except Exception as e:
        elapsed = time.time() - start_time
        logging.error(
            "[REQ_EXCEPTION] id=%d method=%s url=%s elapsed=%.3fs caller=%s error=%s",
            request_id, method, url, elapsed, caller, str(e)
        )
        raise

    finally:
        with _active_requests_lock:
            if request_id in _active_requests:
                del _active_requests[request_id]
            active_count = len(_active_requests)

        elapsed = time.time() - start_time
        logging.warning(
            "[REQ_END] id=%d elapsed=%.3fs active_count=%d",
            request_id, elapsed, active_count
        )

