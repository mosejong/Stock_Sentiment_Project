import os
import time
import json
import re
from datetime import datetime, timedelta
from pathlib import Path
import requests

import pandas as pd
import google.generativeai as genai
from dotenv import load_dotenv

"""
과거 날짜 기준으로 종목별 AI 분석 리포트를 생성하는 백필 스크립트.

오늘 기준 분석(main_auto.py)과 달리, analysis_date 이전의 차트/이력만 사용한다.
뉴스는 Google Search 결과에 미래 정보가 섞일 수 있으므로 프롬프트 제한과
후처리 날짜 검사(find_future_date_mentions)를 함께 사용해 데이터 오염을 줄인다.
"""


# =========================================================
# 1. 환경 설정
# =========================================================
BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env", override=True)
api_key = os.getenv("GOOGLE_API_KEY")

if not api_key:
    raise ValueError("❌ GOOGLE_API_KEY가 .env 파일에 없습니다.")

genai.configure(api_key=api_key)

MODEL_NAME = os.getenv("GEMINI_MODEL_NAME", "gemini-2.5-flash")
GEMINI_API_URL = f"https://generativelanguage.googleapis.com/v1beta/models/{MODEL_NAME}:generateContent"

# 과거데이터 전용 저장 경로
REPORT_PATH = "logs/backfill_analysis_report.csv"
RAW_DATA_DIR = "logs/raw_data"

# 오늘용 누적 리포트는 참고용으로만 사용
HISTORY_REPORT_PATH = "logs/daily_analysis_report.csv"

# 종목 리스트
MY_STOCKS = {
    "삼성전자": "005930",
    "NVDA": "NVDA",
    "TSLA": "TSLA",
    "AAPL": "AAPL",
    "GOOGL": "GOOGL",
    "삼진제약": "000520",
    "케이뱅크": "272210",
    "리얼티인컴": "O",
    "포스코DX": "022100",
    "카카오": "035720"
}


# =========================================================
# 2. 공통 유틸
# =========================================================
def clean_json_text(text: str) -> str:
    """Gemini 응답의 markdown 코드블록을 제거해 JSON 파싱이 가능하게 만든다."""
    if not text:
        return ""
    text = re.sub(r"```json|```", "", text, flags=re.IGNORECASE).strip()
    return text


def safe_json_loads(text: str):
    """모델 응답이 깨져도 전체 백필이 멈추지 않도록 안전하게 JSON을 파싱한다."""
    try:
        return json.loads(clean_json_text(text))
    except Exception:
        return None


def find_future_date_mentions(text: str, analysis_date: str) -> list:
    """
    뉴스 요약에 기준일 이후 날짜 표현이 들어갔는지 찾는다.

    예: 기준일이 2026-03-17인데 "3월 23일", "4월 초"가 나오면
    백테스트 관점에서 미래 정보가 섞인 것으로 보고 오염 후보로 처리한다.
    """
    if not text:
        return []

    try:
        base_date = datetime.strptime(analysis_date, "%Y-%m-%d")
    except Exception:
        return []

    future_mentions = []
    pattern = re.compile(r"(?:(20\d{2})년\s*)?(\d{1,2})월\s*(?:(\d{1,2})일|(초|중순|중|말))")

    for match in pattern.finditer(text):
        year_text, month_text, day_text, period_text = match.groups()
        year = int(year_text) if year_text else base_date.year
        month = int(month_text)

        if day_text:
            day = int(day_text)
        elif period_text == "초":
            day = 1
        elif period_text in ["중", "중순"]:
            day = 15
        else:
            day = 25

        try:
            mentioned_date = datetime(year, month, day)
        except ValueError:
            continue

        if mentioned_date > base_date:
            future_mentions.append(match.group(0))

    return future_mentions


def is_news_time_contaminated(news_data: dict, analysis_date: str) -> tuple:
    """뉴스 수집 결과에 기준일 이후 정보가 섞였는지 최종 검문한다."""
    texts = [
        news_data.get("keyword", ""),
        news_data.get("news_summary", ""),
        news_data.get("source_date", ""),
        news_data.get("reference_period", ""),
    ]
    combined_text = " ".join(str(text) for text in texts if text)
    future_mentions = find_future_date_mentions(combined_text, analysis_date)

    try:
        source_date = str(news_data.get("source_date", "")).strip()
        if re.fullmatch(r"\d{4}-\d{2}-\d{2}", source_date):
            if datetime.strptime(source_date, "%Y-%m-%d") > datetime.strptime(analysis_date, "%Y-%m-%d"):
                future_mentions.append(source_date)
    except Exception:
        pass

    seen = set()
    clean_mentions = []
    for mention in future_mentions:
        if mention not in seen:
            clean_mentions.append(mention)
            seen.add(mention)

    return bool(clean_mentions), clean_mentions


