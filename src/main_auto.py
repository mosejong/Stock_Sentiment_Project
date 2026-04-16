import os
import time
import json
import re
from datetime import datetime
import requests

import pandas as pd
import google.generativeai as genai
from dotenv import load_dotenv


# =========================================================
# 1. 환경 설정
# =========================================================
load_dotenv()
api_key = os.getenv("GOOGLE_API_KEY")


if not api_key:
    raise ValueError("❌ GOOGLE_API_KEY가 .env 파일에 없습니다.")

genai.configure(api_key=api_key)

MODEL_NAME = "gemini-2.5-flash"

# 결과 저장 경로
REPORT_PATH = "logs/daily_analysis_report.csv"
RAW_DATA_DIR = "logs/raw_data"

# 과거 누적 리포트(있으면 활용)
# - 기존 예측/실제결과/적중여부가 쌓인 파일
HISTORY_REPORT_PATH = "logs/daily_analysis_report.csv"

today_date = datetime.now().strftime("%Y-%m-%d")

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
    """모델 응답에서 코드블럭 제거"""
    if not text:
        return ""
    text = re.sub(r"```json|```", "", text, flags=re.IGNORECASE).strip()
    return text


def safe_json_loads(text: str):
    """JSON 파싱 안전 처리"""
    try:
        return json.loads(clean_json_text(text))
    except Exception:
        return None


def ensure_directory_exists(file_path: str):
    directory = os.path.dirname(file_path)
    if directory and not os.path.exists(directory):
        os.makedirs(directory, exist_ok=True)


def get_model_with_tools(tool_set=None):
    """도구 유무에 따라 모델 생성"""
    if tool_set is None:
        return genai.GenerativeModel(model_name=MODEL_NAME)
    return genai.GenerativeModel(model_name=MODEL_NAME, tools=tool_set)


