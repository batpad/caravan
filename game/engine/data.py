"""Static game content for *Caravan Road* — an original Silk Road dice-placement game.

All numbers live here so balance tweaks never touch the rules engine.
"""

GOODS = ("spice", "silk", "jade")
RESOURCES = ("coins", "camels", "spice", "silk", "jade", "omens")

NUM_ROUNDS = 5
DICE_PER_PLAYER = 5
TRADING_POSTS = 8
MAX_OPEN_CONTRACTS = 2
CONTRACT_SLOTS = 6
CONTRACT_CHURN = 2      # oldest contracts leaving the market at the end of each round
GUIDE_DICE = 3          # shared pool of white "guide" dice, refreshed each round
GUIDE_COST = 3          # coins to hire a guide die (once per round per player)
REROLL_COST = 1         # omens, reroll one die
NUDGE_COST = 2          # omens, change a die by +/-1
REST_COINS_PER_DIE = 1  # resting: coins per die you could still have placed

# Crowd toll: placing on a shared space where another player already has a die costs
# TOLL_PER_PIP coins per pip of the value you place (a set pays once, for its common value).
TOLL_PER_PIP = 1
MAX_OCCUPY_COST = 6     # legacy key kept for static_data; the toll never exceeds a 6-pip die

# Sets: some spaces take 2-3 dice showing the same value at once. The effect is the
# single-die amount times the number of dice, plus SET_BONUS[size]. A guide die is wild in a set.
SET_BONUS = [0, 0, 1, 2]

# Low-roll compensation: coins = LOW_ROLL_PER_DIE * dice - total pips, capped (own dice only).
LOW_ROLL_PER_DIE = 3
LOW_ROLL_MAX = 4

START_RESOURCES = {"coins": 6, "camels": 3, "spice": 1, "silk": 1, "jade": 0, "omens": 1, "vp": 0}
SEAT_BONUS_COINS = [0, 1, 1, 2]   # later seats start richer to offset turn order
PLAYER_COLORS = ["#c0392b", "#2471a3", "#239b56", "#b7950b"]
COLOR_NAMES = ["Crimson", "Indigo", "Jade", "Saffron"]

# Die value (1..6) -> amount, index 0 is unused.
# max_dice: largest set the space accepts. cost: paid per die placed.
SPACES = {
    "bazaar_spice": {"name": "Spice Stall", "gain": "spice", "table": [0, 1, 2, 2, 3, 3, 4], "cost": {}, "max_dice": 3},
    "bazaar_silk": {"name": "Silk Stall", "gain": "silk", "table": [0, 1, 1, 2, 2, 3, 3], "cost": {}, "max_dice": 3},
    "bazaar_jade": {"name": "Jade Stall", "gain": "jade", "table": [0, 1, 1, 1, 1, 2, 2], "cost": {"coins": 1}, "max_dice": 2},
    "camels": {"name": "Camel Market", "gain": "camels", "table": [0, 1, 2, 2, 3, 3, 4], "cost": {}, "max_dice": 3},
    "treasury": {"name": "Moneychanger", "gain": "coins", "table": [0, 1, 2, 3, 4, 5, 6], "cost": {}, "max_dice": 2},
    "temple": {"name": "Shrine", "gain": "omens", "table": [0, 1, 1, 1, 2, 2, 2], "cost": {}, "max_dice": 1},
    "caravanserai": {"name": "Caravanserai", "gain": None, "table": None, "cost": {}, "max_dice": 1},
    "road": {"name": "The Road", "gain": None, "table": [0, 1, 1, 2, 2, 3, 3], "cost": {}, "max_dice": 2},
}
CITY_ACTION_REPEATS = [0, 1, 1, 1, 2, 2, 2]

ROUTE_TYPES = {
    "road": {"camels": 1, "coins": 0, "label": "Road"},
    "desert": {"camels": 2, "coins": 0, "label": "Desert"},
    "mountain": {"camels": 2, "coins": 1, "label": "Mountain pass"},
    "sea": {"camels": 0, "coins": 3, "label": "Sea crossing"},
}

START_CITY = "constantinople"
END_CITY = "changan"
END_CITY_ORDER_VP = [8, 5, 3, 1]
NO_POST_CITIES = (START_CITY, END_CITY)   # no trading posts can be founded here