def ensure_directory_exists(file_path: str):
    directory = os.path.dirname(file_path)
    if directory and not os.path.exists(directory):
        os.makedirs(directory, exist_ok=True)


def get_model_with_tools(tool_set=None):
    if tool_set is None:
        return genai.GenerativeModel(model_name=MODEL_NAME)
    return genai.GenerativeModel(model_name=MODEL_NAME, tools=tool_set)


# =========================================================
# 3. 차트 데이터 요약
# =========================================================
def get_stock_data_summary(stock_name: str, analysis_date: str) -> str:
    """
    기준일 이전의 차트 데이터만 잘라서 LLM이 읽기 쉬운 요약문으로 변환한다.

    미래 주가가 분석에 들어가면 백테스트가 오염되므로 반드시
    Date <= analysis_date 조건으로 데이터를 제한한다.
    """
    ticker = MY_STOCKS.get(stock_name, stock_name)

    possible_paths = [
        os.path.join(RAW_DATA_DIR, f"{stock_name}_5year_data.csv"),
        os.path.join(RAW_DATA_DIR, f"{ticker}_5year_data.csv"),
    ]

    file_path = None
    for path in possible_paths:
        if os.path.exists(path):
            file_path = path
            break

    if not file_path:
        return "차트 데이터 없음"

    try:
        df = pd.read_csv(file_path, index_col=0)

        # 날짜 컬럼/인덱스 정리
        if "Date" in df.columns:
            df["Date"] = pd.to_datetime(df["Date"], errors="coerce")
            df = df.dropna(subset=["Date"]).sort_values("Date")
            target_df = df[df["Date"] <= pd.to_datetime(analysis_date)].copy()
        else:
            try:
                df.index = pd.to_datetime(df.index, errors="coerce")
                df = df[~df.index.isna()].sort_index()
                target_df = df[df.index <= pd.to_datetime(analysis_date)].copy()
            except Exception:
                target_df = df.copy()

        if target_df.empty:
            return f"{analysis_date} 기준 차트 데이터 없음"

        required_cols = ["Close", "MA20", "MA60"]
        missing_cols = [col for col in required_cols if col not in target_df.columns]
        if missing_cols:
            return f"차트 데이터 컬럼 부족: {missing_cols}"

        latest = target_df.iloc[-1]

        close_price = float(latest["Close"])
        ma20 = float(latest["MA20"])
        ma60 = float(latest["MA60"])

        pos_vs_20 = "상회" if close_price > ma20 else "하회" if close_price < ma20 else "동일"
        pos_vs_60 = "상회" if close_price > ma60 else "하회" if close_price < ma60 else "동일"
        ma_alignment = "정배열" if ma20 > ma60 else "역배열" if ma20 < ma60 else "중립배열"

        extra_parts = []

        if "Volume" in target_df.columns:
            volume = float(latest["Volume"])
            extra_parts.append(f"거래량: {volume:,.0f}")

        if len(target_df) >= 2:
            prev_close = float(target_df.iloc[-2]["Close"])
            daily_change = ((close_price - prev_close) / prev_close) * 100 if prev_close != 0 else 0
            extra_parts.append(f"전일대비: {daily_change:.2f}%")

        extra_text = ", ".join(extra_parts) if extra_parts else "추가 지표 없음"

        return (
            f"기준일: {analysis_date}, "
            f"현재가: {close_price:.2f}, "
            f"20일선: {ma20:.2f}, "
            f"60일선: {ma60:.2f}, "
            f"현재가-20일선 관계: {pos_vs_20}, "
            f"현재가-60일선 관계: {pos_vs_60}, "
            f"이평선 배열: {ma_alignment}, "
            f"{extra_text}"
        )

    except Exception as e:
        return f"차트 데이터 읽기 오류: {e}"


