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
    ("chat_model", "Thinks and talks: Buddy's words, scam checks, doctor notes, memory book pages, what a letter "
                   "says, and today's weather and news from the web."),
    ("transcribe_model", "Hears you, live, and hears when you've finished."),
    ("image_model", "Paints your memory book pages and the daily postcard."),
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
        "name": "Talking without tapping",
        "what": "Buddy listens until you stop talking, then answers, and shows your words as you say them. "
                "Tap Pause any time.",
        "models": ["transcribe_model"],
        "here": "Live speech-to-text from Meta. Buddy never listens while it is talking itself.",
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
        "here": "Runs on this computer. The labels your family typed never go to the AI.",
    },
    {
        "name": "A pill from a photo of its bottle",
        "what": "A family member takes a photo of the bottle, and Buddy fills in the name and the label as printed.",
        "models": ["chat_model"],
        "here": "Only a suggestion: the family member checks each one against the bottle before it is saved, and "
                "always types the times. Buddy never changes a label.",
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
        "what": "Checks a text, an email, a letter, or a photo of one for the tricks scammers use, and looks up any "
                "phone number or web address in it on the web.",
        "models": ["chat_model"],
        "here": "Plain rules set a floor the AI can't lower. A number or address is never read back to you.",
    },
    {
        "name": "Memory book",
        "what": "Writes down a story from your life in your words, and paints a picture for it. You can start "
                "from an old photo: Buddy says what it shows and asks about it.",
        "models": ["chat_model", "image_model", "sam_model"],
        "here": "Your pages and your photos stay on this computer. A photo with people in it is never repainted.",
    },
    {
        "name": "Find my things",
        "what": "Finds your glasses or keys in a photo of the room, and tells you where they are.",
        "models": ["sam_model", "chat_model"],
        "here": "Your photo is never saved.",
    },
    {
        "name": "Read it to me",
        "what": "Take a photo of a letter, a bill, or a form, and Buddy tells you what it is and what it says, "
                "in plain words, or reads it word for word.",
        "models": ["chat_model"],
        "here": "Your photo is never saved. Letters about your health are read word for word, never explained.",
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
    {
        "name": "Message your family, and the daily postcard",
        "what": "Say a message for your family, read it over, and send it to their family page; when they write back, "
                "Buddy reads it to you, or plays their own voice. Once a day, one cheerful thing you said becomes a "
                "painted postcard to send them.",
        "models": ["chat_model", "image_model", "transcribe_model"],
        "here": "Your message is checked for emergency words first, and only you tap Send. The postcard's words are "
                "yours, word for word: the AI only picks the line and paints the picture.",
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
