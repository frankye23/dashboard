#-*- coding:utf-8 -*-
"""
PyMySQL 兼容层 - 使 PyMySQL 伪装成 MySQLdb
用于替换 mysql-python (仅支持 Python 2)
"""
import pymysql
pymysql.install_as_MySQLdb()