# =========================================================
# 4. 과거 예측/적중 데이터 요약
# =========================================================
def get_historical_context(stock_name: str, analysis_date: str) -> str:
    """기준일 이전에 쌓인 예측 로그만 사용해 종목별 최근 패턴을 요약한다."""
    if not os.path.exists(HISTORY_REPORT_PATH):
        return "과거 누적 분석 데이터 없음"

    try:
        df = pd.read_csv(HISTORY_REPORT_PATH)

        if "종목명" not in df.columns:
            return "과거 누적 분석 데이터 형식 불일치"

        stock_df = df[df["종목명"] == stock_name].copy()

        if stock_df.empty:
            return "해당 종목의 과거 예측 이력 없음"

        if "날짜" in stock_df.columns:
            stock_df["날짜"] = pd.to_datetime(stock_df["날짜"], errors="coerce")
            stock_df = stock_df[stock_df["날짜"] < pd.to_datetime(analysis_date)]
            stock_df = stock_df.sort_values("날짜")

        if stock_df.empty:
            return "해당 종목의 기준일 이전 예측 이력 없음"

        recent_df = stock_df.tail(20).copy()
        total_count = len(recent_df)

        prediction_counts = (
            recent_df["AI예측"].value_counts().to_dict()
            if "AI예측" in recent_df.columns else {}
        )

        up_count = prediction_counts.get("▲ 상승", 0)
        down_count = prediction_counts.get("▼ 하락", 0)
        wait_count = prediction_counts.get("━ 관망", 0)

        hit_rate_text = "적중 데이터 부족"
        if "적중여부" in recent_df.columns:
            valid_hit_df = recent_df[recent_df["적중여부"].isin(["O", "X"])]
            if len(valid_hit_df) > 0:
                hit_rate = (valid_hit_df["적중여부"] == "O").mean() * 100
                hit_rate_text = f"최근 검증 가능 {len(valid_hit_df)}건 기준 적중률 {hit_rate:.1f}%"

        keyword_text = "키워드 정보 부족"
        if "핫키워드" in recent_df.columns:
            keywords = recent_df["핫키워드"].dropna().astype(str)
            keywords = [k for k in keywords if k.strip() and k.strip() != "분석실패"]
            if keywords:
                top_keywords = pd.Series(keywords).value_counts().head(3).index.tolist()
                keyword_text = ", ".join(top_keywords)

        dominant_prediction = "혼조"
        max_count = max(up_count, down_count, wait_count)
        if max_count > 0:
            if max_count == up_count:
                dominant_prediction = "상승 예측 우세"
            elif max_count == down_count:
                dominant_prediction = "하락 예측 우세"
            else:
                dominant_prediction = "관망 예측 우세"

        return (
            f"기준일 이전 최근 {total_count}건 요약, "
            f"상승 예측 {up_count}건, 하락 예측 {down_count}건, 관망 예측 {wait_count}건, "
            f"{hit_rate_text}, "
            f"주요 키워드: {keyword_text}, "
            f"최근 패턴 성향: {dominant_prediction}"
        )

    except Exception as e:
        return f"과거 누적 분석 데이터 요약 실패: {e}"


