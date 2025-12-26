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

# PyMySQL 兼容层 - 必须在所有导入之前
import pymysql
pymysql.install_as_MySQLdb()

import os
import traceback
import logging
from flask import Flask, request
from flask_babel import Babel, gettext
from rrd import config

#-- create app --
app = Flask(__name__)
app.config.from_object("rrd.config")
babel = Babel(app)

import time
from flask import request, g

@app.before_request
def before_request():
    g.request_start_time = time.time()
    g.request_id = id(request)
    
    logging.warning(
        "[HTTP_START] request_id=%s method=%s path=%s remote_addr=%s",
        g.request_id, request.method, request.path, request.remote_addr
    )

@app.after_request
def after_request(response):
    if hasattr(g, 'request_start_time'):
        elapsed = time.time() - g.request_start_time
        
        logging.warning(
            "[HTTP_END] request_id=%s method=%s path=%s status=%s elapsed=%.3fs",
            g.request_id, request.method, request.path, response.status_code, elapsed
        )
        
        # 如果响应慢，记录警告
        if elapsed > 5.0:
            logging.error(
                "[HTTP_SLOW] request_id=%s method=%s path=%s elapsed=%.3fs",
                g.request_id, request.method, request.path, elapsed
            )
    
    return response

@app.errorhandler(Exception)
def all_exception_handler(error):
    # 【止血修复】确保异常路径也记录请求耗时，用于诊断
    if hasattr(g, 'request_start_time'):
        elapsed = time.time() - g.request_start_time
        logging.error(
            "[HTTP_EXCEPTION] request_id=%s method=%s path=%s elapsed=%.3fs error=%s",
            getattr(g, 'request_id', 'unknown'), request.method, request.path, elapsed, str(error)
        )
    else:
        logging.error(
            "[HTTP_EXCEPTION] method=%s path=%s error=%s",
            request.method, request.path, str(error)
        )
    
    if not config.DEBUG:
        tb = traceback.format_exc()
        err_tip = gettext('Temporary error, please contact your administrator.')
        err_msg = err_tip + '\n\nError: %s\n\nTraceback:\n%s' %(error, tb)
        return '<pre>' + err_msg + '</pre>', 500
    else:
        raise
    
@babel.localeselector
def get_locale():
    return request.accept_languages.best_match(config.LANGUAGES.keys())

@babel.timezoneselector
def get_timezone():
    return app.config.get("BABEL_DEFAULT_TIMEZONE")

from .view import index
from .view.auth import auth
from .view.user import user
from .view.team import team
from .view.dashboard import chart, screen
from .view.portal import *
