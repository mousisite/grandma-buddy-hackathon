# app/briefing.py
# "What's happening today": today's weather, one gentle local story, or the
# local teams' sports, for her town. For Buddy's look_up_today tool and the
# weather row on Home.
#
# The weather comes from one place, Open-Meteo (open-meteo.com: free, no
# key, the same source every time): our server asks its geocoder where the
# town is, then its forecast for that spot, and plain code says it in words
# from a fixed table. The news and the sports are looked up on the web with
# Meta's own web search (meta_client.search).
#
# Only these three things can be looked up, and our code writes each
# question, so nothing about health, medicine, or food is ever searched.
# What comes back from the web is checked by plain code before she hears it:
# - it must really come from today's web (a search ran, and sources are cited);
# - links are taken out, and at most 2 sentences are kept;
# - a sentence about health, medicine, or food, or one that gives advice,
#   is left out (docs/SAFETY.md section 8c).
# An answer is kept for 3 hours, and at most 30 searches are made a day, so
# it stays cheap ($0.0025 a search; the weather costs nothing).

import json
import math
import re
from datetime import datetime, timedelta
from urllib.parse import urlsplit

import requests

from app import guard, meta_client, prompts, reminders

FRESH_FOR = timedelta(hours=3)
MAX_SEARCHES_A_DAY = 30
MAX_SENTENCES = 2
MAX_SITES = 3  # the sites named under Buddy's words: the cited ones, or the top results

TOPICS = ("weather", "news", "sports")
# What is looked up on the web, and the question our code asks for it.
QUESTIONS = {
    "news": "What is one cheerful thing happening in {town} today or this week, {day}?",
    "sports": "What was the latest result, or when is the next game, for the major sports teams of {town}, as of {day}?",
}

# ---------- Today's weather, from Open-Meteo ----------

WEATHER_SOURCE = "Open-Meteo.com"  # Weather data by Open-Meteo.com (CC BY 4.0), named under the words
GEOCODE_URL = "https://geocoding-api.open-meteo.com/v1/search"
FORECAST_URL = "https://api.open-meteo.com/v1/forecast"
WEATHER_TIMEOUT = 10  # seconds
RAIN_WORTH_SAYING = 40  # percent: below this, the chance of rain isn't mentioned
_http = requests.Session()  # one connection, reused (tests replace its get)

# Open-Meteo's weather codes (the WMO's), in plain words.
SKY = {
    0: "Clear skies", 1: "Mostly clear", 2: "Partly cloudy", 3: "Cloudy",
    45: "Foggy", 48: "Foggy",
    51: "Light drizzle", 53: "Drizzle", 55: "Drizzle", 56: "Freezing drizzle", 57: "Freezing drizzle",
    61: "Light rain", 63: "Rain", 65: "Heavy rain", 66: "Freezing rain", 67: "Freezing rain",
    71: "Light snow", 73: "Snow", 75: "Heavy snow", 77: "Snow",
    80: "Rain showers", 81: "Rain showers", 82: "Heavy rain showers", 85: "Snow showers", 86: "Snow showers",
    95: "Thunderstorms", 96: "Thunderstorms with hail", 99: "Thunderstorms with hail",
}


# Her words that ask about today: the weather, what's happening in town, or
# a game. Then Buddy is told to look it up before answering (app/companion.py).
ASKS_TODAY = re.compile(
    r"\b(weather|forecast|rain\w*|snow\w*|sunny|cloudy|windy|storm\w*|temperature|how (hot|cold|warm|chilly) is it"
    r"|news|happening|going on (in|around) town|game|match|score\w*|playoffs?|win|won|lose|lost|blazers|team)\b",
    re.IGNORECASE,
)


def asks_about_today(her_words: str) -> bool:
    """True when her words ask about today's weather, news, or a game."""
    return ASKS_TODAY.search(her_words) is not None


# Her words that ask about the weather itself: the forecast is fetched first
# (free) and put in the model's instructions (app/companion.py).
WEATHER_QUESTION = re.compile(
    r"\b(weather|forecast|temperature|how (hot|cold|warm|chilly) is it|(is|will) it (rain|snow)\w*|going to (rain|snow)"
    r"|rain(ing|y)? (today|tomorrow|out)|snow(ing)? (today|tomorrow|out)|sunny (today|out))\b",
    re.IGNORECASE,
)


