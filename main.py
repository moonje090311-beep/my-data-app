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
st.set_page_config(page_title="어제의 박스오피스", page_icon="🎬", layout="wide")

API_URL = "https://www.kobis.or.kr/kobisopenapi/webservice/rest/boxoffice/searchDailyBoxOfficeList.json"

# 인증키는 절대 코드에 직접 쓰지 않고, 스트림릿 클라우드의 secrets(비밀 금고)에서 불러온다.
# 배포 시 앱 설정 > Secrets 에 아래처럼 등록해두면 된다.
#   KOBIS_KEY = "발급받은_인증키"
try:
    KOBIS_KEY = st.secrets["KOBIS_KEY"]
except Exception:
    KOBIS_KEY = None


def get_yesterday_kst() -> str:
    """
    한국 시간(KST) 기준으로 '어제' 날짜를 yyyymmdd 형식 문자열로 계산해서 돌려준다.
    배포 서버가 한국 시간을 쓰지 않을 수 있으므로, UTC 등 서버 시각에 의존하지 않고
    zoneinfo로 명시적으로 한국 시간대를 지정해서 계산한다.
    """
    now_kst = datetime.now(ZoneInfo("Asia/Seoul"))
    yesterday_kst = now_kst - timedelta(days=1)
    return yesterday_kst.strftime("%Y%m%d")


# ----------------------------------------------------------------------
# 2) API 호출 함수 (같은 날짜는 1시간 동안 결과를 기억해서 재호출하지 않음)
# ----------------------------------------------------------------------
@st.cache_data(ttl=3600)  # ttl=3600초 = 1시간 동안 캐시(기억) 유지
def fetch_box_office(target_dt: str, api_key: str):
    """
    KOBIS API를 호출해서 (성공 여부, 데이터 또는 에러메시지) 형태로 돌려준다.
    성공 시: (True, 영화 리스트)
    실패 시: (False, "한국어 안내 메시지")
    """
    params = {"key": api_key, "targetDt": target_dt}

    # 2-1) 네트워크 요청 자체가 실패하는 경우 (타임아웃, 연결 오류 등)
    try:
        response = requests.get(API_URL, params=params, timeout=10)
    except requests.exceptions.RequestException:
        return False, (
            "KOBIS 서버에 연결하지 못했습니다. 인터넷 연결 상태나 "
            "KOBIS 서버 상태를 확인해 주세요."
        )

    # 2-2) 상태 코드가 200이 아닌 경우 (문서에는 없지만 방어적으로 체크)
    if response.status_code != 200:
        return False, (
            f"KOBIS 서버가 정상 응답하지 않았습니다 (상태 코드: {response.status_code}). "
            "잠시 후 다시 시도해 주세요."
        )

    # 2-3) 응답이 JSON 형식이 아닌 경우
    try:
        data = response.json()
    except ValueError:
        return False, "KOBIS 서버 응답을 해석할 수 없습니다. 잠시 후 다시 시도해 주세요."

    # 2-4) 인증키가 틀렸거나 문제가 있으면 상태코드는 200이지만 faultInfo가 들어있다.
    if "faultInfo" in data:
        message = data["faultInfo"].get("message", "알 수 없는 오류")
        return False, (
            f"KOBIS API 오류가 발생했습니다: {message}\n"
            "발급받은 인증키(KOBIS_KEY)가 올바른지, secrets에 정확히 등록했는지 확인해 주세요."
        )

    # 2-5) 정상 구조인지 확인
    box_office_result = data.get("boxOfficeResult")
    if not box_office_result:
        return False, "응답 형식이 예상과 다릅니다. KOBIS API 문서가 변경되었는지 확인해 주세요."

    movie_list = box_office_result.get("dailyBoxOfficeList")

    # 2-6) 영화 목록이 비어 있는 경우 (예: 너무 이른 날짜, 데이터 미집계 등)
    if not movie_list:
        return False, (
            "해당 날짜의 박스오피스 데이터가 비어 있습니다. "
            "날짜가 너무 이르거나(예: 오늘 날짜), 아직 KOBIS 집계가 완료되지 않았을 수 있습니다."
        )

    return True, movie_list


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
st.title("🎬 어제의 박스오피스")

# 인증키가 아예 설정되지 않은 경우, API를 호출하기 전에 먼저 안내한다.
if not KOBIS_KEY:
    show_guide_message(
        "KOBIS_KEY가 설정되어 있지 않습니다. "
        "스트림릿 클라우드의 Secrets에 KOBIS_KEY를 등록해 주세요."
    )
    st.stop()

target_dt = get_yesterday_kst()  # 한국 시간 기준 '어제' 날짜 (yyyymmdd)

# 날짜를 사람이 보기 좋은 형태로도 만들어서 화면에 표시
target_dt_pretty = f"{target_dt[:4]}-{target_dt[4:6]}-{target_dt[6:]}"
st.caption(f"기준일(한국시간): {target_dt_pretty}")

ok, result = fetch_box_office(target_dt, KOBIS_KEY)

if not ok:
    # result에는 한국어 안내 메시지가 들어있다.
    show_guide_message(result)
    st.stop()

movie_list = result  # API에서 받은 원본 리스트 (딕셔너리들의 리스트)

# ----------------------------------------------------------------------
# 5) 데이터프레임으로 변환하고, 문자열 숫자를 실제 숫자로 바꾸기
# ----------------------------------------------------------------------
df = pd.DataFrame(movie_list)

# API에서 숫자 값들이 전부 문자열로 오기 때문에, 정렬/그래프에 쓰려면 숫자로 바꿔줘야 한다.
numeric_columns = ["rank", "audiCnt", "audiAcc", "scrnCnt", "showCnt"]
for col in numeric_columns:
    if col in df.columns:
        df[col] = pd.to_numeric(df[col], errors="coerce")

# 순위 기준으로 정렬 (원래도 순위순으로 오지만, 명시적으로 한 번 더 정렬)
df = df.sort_values("rank").reset_index(drop=True)

# ----------------------------------------------------------------------
# 6) 1위 영화 - 지표 카드 3장으로 크게 보여주기
# ----------------------------------------------------------------------
st.subheader("오늘의 1위")

top_movie = df.iloc[0]

col1, col2, col3 = st.columns(3)
col1.metric("영화명", top_movie["movieNm"])
col2.metric("어제 관객수", f"{int(top_movie['audiCnt']):,}명")
col3.metric("누적 관객수", f"{int(top_movie['audiAcc']):,}명")

st.divider()

# ----------------------------------------------------------------------
# 7) 전체 순위 표
# ----------------------------------------------------------------------
st.subheader("전체 순위")

# 화면에 보여줄 컬럼만 골라서 한글 이름으로 바꾼다.
table_df = df[["rank", "movieNm", "openDt", "audiCnt", "audiAcc", "scrnCnt"]].copy()
table_df.columns = ["순위", "영화명", "개봉일", "관객수", "누적관객수", "스크린수"]

st.dataframe(table_df, use_container_width=True, hide_index=True)

st.divider()

# ----------------------------------------------------------------------
# 8) 관객수 상위 5편 - 막대그래프
# ----------------------------------------------------------------------
st.subheader("관객수 상위 5편")

top5 = df.sort_values("audiCnt", ascending=False).head(5)

# 그래프 x축에 영화명을 쓰기 위해 인덱스를 영화명으로 설정
chart_data = top5.set_index("movieNm")["audiCnt"]

st.bar_chart(chart_data)
