import datetime

import logging
import os
import pprint

from cachier import cachier
from elasticsearch_dsl import Document, Date, Integer, Keyword, Index
from elasticsearch_dsl.connections import connections

from slack_bolt import App
from slack_bolt.adapter.socket_mode import SocketModeHandler

from dotenv import load_dotenv

import sentry_sdk
from sentry_sdk.integrations.redis import RedisIntegration

from wellness_redis import get_redis
from meta import (MetaConversion, ALL_TOTALS_HASH,
                  USER_TOTALS_HASH, DAILY_TOTALS_HASH, DAILY_UNIQUE_HASH,
                  WEEKLY_USER_TOTALS_HASH)

load_dotenv()

sentry_sdk.init(
    dsn=os.environ['SENTRY_TOKEN'],
    traces_sample_rate=1.0,
    max_breadcrumbs=50,
    integrations=[
        RedisIntegration(),
    ],
)

logging.basicConfig(level=logging.INFO)

SLACK_BOT_TOKEN = os.environ['SLACK_BOT_TOKEN']
SLACK_APP_TOKEN = os.environ['SLACK_APP_TOKEN']

BALANCE_CAP = 100

app = App(token=SLACK_BOT_TOKEN)

meta = MetaConversion()

PRAISE = [
    "Having you on the team makes a huge difference.",
    "You always find a way to get it done – and done well!",
    "It’s really admirable how you always see projects through from conception to completion.",
    "Thank you for always speaking up in team meetings and providing a unique perspective.",
    "Your efforts at strengthening our culture have not gone unnoticed.",
    "Fantastic work!",
    "Even when the going gets tough, you continue to have the best attitude!",
    "It’s amazing how you always help new employees get up to speed.",
    "Wow! Just when I thought your work couldn’t get any better!",
    "Your work ethic speaks for itself.",
    "Thanks for always being willing to lend a hand.",
    "The pride you take in your work is truly inspiring.",
    "You’re so great to work with.",
    "I am continually impressed by the results you produce!",
    "Thank you for being so flexible.",
    "It’s incredible how thorough your work is.",
    "Your work ethic is out of this world!",
    "You have an extremely healthy perspective.",
    "You’re one of the most reliable employees I’ve ever had.",
    "Thank you for setting a great example for your coworkers.",
    "You’re really good at cheering everybody up!",
    "Is there anything you can’t do?!",
    "It’s amazing how you’re always able to overcome any obstacle thrown your way.",
    "Keep up the great work!",
    "I was blown away by your contributions this week.",
    "I really enjoy working with you.",
    "You’re awesome!",
    "You are an invaluable member of the team.",
    "I can’t believe how lucky I am to have a great employee like you.",
    "You come up with fantastic ideas!",
    "Wow! Nice work.",
    "I just wanted to let you know how much you mean to the team.",
    "How did this place ever operate without you?!",
    "You play a crucial role in our company’s success.",
    "It’s so obvious how you pay attention to detail.",
    "You are always so quick to show initiative.",
    "You’re an awesome employee!",
    "It’s incredible how often you go above and beyond.",
    "Your work never ceases to amaze me!",
    "Things have definitely been crazy lately, but you’re crushing it!"
]


def convert_slack_time(ts):
    dt = datetime.datetime.fromtimestamp(float(ts))
    return dt


def get_date_meta(ts):
    date = convert_slack_time(ts)
    year, week, day = date.isocalendar()
    return (date, year, week, day)


class WellnessActivity(Document):
    channel = Keyword()
    channel_id = Keyword()
    activity = Keyword()
    user = Keyword()
    user_email = Keyword()

    challenge_link = Keyword()

    challenge_ts = Keyword()
    challenge_date = Date()
    challenge_year = Integer()
    challenge_week = Integer()
    challenge_day = Integer()

    reaction_ts = Keyword()
    reaction_date = Date()
    reaction_year = Integer()
    reaction_week = Integer()
    reaction_day = Integer()

    reported_date = Date()

    points = Integer()

    class Index:
        name = os.environ['WELLNESS_INDEX']
        settings = {
          "number_of_shards": 2,
        }

    def save(self, ** kwargs):
        self.channel = get_channel_name(self.channel_id)
        (self.reaction_date, self.reaction_year, self.reaction_week,
         self.reaction_day) = get_date_meta(self.reaction_ts)
        (self.challenge_date, self.challenge_year, self.challenge_week,
         self.challenge_day) = get_date_meta(self.challenge_ts)

        ts_encoding = str(int(float(self.challenge_ts)*1000000))
        self.challenge_link = '{}archives/{}/p{}'.format(get_workspace_url(),
                                                         self.channel_id,
                                                         ts_encoding)

        return super(WellnessActivity, self).save(** kwargs)

    def is_reported(self):
        return datetime.datetime.utcnow() >= self.reported_date


