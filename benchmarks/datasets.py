"""Deterministic evaluation corpora with known topics.

* ``SAMPLE_MEETING``: a short, realistic meeting (no verbatim repeats).
* ``make_group_chat``: 8 topics x 4 fixed messages, repeated verbatim (easy case).
* ``make_conversation``: 8 topics with *templated* messages: topic nouns change,
  but generic words ("needs", "before", "really"), names and weekdays are shared
  by every topic, as in a real chat. Returns Whisper-like segments with
  timestamps and the true topic of every message, so quality can be scored.
"""

from __future__ import annotations

import random
from dataclasses import dataclass, field

# Realistic meeting: recurring phrases, fillers ("Okay.", "Yes."), no verbatim repeats.
SAMPLE_MEETING = (
    "Good morning everyone, let's start the weekly product meeting. "
    "First item is the release date for the mobile app. "
    "The mobile app release date depends on the payment integration. "
    "Maria said the payment integration is blocked by the bank API. "
    "The bank API sandbox keeps timing out during tests. "
    "Okay. Right. "
    "We could mock the bank API to unblock the mobile app team. "
    "Second item is customer feedback from the beta. "
    "Customer feedback says onboarding is too long. "
    "Several beta users dropped during onboarding on the third screen. "
    "John will redesign the onboarding flow with fewer steps. "
    "Customer feedback also mentions slow search results. "
    "Search results are slow because the data pipeline runs nightly. "
    "The data pipeline should move to hourly updates. "
    "Moving the data pipeline needs more cloud budget. "
    "Cloud budget approval comes from finance next week. "
    "Yes. "
    "Last item, the hiring plan for two backend engineers. "
    "Backend engineers would own the data pipeline and the bank API work. "
    "We will review the release date again next Monday."
)

# Synthetic group chat: 8 unrelated topics, interleaved messages and chat filler.
GROUP_CHAT_TOPICS = {
    "trip": ["Lisbon trip flights are cheaper on Tuesday", "we should book the Lisbon hotel near the river",
             "the trip itinerary needs a day for Sintra", "flights and hotel for the trip cost about the same"],
    "birthday": ["Ana birthday party is on Saturday night", "who is bringing the birthday cake for Ana",
                 "the party playlist needs more dance songs", "birthday gift ideas for Ana include a camera"],
    "rent": ["the apartment rent goes up next month", "landlord wants the rent transfer before Friday",
             "we split the rent and electricity bill evenly", "the apartment heating bill was huge this winter"],
    "football": ["the football match starts at eight tonight", "our football team needs a new striker",
                 "the match tickets sold out in minutes", "the striker scored twice in the last match"],
    "project": ["the client project deadline moved to Monday", "the project database migration broke the login",
                "we need tests before the project release", "client wants the release notes for the database change"],
    "recipes": ["the lasagna recipe needs fresh basil", "dinner recipe for Sunday is vegetable curry",
                "curry spices are in the kitchen cabinet", "lasagna dinner feeds six people"],
    "gym": ["the gym membership renews in March", "gym classes on Thursday focus on strength training",
            "strength training plan has four sessions weekly", "the gym locker room is being renovated"],
    "movies": ["the new science fiction movie is great", "movie night this Friday with popcorn",
               "science fiction series recommendations anyone", "the cinema has a movie marathon on Sunday"],
}

CHAT_FILLER = ["lol", "yeah", "ok", "haha true", "wait what", "omg", "sure", "nice", "same"]


def make_group_chat(n_msgs=400, seed=7, topics=None, punct=True):
    """Deterministic chat transcript: topic switches, 30% filler messages."""
    import random

    topics = topics or GROUP_CHAT_TOPICS
    rnd = random.Random(seed)
    names = list(topics)
    current, out = rnd.choice(names), []
    for _ in range(n_msgs):
        if rnd.random() < 0.25:
            current = rnd.choice(names)
        msg = rnd.choice(CHAT_FILLER) if rnd.random() < 0.3 else rnd.choice(topics[current])
        out.append(msg + ("." if punct else ""))
    return " ".join(out)


# --- templated conversation ------------------------------------------------------------

CONVERSATION_TOPICS = {
    "trip": ["lisbon", "hotel", "flights", "itinerary", "passport", "sintra"],
    "birthday": ["birthday", "cake", "party", "playlist", "balloons", "gift"],
    "rent": ["rent", "landlord", "apartment", "electricity", "heating", "deposit"],
    "football": ["football", "striker", "tickets", "stadium", "goalkeeper", "league"],
    "project": ["client", "database", "deadline", "migration", "release", "invoice"],
    "recipes": ["lasagna", "curry", "basil", "oven", "recipe", "spices"],
    "gym": ["gym", "membership", "treadmill", "workout", "locker", "trainer"],
    "movies": ["cinema", "movie", "popcorn", "trailer", "sequel", "director"],
}

TEMPLATES = [
    "{name} thinks the {a} needs another look before {day}",
    "did anyone check the {a} for the {b} yet",
    "the new {a} is really great",
    "I want to talk about the {a} and the {b}",
    "we still need to sort out the {a}",
    "the {a} looks good but the {b} is a problem",
    "can someone send the {a} details again",
    "last time the {a} took way too long",
    "I am not sure the {b} works with the {a}",
    "let's decide on the {a} by {day}",
    "{name} already paid for the {a}",
    "the {a} and the {b} are both on the list",
]
NAMES = ["Ana", "Bruno", "Carla", "Diego"]
DAYS = ["Monday", "Tuesday", "Friday", "Saturday"]


@dataclass
class Conversation:
    text: str
    segments: list[dict]
    labels: list[str | None] = field(default_factory=list)  # topic per message (None = filler)
    messages: list[str] = field(default_factory=list)


def make_conversation(n_msgs: int = 400, seed: int = 7, topics: dict | None = None,
                      punct: bool = True, filler_rate: float = 0.3,
                      switch_rate: float = 0.25) -> Conversation:
    """Templated group chat; 1-3 messages per Whisper-like segment, 2-6 s per message."""
    topics = topics or CONVERSATION_TOPICS
    rnd = random.Random(seed)
    names = list(topics)
    current = rnd.choice(names)
    messages: list[str] = []
    labels: list[str | None] = []
    for _ in range(n_msgs):
        if rnd.random() < switch_rate:
            current = rnd.choice(names)
        if rnd.random() < filler_rate:
            msg, label = rnd.choice(CHAT_FILLER), None
        else:
            a, b = rnd.sample(topics[current], 2)
            msg = rnd.choice(TEMPLATES).format(a=a, b=b, name=rnd.choice(NAMES), day=rnd.choice(DAYS))
            msg, label = msg[0].upper() + msg[1:], current
        messages.append(msg + ("." if punct else ""))
        labels.append(label)

    segments, clock, i = [], 0.0, 0
    while i < len(messages):
        group = messages[i:i + rnd.randint(1, 3)]
        duration = sum(rnd.uniform(2.0, 6.0) for _ in group)
        segments.append({"start": round(clock, 2), "end": round(clock + duration, 2), "text": " ".join(group)})
        clock += duration
        i += len(group)
    return Conversation(" ".join(messages), segments, labels, messages)
