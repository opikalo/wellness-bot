import datetime
import os
import logging

from cachier import cachier

import humanize

from slack_bolt import App

from meta import (BALANCE_CAP, CATEGORIES, ALL_TOTALS_HASH,
                  DAILY_TOTALS_HASH, DAILY_UNIQUE_HASH)

from wellness_redis import get_redis

from app import setup_elastic, WellnessActivity

from dotenv import load_dotenv

import sentry_sdk

from elasticsearch_dsl import Q, A

from tqdm import tqdm

load_dotenv()

sentry_sdk.init(
    os.environ['SENTRY_TOKEN'],
    traces_sample_rate=1.0
)

SLACK_BOT_TOKEN = os.environ['SLACK_BOT_TOKEN']

CHANNEL_NAME = os.environ['SLACK_POST_CHANNEL']

app = App(token=SLACK_BOT_TOKEN)


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
    now = datetime.datetime.now()
    year, week, day = now.isocalendar()

    setup_elastic(os.environ['ELASTIC_HOST'])

    channel_id = get_channel_id(CHANNEL_NAME)

    weekly_totals_search = WellnessActivity.search().source(False)
    weekly_totals_search.query = Q('bool', must=[Q('match', channel_id=channel_id),
                                                 Q('match', challenge_year=year),
                                                 Q('match', challenge_week=week)])
    weekly_totals_search.aggs.bucket('users', 'terms', field='user_name.keyword', size=1000).metric('weekly_total', 'sum', field='points')

    response = weekly_totals_search.execute()
    users_who_reached_weekly_goal = set()
    for user in response.aggregations.users.buckets:
        print(user.key, user.weekly_total.value)
        if user.weekly_total.value >= BALANCE_CAP:
            users_who_reached_weekly_goal.add(user.key)

    print('reached balance:', users_who_reached_weekly_goal)

    daily_user_search = WellnessActivity.search()

    # the search is already limited to the index and doc_type of our document
    #daily_user_search = daily_user_search.query('match', *{'channel_id': channel_id, 'day': day, 'week': week, 'year': year})

    # , Q('match', year=year), Q('match', week=week), Q('match', day=day)
    daily_user_search.query = Q('bool', must=[Q('match', channel_id=channel_id),
                                              Q('match', challenge_year=year),
                                              Q('match', challenge_week=week),
                                              Q('match', challenge_day=day)])
    daily_user_search = daily_user_search.source(['user_name'])

    results = daily_user_search.scan()

    todays_active_users = set()

    for activity in results:
        todays_active_users.add(activity.user_name)

    users = user_names()

    #print(users)

    members = channel_members(channel_id=channel_id)

    member_names = set()
    for member in members:
        if member in users:
            member_names.add(users[member])

    #print(member_names)

    missing_activity = member_names - todays_active_users - users_who_reached_weekly_goal

    inv_map = {v: k for k, v in users.items()}
    print('missing activity:', missing_activity)
    print('total: ', len(missing_activity))

    input()
    for member in tqdm(missing_activity):
        app.client.chat_postMessage(
            channel=inv_map[member],
            text=f"Happy 4th of July! I'm thankful for all the support the American people have provided Ukraine. And for all the <https://isi-eng.slack.com/archives/C03LJA25B3R/p1656946907790789|support> from you. Thank you!")


if __name__ == '__main__':
    main()
