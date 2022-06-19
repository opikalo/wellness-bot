from app import get_reaction_icon


def test_reaction():
    reaction = 'cook::skin-tone-5'
    assert get_reaction_icon(reaction) == 'cook'
