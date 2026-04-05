# -*- coding: utf-8 -*-
import logging
import os

_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_log_path = os.path.join(_root, 'rester.log')

_handler = logging.FileHandler(_log_path, encoding='utf-8')
_handler.setFormatter(logging.Formatter(
    '%(asctime)s  %(levelname)-7s  %(name)s  %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
))

def get_logger(name):
    logger = logging.getLogger('rester.' + name)
    if not logger.handlers:
        logger.addHandler(_handler)
        logger.setLevel(logging.DEBUG)
    return logger
