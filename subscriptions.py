import json
import os

_SUBS_FILE = os.path.join(os.path.dirname(__file__), "subscriptions.json")
_SENT_FILE = os.path.join(os.path.dirname(__file__), "sent_tweets.json")


def _load(path: str) -> dict:
    if not os.path.exists(path):
        return {}
    with open(path) as f:
        return json.load(f)


def _save(path: str, data: dict):
    with open(path, "w") as f:
        json.dump(data, f, indent=2)


def load_subs() -> dict:
    return _load(_SUBS_FILE)


def get_user_subs(user_id: int) -> list[str]:
    return _load(_SUBS_FILE).get(str(user_id), [])


def add_sub(user_id: int, username: str) -> bool:
    data = _load(_SUBS_FILE)
    key = str(user_id)
    subs = data.get(key, [])
    if any(u.lower() == username.lower() for u in subs):
        return False
    data[key] = subs + [username]
    _save(_SUBS_FILE, data)
    return True


def remove_sub(user_id: int, username: str) -> bool:
    data = _load(_SUBS_FILE)
    key = str(user_id)
    before = data.get(key, [])
    after = [u for u in before if u.lower() != username.lower()]
    if len(before) == len(after):
        return False
    data[key] = after
    _save(_SUBS_FILE, data)
    return True


def was_sent(user_id: int, username: str, tweet_id: str) -> bool:
    data = _load(_SENT_FILE)
    return tweet_id in data.get(str(user_id), {}).get(username.lower(), [])


def mark_sent(user_id: int, username: str, tweet_id: str):
    data = _load(_SENT_FILE)
    key = str(user_id)
    uname = username.lower()
    data.setdefault(key, {}).setdefault(uname, [])
    if tweet_id not in data[key][uname]:
        data[key][uname].append(tweet_id)
    _save(_SENT_FILE, data)
