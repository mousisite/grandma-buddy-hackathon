# Tests for "what's happening today" (app/briefing.py): today's weather from
# Open-Meteo (its geocoder and forecast, faked here), and a gentle local story
# or sports, looked up with Meta's web search (the Responses API's built-in
# web_search tool) near her town. Meta and Open-Meteo are always FAKE here.
# Made-up town and stories only.

import json
from datetime import datetime
from types import SimpleNamespace as N

import pytest
import requests
from fastapi.testclient import TestClient

from app import briefing, db, meta_client, reminders, tools
from app.main import app
from tests.test_companion import chat, reply, tool_call, use_fake

TOWN = "Portland, Oregon"


# ---------- The Meta call (meta_client.search) ----------

def cited(text, *urls, searched=True):
    """A fake Responses answer: a web search, then the text with its sources."""
    notes = [N(type="url_citation", url=url, title="A source", start_index=0, end_index=len(text)) for url in urls]
    output = [N(type="message", content=[N(type="output_text", text=text, annotations=notes)])]
    if searched:
        output.insert(0, N(type="web_search_call", status="completed"))
    return N(output_text=text, output=output)


class FakeResponses:
    def __init__(self, *answers):
        self.answers = list(answers)
        self.requests = []

    def create(self, **request):
        self.requests.append(request)
        return self.answers.pop(0)


@pytest.fixture
def meta(monkeypatch):
    def install(*answers):
        fake = FakeResponses(*answers)
        monkeypatch.setattr(meta_client, "_client", lambda: N(responses=fake))
        return fake
    return install


def test_search_asks_meta_to_search_the_web_near_her_town(meta):
    fake = meta(cited("It's sunny, with a high of 62.", "https://www.weather.gov/pqr"))
    found = meta_client.search("What's the weather today?", "Answer in two short sentences.", TOWN)
    request = fake.requests[0]
    assert request["model"] == "muse-spark-1.3"
    assert request["tools"] == [{"type": "web_search", "search_context_size": "low", "user_location": {
        "type": "approximate", "country": "US", "city": "Portland", "region": "Oregon"}}]
    assert request["instructions"] == "Answer in two short sentences."
    assert request["input"] == "What's the weather today?"
    assert (request["store"], request["max_tool_calls"]) == (False, 2)
    assert found == {"text": "It's sunny, with a high of 62.", "searched": True,
                     "sources": [{"title": "A source", "url": "https://www.weather.gov/pqr"}]}


def test_the_answer_is_the_last_message_not_what_it_said_before_searching(meta):
    # Seen with the real model: "I'll check today's web sources…", a search,
    # "I found several forecasts…", another look, then the answer, which
    # alone carries the citation.
    answer = N(type="message", content=[N(type="output_text", text="Portland is cloudy, with a high of 54.", annotations=[
        N(type="url_citation", url="https://www.timeanddate.com/weather", title="Forecast", start_index=0, end_index=10)])])
    meta(N(output_text="I'll check the web.I found several forecasts.Portland is cloudy, with a high of 54.", output=[
        N(type="message", content=[N(type="output_text", text="I'll check the web.", annotations=[])]),
        N(type="web_search_call", status="completed", action=N(type="search", sources=[])),
        N(type="message", content=[N(type="output_text", text="I found several forecasts.", annotations=[])]),
        answer,
    ]))
    found = meta_client.search("Weather?", "Short.", TOWN)
    assert found["text"] == "Portland is cloudy, with a high of 54."
    assert found["sources"] == [{"title": "Forecast", "url": "https://www.timeanddate.com/weather"}]


def test_with_no_citation_the_pages_it_searched_are_the_sources(meta):
    fake = meta(N(output_text="Sunny, with a high of 60.", output=[
        N(type="web_search_call", status="completed", action=N(type="search", sources=[
            N(type="url", url="https://www.weather.gov/pqr"), N(type="url", url="https://www.weather.gov/pqr")])),
        N(type="message", content=[N(type="output_text", text="Sunny, with a high of 60.", annotations=[])]),
    ]))
    found = meta_client.search("Weather?", "Short.", TOWN)
    assert found["sources"] == [{"title": "", "url": "https://www.weather.gov/pqr"}]
    assert fake.requests[0]["include"] == ["web_search_call.action.sources"]


def test_an_answer_without_a_search_says_so(meta):
    meta(cited("It is usually mild in October.", searched=False))
    assert meta_client.search("Weather?", "Short.", TOWN)["searched"] is False