# =========================================================
# 3. 차트 데이터 요약
# =========================================================
def get_stock_data_summary(stock_name: str) -> str:
    ticker = MY_STOCKS.get(stock_name, stock_name)

    # 한글 종목명 파일 우선, 없으면 티커 파일
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

        required_cols = ["Close", "MA20", "MA60"]
        missing_cols = [col for col in required_cols if col not in df.columns]
        if missing_cols:
            return f"차트 데이터 컬럼 부족: {missing_cols}"

        latest = df.iloc[-1]

        close_price = float(latest["Close"])
        ma20 = float(latest["MA20"])
        ma60 = float(latest["MA60"])

        pos_vs_20 = "상회" if close_price > ma20 else "하회" if close_price < ma20 else "동일"
        pos_vs_60 = "상회" if close_price > ma60 else "하회" if close_price < ma60 else "동일"
        ma_alignment = "정배열" if ma20 > ma60 else "역배열" if ma20 < ma60 else "중립배열"

        extra_parts = []

        if "Volume" in df.columns:
            volume = float(latest["Volume"])
            extra_parts.append(f"거래량: {volume:,.0f}")

        if len(df) >= 2:
            prev_close = float(df.iloc[-2]["Close"])
            daily_change = ((close_price - prev_close) / prev_close) * 100 if prev_close != 0 else 0
            extra_parts.append(f"전일대비: {daily_change:.2f}%")

        extra_text = ", ".join(extra_parts) if extra_parts else "추가 지표 없음"

        return (
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
def get_historical_context(stock_name: str) -> str:
    """
    기존 누적 리포트에서 해당 종목의 과거 예측 패턴/적중률을 요약
    """
    if not os.path.exists(HISTORY_REPORT_PATH):
        return "과거 누적 분석 데이터 없음"

    try:
        df = pd.read_csv(HISTORY_REPORT_PATH)

        if "종목명" not in df.columns:
            return "과거 누적 분석 데이터 형식 불일치"

        stock_df = df[df["종목명"] == stock_name].copy()

        if stock_df.empty:
            return "해당 종목의 과거 예측 이력 없음"

        # 날짜 정렬
        if "날짜" in stock_df.columns:
            stock_df["날짜"] = pd.to_datetime(stock_df["날짜"], errors="coerce")
            stock_df = stock_df.sort_values("날짜")

        recent_df = stock_df.tail(20).copy()

        total_count = len(recent_df)

        prediction_counts = (
            recent_df["AI예측"].value_counts().to_dict()
            if "AI예측" in recent_df.columns else {}
        )

        up_count = prediction_counts.get("▲ 상승", 0)
        down_count = prediction_counts.get("▼ 하락", 0)
        wait_count = prediction_counts.get("━ 관망", 0)

        # 적중률 계산
        hit_rate_text = "적중 데이터 부족"
        if "적중여부" in recent_df.columns:
            valid_hit_df = recent_df[recent_df["적중여부"].isin(["O", "X"])]
            if len(valid_hit_df) > 0:
                hit_rate = (valid_hit_df["적중여부"] == "O").mean() * 100
                hit_rate_text = f"최근 검증 가능 {len(valid_hit_df)}건 기준 적중률 {hit_rate:.1f}%"

        # 최근 키워드
        keyword_text = "키워드 정보 부족"
        if "핫키워드" in recent_df.columns:
            keywords = recent_df["핫키워드"].dropna().astype(str)
            keywords = [k for k in keywords if k.strip() and k.strip() != "분석실패"]
            if keywords:
                top_keywords = pd.Series(keywords).value_counts().head(3).index.tolist()
                keyword_text = ", ".join(top_keywords)

        # 최근 패턴 성향
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
            f"최근 {total_count}건 요약, "
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
def get_news_context(stock_name: str) -> dict:
    """
    REST 방식으로 Google Search grounding을 사용해 최신 뉴스 수집
    터미널 로그 최소화 버전
    """
    api_key = os.getenv("GOOGLE_API_KEY")
    if not api_key:
        return {
            "keyword": "뉴스수집실패",
            "news_signal": "단순 기대감",
            "news_summary": "GOOGLE_API_KEY가 없어 뉴스 수집 불가",
            "news_sources": "출처 없음"
        }

    url = "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent"

    prompt = f"""
너는 종목 관련 최신 뉴스를 짧고 사실적으로 요약하는 뉴스 분석기다.

분석 종목: {stock_name}
오늘 날짜: {today_date}

할 일:
1. 최근 뉴스/이슈를 검색해 핵심 재료만 요약하라.
2. 뉴스는 반드시 아래 셋 중 하나로 분류하라.
   - 실질 호재
   - 실질 악재
   - 단순 기대감
3. news_summary는 너무 길지 않게 1~2문장으로 작성하라.
4. 반드시 JSON만 출력하라.

출력 형식:
{{
  "keyword": "핵심 키워드 1개",
  "news_signal": "실질 호재 / 실질 악재 / 단순 기대감",
  "news_summary": "최근 뉴스 핵심 요약 1~2문장"
}}
"""

    payload = {
        "contents": [
            {
                "parts": [
                    {"text": prompt}
                ]
            }
        ],
        "tools": [
            {
                "google_search": {}
            }
        ]
    }

    headers = {
        "x-goog-api-key": api_key,
        "Content-Type": "application/json"
    }

    try:
        res = requests.post(url, headers=headers, data=json.dumps(payload), timeout=30)
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
            return {
                "keyword": parsed.get("keyword", "뉴스수집실패"),
                "news_signal": parsed.get("news_signal", "단순 기대감"),
                "news_summary": parsed.get("news_summary", "관련 뉴스 요약 없음"),
                "news_sources": news_sources
            }

        return {
            "keyword": "뉴스수집실패",
            "news_signal": "단순 기대감",
            "news_summary": "응답은 받았지만 JSON 파싱 실패",
            "news_sources": news_sources
        }

    except Exception:
        return {
            "keyword": "뉴스수집실패",
            "news_signal": "단순 기대감",
            "news_summary": "REST 방식 뉴스 수집 실패",
            "news_sources": "출처 없음"
        }
        
# =========================================================
# 6. 최종 AI 분석
# =========================================================
def get_ai_analysis(stock_name: str):
    chart_info = get_stock_data_summary(stock_name)
    historical_context = get_historical_context(stock_name)
    news_data = get_news_context(stock_name)

    news_keyword = news_data.get("keyword", "뉴스수집실패")
    news_signal = news_data.get("news_signal", "단순 기대감")
    news_summary = news_data.get("news_summary", "관련 뉴스 요약 없음")
    news_sources = news_data.get("news_sources", "출처 없음")

    model = get_model_with_tools(None)

    prompt = f"""
너는 과거 패턴, 뉴스 재료, 기술적 지표를 함께 해석하는 냉정한 단기 주식 애널리스트다.

오늘 날짜: {today_date}
분석 종목: {stock_name}

[현재 차트 요약]
{chart_info}

[과거 유사 패턴 참고]
{historical_context}

[오늘/최근 뉴스 요약]
핵심키워드: {news_keyword}
뉴스판정: {news_signal}
뉴스요약: {news_summary}

임무:
과거 유사 패턴 + 오늘 뉴스 + 현재 차트 상태를 종합하여
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
            # 뉴스 수집 결과를 같이 붙여서 반환
            parsed["news_summary"] = news_summary
            parsed["collected_news_keyword"] = news_keyword
            parsed["news_sources"] = news_sources
            return parsed

        print(f"⚠️ {stock_name} JSON 파싱 실패")
        print(response.text)
        return None

    except Exception as e:
        print(f"❌ {stock_name} 최종 분석 실패: {e}")
        return None


# =========================================================
# 7. 전체 실행
# =========================================================
def run_auto_analysis():
    print(f"🚀 {today_date} 전 종목 자동 분석 시작")
    ensure_directory_exists(REPORT_PATH)

    results = []

    for stock in MY_STOCKS.keys():
        print(f"🔍 {stock} 분석 중...")
        analysis = get_ai_analysis(stock)

        if analysis:
            data = {
                "날짜": today_date,
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
                "날짜": today_date,
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

    print(f"✅ 분석 완료! [ {REPORT_PATH} ] 파일을 확인하십시오.")
    print(df)


# =========================================================
# 8. 실행
# =========================================================
if __name__ == "__main__":
    run_auto_analysis()