def asks_about_weather(her_words: str) -> bool:
    """True when her words ask about the weather (today's or tomorrow's)."""
    return WEATHER_QUESTION.search(her_words) is not None


class WeatherError(Exception):
    """Open-Meteo couldn't be reached, or answered in a way we can't read."""


def from_words(topic: str) -> str:
    """The words before the source's name on the screen."""
    return "Weather from" if topic == "weather" else "From the web:"


def degrees(value: float) -> int:
    """A temperature as a whole number, halves rounded up (40.5 is 41; Python's
    own round() would make it 40)."""
    return math.floor(value + 0.5)


def weather_words(code: int, high: float, low: float, rain: float) -> str:
    """Today's weather in one or two plain sentences, from the fixed table."""
    words = f"{SKY.get(code, 'Changeable weather')} today, with a high of {degrees(high)} and a low of {degrees(low)}."
    if rain >= RAIN_WORTH_SAYING:
        words += f" The chance of rain is {degrees(rain)}%."
    return words


def place_of(town: str) -> dict | None:
    """Where the town is (its latitude and longitude), from Open-Meteo's
    geocoder, or None when it doesn't know the town. Only the town's name
    is sent. "Portland, Oregon" picks the Portland in Oregon, not Maine."""
    name, _, region = (part.strip() for part in town.partition(","))
    try:
        answer = _http.get(GEOCODE_URL, params={"name": name, "count": 5, "language": "en", "format": "json"},
                           timeout=WEATHER_TIMEOUT)
        answer.raise_for_status()
        places = answer.json().get("results") or []
    except (requests.RequestException, ValueError, AttributeError) as problem:
        raise WeatherError(f"the geocoder failed: {type(problem).__name__}")
    if region:
        in_region = [place for place in places
                     if region.lower() in (str(place.get("admin1", "")).lower(), str(place.get("country", "")).lower())]
        places = in_region or places
    if not places or "latitude" not in places[0]:
        return None
    return {"latitude": places[0]["latitude"], "longitude": places[0]["longitude"]}


def weather_today(town: str) -> dict | None:
    """Today's forecast for the town from Open-Meteo: {"text", "sites"}, or
    None when the town isn't known. Raises WeatherError when it can't be fetched."""
    place = place_of(town)
    if place is None:
        return None
    try:
        answer = _http.get(FORECAST_URL, params={
            "latitude": place["latitude"], "longitude": place["longitude"],
            "daily": "weather_code,temperature_2m_max,temperature_2m_min,precipitation_probability_max",
            "temperature_unit": "fahrenheit", "timezone": "auto", "forecast_days": 1,
        }, timeout=WEATHER_TIMEOUT)
        answer.raise_for_status()
        daily = answer.json()["daily"]
        text = weather_words(int(daily["weather_code"][0]), float(daily["temperature_2m_max"][0]),
                             float(daily["temperature_2m_min"][0]), float(daily["precipitation_probability_max"][0] or 0))
    except (requests.RequestException, ValueError, KeyError, IndexError, TypeError) as problem:
        raise WeatherError(f"the forecast failed: {type(problem).__name__}")
    return {"text": text, "sites": [WEATHER_SOURCE]}

# Links in the answer: "([weather.gov](https://…))", "[weather.gov](https://…)", or a bare address.
CITED_LINK = re.compile(r"\s*\(\[[^\]]*\]\([^)]*\)\)")
LINK = re.compile(r"\[([^\]]*)\]\([^)]*\)")
ADDRESS = re.compile(r"\s*\(?\bhttps?://\S+")
SENTENCE_END = re.compile(r"(?<=[.!?])\s+")