# =========================================================
# 5. 뉴스 수집 / 뉴스 요약
# =========================================================
def get_news_context(stock_name: str, analysis_date: str) -> dict:
    """
    기준일 관점의 뉴스 요약을 생성한다.

    Google Search는 현재 웹을 검색하므로 과거 분석에 미래 뉴스가 섞일 수 있다.
    그래서 source_date/reference_period를 모델에게 요구하고, 응답 후에는
    is_news_time_contaminated()로 한 번 더 걸러낸다.
    """
    api_key = os.getenv("GOOGLE_API_KEY")
    if not api_key:
        return {
            "keyword": "뉴스수집실패",
            "news_signal": "단순 기대감",
            "news_summary": "GOOGLE_API_KEY가 없어 뉴스 수집 불가",
            "news_sources": "출처 없음",
            "news_failed": True,
        }

    prompt = f"""
너는 종목 관련 뉴스를 짧고 사실적으로 요약하는 뉴스 분석기다.

분석 종목: {stock_name}
기준 날짜: {analysis_date}

할 일:
1. 해당 종목 관련 뉴스를 검색하라.
2. 반드시 기준 날짜 당시 알려져 있던 정보만 사용하라.
3. 기준 날짜 이후에 새롭게 발생한 사건, 결과, 주가 반응은 사용하지 마라.
4. 미래 일정(예정, 출시 임박, 발표 예정)은 기준 날짜 시점에 공개된 정보라면 사용 가능하다.
5. 기준 날짜 이후의 구체적인 날짜(예: 3월 23일, 4월 초 등)를 근거로 사용하지 마라.
6. 가능하면 기준 날짜 전후 맥락에 맞는 이슈를 중심으로 요약하라.
7. 뉴스는 반드시 아래 셋 중 하나로 분류하라.
   - 실질 호재
   - 실질 악재
   - 단순 기대감
8. news_summary는 너무 길지 않게 1~2문장으로 작성하라.
9. source_date에는 참고한 핵심 뉴스가 기준 날짜 이전 또는 당일에 공개된 날짜를 YYYY-MM-DD 형식으로 적어라.
10. 정확한 출처 날짜를 알 수 없으면 source_date는 "unknown"으로 적어라.
11. reference_period에는 뉴스가 다루는 사건의 기간을 짧게 적어라.
12. 반드시 JSON만 출력하라.

출력 형식:
{{
  "keyword": "핵심 키워드 1개",
  "news_signal": "실질 호재 / 실질 악재 / 단순 기대감",
  "news_summary": "최근 뉴스 핵심 요약 1~2문장",
  "source_date": "YYYY-MM-DD 또는 unknown",
  "reference_period": "뉴스가 다루는 사건 기간"
}}
"""

    payload = {
        "contents": [{"parts": [{"text": prompt}]}],
        "tools": [{"google_search": {}}]
    }

    headers = {
        "x-goog-api-key": api_key,
        "Content-Type": "application/json"
    }

    max_retries = 3
    last_error = None

    for attempt in range(1, max_retries + 1):
        try:
            res = requests.post(GEMINI_API_URL, headers=headers, data=json.dumps(payload), timeout=30)
            res.raise_for_status()
            data = res.json()

            text = data["candidates"][0]["content"]["parts"][0]["text"]
            parsed = safe_json_loads(text)

            grounding_chunks = data["candidates"][0].get("groundingMetadata", {}).get("groundingChunks", [])

            source_titles = []
            for chunk in grounding_chunks:
                web_info = chunk.get("web", {})
                title = web_info.get("title")
                if title and title not in source_titles:
                    source_titles.append(title)

            news_sources = ", ".join(source_titles[:3]) if source_titles else "출처 없음"

            if parsed and isinstance(parsed, dict):
                # 모델이 날짜 제한을 어겼는지 후처리로 다시 확인한다.
                candidate_news = {
                    "keyword": parsed.get("keyword", "뉴스수집실패"),
                    "news_signal": parsed.get("news_signal", "단순 기대감"),
                    "news_summary": parsed.get("news_summary", "관련 뉴스 요약 없음"),
                    "source_date": parsed.get("source_date", "unknown"),
                    "reference_period": parsed.get("reference_period", ""),
                }
                contaminated, mentions = is_news_time_contaminated(candidate_news, analysis_date)

                if contaminated:
                    return {
                        "keyword": "뉴스오염의심",
                        "news_signal": "단순 기대감",
                        "news_summary": (
                            "기준일 이후 정보가 포함된 것으로 의심되어 뉴스 신호를 분석에서 제외함 "
                            f"(감지: {', '.join(mentions)})"
                        ),
                        "news_sources": news_sources,
                        "news_failed": False,
                        "future_news_flag": True,
                    }

                return {
                    "keyword": candidate_news["keyword"],
                    "news_signal": candidate_news["news_signal"],
                    "news_summary": candidate_news["news_summary"],
                    "news_sources": news_sources,
                    "news_failed": False,
                    "future_news_flag": False,
                }

            last_error = "응답은 받았지만 JSON 파싱 실패"

        except Exception as e:
            last_error = str(e)

        if attempt < max_retries:
            time.sleep(2 * attempt)  # 2초, 4초 대기

    return {
        "keyword": "뉴스수집실패",
        "news_signal": "단순 기대감",
        "news_summary": f"REST 방식 뉴스 수집 실패: {last_error}",
        "news_sources": "출처 없음",
        "news_failed": True,
        "future_news_flag": False,
    }

