# -*- coding: utf-8 -*-
import logging
import os

_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_log_path = os.path.join(_root, 'rst.log')

# Truncate if over 1 MB
_MAX_LOG_BYTES = 512 * 1024
try:
    if os.path.exists(_log_path) and os.path.getsize(_log_path) > _MAX_LOG_BYTES:
        open(_log_path, 'w').close()
except Exception:
    pass

try:
    _handler = logging.FileHandler(_log_path, encoding='utf-8')
except TypeError:
    # IronPython may not support encoding param on FileHandler
    _handler = logging.FileHandler(_log_path)

_handler.setFormatter(logging.Formatter(
    '%(asctime)s  %(levelname)-7s  %(name)s  %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
))

def get_logger(name):
    logger = logging.getLogger('rst.' + name)
    if not logger.handlers:
        logger.addHandler(_handler)
        logger.setLevel(logging.DEBUG)
    return logger
