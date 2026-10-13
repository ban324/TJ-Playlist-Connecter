
import os
import re
import json
import sqlite3
from pathlib import Path

from googleapiclient.discovery import build
from googleapiclient.errors import HttpError


BASE_DIR = Path(__file__).resolve().parent
CACHE_FILE = BASE_DIR / ".youtube_search_cache.sqlite3"
CACHE_TTL_SECONDS = 60 * 60 * 24 * 30

OFFICIAL_HINTS = (
    "official artist channel",
    "vevo",
    "official music",
    "official video",
    "공식",
    "뮤직비디오",
    "music video",
)

UNOFFICIAL_HINTS = (
    "cover", "커버", "karaoke", "노래방",
    "반주", "가사", "lyrics", "reaction",
    "리액션", "직캠", "live", "라이브", "remix",
)


class QuotaExceededError(RuntimeError):
    """YouTube 검색 할당량 초과."""


def init_cache():
    with sqlite3.connect(CACHE_FILE) as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS search_cache (
                cache_key TEXT PRIMARY KEY,
                created_at INTEGER NOT NULL,
                results TEXT NOT NULL
            )
        """)


def get_cached(key):
    import time

    init_cache()
    with sqlite3.connect(CACHE_FILE) as conn:
        row = conn.execute(
            "SELECT created_at, results FROM search_cache "
            "WHERE cache_key = ?",
            (key,),
        ).fetchone()

    if row is None:
        return None

    created_at, results = row
    if int(time.time()) - created_at > CACHE_TTL_SECONDS:
        with sqlite3.connect(CACHE_FILE) as conn:
            conn.execute(
                "DELETE FROM search_cache WHERE cache_key = ?",
                (key,),
            )
        return None

    return json.loads(results)


def save_cached(key, results):
    import time

    init_cache()
    with sqlite3.connect(CACHE_FILE) as conn:
        conn.execute(
            """
            INSERT OR REPLACE INTO search_cache
            (cache_key, created_at, results)
            VALUES (?, ?, ?)
            """,
            (key, int(time.time()), json.dumps(
                results, ensure_ascii=False
            )),
        )


def youtube_client():
    api_key = os.getenv("YOUTUBE_API_KEY")
    if not api_key:
        raise RuntimeError(
            "YOUTUBE_API_KEY 환경변수가 없습니다."
        )

    return build(
        "youtube",
        "v3",
        developerKey=api_key,
        cache_discovery=False,
    )


def normalize(value):
    value = value.lower()
    value = re.sub(r"\[[^\]]*\]|\([^)]*\)", " ", value)
    value = re.sub(r"[^0-9a-z가-힣ぁ-んァ-ン一-龯]+", " ", value)
    return " ".join(value.split())


def search_official_candidates(title, artist, max_results=10):
    key = json.dumps(
        [normalize(artist), normalize(title), max_results],
        ensure_ascii=False,
    )

    # 이전에 검색한 곡은 API를 호출하지 않습니다.
    cached = get_cached(key)
    if cached is not None:
        return cached

    query = f"{artist} {title} official music video"

    try:
        response = youtube_client().search().list(
            part="snippet",
            q=query,
            type="video",
            maxResults=max_results,
            regionCode="KR",
            relevanceLanguage="ko",
            safeSearch="none",
        ).execute()

    except HttpError as exc:
        message = str(exc).lower()
        if (
            exc.resp.status in (403, 429)
            and any(term in message for term in (
                "quotaexceeded",
                "quota exceeded",
                "ratelimitexceeded",
                "rate limit",
            ))
        ):
            raise QuotaExceededError(
                "YouTube 검색 할당량을 초과했습니다. "
                "추가 검색을 중단했습니다. "
                "할당량 초기화 후 다시 시도하세요."
            ) from exc
        raise

    candidates = []
    wanted_title = normalize(title)
    wanted_artist = normalize(artist)

    for item in response.get("items", []):
        video_id = item.get("id", {}).get("videoId")
        if not video_id:
            continue

        snippet = item.get("snippet", {})
        video_title = snippet.get("title", "")
        channel = snippet.get("channelTitle", "")
        description = snippet.get("description", "")

        combined = normalize(video_title + " " + description)
        normalized_channel = normalize(channel)
        score = 0

        if wanted_title and wanted_title in normalize(video_title):
            score += 5

        if wanted_artist and wanted_artist in normalize(video_title):
            score += 4
        elif wanted_artist and wanted_artist in combined:
            score += 2

        if any(hint in video_title.lower() for hint in OFFICIAL_HINTS):
            score += 2

        if any(hint in video_title.lower() for hint in UNOFFICIAL_HINTS):
            score -= 5

        if wanted_artist and wanted_artist in normalized_channel:
            score += 1

        candidates.append({
            "video_id": video_id,
            "title": video_title,
            "channel": channel,
            "url": f"https://www.youtube.com/watch?v={video_id}",
            "score": score,
            "official_verified": False,
        })

    candidates.sort(key=lambda item: item["score"], reverse=True)

    # 검색 결과가 없는 경우도 캐시해 불필요한 재검색을 막습니다.
    save_cached(key, candidates)
    return candidates


def choose_candidate(candidates, minimum_score=9):
    if not candidates:
        return None

    best = candidates[0]
    if best["score"] < minimum_score:
        return None

    if not best["official_verified"]:
        return None

    return best