# ---------- Looking it up (briefing.look_up) ----------

class Searches:
    """A fake meta_client.search that counts its calls."""

    def __init__(self, monkeypatch, text="It's sunny in Portland today, with a high of 62.", sources=None, searched=True):
        self.calls = []
        self.text, self.searched = text, searched
        self.sources = [{"title": "Forecast", "url": "https://www.weather.gov/pqr"}] if sources is None else sources
        monkeypatch.setattr(meta_client, "search", self)

    def __call__(self, question, instructions, town):
        self.calls.append((question, instructions, town))
        return {"text": self.text, "sources": self.sources, "searched": self.searched}


@pytest.fixture
def clock(monkeypatch):
    class Clock:
        now = datetime(2026, 10, 30, 8, 0)

        def set(self, hour, minute=0, day=30):
            self.now = datetime(2026, 10, day, hour, minute)

    test_clock = Clock()
    monkeypatch.setattr(reminders, "current_time", lambda: test_clock.now)
    return test_clock


@pytest.fixture
def connection(safe_test_setup):
    opened = db.get_connection(safe_test_setup)
    yield opened
    opened.close()


def test_a_look_up_is_made_once_then_kept_for_three_hours(monkeypatch, connection, clock):
    searches = Searches(monkeypatch, text="The farmers market opens Saturday at 9.",
                        sources=[{"title": "Market", "url": "https://www.kgw.com/market"}])
    first = briefing.look_up(connection, "news", TOWN)
    assert first == {"text": "The farmers market opens Saturday at 9.", "sites": ["kgw.com"], "from": "From the web:"}
    clock.set(10, 59)
    assert briefing.look_up(connection, "news", TOWN) == first
    assert len(searches.calls) == 1
    clock.set(11, 1)
    briefing.look_up(connection, "news", TOWN)
    assert len(searches.calls) == 2
    question, instructions, town = searches.calls[0]
    assert "Friday, October 30" in question and town == TOWN


def test_each_topic_gets_only_its_own_instructions(monkeypatch, connection, clock):
    # One set of instructions for both made the real model answer both at
    # once ("…the Trail Blazers lost…" in the news).
    searches = Searches(monkeypatch)
    for topic in ("news", "sports"):
        briefing.look_up(connection, topic, TOWN)
    news, sports = (instructions for _, instructions, _ in searches.calls)
    assert "festival" in news and "score" not in news
    assert "score" in sports and "festival" not in sports
    assert all("Don't say what you are going to do" in text for text in (news, sports))


def test_an_answer_that_wasnt_found_on_the_web_is_not_used(monkeypatch, connection, clock):
    Searches(monkeypatch, searched=False)
    assert briefing.look_up(connection, "news", TOWN) is None
    Searches(monkeypatch, sources=[])
    assert briefing.look_up(connection, "news", TOWN) is None


def test_three_sites_at_most_are_named_each_once(monkeypatch, connection, clock):
    # Without a citation, the real search listed 21 pages it looked at.
    urls = ["https://www.weather.gov/a", "https://forecast.weather.gov/b", "https://www.weather.gov/c",
            "https://kgw.com/d", "https://koin.com/e", "https://wweek.com/f"]
    Searches(monkeypatch, sources=[{"title": "", "url": url} for url in urls])
    assert briefing.look_up(connection, "news", TOWN)["sites"] == ["weather.gov", "forecast.weather.gov", "kgw.com"]


def test_links_are_taken_out_and_two_sentences_at_most_are_kept(monkeypatch, connection, clock):
    Searches(monkeypatch, text="It's sunny today ([weather.gov](https://www.weather.gov/pqr)). "
                               "The high is 62. The low is 48. More at https://example.com/forecast")
    assert briefing.look_up(connection, "news", TOWN)["text"] == "It's sunny today. The high is 62."


def test_sentences_about_health_or_with_advice_are_left_out(monkeypatch, connection, clock):
    Searches(monkeypatch, text="Flu shots are free at the library this week. You should drink plenty of water. "
                               "The farmers market opens Saturday at 9.")
    assert briefing.look_up(connection, "news", TOWN)["text"] == "The farmers market opens Saturday at 9."


def test_nothing_left_after_the_checks_means_nothing_to_share(monkeypatch, connection, clock):
    Searches(monkeypatch, text="Flu shots are free at the library this week.")
    assert briefing.look_up(connection, "news", TOWN) is None


