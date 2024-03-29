import datetime

import json
import logging
import os
import pprint

from cachier import cachier
from elasticsearch_dsl import Boolean, Document, Date, Integer, Keyword, Index, Q
from elasticsearch_dsl.connections import connections

from slack_bolt import App
from slack_bolt.adapter.socket_mode import SocketModeHandler

from dotenv import load_dotenv

import humanize

import sentry_sdk
from sentry_sdk.integrations.redis import RedisIntegration

from wellness_redis import get_redis
from meta import (MetaConversion, BALANCE_CAP, REWARDS, MEGA_REWARDS, ALL_TOTALS_HASH,
                  USER_TOTALS_HASH, DAILY_TOTALS_HASH, DAILY_UNIQUE_HASH,
                  WEEKLY_USER_TOTALS_HASH, CUSTOM_DURATION_OPTIONS,
                  CUSTOM_ACTIVITIES_OPTIONS, POINTS_TO_HUMAN_DURATIONS,
                  CATEGORY_TO_DESCRIPTION)

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


app = App(token=SLACK_BOT_TOKEN)

meta_conv = MetaConversion()


def convert_slack_time(ts):
    dt = datetime.datetime.fromtimestamp(float(ts))
    return dt


def get_date_meta(ts):
    date = convert_slack_time(ts)
    sun_week = int(date.strftime("%U"))
    year, week, day = date.isocalendar()
    return (date, year, sun_week, day)


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

    category = Keyword()
    reaction_ts = Keyword()
    reaction_date = Date()
    reaction_year = Integer()
    reaction_week = Integer()
    reaction_day = Integer()

    reported_date = Date()

    points = Integer()

    deleted = Boolean()

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

        if self.deleted is None:
            self.deleted = False

        return super(WellnessActivity, self).save(** kwargs)

    def is_reported(self):
        return datetime.datetime.utcnow() >= self.reported_date

    def human_str(self):
        human_duration = POINTS_TO_HUMAN_DURATIONS[abs(self.points)]
        human_descr = CATEGORY_TO_DESCRIPTION[self.category]
        descr = f":{self.activity}: {human_descr} for {human_duration} ({self.points} points)"
        return descr


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


@cachier(stale_after=datetime.timedelta(weeks=1))
def channel_names():
    cursor = None
    channels = []
    while True:
        conv_list = app.client.conversations_list(cursor=cursor, limit=200)
        channels.extend(conv_list.data['channels'])
        cursor = conv_list['response_metadata']['next_cursor']
        if cursor == '':
            break

    channel_mapping = {}
    for channel in channels:
        channel_mapping[channel['id']] = channel['name']

    return channel_mapping


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


def get_username_email(slack_user_id):
    user_info = get_cached_user_data(slack_user_id)

    user_name = user_info['user']['name']
    user_email = user_info['user']['profile']['email']
    sentry_sdk.set_user({'username': user_name, 'email': user_email})

    return (user_name, user_email)


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

    if icon not in meta_conv.valid_reactions:
        return

    logger.debug(pprint.pformat(event))

    slack_user_id = event['user']
    user_name,  user_email = get_username_email(slack_user_id)

    logger.debug('%s reaction from %s (%s)', reaction, user_name, user_email)

    channel_id = event['item']['channel']
    challenge_ts = event['item']['ts']
    reaction_ts = event['event_ts']

    points = meta_conv.reaction_to_points[icon]
    description = meta_conv.reaction_to_description[icon]
    action = meta_conv.reaction_to_action[icon]
    category = meta_conv.reaction_to_category[icon]

    deleted = False

    if event['type'] == 'reaction_removed':
        points = -points
        deleted = True

    activity = WellnessActivity(
        channel_id=channel_id,
        activity=action,
        category=category,
        user_name=user_name,
        user_email=user_email,
        challenge_ts=challenge_ts,
        reaction_ts=reaction_ts,
        points=points,
        deleted=deleted
    )

    activity.save()

    (user_before_balance, user_balance, after_balance) = register_activity(
        activity, slack_user_id, description, logger)

    post_reward_update(user_before_balance, user_balance, slack_user_id,
                       channel_id)

    post_dm_update(points, after_balance, user_balance, activity,
                   slack_user_id, reaction, description)


