import json
import os
from pathlib import Path

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build


SCOPES = ["https://www.googleapis.com/auth/youtube"]
TOKEN_FILE = Path("token.json")
CLIENT_FILE = Path("credentials.json")


def get_youtube_service():
    creds = None

    if TOKEN_FILE.exists():
        creds = Credentials.from_authorized_user_file(
            str(TOKEN_FILE), SCOPES
        )

    if creds and creds.expired and creds.refresh_token:
        creds.refresh(Request())

    if not creds or not creds.valid:
        if not CLIENT_FILE.exists():
            raise FileNotFoundError(
                "Google Cloud에서 OAuth 클라이언트 JSON을 내려받아 "
                "프로젝트 루트에 credentials.json으로 저장하세요."
            )

        flow = InstalledAppFlow.from_client_secrets_file(
            str(CLIENT_FILE), SCOPES
        )
        creds = flow.run_local_server(
            host="localhost",
            port=0,
            open_browser=False,
        )

        TOKEN_FILE.write_text(
            creds.to_json(), encoding="utf-8"
        )

    return build("youtube", "v3", credentials=creds)


def create_playlist(title, description="TJ미디어 랭킹 기반 플레이리스트"):
    youtube = get_youtube_service()

    response = youtube.playlists().insert(
        part="snippet,status",
        body={
            "snippet": {
                "title": title[:150],
                "description": description[:5000],
                "defaultLanguage": "ko",
            },
            "status": {
                "privacyStatus": "private",
            },
        },
    ).execute()

    return {
        "id": response["id"],
        "url": f'https://www.youtube.com/playlist?list={response["id"]}',
    }


def add_video(playlist_id, video_id, position):
    youtube = get_youtube_service()

    return youtube.playlistItems().insert(
        part="snippet",
        body={
            "snippet": {
                "playlistId": playlist_id,
                "position": position,
                "resourceId": {
                    "kind": "youtube#video",
                    "videoId": video_id,
                },
            }
        },
    ).execute()


def create_from_tracks(title, tracks):
    """
    tracks: [{"video_id": "...", "title": "..."} ...]
    입력 순서대로 영상을 등록한다.
    """
    playlist = create_playlist(title)
    added = []
    failed = []

    for position, track in enumerate(tracks):
        try:
            add_video(
                playlist["id"],
                track["video_id"],
                position,
            )
            added.append(track)
        except Exception as exc:
            failed.append({
                "track": track,
                "error": str(exc),
            })

    return {
        **playlist,
        "added": added,
        "failed": failed,
    }
