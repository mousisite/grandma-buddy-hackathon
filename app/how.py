# app/how.py
# "How Buddy works" (the Help screen): every feature, the Meta model behind
# it, and what runs on this computer instead. The model names come from the
# app's own settings, so the page always says what really runs.
#
# When a feature is added, add it here too.

from app.config import Settings

# Each Meta model the app uses: which setting holds it, and what it does,
# in her words.
MODELS = [
    ("chat_model", "Thinks and talks: Buddy's words, check-in questions, doctor-note topics, scam checks, "
                   "Memory book pages, and where your things are. It also looks up today's weather and news "
                   "with Meta's web search."),
    ("transcribe_model", "Hears you: turns what you say into words."),
    ("image_model", "Paints the pictures in your Memory book."),
    ("sam_model", "Finds your glasses or keys in a photo of the room."),
]

# Every feature: what it does, which models it uses (by setting), and what
# runs on this computer. A feature with no model says where it runs instead.
FEATURES = [
    {
        "name": "Talking with Buddy",
        "what": "You talk, and Buddy answers like a kind friend. It remembers what you share about your life.",
        "models": ["transcribe_model", "chat_model"],
        "here": "Buddy's natural voice speaks on this computer.",
    },
    {
        "name": "The safety net",
        "what": "Before any AI sees your words, plain rules look for an emergency, a pill mix-up, or a crisis, "
                "and show you who to call.",
        "models": [],
        "here": "Runs on this computer, even without the internet.",
    },
    {
        "name": "Pill reminders",
        "what": "At each pill's time, Buddy reminds you and reads the label exactly as your family typed it.",
        "models": [],
        "here": "Runs on this computer. The AI never sees a pill's label.",
    },
    {
        "name": "Daily check-in and diary",
        "what": "Buddy asks how you feel, and writes down what hurts in your own words.",
        "models": ["transcribe_model", "chat_model"],
        "here": "",
    },
    {
        "name": "Doctor notes",
        "what": "One page for your next visit, straight from your diary and pills. The AI only sorts your notes "
                "by topic, using your own words.",
        "models": ["chat_model"],
        "here": "The facts on the page are written on this computer.",
    },
    {
        "name": "Check a message",
        "what": "Checks a text, an email, a letter, or a photo of one for the tricks scammers use.",
        "models": ["chat_model"],
        "here": "",
    },
    {
        "name": "Memory book",
        "what": "Writes down a story from your life in your words, and paints a picture for it.",
        "models": ["chat_model", "image_model"],
        "here": "Your pages stay on this computer.",
    },
    {
        "name": "Find my things",
        "what": "Finds your glasses or keys in a photo of the room, and tells you where they are.",
        "models": ["sam_model", "chat_model"],
        "here": "Your photo is never saved.",
    },
    {
        "name": "Today's weather and news",
        "what": "Buddy tells you today's weather, one cheerful thing happening in your town, or how your teams "
                "did, and shows where it read it.",
        "models": ["chat_model"],
        "here": "Looked up with Meta's web search. Only your town is sent.",
    },
    {
        "name": "Family update",
        "what": "A short note about your day for the family member you chose. You send it yourself.",
        "models": [],
        "here": "Written on this computer from what Buddy wrote down.",
    },
]


def model_name(model_id: str) -> str:
    """ "muse-spark-1.3" -> "Muse Spark 1.3", "sam-3.1" -> "SAM 3.1". """
    words = model_id.split("-")
    return " ".join(word.upper() if word == "sam" else word.capitalize() for word in words)


def how(settings: Settings) -> dict:
    """The models and the features, with the model names from the settings."""
    return {
        "models": [
            {"id": getattr(settings, setting), "name": model_name(getattr(settings, setting)), "does": does}
            for setting, does in MODELS
        ],
        "features": [
            {**feature, "models": [getattr(settings, setting) for setting in feature["models"]]}
            for feature in FEATURES
        ],
    }
