#!/usr/bin/env python3
"""
Event filtering and label merging configuration for AST audio event detection.

Raw output is now the default. Filtering remains available via environment
variables when comparison with the legacy setup is needed.
"""

import os


def _env_flag(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}

# ========================================
# FEATURE FLAGS - Easy on/off toggle
# ========================================
ENABLE_BLACKLIST_FILTER = _env_flag("SED_ENABLE_BLACKLIST_FILTER", False)
ENABLE_LABEL_MERGE = _env_flag("SED_ENABLE_LABEL_MERGE", False)


# ========================================
# BLACKLIST - Events to exclude
# ========================================
# Events that are not useful for behavior analysis
BLACKLIST_EVENTS = [
    # Noise
    "White noise",
    "Static",
    "Hum",
    "Mains hum",
    "Buzz",
    "Background noise",

    # Insects
    "Insect",
    "Cricket",
    "Crickets",
    "Mosquito",
    "Fly, housefly",
    "Bee, wasp, etc.",

    # Animals (excluding Dog and Cat - keep them as they are common pets)
    "Snake",
    "Sheep",
    "Livestock",
    "Farm animals, working animals",
    "Animal",
    "Mouse",
    "Rodents, rats, mice",
    "Domestic animals, pets",  # Too generic
    "Wild animals",
    "Fowl",
    "Chicken, rooster",
    "Cluck",
    "Crowing, cock-a-doodle-doo",
    "Turkey",
    "Gobble",
    "Duck",
    "Quack",
    "Goose",
    "Honk",
    "Pig",
    "Oink",
    "Goat",
    "Bleat",
    "Horse",
    "Clip-clop",
    "Neigh, whinny",
    "Cattle, bovinae",
    "Moo",
    "Cowbell",
    "Roaring cats (lions, tigers)",
    "Roar",
    "Frog",
    "Croak",
    "Rattle",
    "Whale vocalization",

    # Birds (too many false positives)
    "Bird",
    "Bird vocalization, bird call, bird song",
    "Chirp, tweet",
    "Squawk",
    "Pigeon, dove",
    "Coo",
    "Crow",
    "Caw",
    "Owl",
    "Hoot",
    "Bird flight, flapping wings",

    # Other
    "Arrow",
]


