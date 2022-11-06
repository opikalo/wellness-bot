import datetime
import json
import os
import logging
import pprint

from cachier import cachier

import humanize

from slack_bolt import App

from meta import (BALANCE_CAP, CATEGORIES, ALL_TOTALS_HASH,
                  DAILY_TOTALS_HASH, DAILY_UNIQUE_HASH)

from wellness_redis import get_redis

from app import setup_elastic, WellnessActivity

from dotenv import load_dotenv

import sentry_sdk

from elasticsearch_dsl import Q

from tqdm import tqdm

load_dotenv()

sentry_sdk.init(
    os.environ['SENTRY_TOKEN'],
    traces_sample_rate=1.0
)

SLACK_BOT_TOKEN = os.environ['SLACK_BOT_TOKEN']

CHANNEL_NAME = os.environ['SLACK_POST_CHANNEL']

app = App(token=SLACK_BOT_TOKEN)

ADMIN = 'oleksiy.pikalo'

def get_channel_id(channel_name):
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
        channel_mapping[channel['name']] = channel['id']

    return channel_mapping[channel_name]



def user_names():
    cursor = None
    users = []
    while True:
        user_list = app.client.users_list(cursor=cursor, limit=200)
        users.extend(user_list.data['members'])
        cursor = user_list['response_metadata']['next_cursor']
        if cursor == '':
            break

    user_mapping = {}
    for user in users:
        if not user['is_bot']:
            user_mapping[user['id']] = user['name']

    return user_mapping


def channel_members(channel_id):
    cursor = None
    members = []
    while True:
        member_list = app.client.conversations_members(channel=channel_id, cursor=cursor, limit=200)
        members.extend(member_list.data['members'])
        cursor = member_list['response_metadata']['next_cursor']
        if cursor == '':
            break

    return members




def main():
    setup_elastic(os.environ['ELASTIC_HOST'])
    channel_id = get_channel_id(CHANNEL_NAME)

    activity_search = WellnessActivity.search()

    activity_search.query = Q('bool', must=[Q('match', channel_id=channel_id)])

    activities = activity_search.scan()

    # if True:
    #     for activity in tqdm(activities):
    #         with open(os.path.join('backup', activity.meta.id + '.json'), 'w') as fh:
    #             json.dump(activity.__dict__['_d_'], fh, indent=4, sort_keys=True, default=str)

    user_weekly_points = {}
    user_weekly_activities = {}

    for activity in tqdm(activities):
        key = f"{activity.challenge_week}-{activity.challenge_year}-{activity.user_email}"

        if key not in user_weekly_points:
            user_weekly_points[key] = []
            user_weekly_activities[key] = []

        user_weekly_points[key].append(activity.points)
        user_weekly_activities[key].append(activity.activity)

    totals = {}
    excess = {}
    for key, points in user_weekly_points.items():
        week, year, user = key.split('-', 2)
        totals_key = f'{week}-{year}'
        if totals_key not in totals:
            totals[totals_key] = 0

        totals[totals_key] += min(sum(points), BALANCE_CAP)

        if sum(points) - BALANCE_CAP > 0:
            if user not in excess:
                excess[user] = 0

            excess[user] += sum(points) - BALANCE_CAP

    print('Weekly Totals')
    pprint.pprint(totals)

    print('User Excess')
    pprint.pprint(excess)



if __name__ == '__main__':
    main()