def setup_elastic(elastic_host):
    es_logger = logging.getLogger('elasticsearch')
    es_logger.setLevel(logging.WARNING)

    connections.create_connection(hosts=[elastic_host])

    index = Index(os.environ['WELLNESS_INDEX'])

    # create the mappings in elasticsearch
    WellnessActivity.init()


@app.event("app_mention")
def mention_handler(body, say, logger):
    logger.warning(pprint.pformat(body))

    rds = get_redis()
    pong = rds.ping()
    logger.warning('Redis PING: %s', pong)
    say(f'redis ping:{pong}')

    es_health = connections.get_connection().cluster.health()
    logger.warning('ES health: %s', es_health)
    say(f'es health: {es_health}')
    sentry_sdk.capture_message("Testing sentry integration")


# @app.event("app_mention")
# def mention_handler(body, say):
#     pprint.pprint(body)
#     say('Hello World!')

#     # Create a timestamp for tomorrow at 9AM
#     tomorrow = datetime.date.today() + datetime.timedelta(days=0)
#     #scheduled_time = datetime.time(hour=19, minute=15)

#     scheduled_time =(datetime.datetime.now() + datetime.timedelta(seconds=30)).time()

#     schedule_timestamp = datetime.datetime.combine(tomorrow, scheduled_time).strftime('%s')

#     channel_id = body['event']["channel"]

#     channel_info = app.client.conversations_info(channel=channel_id)

#     channel_name = channel_info.get('channel', {}).get('name', 'unknown')

#     print("I'm in channel:", channel_name)

#     app.client.chat_scheduleMessage(
#         channel=channel_id,
#         text="<@U03HTRRL0L9> scheduled message :wave:",
#         post_at=schedule_timestamp,
#     )

#     if "event" in body and "event_ts" in body["event"]:
#         for reaction in ['coffee', 'book', 'flag-ua', 'potted_plant']:
#             app.client.reactions_add(
#                 name=reaction,
#                 channel=body['event']["channel"],
#                 timestamp=body["event"]["event_ts"],
#             )

