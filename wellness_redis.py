import logging
import os

import redis

from dotenv import load_dotenv

load_dotenv()

REDIS_HOST = os.environ.get('REDIS_HOST', 'localhost')
REDIS_PORT = int(os.environ.get('REDIS_PORT', '6379'))
REDIS_DB = int(os.environ.get('REDIS_DB', '0'))


def get_redis():
    return redis.Redis(host=REDIS_HOST, port=REDIS_PORT, db=REDIS_DB,
                       decode_responses=True)
