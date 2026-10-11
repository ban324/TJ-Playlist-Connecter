from datetime import date
import json
from pathlib import Path

import pandas as pd
import requests
from bs4 import BeautifulSoup

PAGE_URL = "https://www.tjmedia.com/chart/top100"
API_URL = "https://www.tjmedia.com/legacy/api/topAndHot100"

# 장르별 strType 값은 실제 요청을 확인한 후 추가한다.
# 빈 문자열은 사용자가 확인한 종합 차트 요청 값이다.

GENRES = {
    "종합": "",
    "가요": "1",
    "POP": "2",
    "JPOP": "3",
    "발라드": "4",
    "댄스": "5",
    "트로트": "6",
    "포크": "7",
    "OST": "8",
    "락/메탈": "9",
    "랩/힙합": "10",
    "R&B/어반": "11",
}


def create_session():
    session = requests.Session()
    session.headers.update({
        "User-Agent": "Mozilla/5.0",
        "Accept": "application/json, text/plain, */*",
        "Origin": "https://www.tjmedia.com",
        "Referer": PAGE_URL,
        "X-Requested-With": "XMLHttpRequest",
    })

    response = session.get(PAGE_URL, timeout=30)
    response.raise_for_status()

    soup = BeautifulSoup(response.text, "html.parser")
    token = session.cookies.get("CSRF_TOKEN")

    if not token:
        for selector in (
            'meta[name="_csrf"]',
            'meta[name="csrf-token"]',
        ):
            element = soup.select_one(selector)
            if element:
                token = element.get("content")
                if token:
                    break

    if token:
        session.headers["X-CSRF-TOKEN"] = token

    return session


def fetch_chart(genre="종합", start_date=None, end_date=None):
    if genre not in GENRES:
        raise ValueError(f"지원하지 않는 장르: {genre}")

    str_type = GENRES[genre]

    if str_type is None:
        raise NotImplementedError(
            f"'{genre}'의 strType 값을 아직 확인하지 못했습니다. "
            "TJ 사이트에서 해당 장르를 선택한 요청의 Form Data를 "
            "확인한 후 GENRES에 값을 추가하세요."
        )

    start_date = start_date or date.today().replace(day=1).isoformat()
    end_date = end_date or date.today().isoformat()

    session = create_session()

    response = session.post(
        API_URL,
        data={
            "chartType": "TOP",
            "searchStartDate": start_date,
            "searchEndDate": end_date,
            "strType": str_type,
        },
        timeout=30,
    )
    response.raise_for_status()

    try:
        payload = response.json()
    except requests.exceptions.JSONDecodeError as exc:
        raise RuntimeError(
            f"TJ API가 JSON이 아닌 응답을 반환했습니다: "
            f"{response.text[:300]}"
        ) from exc

    result_data = payload.get("resultData") or {}
    items = result_data.get("items") or []

    if not items:
        raise RuntimeError(
            "TJ API 응답에 곡 목록이 없습니다. "
            f"resultCode={payload.get('resultCode')}, "
            f"응답 키={list(payload.keys())}"
        )

    rows = []

    for item in items:
        rows.append({
            "rank": int(item.get("rank") or len(rows) + 1),
            "song_number": str(item.get("pro") or ""),
            "title": item.get("indexTitle", "").strip(),
            "artist": item.get("indexSong", "").strip(),
            "mv_yn": item.get("mv_yn", ""),
            "thumbnail": item.get("imgthumb_path", ""),
        })

    df = pd.DataFrame(rows)
    df = df[df["title"].ne("") & df["artist"].ne("")]
    df = df.sort_values("rank").reset_index(drop=True)

    return df


def get_chart(genre="종합", limit=100):
    if limit < 1:
        raise ValueError("순위 범위는 1 이상이어야 합니다.")

    chart = fetch_chart(genre=genre)
    return chart.head(limit).copy()


if __name__ == "__main__":
    chart = get_chart("종합", 10)
    print(chart.to_string(index=False))

    Path("data").mkdir(exist_ok=True)
    chart.to_csv(
        "data/tj_chart.csv",
        index=False,
        encoding="utf-8-sig",
    )
    print("\n저장 완료: data/tj_chart.csv")