def register_activity(activity, slack_user_id, description, logger):

    points = activity.points

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
            .pfadd(daily_activity_hash, activity.user_name)\
            .hincrby(DAILY_TOTALS_HASH, daily_activity_hash, points)\
            .hget(USER_TOTALS_HASH, user_activity_hash)\
            .hincrby(USER_TOTALS_HASH, user_activity_hash, points)\
            .hincrby(ALL_TOTALS_HASH, total_activity_hash, points)
        (before_balance, after_balance, unique_status, daily_balance,
         user_before_balance, user_balance, total) = pipe.execute()

    logger.warning('%s: before=%s, after=%s, daily=%s, '
                   'user_total=%s, total=%s',
                   activity.user_name, before_balance,
                   after_balance, daily_balance, user_balance, total)

    if before_balance is None:
        before_balance = 0
    else:
        before_balance = int(before_balance)

    if user_before_balance is None:
        user_before_balance = 0
    else:
        user_before_balance = int(user_before_balance)

    if user_balance is None:
        user_balance = 0
    else:
        user_balance = int(user_balance)

    if before_balance < BALANCE_CAP and after_balance >= BALANCE_CAP:
        app.client.chat_postMessage(
            channel=slack_user_id,
            text=':tada: Congratulations on topping out the maximum weekly '
            f'wellness contribution of {BALANCE_CAP} points!\n _Feel free to '
            ' go above the limit if it helps you to track your '
            'wellness goals: we do not mind at all. However, Intuitive Foundation'
            f' matches only up to {BALANCE_CAP} points weekly._')

        app.client.chat_postMessage(
            channel=activity.channel_id,
            text=f':tada: <@{slack_user_id}> reached a weekly '
            f'maximum weekly goal of {BALANCE_CAP} points!')

    logger.warning('%s=%s', weekly_user_activity_hash, after_balance)

    return (user_before_balance, user_balance, after_balance)


def post_reward_update(user_before_balance, user_balance, slack_user_id,
                       channel_id):
    for reward in REWARDS:
        threshold = reward.cost
        if user_before_balance < threshold and user_balance >= threshold:
            app.client.chat_postMessage(
                channel=slack_user_id,
                text=f':tada: You have a :{reward.reaction}: reward: '
                f'{reward.description}. Thank you so much!')

            app.client.chat_postMessage(
                channel=channel_id,
                text=f':tada: <@{slack_user_id}> just earned :{reward.reaction}: '
                f'badge @{reward.cost} points: {reward.description}')


def post_dm_update(points, after_balance, user_balance, activity,
                   slack_user_id, reaction, description, category=False):

    if category:
        add_identifier = f'custom duration {description.lower()} entry'
        remove_identifier = f'custom duration {description.lower()} entry'
    else:
        add_identifier = f':{reaction}:={description}'
        remove_identifier = f':{reaction}:'

    parent_url = activity.challenge_link
    if points > 0:
        app.client.chat_postMessage(
            channel=slack_user_id,
            text=f'{points:+} points for {add_identifier} '
            f'<{parent_url}|here> '
            '(your weekly balance is '
            f'{after_balance} out of weekly {BALANCE_CAP}. Grand total is '
            f'{user_balance} points).'
        )
    elif points < 0:
        app.client.chat_postMessage(
            channel=slack_user_id,
            text=f'adjusted {points:+} points for removing {remove_identifier} '
            f'<{parent_url}|here> '
            f'(your weekly balance is {after_balance} out of {BALANCE_CAP})'
        )


