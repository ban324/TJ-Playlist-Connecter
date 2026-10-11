import os

import pandas as pd
import streamlit as st
from dotenv import load_dotenv

from tj_chart import GENRES, get_chart
from youtube_search import search_official_candidates
from youtube_playlist import create_from_tracks
from pathlib import Path
from dotenv import load_dotenv

load_dotenv(dotenv_path=Path(__file__).resolve().parent / ".env")


st.set_page_config(
    page_title="TJ Music Playlist",
    page_icon="🎵",
    layout="wide",
)

st.title("🎵 TJ미디어 랭킹 플레이리스트")
st.caption("TJ미디어 차트에서 곡을 가져와 YouTube 재생목록을 만듭니다.")

with st.sidebar:
    st.header("차트 설정")
    genre = st.selectbox("장르", list(GENRES.keys()))
    limit = st.select_slider(
        "가져올 순위",
        options=[10, 20, 30, 50, 100],
        value=50,
    )
    load_button = st.button("차트 불러오기", type="primary")

if load_button:
    try:
        with st.spinner("TJ미디어 차트를 불러오는 중..."):
            chart = get_chart(genre, limit)
        st.session_state["chart"] = chart
        st.session_state.pop("candidates", None)
    except Exception as exc:
        st.error(f"차트 수집 실패: {exc}")

chart = st.session_state.get("chart")

if chart is not None:
    st.subheader(f"{genre} 차트")
    st.dataframe(chart, use_container_width=True, hide_index=True)

    st.download_button(
        "차트 CSV 다운로드",
        data=chart.to_csv(index=False).encode("utf-8-sig"),
        file_name=f"tj_chart_{genre}.csv",
        mime="text/csv",
    )

    if st.button("유튜브 영상 검색"):
        results = []
        progress = st.progress(0)

        for i, row in chart.iterrows():
            try:
                candidates = search_official_candidates(
                    str(row["title"]),
                    str(row["artist"]),
                )
                best = candidates[0] if candidates else None

                results.append({
                    "rank": int(row["rank"]),
                    "title": row["title"],
                    "artist": row["artist"],
                    "video_id": best["video_id"] if best else "",
                    "video_title": best["title"] if best else "",
                    "channel": best["channel"] if best else "",
                    "score": best["score"] if best else 0,
                    "url": best["url"] if best else "",
                })
            except Exception as exc:
                results.append({
                    "rank": int(row["rank"]),
                    "title": row["title"],
                    "artist": row["artist"],
                    "video_id": "",
                    "video_title": f"검색 오류: {exc}",
                    "channel": "",
                    "score": 0,
                    "url": "",
                })

            progress.progress((i + 1) / len(chart))

        st.session_state["candidates"] = pd.DataFrame(results)

candidates = st.session_state.get("candidates")

if candidates is not None:
    st.subheader("유튜브 검색 결과")
    st.warning(
        "검색 상위 결과가 공식 음원이라는 보장은 없습니다. "
        "아래에서 실제 추가할 영상을 확인하세요."
    )

    st.dataframe(
        candidates[
            ["rank", "title", "artist", "video_title", "channel", "url"]
        ],
        use_container_width=True,
        hide_index=True,
    )

    # 사용자가 실제로 확인한 영상만 등록 대상으로 선택한다.
    available = candidates[candidates["video_id"] != ""].copy()

    if not available.empty:
        selected_rows = st.multiselect(
            "플레이리스트에 추가할 곡 선택",
            options=available.index.tolist(),
            default=available.index.tolist(),
            format_func=lambda idx: (
                f'{available.loc[idx, "rank"]}. '
                f'{available.loc[idx, "artist"]} - '
                f'{available.loc[idx, "title"]}'
            ),
        )

        playlist_title = st.text_input(
            "플레이리스트 제목",
            value=f"TJ미디어 {genre} TOP {len(chart)}",
        )

        confirmed = st.checkbox(
            "선택한 영상이 원하는 공식 음원인지 확인했습니다."
        )

        if st.button("유튜브 플레이리스트 생성", type="primary"):
            if not confirmed:
                st.error("영상 확인 후 체크박스를 선택하세요.")
            elif not selected_rows:
                st.error("최소 한 곡을 선택하세요.")
            else:
                tracks = []
                for idx in selected_rows:
                    row = candidates.loc[idx]
                    tracks.append({
                        "video_id": row["video_id"],
                        "title": row["title"],
                    })

                try:
                    with st.spinner("플레이리스트 생성 중..."):
                        result = create_from_tracks(
                            playlist_title, tracks
                        )

                    st.success("플레이리스트 생성 요청이 완료됐습니다.")
                    st.link_button(
                        "유튜브 플레이리스트 열기",
                        result["url"],
                    )
                    st.write(f"성공: {len(result['added'])}곡")
                    st.write(f"실패: {len(result['failed'])}곡")

                    if result["failed"]:
                        st.dataframe(
                            pd.DataFrame(result["failed"]),
                            use_container_width=True,
                        )
                except Exception as exc:
                    st.error(f"플레이리스트 생성 실패: {exc}")
    else:
        st.info("추가할 수 있는 영상 검색 결과가 없습니다.")
else:
    st.info("사이드바에서 장르를 선택하고 차트를 불러오세요.")
