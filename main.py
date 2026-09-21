# -*- coding: utf-8 -*-
"""
어제의 박스오피스 순위를 보여주는 스트림릿 앱
- KOBIS(영화진흥위원회) 일별 박스오피스 API 사용
- 스트림릿 클라우드 배포를 염두에 두고 작성함
"""

import requests
import pandas as pd
import streamlit as st
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo  # 파이썬 내장 시간대 모듈 (별도 설치 불필요)

# ----------------------------------------------------------------------
# 1) 기본 설정
# ----------------------------------------------------------------------
st.set_page_config(page_title="날짜별 박스오피스", page_icon="🎬", layout="wide")

API_URL = "https://www.kobis.or.kr/kobisopenapi/webservice/rest/boxoffice/searchDailyBoxOfficeList.json"

# 인증키는 절대 코드에 직접 쓰지 않고, 스트림릿 클라우드의 secrets(비밀 금고)에서 불러온다.
# 배포 시 앱 설정 > Secrets 에 아래처럼 등록해두면 된다.
#   KOBIS_KEY = "발급받은_인증키"
try:
    KOBIS_KEY = st.secrets["KOBIS_KEY"]
except Exception:
    KOBIS_KEY = None


def get_yesterday_kst_date():
    """
    한국 시간(KST) 기준으로 '어제' 날짜를 date 객체로 계산해서 돌려준다.
    배포 서버가 한국 시간을 쓰지 않을 수 있으므로, UTC 등 서버 시각에 의존하지 않고
    zoneinfo로 명시적으로 한국 시간대를 지정해서 계산한다.
    이 날짜가 달력에서 고를 수 있는 '가장 늦은 날짜'가 된다. (오늘 건 아직 집계 전이라서)
    """
    now_kst = datetime.now(ZoneInfo("Asia/Seoul"))
    yesterday_kst = now_kst - timedelta(days=1)
    return yesterday_kst.date()


# ----------------------------------------------------------------------
# 2) API 호출 함수 (같은 날짜는 1시간 동안 결과를 기억해서 재호출하지 않음)
# ----------------------------------------------------------------------
@st.cache_data(ttl=3600)  # ttl=3600초 = 1시간 동안 캐시(기억) 유지
def fetch_box_office(target_dt: str, api_key: str):
    """
    KOBIS API를 호출해서 (상태, 데이터 또는 안내메시지) 형태로 돌려준다.
    상태는 세 가지 중 하나:
      "ok"    -> 두 번째 값은 영화 리스트
      "empty" -> 그 날짜는 아직 집계가 안 된 경우 (영화 목록이 비어 있음)
      "error" -> 두 번째 값은 화면에 보여줄 한국어 안내 메시지
    """
    params = {"key": api_key, "targetDt": target_dt}

    # 2-1) 네트워크 요청 자체가 실패하는 경우 (타임아웃, 연결 오류 등)
    try:
        response = requests.get(API_URL, params=params, timeout=10)
    except requests.exceptions.RequestException:
        return "error", (
            "KOBIS 서버에 연결하지 못했습니다. 인터넷 연결 상태나 "
            "KOBIS 서버 상태를 확인해 주세요."
        )

    # 2-2) 상태 코드가 200이 아닌 경우 (문서에는 없지만 방어적으로 체크)
    if response.status_code != 200:
        return "error", (
            f"KOBIS 서버가 정상 응답하지 않았습니다 (상태 코드: {response.status_code}). "
            "잠시 후 다시 시도해 주세요."
        )

    # 2-3) 응답이 JSON 형식이 아닌 경우
    try:
        data = response.json()
    except ValueError:
        return "error", "KOBIS 서버 응답을 해석할 수 없습니다. 잠시 후 다시 시도해 주세요."

    # 2-4) 인증키가 틀렸거나 문제가 있으면 상태코드는 200이지만 faultInfo가 들어있다.
    if "faultInfo" in data:
        message = data["faultInfo"].get("message", "알 수 없는 오류")
        return "error", (
            f"KOBIS API 오류가 발생했습니다: {message}\n"
            "발급받은 인증키(KOBIS_KEY)가 올바른지, secrets에 정확히 등록했는지 확인해 주세요."
        )

    # 2-5) 정상 구조인지 확인
    box_office_result = data.get("boxOfficeResult")
    if not box_office_result:
        return "error", "응답 형식이 예상과 다릅니다. KOBIS API 문서가 변경되었는지 확인해 주세요."

    movie_list = box_office_result.get("dailyBoxOfficeList")

    # 2-6) 영화 목록이 비어 있는 경우 -> 그 날짜는 아직 집계 전이라는 뜻
    if not movie_list:
        return "empty", None

    return "ok", movie_list


# ----------------------------------------------------------------------
# 3) 화면에 안내 메시지를 보여주는 헬퍼 함수
# ----------------------------------------------------------------------
def show_guide_message(message: str):
    """빈 화면 대신, 무엇을 확인해야 하는지 안내 문구를 보여준다."""
    st.error(message)
    st.info(
        "확인 체크리스트\n\n"
        "1. 스트림릿 클라우드 앱 설정 > Secrets 에 KOBIS_KEY가 등록되어 있는지\n"
        "2. 인증키 값이 정확히 복사되었는지 (앞뒤 공백 포함 여부)\n"
        "3. KOBIS 서비스 상태(점검 여부)나 요청 횟수 제한을 초과하지 않았는지"
    )


# ----------------------------------------------------------------------
# 4) 메인 화면 구성
# ----------------------------------------------------------------------
st.title("🎬 날짜별 박스오피스")