@app.event("message")
def handle_message_events(body, logger):
    return




@app.command("/balance")
def hello(body, ack):
    ack(f"Hi <@{body['user_id']}> contibuted 10 coins!")


@app.action("button-action")
def handle_some_action(ack, body, logger):
    ack()
    logger.info(pprint.pformat(body))


@app.action("actionId-activity")
def handle_some_action(ack, body, logger):
    ack()
    logger.info(pprint.pformat(body))


def private_metadata_to_str(channel_id, message_ts, action_ts):
    return json.dumps([channel_id, message_ts, action_ts])


def private_metadata_from_str(str_data):
    return json.loads(str_data)



@app.shortcut("open_modal")
@app.action("open_add_modal")
def open_add_modal(ack, body, client, logger):
    # Acknowledge the command request
    ack()

    logger.info(pprint.pformat(body))

    message_date = convert_slack_time(body['message']['ts'])

    display_date = humanize.naturaldate(message_date)

    action_ts = body['actions'][0]['action_ts']
    channel_id = body['container']['channel_id']
    message_ts = body['container']['message_ts']

    private_metadata = private_metadata_to_str(channel_id, message_ts,
                                               action_ts)

    logger.info('private_metadata %s', private_metadata)

    # Call views_open with the built-in client
    client.views_open(
        # Pass a valid trigger_id within 3 seconds of receiving it
        trigger_id=body["trigger_id"],
        # View payload
        view={
            "type": "modal",
            # View identifier
            "callback_id": "view_add",
            "title": {"type": "plain_text", "text": "Adding Custom Duration"},
            "submit": {"type": "plain_text", "text": "Add"},
            "private_metadata": private_metadata,
            "blocks": [
                {
                    "type": "section",
                    "block_id": "title_block_id",
                    "text": {
                        "type": "mrkdwn",
                        "text": f"\n *Please select an activity to add for {display_date}"
                    }
                },
                {
                    "type": "actions",
                    "block_id": "activity_block_id",
                    "elements": [
                        {
                            "type": "static_select",
                            "placeholder": {
                                "type": "plain_text",
                                "text": "What activity did you do?",
                                "emoji": True
                            },
                            "options": CUSTOM_ACTIVITIES_OPTIONS,
                            "action_id": "changed-activity"
                        },
                        {
                            "type": "static_select",
                            "placeholder": {
                                "type": "plain_text",
                                "text": "Duration",
                                "emoji": True
                            },
                            "options": CUSTOM_DURATION_OPTIONS,
                            "action_id": "changed-duration"
                        },
                    ]
                }
            ]
        }
    )


@app.action("multi_static_select-action")
def handle_multi_select_action(ack, body, logger):
    ack()
    logger.debug(body)


@app.action("selected_option")
def handle_selected_option(ack, body, logger):
    ack()
    logger.debug(body)