# income: gained every round start by each player with a post here
# action: exchange usable by post owners (one die per city per round)
CITIES = {
    "constantinople": {"name": "Constantinople", "x": 70, "y": 170, "post_vp": 0, "income": {}, "action": None},
    "trebizond": {"name": "Trebizond", "x": 250, "y": 95, "post_vp": 1, "income": {"coins": 2},
                  "action": {"pay": {"spice": 1}, "gain": {"coins": 3}}},
    "antioch": {"name": "Antioch", "x": 165, "y": 300, "post_vp": 1, "income": {"spice": 1},
                "action": {"pay": {"coins": 2}, "gain": {"silk": 1}}},
    "baghdad": {"name": "Baghdad", "x": 300, "y": 340, "post_vp": 2, "income": {"silk": 1},
                "action": {"pay": {"silk": 1}, "gain": {"vp": 2}}},
    "tabriz": {"name": "Tabriz", "x": 360, "y": 190, "post_vp": 2, "income": {"camels": 1, "coins": 1},
               "action": {"pay": {}, "gain": {"camels": 2}}},
    "hormuz": {"name": "Hormuz", "x": 440, "y": 455, "post_vp": 2, "income": {"spice": 2},
               "action": {"pay": {"spice": 1, "silk": 1}, "gain": {"jade": 1}}},
    "merv": {"name": "Merv", "x": 510, "y": 230, "post_vp": 2, "income": {"camels": 2},
             "action": {"pay": {}, "gain": {"omens": 1, "coins": 1}}},
    "herat": {"name": "Herat", "x": 540, "y": 355, "post_vp": 3, "income": {"silk": 1},
              "action": {"pay": {"coins": 3}, "gain": {"jade": 1}}},
    "bukhara": {"name": "Bukhara", "x": 590, "y": 120, "post_vp": 3, "income": {"coins": 3},
                "action": {"pay": {"spice": 1}, "gain": {"vp": 1, "coins": 1}}},
    "samarkand": {"name": "Samarkand", "x": 680, "y": 175, "post_vp": 3, "income": {"silk": 1, "spice": 1},
                  "action": {"pay": {"jade": 1}, "gain": {"vp": 3}}},
    "kabul": {"name": "Kabul", "x": 670, "y": 360, "post_vp": 3, "income": {"jade": 1},
              "action": {"pay": {"camels": 3}, "gain": {"vp": 3}}},
    "kashgar": {"name": "Kashgar", "x": 790, "y": 245, "post_vp": 4, "income": {"camels": 1, "omens": 1},
                "action": {"pay": {}, "gain": {"silk": 1, "spice": 1}}},
    "khotan": {"name": "Khotan", "x": 815, "y": 395, "post_vp": 4, "income": {"jade": 1},
               "action": {"pay": {"silk": 1}, "gain": {"vp": 2}}},
    "dunhuang": {"name": "Dunhuang", "x": 920, "y": 205, "post_vp": 5, "income": {"coins": 2, "camels": 1},
                 "action": {"pay": {"spice": 1, "silk": 1, "jade": 1}, "gain": {"vp": 6}}},
    "lanzhou": {"name": "Lanzhou", "x": 1010, "y": 310, "post_vp": 5, "income": {"silk": 1, "coins": 1},
                "action": {"pay": {}, "gain": {"jade": 1}}},
    "changan": {"name": "Chang'an", "x": 1080, "y": 430, "post_vp": 0, "income": {}, "action": None},
}

ROUTES = [
    ("constantinople", "trebizond", "sea"),
    ("constantinople", "antioch", "road"),
    ("trebizond", "tabriz", "mountain"),
    ("antioch", "baghdad", "road"),
    ("baghdad", "tabriz", "road"),
    ("baghdad", "hormuz", "desert"),
    ("tabriz", "merv", "desert"),
    ("hormuz", "herat", "desert"),
    ("merv", "herat", "road"),
    ("merv", "bukhara", "desert"),
    ("bukhara", "samarkand", "road"),
    ("herat", "kabul", "mountain"),
    ("samarkand", "kabul", "mountain"),
    ("samarkand", "kashgar", "mountain"),
    ("kabul", "kashgar", "mountain"),
    ("kashgar", "khotan", "desert"),
    ("kashgar", "dunhuang", "desert"),
    ("khotan", "dunhuang", "desert"),
    ("dunhuang", "lanzhou", "road"),
    ("lanzhou", "changan", "road"),
    ("khotan", "changan", "desert"),
]