# ========================================
# LABEL MERGE MAP - Combine similar events
# ========================================
# Format: "Original Label" -> "Merged Label"
# Similar events will be combined under the merged label
LABEL_MERGE_MAP = {
    # Clock sounds - merge Tick into Tick-tock
    "Tick": "Tick-tock",

    # Child speech - merge all child-related speech into one category
    "Child speech, kid speaking": "Child speech",
    "Children shouting": "Child speech",
    "Baby cry, infant cry": "Child speech",
    "Babbling": "Child speech",
    "Children playing": "Child speech",

    # Kitchen sounds - merge cutlery and dishes
    "Dishes, pots, and pans": "Cutlery and kitchenware",
    "Cutlery, silverware": "Cutlery and kitchenware",
    "Coin (dropping)": "Cutlery and kitchenware",

    # Water sounds - merge all water-related sounds
    "Water tap, faucet": "Water",
    "Fill (with liquid)": "Water",
    "Pour": "Water",
    "Sink (filling or washing)": "Water",
    "Bathtub (filling or washing)": "Water",
    "Splash, splatter": "Water",
    "Slosh": "Water",
    "Drip": "Water",
    "Trickle, dribble": "Water",
    "Gush": "Water",
    "Stream": "Water",
    "Waterfall": "Water",
    "Rain": "Water",
    "Raindrop": "Water",
    "Rain on surface": "Water",

    # Laughter - merge all laughter types
    "Baby laughter": "Laughter",
    "Giggle": "Laughter",
    "Snicker": "Laughter",
    "Belly laugh": "Laughter",
    "Chuckle, chortle": "Laughter",

    # Crying - merge all crying types
    "Crying, sobbing": "Crying",
    "Whimper": "Crying",
    "Wail, moan": "Crying",

    # Dog sounds - merge all dog vocalizations
    "Bark": "Dog",
    "Yip": "Dog",
    "Howl": "Dog",
    "Bow-wow": "Dog",
    "Growling": "Dog",
    "Whimper (dog)": "Dog",

    # Cat sounds - merge all cat vocalizations
    "Meow": "Cat",
    "Purr": "Cat",
    "Hiss": "Cat",
    "Caterwaul": "Cat",

    # Music genres - merge all into Music
    "Musical instrument": "Music",
    "Pop music": "Music",
    "Hip hop music": "Music",
    "Rock music": "Music",
    "Heavy metal": "Music",
    "Punk rock": "Music",
    "Grunge": "Music",
    "Progressive rock": "Music",
    "Rock and roll": "Music",
    "Psychedelic rock": "Music",
    "Rhythm and blues": "Music",
    "Soul music": "Music",
    "Reggae": "Music",
    "Country": "Music",
    "Swing music": "Music",
    "Bluegrass": "Music",
    "Funk": "Music",
    "Folk music": "Music",
    "Middle Eastern music": "Music",
    "Jazz": "Music",
    "Disco": "Music",
    "Classical music": "Music",
    "Opera": "Music",
    "Electronic music": "Music",
    "House music": "Music",
    "Techno": "Music",
    "Dubstep": "Music",
    "Drum and bass": "Music",
    "Electronica": "Music",
    "Electronic dance music": "Music",
    "Ambient music": "Music",
    "Trance music": "Music",
    "Music of Latin America": "Music",
    "Salsa music": "Music",
    "Flamenco": "Music",
    "Blues": "Music",
    "Music for children": "Music",
    "New-age music": "Music",
    "Vocal music": "Music",
    "A capella": "Music",
    "Music of Africa": "Music",
    "Afrobeat": "Music",
    "Christian music": "Music",
    "Gospel music": "Music",
    "Music of Asia": "Music",
    "Carnatic music": "Music",
    "Music of Bollywood": "Music",
    "Ska": "Music",
    "Traditional music": "Music",
    "Independent music": "Music",
    "Background music": "Music",
    "Theme music": "Music",
    "Jingle (music)": "Music",
    "Soundtrack music": "Music",
    "Lullaby": "Music",
    "Video game music": "Music",
    "Christmas music": "Music",
    "Dance music": "Music",
    "Wedding music": "Music",
    "Happy music": "Music",
    "Funny music": "Music",
    "Sad music": "Music",
    "Tender music": "Music",
    "Exciting music": "Music",
    "Angry music": "Music",
    "Scary music": "Music",

    # Vehicles - merge all vehicles
    "Motor vehicle (road)": "Vehicle",
    "Car": "Vehicle",
    "Vehicle horn, car horn, honking": "Vehicle",
    "Truck": "Vehicle",
    "Bus": "Vehicle",
    "Motorcycle": "Vehicle",
    "Traffic noise, roadway noise": "Vehicle",
    "Train": "Vehicle",
    "Subway, metro, underground": "Vehicle",
    "Aircraft": "Vehicle",
    "Boat, Water vehicle": "Vehicle",

    # Engine sounds - merge all engine types
    "Engine": "Engine",
    "Aircraft engine": "Engine",
    "Jet engine": "Engine",
    "Light engine (high frequency)": "Engine",
    "Medium engine (mid frequency)": "Engine",
    "Heavy engine (low frequency)": "Engine",
    "Idling": "Engine",
    "Accelerating, revving, vroom": "Engine",

    # Tools and machines
    "Lawn mower": "Machine",
    "Chainsaw": "Machine",
    "Vacuum cleaner": "Machine",
    "Drill": "Machine",
    "Power tool": "Machine",
    "Sewing machine": "Machine",
    "Mechanical fan": "Machine",
}


def apply_event_filter(events_list):
    """
    Apply blacklist filtering and label merging to event list.

    Args:
        events_list: List of event dicts with 'label' and 'score' keys

    Returns:
        Filtered and merged event list
    """
    if not events_list:
        return []

    filtered_events = []

    for event in events_list:
        label = event.get("label", "")
        score = event.get("score", 0.0)

        # Step 1: Apply blacklist filter
        if ENABLE_BLACKLIST_FILTER and label in BLACKLIST_EVENTS:
            continue

        # Step 2: Apply label merge
        if ENABLE_LABEL_MERGE and label in LABEL_MERGE_MAP:
            label = LABEL_MERGE_MAP[label]

        # Add to filtered list
        filtered_events.append({
            "label": label,
            "score": score
        })

    # Step 3: Merge duplicate labels (after merging, same label might appear multiple times)
    # Combine scores by taking the maximum score for each label
    merged_dict = {}
    for event in filtered_events:
        label = event["label"]
        score = event["score"]

        if label in merged_dict:
            # Keep the higher score
            merged_dict[label] = max(merged_dict[label], score)
        else:
            merged_dict[label] = score

    # Convert back to list format
    result = [
        {"label": label, "score": score}
        for label, score in merged_dict.items()
    ]

    # Sort by score (descending)
    result.sort(key=lambda x: x["score"], reverse=True)

    return result


def get_filter_stats():
    """
    Get current filter configuration stats.

    Returns:
        Dict with filter statistics
    """
    return {
        "blacklist_enabled": ENABLE_BLACKLIST_FILTER,
        "blacklist_count": len(BLACKLIST_EVENTS),
        "label_merge_enabled": ENABLE_LABEL_MERGE,
        "label_merge_count": len(LABEL_MERGE_MAP),
        "blacklist_events": BLACKLIST_EVENTS if ENABLE_BLACKLIST_FILTER else [],
        "merge_rules": LABEL_MERGE_MAP if ENABLE_LABEL_MERGE else {}
    }
