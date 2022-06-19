
import datetime
import os
import pprint

from cachier import cachier

from elasticsearch_dsl import Document, Date, Integer, Keyword, Text
from elasticsearch_dsl.connections import connections


from slack_bolt import App
from slack_bolt.adapter.socket_mode import SocketModeHandler

from meta import CATEGORIES

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

    daily_post_status = app.client.chat_postMessage(
        channel=channel_id,
        text='<!channel> Today is a good day to achieve the wellness goal'
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