# =========================================================
# 6. 최종 AI 분석
# =========================================================
def get_ai_analysis(stock_name: str, analysis_date: str):
    """차트, 과거 패턴, 뉴스 요약을 합쳐 최종 예측 JSON을 생성한다."""
    chart_info = get_stock_data_summary(stock_name, analysis_date)
    historical_context = get_historical_context(stock_name, analysis_date)
    news_data = get_news_context(stock_name, analysis_date)

    news_keyword = news_data.get("keyword", "뉴스수집실패")
    news_signal = news_data.get("news_signal", "단순 기대감")
    news_summary = news_data.get("news_summary", "관련 뉴스 요약 없음")
    news_sources = news_data.get("news_sources", "출처 없음")
    future_news_flag = news_data.get("future_news_flag", False)

    if future_news_flag:
        # 오염 의심 뉴스는 방향성 판단 재료로 쓰지 않도록 중립화한다.
        news_keyword = "뉴스오염의심"
        news_signal = "단순 기대감"
        news_summary = (
            f"{analysis_date} 이후 정보가 포함된 것으로 의심되어 "
            "뉴스 신호를 최종 판단에서 제외함."
        )

    model = get_model_with_tools(None)

    prompt = f"""
너는 과거 패턴, 뉴스 재료, 기술적 지표를 함께 해석하는 냉정한 단기 주식 애널리스트다.
반드시 기준 날짜 당시 알려져 있던 정보만 사용하라.
기준 날짜 이후에 새롭게 발생한 사건, 결과, 주가 반응은 사용하지 마라.
미래 일정(예정, 출시 임박, 발표 예정)은 기준 날짜 시점에 공개된 정보라면 사용 가능하다.
기준 날짜 이후의 구체적 결과를 이미 확정된 사실처럼 서술하지 마라.
기준 날짜 이후의 구체적인 날짜(예: 3월 23일, 4월 초 등)를 근거로 사용하지 마라.


기준 날짜: {analysis_date}
분석 종목: {stock_name}

[현재 차트 요약]
{chart_info}

[과거 유사 패턴 참고]
{historical_context}

[최근 뉴스 요약]
핵심키워드: {news_keyword}
뉴스판정: {news_signal}
뉴스요약: {news_summary}

임무:
과거 유사 패턴 + 최근 뉴스 + 현재 차트 상태를 종합하여
이 종목의 향후 단기 방향성을 예측하라.

판단 절차:
1. 현재가가 20일선과 60일선 대비 어디에 있는지 해석하라.
2. 20일선과 60일선 배열을 보고 추세를 판단하라.
3. 과거 유사 패턴에서 예측 성향과 적중률을 참고하라.
4. 뉴스 재료를 실질 호재 / 실질 악재 / 단순 기대감으로 반영하라.
5. 차트와 뉴스와 과거 패턴이 같은 방향이면 confidence를 높여라.
6. 셋이 충돌하면 관망 또는 낮은 confidence를 부여하라.
7. 과장된 낙관론이나 비관론을 금지한다.

판정 기준:
- ▲ 상승: 차트와 뉴스와 과거 패턴이 대체로 상승 쪽
- ▼ 하락: 차트와 뉴스와 과거 패턴이 대체로 하락 쪽
- ━ 관망: 신호가 상충하거나 확신 부족

confidence 기준:
- 85~95: 차트/뉴스/과거패턴이 강하게 일치
- 70~84: 우세 방향은 있으나 일부 불확실성 존재
- 55~69: 혼조세, 관망에 가까움
- 0~54: 근거 부족 또는 신뢰 낮음

출력 규칙:
- 반드시 JSON만 출력
- 마크다운 금지
- confidence는 정수
- keyword는 핵심 재료 1개
- final_reason은 1문장
- news_signal은 반드시 "실질 호재", "실질 악재", "단순 기대감" 중 하나
- pattern_match는 "유사패턴 강세", "유사패턴 약세", "유사패턴 혼조" 중 하나
- chart_score는 "강세", "약세", "혼조" 중 하나

{{
  "prediction": "▲ 상승 / ▼ 하락 / ━ 관망",
  "confidence": 0,
  "keyword": "핵심키워드",
  "news_signal": "실질 호재 / 실질 악재 / 단순 기대감",
  "pattern_match": "유사패턴 강세 / 유사패턴 약세 / 유사패턴 혼조",
  "chart_score": "강세 / 약세 / 혼조",
  "final_reason": "최종 판단의 핵심 근거 1문장"
}}
"""

    try:
        response = model.generate_content(prompt)
        parsed = safe_json_loads(response.text)

        if parsed and isinstance(parsed, dict):
            parsed["news_summary"] = news_summary
            parsed["collected_news_keyword"] = news_keyword
            parsed["news_sources"] = news_sources

            if news_data.get("news_failed", False) or future_news_flag:
                # 뉴스가 실패했거나 오염된 경우 확신도를 낮춰 과신을 방지한다.
                try:
                    original_conf = int(parsed.get("confidence", 50))
                except Exception:
                    original_conf = 50

                lowered_conf = max(45, original_conf - 15)
                parsed["confidence"] = lowered_conf

                if parsed.get("prediction") in ["▲ 상승", "▼ 하락"] and lowered_conf <= 60:
                    parsed["prediction"] = "━ 관망"

                if future_news_flag:
                    parsed["news_signal"] = "단순 기대감"
                    parsed["collected_news_keyword"] = "뉴스오염의심"
                    parsed["news_summary"] = news_summary

            return parsed

        print(f"⚠️ {stock_name} JSON 파싱 실패")
        print(response.text)
        return None

    except Exception as e:
        print(f"❌ {stock_name} 최종 분석 실패: {e}")
        return None