def test_no_more_than_thirty_searches_a_day(monkeypatch, connection, clock):
    searches = Searches(monkeypatch)
    for hour in range(31):  # a new look every 3 hours would never get this far: force it
        connection.execute("DELETE FROM briefings")
        briefing.look_up(connection, "news", TOWN)
    assert len(searches.calls) == briefing.MAX_SEARCHES_A_DAY == 30


def test_when_a_new_look_fails_the_last_one_from_today_is_kept(monkeypatch, connection, clock):
    Searches(monkeypatch)
    morning = briefing.look_up(connection, "news", TOWN)

    def no_internet(*args):
        raise meta_client.MetaError("Web search failed: APIConnectionError")

    monkeypatch.setattr(meta_client, "search", no_internet)
    clock.set(12)  # over 3 hours later: a new look is due, and it fails
    assert briefing.look_up(connection, "news", TOWN) == morning
    clock.set(8, day=31)  # but yesterday's news is never shown
    with pytest.raises(meta_client.MetaError):
        briefing.look_up(connection, "news", TOWN)


def test_without_her_town_nothing_is_looked_up(monkeypatch, connection, clock):
    searches = Searches(monkeypatch)
    meteo = OpenMeteo(monkeypatch)
    assert briefing.look_up(connection, "news", "") is None
    assert briefing.look_up(connection, "weather", "") is None
    assert searches.calls == [] and meteo.calls == []


# ---------- Today's weather, from Open-Meteo ----------

PLACES = [
    {"name": "Portland", "admin1": "Maine", "country_code": "US", "latitude": 43.66, "longitude": -70.26},
    {"name": "Portland", "admin1": "Oregon", "country_code": "US", "latitude": 45.52, "longitude": -122.68},
]
CLOUDY = {"text": "Cloudy today, with a high of 48 and a low of 41.", "sites": ["Open-Meteo.com"], "from": "Weather from"}


class OpenMeteo:
    """A fake briefing._http.get: Open-Meteo's geocoder, then its forecast."""

    def __init__(self, monkeypatch, code=3, high=47.7, low=40.5, rain=1, places=PLACES, fail=False):
        self.code, self.high, self.low, self.rain, self.places, self.fail = code, high, low, rain, places, fail
        self.calls = []
        monkeypatch.setattr(briefing._http, "get", self)

    def __call__(self, url, params=None, timeout=None):
        self.calls.append((url, params))
        if self.fail:
            raise requests.ConnectionError("no internet")
        if "geocoding" in url:
            return N(raise_for_status=lambda: None, json=lambda: {"results": self.places})
        daily = {"weather_code": [self.code], "temperature_2m_max": [self.high], "temperature_2m_min": [self.low],
                 "precipitation_probability_max": [self.rain]}
        return N(raise_for_status=lambda: None, json=lambda: {"daily": daily})


@pytest.mark.parametrize("code, high, low, rain, words", [
    (3, 47.7, 40.5, 1, "Cloudy today, with a high of 48 and a low of 41."),
    (0, 71.2, 50.0, 0, "Clear skies today, with a high of 71 and a low of 50."),
    (61, 55.4, 44.9, 80, "Light rain today, with a high of 55 and a low of 45. The chance of rain is 80%."),
    (2, 60.0, 48.0, 45, "Partly cloudy today, with a high of 60 and a low of 48. The chance of rain is 45%."),
    (999, 60.0, 48.0, 10, "Changeable weather today, with a high of 60 and a low of 48."),
])
def test_the_weather_is_said_in_plain_words_from_a_fixed_table(code, high, low, rain, words):
    assert briefing.weather_words(code, high, low, rain) == words


def test_the_weather_comes_from_open_meteo_for_her_own_portland(monkeypatch, connection, clock):
    meteo = OpenMeteo(monkeypatch)
    assert briefing.look_up(connection, "weather", TOWN) == CLOUDY
    geocode, forecast = meteo.calls
    assert geocode[1]["name"] == "Portland"  # only the town's name goes out, never hers
    assert (forecast[1]["latitude"], forecast[1]["longitude"]) == (45.52, -122.68), "Oregon, not Maine"
    assert forecast[1]["temperature_unit"] == "fahrenheit" and forecast[1]["forecast_days"] == 1


def test_the_weather_is_kept_for_three_hours_and_is_never_a_web_search(monkeypatch, connection, clock):
    meteo = OpenMeteo(monkeypatch)
    searches = Searches(monkeypatch)
    first = briefing.look_up(connection, "weather", TOWN)
    clock.set(10, 59)
    assert briefing.look_up(connection, "weather", TOWN) == first
    assert len(meteo.calls) == 2  # the geocoder and the forecast, once
    clock.set(11, 1)
    briefing.look_up(connection, "weather", TOWN)
    assert len(meteo.calls) == 4
    assert searches.calls == [] and briefing.searches_today(connection, clock.now) == 0