@cachier(stale_after=datetime.timedelta(weeks=1))
def get_cached_user_data(user):
    # Returs something like this:
    # {'ok': True,
    #  'user': {'color': '9f69e7',
    #           'deleted': False,
    #           'id': 'U03H0JJQXJB',
    #           'is_admin': True,
    #           'is_app_user': False,
    #           'is_bot': False,
    #           'is_email_confirmed': True,
    #           'is_owner': True,
    #           'is_primary_owner': True,
    #           'is_restricted': False,
    #           'is_ultra_restricted': False,
    #           'name': 'opikalo',
    #           'profile': {'avatar_hash': 'gce007755c38',
    #                       'display_name': '',
    #                       'display_name_normalized': '',
    #                       'email': 'opikalo@gmail.com',
    #                       'fields': None,
    #                       'first_name': 'opikalo',
    #                       'image_192': 'https://secure.gravatar.com/avatar/ce007755c38d55cbba50935fdce1e9c4.jpg?s=192&d=https%3A%2F%2Fa.slack-edge.com%2Fdf10d%2Fimg%2Favatars%2Fava_0012-192.png',
    #                       'image_24': 'https://secure.gravatar.com/avatar/ce007755c38d55cbba50935fdce1e9c4.jpg?s=24&d=https%3A%2F%2Fa.slack-edge.com%2Fdf10d%2Fimg%2Favatars%2Fava_0012-24.png',
    #                       'image_32': 'https://secure.gravatar.com/avatar/ce007755c38d55cbba50935fdce1e9c4.jpg?s=32&d=https%3A%2F%2Fa.slack-edge.com%2Fdf10d%2Fimg%2Favatars%2Fava_0012-32.png',
    #                       'image_48': 'https://secure.gravatar.com/avatar/ce007755c38d55cbba50935fdce1e9c4.jpg?s=48&d=https%3A%2F%2Fa.slack-edge.com%2Fdf10d%2Fimg%2Favatars%2Fava_0012-48.png',
    #                       'image_512': 'https://secure.gravatar.com/avatar/ce007755c38d55cbba50935fdce1e9c4.jpg?s=512&d=https%3A%2F%2Fa.slack-edge.com%2Fdf10d%2Fimg%2Favatars%2Fava_0012-512.png',
    #                       'image_72': 'https://secure.gravatar.com/avatar/ce007755c38d55cbba50935fdce1e9c4.jpg?s=72&d=https%3A%2F%2Fa.slack-edge.com%2Fdf10d%2Fimg%2Favatars%2Fava_0012-72.png',
    #                       'last_name': '',
    #                       'phone': '',
    #                       'real_name': 'opikalo',
    #                       'real_name_normalized': 'opikalo',
    #                       'skype': '',
    #                       'status_emoji': '',
    #                       'status_emoji_display_info': [],
    #                       'status_expiration': 0,
    #                       'status_text': '',
    #                       'status_text_canonical': '',
    #                       'team': 'T03HC8QGDRB',
    #                       'title': ''},
    #           'real_name': 'opikalo',
    #           'team_id': 'T03HC8QGDRB',
    #           'tz': 'America/New_York',
    #           'tz_label': 'Eastern Daylight Time',
    #           'tz_offset': -14400,
    #           'updated': 1653872095,
    #           'who_can_share_contact_card': 'EVERYONE'}}

    return app.client.users_info(user=user).data


@app.event("member_joined_channel")
def member_joined(event):
    pprint.pprint(event)

    dm_channel_id = event['user']

    app.client.chat_postMessage(
        channel=dm_channel_id,
        text='welcome to the challenge'
    )


@app.event("member_left_channel")
def handle_member_left_channel_events(body, logger):
    logger.info(body)


@cachier()
def channel_names():
    conv_list = app.client.conversations_list()

    channel_mapping = {}
    for channel in conv_list.data['channels']:
        channel_mapping[channel['id']] = channel['name']

    return channel_mapping


@cachier()
def get_channel_name(channel_id):
    channel_mapping = channel_names()
    return channel_mapping[channel_id]


@cachier()
def get_auth():
    auth = app.client.auth_test()

    # {
    #     "ok": true,
    #     "url": "https://subarachnoid.slack.com/",
    #     "team": "Subarachnoid Workspace",
    #     "user": "grace",
    #     "team_id": "T12345678",
    #     "user_id": "W12345678"
    # }

    return auth


@cachier()
def get_bot_id():
    return get_auth()['user_id']


@cachier()
def get_workspace_url():
    return get_auth()['url']


def get_reaction_icon(reaction):
    return reaction.split('::')[0]