CHARACTERS = {
    "cartographer": {"name": "The Cartographer",
                     "text": "Once per round, a journey may also found a trading post (worth 1 VP) in a city it passes through."},
    "breeder": {"name": "The Camel Breeder",
                "text": "Gain 2 camels each round. Camels may stand in for omens (1 each) and for missing contract goods (2 camels per good)."},
    "seer": {"name": "The Seer",
             "text": "Gain 1 omen and 1 coin each round; your nudges cost 1 omen. Twice per round, set an unused die to any value."},
    "heiress": {"name": "The Silk Heiress",
                "text": "Roll 6 dice each round but place at most 5 of them (guide dice excluded). Gain 1 silk each round."},
    "moneylender": {"name": "The Moneylender",
                    "text": "Pay only half the crowd toll (rounded up)."},
    "guildmaster": {"name": "The Guildmaster",
                    "text": "Hold up to 3 open contracts and reach 1 slot further at the Caravanserai. Each delivery scores +1 VP."},
    "pathfinder": {"name": "The Pathfinder",
                   "text": "Desert and mountain routes cost you 1 fewer camel. Score +4 VP on reaching Chang'an."},
    "quartermaster": {"name": "The Quartermaster",
                      "text": "Your city actions may be used one extra time. Each round gain 1 coin per 4 trading posts."},
}
# Numbers behind the character powers.
CARTOGRAPHER_SURVEY_VP = 1   # flat VP for a surveyed post (instead of the printed VP)
CARTOGRAPHER_SURVEY_COST = {}
BREEDER_INCOME = {"camels": 2}
BREEDER_GOOD_CAMELS = 2      # camels per missing good when delivering a contract
SEER_INCOME = {"omens": 1, "coins": 1}
SEER_USES = 2               # times per round the Seer may set a die
SEER_NUDGE_COST = 1
HEIRESS_DICE = 6
HEIRESS_MAX_PLACED = 5
HEIRESS_INCOME = {"silk": 1}
GUILDMASTER_CONTRACTS = 3
GUILDMASTER_BONUS_VP = 1
GUILDMASTER_BONUS_COINS = 0
GUILDMASTER_REACH = 1        # extra Caravanserai slots reachable beyond the die value
PATHFINDER_ROUTES = ("desert", "mountain")
PATHFINDER_DISCOUNT = 1
PATHFINDER_CHANGAN_VP = 4   # extra VP when the Pathfinder first reaches Chang'an
QUARTERMASTER_EXTRA_USES = 1
QUARTERMASTER_POSTS_PER_COIN = 4   # round income: 1 coin per this many trading posts
MONEYLENDER_TOLL_SHARE = 0.5   # fraction of the crowd toll paid, rounded up
MONEYLENDER_KICKBACK = 0   # coins taken when a rival pays a toll on your space

# (requirements, vp, bonus)
CONTRACTS = [
    ({"spice": 2}, 3, {"coins": 1}),
    ({"spice": 3}, 4, {"camels": 1}),
    ({"silk": 2}, 5, {}),
    ({"silk": 1, "spice": 1}, 3, {"coins": 2}),
    ({"silk": 1, "spice": 2}, 5, {}),
    ({"jade": 1}, 4, {"coins": 1}),
    ({"jade": 1, "spice": 1}, 5, {"camels": 1}),
    ({"jade": 1, "silk": 1}, 6, {"coins": 1}),
    ({"silk": 3}, 7, {}),
    ({"spice": 4}, 6, {}),
    ({"jade": 2}, 8, {}),
    ({"silk": 2, "spice": 2}, 7, {"omens": 1}),
    ({"jade": 1, "silk": 1, "spice": 1}, 8, {}),
    ({"jade": 2, "silk": 1}, 10, {}),
    ({"jade": 1, "spice": 3}, 7, {"coins": 1}),
    ({"silk": 2, "jade": 1}, 8, {"omens": 1}),
    ({"spice": 2, "camels": 2}, 4, {"coins": 2}),
    ({"silk": 1, "coins": 3}, 4, {}),
    ({"jade": 3}, 13, {}),
    ({"spice": 3, "silk": 2}, 9, {}),
    ({"jade": 2, "spice": 2}, 10, {"camels": 1}),
    ({"silk": 1}, 2, {"omens": 1}),
    ({"spice": 1}, 1, {"coins": 2}),
    ({"jade": 1, "silk": 2, "spice": 1}, 10, {"coins": 1}),
    ({"spice": 2, "silk": 1}, 4, {"camels": 1}),
    ({"jade": 1, "camels": 2}, 5, {"coins": 1}),
    ({"silk": 2, "camels": 1}, 5, {}),
    ({"spice": 5}, 8, {}),
]

# Secret commissions: pairs of cities. Posts in both = 6 VP, in one = 2 VP.
COMMISSIONS = [
    ("trebizond", "kabul"), ("antioch", "kashgar"), ("baghdad", "samarkand"),
    ("tabriz", "khotan"), ("hormuz", "bukhara"), ("merv", "dunhuang"),
    ("herat", "lanzhou"), ("bukhara", "khotan"), ("kabul", "dunhuang"),
    ("tabriz", "herat"), ("antioch", "merv"), ("samarkand", "lanzhou"),
]
COMMISSION_BOTH_VP = 6
COMMISSION_ONE_VP = 2

# End-game scoring
POST_MAJORITY_VP = [6, 3]
CONTRACT_MAJORITY_VP = 4
COINS_PER_VP = 10
GOODS_PER_VP = 3
