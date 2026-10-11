import os
import re

from googleapiclient.discovery import build


OFFICIAL_HINTS = (
    "official artist channel",
    "vevo",
    "official music",
    "공식",
    "뮤직비디오",
    "music video",
)

UNOFFICIAL_HINTS = (
    "cover",
    "커버",
    "karaoke",
    "노래방",
    "반주",
    "가사",
    "lyrics",
    "reaction",
    "리액션",
    "직캠",
    "live",
    "라이브",
    "remix",
)


def youtube_client():
    api_key = os.getenv("YOUTUBE_API_KEY")
    if not api_key:
        raise RuntimeError("YOUTUBE_API_KEY 환경변수가 없습니다.")
    return build("youtube", "v3", developerKey=api_key)


def normalize(value):
    value = value.lower()
    value = re.sub(r"\[[^\]]*\]|\([^)]*\)", " ", value)
    value = re.sub(r"[^0-9a-z가-힣]+", " ", value)
    return " ".join(value.split())


def search_official_candidates(title, artist, max_results=10):
    youtube = youtube_client()
    query = f'{artist} {title} official music video'

    response = youtube.search().list(
        part="snippet",
        q=query,
        type="video",
        maxResults=max_results,
        regionCode="KR",
        relevanceLanguage="ko",
        safeSearch="none",
    ).execute()

    candidates = []
    wanted_title = normalize(title)
    wanted_artist = normalize(artist)

    for item in response.get("items", []):
        video_id = item["id"].get("videoId")
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

        # 이름이 비슷한 채널만으로 공식 인증을 단정하지 않는다.
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

    return sorted(candidates, key=lambda x: x["score"], reverse=True)


def choose_candidate(candidates, minimum_score=9):
    """
    점수는 검색 후보 정렬용이다.
    높은 점수도 공식 음원임을 증명하지 않으므로,
    검증 전에는 자동 등록하지 않는다.
    """
    if not candidates:
        return None

    best = candidates[0]
    if best["score"] < minimum_score:
        return None

    if not best["official_verified"]:
        return None

    return best