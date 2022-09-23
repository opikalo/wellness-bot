import datetime
import os
import logging
import random

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
    daily_user_search = daily_user_search.source(['user_name', 'challenge_link'])

    results = daily_user_search.scan()

    todays_active_users = set()

    challenge_link = None
    for activity in results:
        todays_active_users.add(activity.user_name)
        if not challenge_link:
            challenge_link = activity.challenge_link

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


    reminders = (
        f"Everyday I see friends reaching their <{challenge_link}|#wellness-ukraine> goals and it restores my faith in humanity. Thank you from the bottom of my heart <{challenge_link}|for your continuous support>",
        f"Today <http://go/wellness-ukraine-stats|{len(todays_active_users)}> employees participated in <{challenge_link}|#wellness-ukraine challenge>. I hope you will <{challenge_link}|join them. Thank you!>",
        f"It is not too late to join <http://go/wellness-ukraine-stats|{len(todays_active_users)}> employees who participated in <{challenge_link}|#wellness-ukraine challenge>. Please <{challenge_link}|continue your support.Thank you!>",
        f"It is not too late to reward yourself <{challenge_link}|with some #wellness-ukraine :muscle:>",
        f"Today <http://go/wellness-ukraine-stats|{len(todays_active_users)}> of your friends enriched their life with <{challenge_link}|#wellness-ukraine.> It is not too late  <{challenge_link}|to join them. Thank you!>",
        #f"Did you know that <https://isi-eng.slack.com/archives/C03LJA25B3R/p1658888338096809|spending quality time with your pets> counts towards <{challenge_link}|#wellness-ukraine :quality_time_full_hour_wellness:?>. It is not too late to go for an extra :walking-the-dog: Thank you for your support!"
    )

    reminder_text = f"Today is a <https://isi-eng.slack.com/archives/C03LJA25B3R/p1661364547624739|special> day: we are celebrating Ukrainian Independence Day among the continuous rocket bombings from Russia. And it is another opportunity to <{challenge_link}|continue your support towards #wellness-ukraine campaign.> Thank you for your help!"

    reminder_text = f"<https://isi-eng.slack.com/archives/C03LJA25B3R/p1661562829586439|Resist> with <http://go/wellness-ukraine-stats|{len(todays_active_users)}> of your friends who participated in <{challenge_link}|#wellness-ukraine challenge>. Please <{challenge_link}|continue your support. Thank you!>"

    reminder_text = f"This is the last day to play the game :tada: I can't beleive this journey is over and this is your last reminder! At this time we have raised $99620: but if 38 more people will participate in <{challenge_link}|#wellness-ukraine today> we will be at 100K! Take a great care of yourself, and please continue your wellness activities: from now the honors are on you to spend time on what brings you wellness and balance in life. If you have not completed the <https://forms.gle/y87d7xio6P7Ctiun8|survey> it is not too late to claim your prize! And thank you for making a difference!"

    #reminder_text = random.choice(reminders)

    app.client.chat_postMessage(
        channel=inv_map[ADMIN],
        text=reminder_text)

    input()
    for member in tqdm(missing_activity):
        app.client.chat_postMessage(
            channel=inv_map[member],
            text=reminder_text)


if __name__ == '__main__':
    main()
