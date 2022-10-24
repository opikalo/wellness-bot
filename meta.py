import collections
from datetime import timedelta

import human_readable

ALL_TOTALS_HASH = 'all_points'
USER_TOTALS_HASH = 'user_points'
DAILY_TOTALS_HASH = 'daily_points'
DAILY_UNIQUE_HASH = 'daily_unique'
WEEKLY_USER_TOTALS_HASH = 'user_weekly_points'

BALANCE_CAP = 100

WellnessOption = collections.namedtuple('WellnessOption',
                                        ['reaction', 'action', 'description',
                                         'points'])

Reward = collections.namedtuple('Reward', ['cost', 'reaction', 'description'])


_MEGA_REWARDS = [
    (12000, 'ambulance', 'Ambulance Purchase'),
    (6000, 'truck', 'SUV for medical delivery or evacuation'),
]


_REWARDS = [
    (1000, 'medical_symbol', '20 suitcases of medical supplies checked baggage'),
    (500, 'fuelpump', 'Fuel and canisters for one 3 day evacuation mission'),
    (250, 'drop_of_blood', 'Emergency medical supplies for the front line'),
    (125, 'helmet_with_white_cross', 'North American Rescue M-FAK mini advanced first aid kits'),
    (50, 'pill', 'Flu, Cough, Cold, and Anti-Nausea Medicine'),
    (30, 'adhesive_bandage', 'QuikClot Combat Gauze'),
]

_DURATIONS = {}
_INCREMENTS = 30
_MIN_DURATION = timedelta(hours=2)
_MAX_DURATION = timedelta(hours=10)


def get_custom_durations():
    durations = {}
    td = _MIN_DURATION
    while td <= _MAX_DURATION:
        # 30 mins is 5 points
        # points = total minutes/6
        total_mins = td.seconds//60
        durations[human_readable.precise_delta(td)] = total_mins // 6
        td += timedelta(hours=1)

    return durations


_DURATIONS = get_custom_durations()


def get_duration_options():
    duration_options = []
    for duration, points in _DURATIONS.items():
        duration_option = {
            "text": {
                "type": "plain_text",
                "text": duration
            },
            "value": str(points)
        }

        duration_options.append(duration_option)

    return duration_options


CUSTOM_DURATION_OPTIONS = get_duration_options()

CUSTOM_ACTIVITIES = [
    ('family', 'Quality time'),
    ('muscle', 'Working out'),
    ('10000', 'Exceeding 10,000 steps'),
    ('book', 'Reading a book'),
    ('soccer', 'Playing a sport'),
    ('art', 'Practicing a hobby'),
    ('person_in_lotus_position', 'Yoga or meditation'),
    ('sunflower', 'Gardening'),
    ('teacher', 'Mentoring'),
    ('raising_hand', 'Volunteering'),
]


def get_custom_activities():
    activities_options = []

    for icon, text in CUSTOM_ACTIVITIES:
        activities_option = {
            "text": {
                "type": "plain_text",
                "text": f":{icon}: {text}",
                "emoji": True
            },
            "value": icon
        }
        activities_options.append(activities_option)

    return activities_options


CUSTOM_ACTIVITIES_OPTIONS = get_custom_activities()

# icon, alias, full description, points
_CATEGORIES = [
    ('family', 'quality_time_full_hour_wellness', 'Spending quality time with the family or pets with no screens, full hour', 10),
    ('muscle', 'workout_full_hour_wellness', 'Structured workout (including gym, PT, OT or other structured workouts), full hour', 10),
    ('10000', '10000_steps_wellness', 'Exceeding a 10,000 steps per day step count (including treadmill or elliptical)', 10),
    ('green_salad', 'one_day_healthy_eating_wellness', '1 day of eating healthy meals and balanced diet', 10),
    ('book', 'reading_full_hour_wellness', 'Reading a book for pleasure, full hour', 10),
    ('cook', 'cook_healthy_meal_wellness', 'Cook and prepare a healthy meal for your family', 10),
    ('soccer', 'playing_sport_full_hour_wellness', 'Playing a sport, full hour', 10),
    ('art', 'hobby_full_hour_wellness', 'Practicing a hobby – music, painting, pottery, carving, stitching etc., full hour', 10),
    ('person_in_lotus_position', 'yoga_meditation_full_hour_wellness', 'Yoga or meditation, full hour', 10),
    ('sunflower', 'gardening_full_hour_wellness', 'Gardening, full hour', 10),
    ('teacher', 'mentoring_full_hour_wellness', 'Mentoring students in the community, full hour', 10),
    ('raising_hand', 'volunteering_full_hour_wellness', 'Volunteering, full hour', 10),
    ('workout_half_hour_wellness', 'workout_half_hour_wellness', 'Structured workout (including gym, PT, OT or other structured workouts), half hour', 5),
    ('reading_half_hour_wellness', 'reading_half_hour_wellness', 'Reading a book for pleasure, half hour', 5),
    ('quality_time_half_hour_wellness', 'quality_time_half_hour_wellness', 'Spending quality time with the family or pets with no screens, half hour', 5),
    ('yoga_meditation_half_hour_wellness', 'yoga_meditation_half_hour_wellness', 'Yoga or meditation, half hour', 5),
    ('playing_sport_half_hour_wellness', 'playing_sport_half_hour_wellness', 'Playing a sport, half hour', 5),
    ('gardening_half_hour_wellness', 'gardening_half_hour_wellness', 'Gardening, half hour', 5),
    ('hobby_half_hour_wellness', 'hobby_half_hour_wellness', 'Practicing a hobby – music, painting, pottery, carving, stitching etc., half hour', 5),
    ('mentoring_half_hour_wellness', 'mentoring_half_hour_wellness', 'Mentoring students in the community, half hour', 5),
    ('volunteering_half_hour_wellness', 'volunteering_half_hour_wellness', 'Volunteering, half hour', 5),
]

CATEGORIES = [WellnessOption(*category) for category in _CATEGORIES]

REWARDS = [Reward(*reward) for reward in _REWARDS]

MEGA_REWARDS = [Reward(*reward) for reward in _MEGA_REWARDS]


class MetaConversion:
    reaction_to_points = {}
    reaction_to_description = {}
    reaction_to_action = {}
    valid_reactions = set()

    def __init__(self):
        for category in CATEGORIES:
            self.valid_reactions.add(category.reaction)
            self.reaction_to_points[category.reaction] = category.points
            self.reaction_to_description[category.reaction] = category.description
            self.reaction_to_action[category.reaction] = category.action