def test_a_town_open_meteo_doesnt_know_has_no_weather(monkeypatch, connection, clock):
    OpenMeteo(monkeypatch, places=[])
    assert briefing.look_up(connection, "weather", "Nowhere, Oregon") is None


def test_when_open_meteo_cant_be_reached_the_last_forecast_from_today_is_kept(monkeypatch, connection, clock):
    OpenMeteo(monkeypatch)
    morning = briefing.look_up(connection, "weather", TOWN)
    OpenMeteo(monkeypatch, fail=True)
    clock.set(12)  # over 3 hours later: a new look is due, and it fails
    assert briefing.look_up(connection, "weather", TOWN) == morning
    clock.set(8, day=31)  # but yesterday's weather is never shown
    with pytest.raises(briefing.WeatherError):
        briefing.look_up(connection, "weather", TOWN)


# ---------- Buddy's tool, the Home row, and her town ----------

def tool_context(connection, town=TOWN):
    db.get_profile(connection)  # makes her profile row
    connection.execute("UPDATE profile SET city = ? WHERE id = 1", (town,))
    return {"connection": connection, "profile": db.get_profile(connection), "conversation_id": "day", "mode": "chat"}


def test_buddy_can_look_up_the_weather_and_shows_where_it_came_from(monkeypatch, connection, clock):
    OpenMeteo(monkeypatch)
    result, actions = tools.run_tool("look_up_today", json.dumps({"topic": "weather"}), tool_context(connection))
    assert result == {"ok": True, "found": "Cloudy today, with a high of 48 and a low of 41.", "from": ["Open-Meteo.com"]}
    assert actions == [{"type": "sources", "sites": ["Open-Meteo.com"], "from": "Weather from"}]


def test_only_the_weather_news_or_sports_can_be_looked_up(monkeypatch, connection, clock):
    searches = Searches(monkeypatch)
    result, actions = tools.run_tool("look_up_today", json.dumps({"topic": "blood pressure pills"}),
                                     tool_context(connection))
    assert result["ok"] is False and actions == [] and searches.calls == []


def test_without_her_town_buddy_says_a_family_member_can_add_it(monkeypatch, connection, clock):
    Searches(monkeypatch)
    result, _ = tools.run_tool("look_up_today", json.dumps({"topic": "weather"}), tool_context(connection, ""))
    assert result["ok"] is False and "Settings" in result["error"]


def test_her_town_is_part_of_her_profile():
    client = TestClient(app)
    assert client.put("/api/profile", json={"city": TOWN}).status_code == 200
    assert client.get("/api/profile").json()["city"] == TOWN


NOTHING = {"text": "", "sites": [], "from": ""}


def test_home_gets_the_weather(monkeypatch, clock):
    OpenMeteo(monkeypatch)
    client = TestClient(app)
    # No town yet is normal, not an error (a browser logs every 404 as one): nothing to show.
    assert client.get("/api/briefing/weather").json() == NOTHING
    client.put("/api/profile", json={"city": TOWN})
    assert client.get("/api/briefing/weather").json() == CLOUDY
    assert client.get("/api/briefing/horoscope").status_code == 404


def test_when_open_meteo_cant_be_reached_home_just_shows_no_weather(monkeypatch, clock):
    OpenMeteo(monkeypatch, fail=True)
    client = TestClient(app)
    client.put("/api/profile", json={"city": TOWN})
    answer = client.get("/api/briefing/weather")
    assert (answer.status_code, answer.json()) == (200, NOTHING)


def test_a_talk_shows_where_the_news_came_from(monkeypatch, clock):
    Searches(monkeypatch, text="The Rose Festival parade is on Saturday at 10.",
             sources=[{"title": "Parade", "url": "https://www.kgw.com/parade"}])
    client = TestClient(app)
    client.put("/api/profile", json={"preferred_name": "Rose", "city": TOWN})
    use_fake(monkeypatch, tool_call("c1", "look_up_today", {"topic": "news"}),
             reply("There's a parade on Saturday at 10!"))
    body = chat(client, "Anything happening in town?")
    assert {"type": "sources", "sites": ["kgw.com"], "from": "From the web:"} in body["actions"]