@app.event("reaction_added")
@app.event("reaction_removed")
def reaction_added(event, say, logger):
    # Events looks like this:
    # {'event_ts': '1654995237.000100',
    #  'item': {'channel': 'C03HW2QP3QF',
    #           'ts': '1654458051.148919',
    #           'type': 'message'},
    #  'item_user': 'U03HTRRL0L9',
    #  'reaction': 'family',
    #  'type': 'reaction_added',
    #  'user': 'U03H0JJQXJB'}

    # If this is a reaction to a non-bot owned message, we don't care
    if get_bot_id() != event['item_user']:
        return

    reaction = event['reaction']

    # reaction has skin tone, while icon is just an icon name
    icon = get_reaction_icon(reaction)

    if icon not in meta.valid_reactions:
        return

    logger.debug(pprint.pformat(event))

    user_info = get_cached_user_data(event["user"])

    user_name = user_info['user']['name']
    user_email = user_info['user']['profile']['email']
    sentry_sdk.set_user({'username': user_name, 'email': user_email})

    channel_id = event['item']['channel']
    challenge_ts = event['item']['ts']
    reaction_ts = event['event_ts']

    logger.debug('%s reaction from %s (%s)', reaction, user_name, user_email)

    slack_user_id = event['user']

    points = meta.reaction_to_points[icon]
    description = meta.reaction_to_description[icon]
    action = meta.reaction_to_action[icon]

    if event['type'] == 'reaction_removed':
        points = -points

    activity = WellnessActivity(
        channel_id=channel_id,
        activity=action,
        user_name=user_name,
        user_email=user_email,
        challenge_ts=challenge_ts,
        reaction_ts=reaction_ts,
        points=points,
    )

    activity.save()

    # Get totals
    rds = get_redis()

    total_activity_hash = '{}'.format(activity.channel)

    # daily balance for all users
    # it is useful when you say "Yesterday we all made XXX points"
    daily_activity_hash = '{}-{}-{}-{}'.format(activity.channel,
                                               activity.challenge_year,
                                               activity.challenge_week,
                                               activity.challenge_day)

    logger.warning('daily_hash: %s', daily_activity_hash)

    # total balance for each user
    # Used when user asks how much he contributed total
    user_activity_hash = '{}-{}'.format(activity.channel,
                                        activity.user_name)

    # weekly balance for each user
    # used to tell the user whenthey reached balance_cap
    weekly_user_activity_hash = '{}-{}-{}-{}'.format(activity.channel,
                                                     activity.challenge_year,
                                                     activity.challenge_week,
                                                     activity.user_name)
    with rds.pipeline() as pipe:
        pipe.hget(WEEKLY_USER_TOTALS_HASH, weekly_user_activity_hash)\
            .hincrby(WEEKLY_USER_TOTALS_HASH, weekly_user_activity_hash,
                     points)\
            .pfadd(DAILY_UNIQUE_HASH, daily_activity_hash, activity.user_name)\
            .hincrby(DAILY_TOTALS_HASH, daily_activity_hash, points)\
            .hincrby(USER_TOTALS_HASH, user_activity_hash, points)\
            .hincrby(ALL_TOTALS_HASH, total_activity_hash, points)
        (before_balance, after_balance, unique_status, daily_balance,
         user_balance, total) = pipe.execute()

    logger.warning('%s: before=%s, after=%s, daily=%s, '
                   'user_total=%s, total=%s',
                   activity.user_name, before_balance,
                   after_balance, daily_balance, user_balance, total)

    if before_balance is None:
        before_balance = 0
    else:
        before_balance = int(before_balance)

    if before_balance < BALANCE_CAP and after_balance >= BALANCE_CAP:
        app.client.chat_postMessage(
            channel=slack_user_id,
            text=':tada: Congratulations on topping out the maximum weekly '
            f'wellness contribution of {BALANCE_CAP} points!\n _Feel free to '
            ' go above the limit if it helps you in track your '
            'wellness goals: we do not mind at all. However, Intuitive Foundation'
            f' matches only up to {BALANCE_CAP} points weekly._')

        say(f':tada: <@{slack_user_id}> reached a weekly '
            f'limit of {BALANCE_CAP} points!')

    logger.warning('%s=%s', weekly_user_activity_hash, after_balance)

    parent_url = activity.challenge_link
    if event['type'] == 'reaction_added':
        app.client.chat_postMessage(
            channel=slack_user_id,
            text=f'{points:+} points for :{reaction}:={description} <{parent_url}|here> '
            '(your weekly balance is '
            f'{after_balance} out of {BALANCE_CAP})'
        )
    elif event['type'] == 'reaction_removed':
        app.client.chat_postMessage(
            channel=slack_user_id,
            text=f'adjusted {points:+} points for removing :{reaction}: '
            f'<{parent_url}|here> '
            f'(your weekly balance is {after_balance} out of {BALANCE_CAP})'
        )


@app.event("message")
def handle_message_events(body, logger):
    return




@app.command("/balance")
def hello(body, ack):
    ack(f"Hi <@{body['user_id']}> contibuted 10 coins!")


if __name__ == "__main__":
    setup_elastic(os.environ['ELASTIC_HOST'])
    handler = SocketModeHandler(app, SLACK_APP_TOKEN)
    handler.start()
