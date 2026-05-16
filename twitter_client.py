import os
import tweepy


def get_client():
    return tweepy.Client(
        bearer_token=os.getenv("TWITTER_BEARER_TOKEN"),
        consumer_key=os.getenv("TWITTER_API_KEY"),
        consumer_secret=os.getenv("TWITTER_API_SECRET"),
        access_token=os.getenv("TWITTER_ACCESS_TOKEN"),
        access_token_secret=os.getenv("TWITTER_ACCESS_TOKEN_SECRET"),
        wait_on_rate_limit=True,
    )


def get_my_user_id(client: tweepy.Client) -> str:
    resp = client.get_me(user_auth=True)
    if not resp.data:
        raise ValueError("Не удалось определить твой аккаунт — проверь TWITTER_ACCESS_TOKEN")
    return str(resp.data.id)


def get_target_user_id(client: tweepy.Client, username: str) -> str:
    resp = client.get_user(username=username, user_auth=False)
    if not resp.data:
        raise ValueError(f"Аккаунт @{username} не найден")
    return str(resp.data.id)


def get_liked_tweet_ids(client: tweepy.Client, my_user_id: str) -> set[str]:
    resp = client.get_liked_tweets(
        id=my_user_id,
        max_results=100,
        tweet_fields=["id"],
        user_auth=True,
    )
    if not resp.data:
        return set()
    return {str(t.id) for t in resp.data}


def get_last_3_posts(username: str) -> tuple[list[dict], list[dict]]:
    """Returns (unliked, all_tweets) for the last 3 posts of username."""
    client = get_client()
    my_user_id = get_my_user_id(client)
    target_user_id = get_target_user_id(client, username)
    liked_ids = get_liked_tweet_ids(client, my_user_id)

    resp = client.get_users_tweets(
        id=target_user_id,
        max_results=5,
        tweet_fields=["id", "text", "created_at"],
        exclude=["retweets", "replies"],
    )
    if not resp.data:
        return [], []

    all_tweets, unliked = [], []
    for tweet in resp.data[:3]:
        t = {
            "id": str(tweet.id),
            "text": tweet.text,
            "url": f"https://x.com/{username}/status/{tweet.id}",
            "liked": str(tweet.id) in liked_ids,
        }
        all_tweets.append(t)
        if not t["liked"]:
            unliked.append(t)

    return unliked, all_tweets