# Health, medicine, and food words: a sentence with one is left out. (Not
# the guard's own list, which has "cold" and "condition": weather words.)
HEALTH = re.compile(
    r"\b(health\w*|ill|illness\w*|sick\w*|diseases?|infections?|virus\w*|flu|covid\w*|vaccin\w*|booster|cancer"
    r"|allerg\w*|arthritis|diabetes|blood pressure|heart attacks?|strokes?|dehydrat\w*|anxiety|depression"
    r"|hospitals?|clinics?|doctors?|nurses?|medic\w*|prescriptions?|pharmac\w*|drugs?|diet\w*|calories"
    r"|nutrition\w*|supplements?|vitamins?)\b"
    rf"|{guard.REMEDIES.pattern}",
    re.IGNORECASE,
)


def site(url: str) -> str:
    """ "https://www.weather.gov/pqr" -> "weather.gov" """
    host = urlsplit(url).hostname or ""
    return host[4:] if host.startswith("www.") else host


def clean(text: str) -> str:
    """The answer without links, without sentences about health or with
    advice, and at most 2 sentences long."""
    text = ADDRESS.sub("", LINK.sub(r"\1", CITED_LINK.sub("", text))).strip()
    kept = []
    for sentence in SENTENCE_END.split(text):
        sentence = sentence.strip()
        if sentence and not HEALTH.search(sentence) and not guard.check_reply(sentence):
            kept.append(sentence)
    return " ".join(kept[:MAX_SENTENCES])


def searches_today(connection, now: datetime) -> int:
    row = connection.execute("SELECT count FROM web_searches WHERE day = ?", (now.date().isoformat(),)).fetchone()
    return row["count"] if row else 0


def take_search(connection, now: datetime) -> bool:
    """One of today's web searches (at most 30 a day, for the briefing and
    the scam lookup together): counted and allowed, or False when today's
    are used up. The caller commits."""
    if searches_today(connection, now) >= MAX_SEARCHES_A_DAY:
        return False
    connection.execute(
        "INSERT INTO web_searches (day, count) VALUES (?, 1) ON CONFLICT (day) DO UPDATE SET count = count + 1",
        (now.date().isoformat(),),
    )
    return True


def look_up(connection, topic: str, town: str) -> dict | None:
    """Today's weather, news, or sports for her town: {"text", "sites",
    "from"}, or None when there is nothing good to share (no town, a town
    the weather service doesn't know, nothing found on the web, or too many
    searches today). When a new look fails or can't be made, the last one
    from today is kept (never yesterday's). Raises meta_client.MetaError
    (or WeatherError) when the look fails and there is none."""
    town = town.strip()
    if topic not in TOPICS or not town:
        return None
    now = reminders.current_time()
    kept = connection.execute(
        "SELECT text, sources, made_at FROM briefings WHERE topic = ? AND city = ?", (topic, town)
    ).fetchone()
    made = datetime.fromisoformat(kept["made_at"]) if kept else None
    last = ({"text": kept["text"], "sites": json.loads(kept["sources"]), "from": from_words(topic)}
            if kept and made.date() == now.date() else None)
    if last and now - made < FRESH_FOR:
        return last
    if topic == "weather":
        try:
            found = weather_today(town)
        except WeatherError:
            if last:
                return last  # no internet just now: this morning's is still right
            raise
        if not found:
            return None
        text, sites = found["text"], found["sites"]
    else:
        if not take_search(connection, now):
            return last
        connection.commit()
        day = f"{now:%A, %B} {now.day}"
        instructions = prompts.BRIEFING.format(rules=prompts.BRIEFING_RULES[topic])
        try:
            found = meta_client.search(QUESTIONS[topic].format(town=town, day=day), instructions, town)
        except meta_client.MetaError:
            if last:
                return last  # no internet just now: this morning's is still right
            raise
        text = clean(found["text"])
        sites = list(dict.fromkeys(site(source["url"]) for source in found["sources"] if site(source["url"])))[:MAX_SITES]
        if not found["searched"] or not sites or not text:
            return None
    connection.execute(
        "INSERT OR REPLACE INTO briefings (topic, city, text, sources, made_at) VALUES (?, ?, ?, ?, ?)",
        (topic, town, text, json.dumps(sites), now.isoformat(timespec="seconds")),
    )
    connection.commit()
    return {"text": text, "sites": sites, "from": from_words(topic)}