# =========================================================
# 7. 하루치 실행
# =========================================================
def run_auto_analysis_for_date(target_date: str):
    """특정 거래일 하루에 대해 전체 관심 종목을 분석하고 CSV에 추가 저장한다."""
    print(f"🚀 {target_date} 전 종목 과거 분석 시작")
    ensure_directory_exists(REPORT_PATH)

    results = []

    for stock in MY_STOCKS.keys():
        print(f"🔍 {stock} 분석 중... ({target_date})")
        analysis = get_ai_analysis(stock, target_date)

        if analysis:
            data = {
                "날짜": target_date,
                "종목명": stock,
                "티커": MY_STOCKS[stock],
                "AI예측": analysis.get("prediction", "━ 관망"),
                "확신도": str(analysis.get("confidence", "50")).replace("%", ""),
                "핫키워드": analysis.get("keyword", "#미분류"),
                "뉴스판정": analysis.get("news_signal", "단순 기대감"),
                "뉴스요약": analysis.get("news_summary", "뉴스 요약 없음"),
                "뉴스출처": analysis.get("news_sources", "출처 없음"),
                "패턴판정": analysis.get("pattern_match", "유사패턴 혼조"),
                "차트판정": analysis.get("chart_score", "혼조"),
                "핵심사유": analysis.get("final_reason", "내용 없음"),
            }
        else:
            data = {
                "날짜": target_date,
                "종목명": stock,
                "티커": MY_STOCKS[stock],
                "AI예측": "━ 관망",
                "확신도": "0",
                "핫키워드": "분석실패",
                "뉴스판정": "단순 기대감",
                "뉴스요약": "뉴스 요약 없음",
                "뉴스출처": "출처 없음",
                "패턴판정": "유사패턴 혼조",
                "차트판정": "혼조",
                "핵심사유": "서버 응답 오류",
            }

        results.append(data)
        time.sleep(2)

    df = pd.DataFrame(results)

    target_columns = [
        "날짜",
        "종목명",
        "티커",
        "AI예측",
        "확신도",
        "핫키워드",
        "뉴스판정",
        "뉴스요약",
        "뉴스출처",
        "패턴판정",
        "차트판정",
        "핵심사유",
    ]
    df = df[target_columns]

    if (not os.path.exists(REPORT_PATH)) or os.path.getsize(REPORT_PATH) == 0:
        df.to_csv(REPORT_PATH, index=False, encoding="utf-8-sig")
    else:
        df.to_csv(REPORT_PATH, mode="a", header=False, index=False, encoding="utf-8-sig")

    print(f"✅ {target_date} 저장 완료 -> [ {REPORT_PATH} ]")
    print(df)


# =========================================================
# 8. 날짜 범위 실행
# =========================================================
def run_backfill(start_date: str, end_date: str):
    """시작일~종료일 사이의 평일만 순회하며 백필을 실행한다."""
    start = datetime.strptime(start_date, "%Y-%m-%d")
    end = datetime.strptime(end_date, "%Y-%m-%d")

    current = start
    while current <= end:
        # 월~금만 실행
        if current.weekday() < 5:
            date_str = current.strftime("%Y-%m-%d")
            run_auto_analysis_for_date(date_str)

        current += timedelta(days=1)


# =========================================================
# 9. 실행
# =========================================================
if __name__ == "__main__":
    # 예시:
    # run_auto_analysis_for_date("2026-04-16")
    # run_backfill("2026-03-16", "2026-04-17")

    run_backfill("2026-03-21", "2026-04-15")