# 인증키가 아예 설정되지 않은 경우, API를 호출하기 전에 먼저 안내한다.
if not KOBIS_KEY:
    show_guide_message(
        "KOBIS_KEY가 설정되어 있지 않습니다. "
        "스트림릿 클라우드의 Secrets에 KOBIS_KEY를 등록해 주세요."
    )
    st.stop()

max_selectable_date = get_yesterday_kst_date()  # 고를 수 있는 가장 늦은 날짜 = 어제(한국시간)

# 달력에서 날짜를 고를 수 있는 위젯. 오늘 날짜는 아직 집계 전이라 고를 수 없게 막아둔다.
selected_date = st.date_input(
    "조회할 날짜를 선택하세요 (오늘 날짜는 아직 집계 전이라 선택할 수 없습니다)",
    value=max_selectable_date,
    max_value=max_selectable_date,
)

target_dt = selected_date.strftime("%Y%m%d")  # API에 보낼 yyyymmdd 형식
st.caption(f"선택한 날짜: {selected_date.strftime('%Y-%m-%d')}")

status, result = fetch_box_office(target_dt, KOBIS_KEY)

if status == "empty":
    # 영화 목록이 비어서 온 경우 -> 그날은 아직 집계가 안 된 것
    st.warning("그날은 아직 집계 전입니다. 다른 날짜를 선택해 보세요.")
    st.stop()

if status == "error":
    # result에는 한국어 안내 메시지가 들어있다.
    show_guide_message(result)
    st.stop()

movie_list = result  # API에서 받은 원본 리스트 (딕셔너리들의 리스트)

# ----------------------------------------------------------------------
# 5) 데이터프레임으로 변환하고, 문자열 숫자를 실제 숫자로 바꾸기
# ----------------------------------------------------------------------
df = pd.DataFrame(movie_list)

# API에서 숫자 값들이 전부 문자열로 오기 때문에, 정렬/그래프에 쓰려면 숫자로 바꿔줘야 한다.
numeric_columns = ["rank", "rankInten", "audiCnt", "audiAcc", "scrnCnt", "showCnt"]
for col in numeric_columns:
    if col in df.columns:
        df[col] = pd.to_numeric(df[col], errors="coerce")

# 순위 기준으로 정렬 (원래도 순위순으로 오지만, 명시적으로 한 번 더 정렬)
df = df.sort_values("rank").reset_index(drop=True)

# ----------------------------------------------------------------------
# 6) 1위 영화 - 지표 카드 3장으로 크게 보여주기
# ----------------------------------------------------------------------
st.subheader("1위 영화")

top_movie = df.iloc[0]

col1, col2, col3 = st.columns(3)
col1.metric("영화명", top_movie["movieNm"])
col2.metric("그날 관객수", f"{int(top_movie['audiCnt']):,}명")
col3.metric("누적 관객수", f"{int(top_movie['audiAcc']):,}명")

st.divider()

# ----------------------------------------------------------------------
# 7) 전체 순위 표
# ----------------------------------------------------------------------
st.subheader("전체 순위")


def make_rank_change_text(value) -> str:
    """
    rankInten(전날 대비 순위 증감) 숫자를 화살표가 붙은 글자로 바꾼다.
    양수(값이 큼) = 순위가 오름 -> 빨간 위 화살표
    음수 = 순위가 내림 -> 파란 아래 화살표
    0 = 변동 없음
    """
    if pd.isna(value) or value == 0:
        return "- 0"
    if value > 0:
        return f"▲ {int(value)}"
    return f"▼ {int(abs(value))}"


def make_movie_name_text(row) -> str:
    """누적관객수가 100만 명을 넘으면 영화명 옆에 트로피 이모지를 붙인다."""
    name = row["movieNm"]
    if pd.notna(row["audiAcc"]) and row["audiAcc"] >= 1_000_000:
        return f"{name} 🏆"
    return name


def style_rank_change(value: str):
    """화살표 문자열의 글자 색을 정해주는 스타일 함수. (빨강=상승, 파랑=하강)"""
    if isinstance(value, str) and value.startswith("▲"):
        return "color: red; font-weight: bold;"
    if isinstance(value, str) and value.startswith("▼"):
        return "color: blue; font-weight: bold;"
    return ""


# 화면에 보여줄 컬럼만 골라서 한글 이름으로 바꾼다.
table_df = df[["rank", "movieNm", "openDt", "audiCnt", "audiAcc", "scrnCnt"]].copy()
table_df["movieNm"] = df.apply(make_movie_name_text, axis=1)
table_df["순위변동"] = df["rankInten"].apply(make_rank_change_text)
table_df = table_df[["rank", "movieNm", "순위변동", "openDt", "audiCnt", "audiAcc", "scrnCnt"]]
table_df.columns = ["순위", "영화명", "순위변동", "개봉일", "관객수", "누적관객수", "스크린수"]

# Styler로 '순위변동' 칸에만 색을 입혀서 보여준다.
# pandas 버전에 따라 메서드 이름이 다르다: 최신 버전은 style.map, 옛날 버전은 style.applymap을 쓴다.
# 둘 다 지원하도록 있는 것을 골라서 쓴다.
styler = table_df.style
style_func = styler.map if hasattr(styler, "map") else styler.applymap
styled_table = style_func(style_rank_change, subset=["순위변동"])
st.dataframe(styled_table, use_container_width=True, hide_index=True)

st.divider()

# ----------------------------------------------------------------------
# 8) 관객수 상위 5편 - 막대그래프
# ----------------------------------------------------------------------
st.subheader("관객수 상위 5편")

top5 = df.sort_values("audiCnt", ascending=False).head(5)

# 그래프 x축에 영화명을 쓰기 위해 인덱스를 영화명으로 설정
chart_data = top5.set_index("movieNm")["audiCnt"]

st.bar_chart(chart_data)
