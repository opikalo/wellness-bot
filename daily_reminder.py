
import datetime
import os
import pprint
import logging

from cachier import cachier

from elasticsearch_dsl import Document, Date, Integer, Keyword, Text
from elasticsearch_dsl.connections import connections

import humanize

from slack_bolt import App
from slack_bolt.adapter.socket_mode import SocketModeHandler

from meta import (CATEGORIES, ALL_TOTALS_HASH, USER_TOTALS_HASH,
                  DAILY_TOTALS_HASH, DAILY_UNIQUE_HASH,
                  WEEKLY_USER_TOTALS_HASH)

from wellness_redis import get_redis

from dotenv import load_dotenv

import sentry_sdk

load_dotenv()

sentry_sdk.init(
    os.environ['SENTRY_TOKEN'],
    traces_sample_rate=1.0
)

SLACK_BOT_TOKEN = os.environ['SLACK_BOT_TOKEN']
SLACK_APP_TOKEN = os.environ['SLACK_APP_TOKEN']

CHANNEL_NAME = 'wellness-ukraine'

app = App(token=SLACK_BOT_TOKEN)

@cachier()
def get_channel_id(channel_name):
    conv_list = app.client.conversations_list()

    channel_mapping = {}
    for channel in conv_list.data['channels']:
        channel_mapping[channel['name']] = channel['id']

    return channel_mapping[channel_name]


def main():
    channel_id = get_channel_id(CHANNEL_NAME)

    war_start = datetime.datetime(day=24, month=2, year=2022)
    now = datetime.datetime.now()

    day_number = (now - war_start).days
    day_number_str = humanize.ordinal(day_number)
    today_str = now.date().strftime("%A, %B %d, %Y")

    yesterday = now - datetime.timedelta(days=1)

    year, week, day = yesterday.isocalendar()

    # daily balance for all users
    # it is useful when you say "Yesterday we all made XXX points"
    daily_activity_hash = f'{CHANNEL_NAME}-{year}-{week}-{day}'
    total_activity_hash = f'{CHANNEL_NAME}'

    logging.warning(daily_activity_hash)

    rds = get_redis()
    with rds.pipeline() as pipe:
        pipe.hget(DAILY_TOTALS_HASH, daily_activity_hash)\
            .pfcount(DAILY_UNIQUE_HASH, daily_activity_hash)\
            .hget(ALL_TOTALS_HASH, total_activity_hash)
        (daily_balance, user_count, total) = pipe.execute()

    daily_post_status = app.client.chat_postMessage(
        channel=channel_id,
        text=f"<!channel> Today is {today_str}, the {day_number_str} day of the Russian Invasion of :flag-ua: "
        "*\nPlease consider participating in the wellness challenge today!*"
        f"\n_Yesterday, commitment to wellness from {user_count} users added {daily_balance}$ "
        "towards saving people from pain and suffering. Together we are stronger than ever. Thank you!_"
    )

    timestamp = daily_post_status.data['ts']

    for category in CATEGORIES:
        app.client.reactions_add(
            name=category.reaction,
            channel=channel_id,
            timestamp=timestamp,
        )

if __name__ == '__main__':
    main()