@app.shortcut("open_modal")
@app.action("open_edit_modal")
def open_edit_modal(ack, body, client, logger):
    # Acknowledge the command request
    ack()

    logger.info(pprint.pformat(body))

    message_date = convert_slack_time(body['message']['ts'])

    display_date = humanize.naturaldate(message_date)

    action_ts = body['actions'][0]['action_ts']
    channel_id = body['container']['channel_id']
    message_ts = body['container']['message_ts']

    user_name = body['user']['name']

    private_metadata = private_metadata_to_str(channel_id, message_ts,
                                               action_ts)

    logger.info('private_metadata %s', private_metadata)

    activity_search = WellnessActivity.search()
    activity_search.query = Q('bool', must=[
        Q('match', channel_id=channel_id),
        Q('match', challenge_ts=message_ts),
        Q('match', user_name=user_name),
        Q('match', deleted=False)])

    activities = activity_search.filter('range', points={'gte': 20}).execute()

    options = []

    for activity in activities:
        logger.info("Found: %s", activity.human_str())
        options.append({
            "text": {
                "type": "plain_text",
                "text": activity.human_str(),
                "emoji": True
            },
            "value": f"{activity.meta.id}"
        })

    if options:
        blocks = [
            {
                "block_id": "selection",
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": f"Select long activities to delete for {display_date}"
                },
                "accessory": {
                    "type": "multi_static_select",
                    "placeholder": {
                        "type": "plain_text",
                        "text": "Select options",
                        "emoji": True
                    },
                    "options": options,
                    "action_id": "multi_static_select-action"
                }
            }
        ]

        client.views_open(
            # Pass a valid trigger_id within 3 seconds of receiving it
            trigger_id=body["trigger_id"],
            # View payload
            view={
                "type": "modal",
                # View identifier
                "callback_id": "view_edit",
                "title": {"type": "plain_text", "text": "Delete Custom Activity"},
                "submit": {"type": "plain_text", "text": "Delete"},
                "private_metadata": private_metadata,
                "blocks":  blocks
            }
        )

    else:
        blocks = [
            {
                "type": "section",
                "block_id": "title_block_id",
                "text": {
                    "type": "mrkdwn",
                    "text": f"Sorry, could not find custom activities (2 hours+) recorded {display_date}.\nNot seeing short activities? You can delete those by clicking your previous reactions."
                }
            }
        ]

        client.views_open(
            # Pass a valid trigger_id within 3 seconds of receiving it
            trigger_id=body["trigger_id"],
            # View payload
            view={
                "type": "modal",
                # View identifier
                "callback_id": "view_edit",
                "title": {"type": "plain_text", "text": "Delete Custom Activity"},
                "private_metadata": private_metadata,
                "blocks":  blocks
            }
        )



    # Call views_open with the built-in client
    # client.views_open(
    #     # Pass a valid trigger_id within 3 seconds of receiving it
    #     trigger_id=body["trigger_id"],
    #     # View payload
    #     view={
    #         "type": "modal",
    #         # View identifier
    #         "callback_id": "view_edit",
    #         "title": {
    #             "type": "plain_text",
    #             "text": "Adjusting Custom Activity"
    #         },
    #         "submit": {"type": "plain_text", "text": "Delete"},
    #         "private_metadata": private_metadata,
    #         "blocks": [
    #             {
    #                 "type": "section",
    #                 "text": {
    #                     "type": "mrkdwn",
    #                     "text": "Select activities to delete"
    #                 },
    #                 "accessory": {
    #                     "type": "multi_static_select",
    #                     "placeholder": {
    #                         "type": "plain_text",
    #                         "text": "Select options",
    #                         "emoji": True
    #                     },
    #                     "options": [
    #                         {
    #                             "text": {
    #                                 "type": "plain_text",
    #                                 "text": ":family: Quality time, 2 hours",
    #                                 "emoji": True
    #                             },
    #                             "value": "value-0"
    #                         },
    #                         {
    #                             "text": {
    #                                 "type": "plain_text",
    #                                 "text": ":muscle: Working out, 10 hours",
    #                                 "emoji": True
    #                             },
    #                             "value": "value-1"
    #                         },
    #                     ],
    #                     "action_id": "multi_static_select-action"
    #                 }
    #             }
    #         ]
    #     })


@app.action("changed-activity")
@app.action("changed-duration")
def open_add_modal(ack, body, client, logger):
    # Acknowledge the command request
    ack()

    logger.info(pprint.pformat(body))


@app.view("view_edit")
def handle_edit_events(ack, body, logger):
    ack()
    logger.info(pprint.pformat(body))

    slack_user_id = body['user']['id']
    user_name,  user_email = get_username_email(slack_user_id)

    channel_id, challenge_ts, reaction_ts = private_metadata_from_str(body['view']['private_metadata'])

    docs = body['view']['state']['values']['selection']['multi_static_select-action']['selected_options']

    doc_ids = []
    for doc in docs:
        doc_ids.append(doc['value'])

    logger.info('deleting %s', doc_ids)

    # make sure user cannot delete document many times by tagging it as 'deleted=True'
    for doc_id in doc_ids:
        record = WellnessActivity.get(id=doc_id)
        record.update(deleted=True)

        assert record.points > 0
        negative_activity = WellnessActivity(
            channel_id=record.channel_id,
            activity=record.activity,
            category=record.category,
            user_name=record.user_name,
            user_email=record.user_email,
            challenge_ts=record.challenge_ts,
            reaction_ts=reaction_ts,
            points=-record.points,
        )

        negative_activity.save()

        description_with_hours = record.human_str()

        (user_before_balance, user_balance, after_balance) = register_activity(
            negative_activity, slack_user_id, description_with_hours, logger)

        post_reward_update(user_before_balance, user_balance, slack_user_id,
                           channel_id)

        category_icon = meta_conv.category_to_icon[negative_activity.category]

        post_dm_update(negative_activity.points, after_balance, user_balance,
                       negative_activity,
                       slack_user_id, category_icon,
                       description_with_hours, True)




@app.view("view_add")
def handle_add_events(ack, body, logger):
    ack()
    #logger.info(pprint.pformat(body))

    slack_user_id = body['user']['id']
    user_name,  user_email = get_username_email(slack_user_id)

    channel_id, challenge_ts, reaction_ts = private_metadata_from_str(body['view']['private_metadata'])

    category = body['view']['state']['values']['activity_block_id']['changed-activity']['selected_option']['value']
    description = body['view']['state']['values']['activity_block_id']['changed-activity']['selected_option']['text']['text']
    human_hours = body['view']['state']['values']['activity_block_id']['changed-duration']['selected_option']['text']['text']

    description_with_hours = description + ' for ' + human_hours

    points = int(body['view']['state']['values']['activity_block_id']['changed-duration']['selected_option']['value'])

    logger.debug('%s category from %s (%s) for %s points', category, user_name, user_email, points)

    category_icon = meta_conv.category_to_icon[category]

    activity = WellnessActivity(
        channel_id=channel_id,
        activity=category_icon,
        category=category,
        user_name=user_name,
        user_email=user_email,
        challenge_ts=challenge_ts,
        reaction_ts=reaction_ts,
        points=points,
    )

    activity.save()

    (user_before_balance, user_balance, after_balance) = register_activity(
        activity, slack_user_id, description_with_hours, logger)

    post_reward_update(user_before_balance, user_balance, slack_user_id,
                       channel_id)

    category_icon = meta_conv.category_to_icon[category]

    post_dm_update(points, after_balance, user_balance, activity,
                   slack_user_id, category_icon, description_with_hours, True)




# Listen for a button invocation with action_id `button_abc` (assume it's inside of a modal)
@app.action("add-activity")
def update_modal(ack, body, client):
    # Acknowledge the button request
    ack()
    # Call views_update with the built-in client
    client.views_update(
        # Pass the view_id
        view_id=body["view"]["id"],
        # String that represents view state to protect against race conditions
        hash=body["view"]["hash"],
        # View payload with updated blocks
        view={
            "type": "modal",
            # View identifier
            "callback_id": "view_1",
            "title": {"type": "plain_text", "text": "Updated modal"},
            "blocks": [
                {
                    "type": "section",
                    "text": {"type": "plain_text", "text": "You updated the modal!"}
                },
                {
                    "type": "image",
                    "image_url": "https://media.giphy.com/media/SVZGEcYt7brkFUyU90/giphy.gif",
                    "alt_text": "Yay! The modal was updated"
                }
            ]
        }
    )

if __name__ == "__main__":
    setup_elastic(os.environ['ELASTIC_HOST'])
    handler = SocketModeHandler(app, SLACK_APP_TOKEN)
    handler.start()
