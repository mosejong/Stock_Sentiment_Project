import os
import time
import json
import re
from datetime import datetime
from pathlib import Path

import requests
import pandas as pd
import google.generativeai as genai
from dotenv import load_dotenv
from stock_filter import describe_stock_filter, filter_stocks


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
COMPARE_MODEL_NAME = os.getenv("GEMINI_COMPARE_MODEL_NAME", "").strip()

# 결과 저장 경로
REPORT_PATH = "logs/daily_analysis_report.csv"
RAW_DATA_DIR = "logs/raw_data"

# 과거 누적 리포트(있으면 활용)
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
    "카카오": "035720",
}

ACTIVE_STOCKS = filter_stocks(MY_STOCKS)


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


def get_gemini_api_url(model_name: str) -> str:
    return f"https://generativelanguage.googleapis.com/v1beta/models/{model_name}:generateContent"


def get_model_with_tools(tool_set=None, model_name: str = MODEL_NAME):
    """도구 유무에 따라 모델 생성"""
    if tool_set is None:
        return genai.GenerativeModel(model_name=model_name)
    return genai.GenerativeModel(model_name=model_name, tools=tool_set)


def normalize_report_columns(df: pd.DataFrame, target_columns: list) -> pd.DataFrame:
    """기존 CSV와 새 비교 컬럼이 섞여도 항상 같은 컬럼 순서로 맞춘다."""
    for col in target_columns:
        if col not in df.columns:
            df[col] = ""
    return df[target_columns].copy()


def prediction_to_direction(prediction: str) -> int:
    """상승/하락/관망 예측을 계산용 방향 점수로 변환한다."""
    prediction = str(prediction)
    if "상승" in prediction or "▲" in prediction:
        return 1
    if "하락" in prediction or "▼" in prediction:
        return -1
    return 0


def news_signal_weight(signal: str) -> int:
    """뉴스판정의 강도를 방향성 점수로 변환한다."""
    signal = str(signal)
    if "호재" in signal:
        return 1
    if "악재" in signal:
        return -1
    return 0


def to_int(value, default: int = 50) -> int:
    try:
        return int(float(str(value).replace("%", "").strip()))
    except Exception:
        return default


def is_invalid_news(text: str | None) -> bool:
    """UI에 보여주면 안 되는 실패/빈 뉴스인지 판별"""
    if text is None:
        return True

    text = str(text).strip()
    if not text:
        return True

    bad_patterns = [
        "REST 방식 뉴스 수집 실패",
        "뉴스 수집 실패",
        "GOOGLE_API_KEY가 없어 뉴스 수집 불가",
        "응답은 받았지만 JSON 파싱 실패",
        "관련 뉴스 요약 없음",
        "뉴스 요약 없음",
    ]
    return any(pattern in text for pattern in bad_patterns)


def normalize_source_text(source_text: str | None) -> str:
    if source_text is None:
        return ""
    source_text = str(source_text).strip()
    if source_text == "출처 없음":
        return ""
    return source_text


def score_news_candidate(news_text: str, news_signal: str = "", news_sources: str = "", keyword: str = "") -> int:
    """
    뉴스 후보 품질 점수 계산
    - 실패 뉴스는 탈락
    - 실질 호재/악재, 출처 존재, 키워드 존재, 본문 구체성에 가점
    """
    if is_invalid_news(news_text):
        return -100

    score = 20

    news_signal = str(news_signal).strip()
    news_sources = normalize_source_text(news_sources)
    keyword = str(keyword).strip()

    if "실질 호재" in news_signal or "실질 악재" in news_signal:
        score += 30
    elif "단순 기대감" in news_signal:
        score += 10

    if news_sources:
        score += 15
        if "," in news_sources:
            score += 5

    if keyword and keyword not in ["뉴스수집실패", "분석실패", "#미분류"]:
        score += 10

    text_len = len(str(news_text).strip())
    if text_len >= 40:
        score += 10
    if text_len >= 80:
        score += 5

    vague_words = ["기대", "전망", "가능성", "관측"]
    if any(word in str(news_text) for word in vague_words):
        score -= 5

    return max(0, min(100, score))


def detect_prediction_conflict(data: dict) -> bool:
    """
    두 모델이 상승/하락으로 정면 충돌하는지 확인
    """
    base_pred = str(data.get("AI예측", "")).strip()
    compare_pred = str(data.get("비교AI예측", "")).strip()

    if not compare_pred:
        return False

    return (
        base_pred in ["▲ 상승", "▼ 하락"]
        and compare_pred in ["▲ 상승", "▼ 하락"]
        and base_pred != compare_pred
    )


def signal_to_label(signal: str, default_label: str = "재료") -> str:
    signal = str(signal).strip()
    if "호재" in signal:
        return "호재"
    if "악재" in signal:
        return "악재"
    if "기대감" in signal:
        return "기대감"
    return default_label


def clean_keyword_for_conflict(keyword: str, fallback: str) -> str:
    keyword = str(keyword).strip()
    if not keyword or keyword in ["뉴스수집실패", "분석실패", "#미분류"]:
        return fallback
    return keyword


def build_conflict_news_summary(data: dict) -> dict:
    """
    뉴스/모델 방향이 강하게 충돌할 때 메인 화면용 요약 생성
    """
    base_kw = clean_keyword_for_conflict(data.get("핫키워드", ""), "기준 재료")
    compare_kw = clean_keyword_for_conflict(data.get("비교핫키워드", ""), "비교 재료")

    base_signal = signal_to_label(data.get("뉴스판정", ""), "재료")
    compare_signal = signal_to_label(data.get("비교뉴스판정", ""), "재료")

    return {
        "대표뉴스키워드": "의견 충돌",
        "대표뉴스요약": f"{base_kw} 관련 {base_signal}와 {compare_kw} 관련 {compare_signal}가 함께 존재해 단기 방향성 확인이 필요합니다.",
        "대표뉴스판정": "혼재",
        "대표뉴스모델": "conflict",
        "대표뉴스점수": "0",
    }


def pick_featured_news(data: dict) -> dict:
    """
    기준 모델 뉴스와 비교 모델 뉴스 중 메인 화면에 보여줄 대표 뉴스 선택
    """
    if detect_prediction_conflict(data):
        return build_conflict_news_summary(data)

    candidates = []

    # 기준 모델 뉴스 후보
    base_news = data.get("뉴스요약", "")
    base_signal = data.get("뉴스판정", "")
    base_sources = data.get("뉴스출처", "")
    base_keyword = data.get("핫키워드", "")

    base_score = score_news_candidate(
        news_text=base_news,
        news_signal=base_signal,
        news_sources=base_sources,
        keyword=base_keyword,
    )
    if base_score >= 0:
        candidates.append({
            "model": data.get("기준모델", "base"),
            "keyword": base_keyword,
            "summary": base_news,
            "signal": base_signal,
            "score": base_score,
        })

    # 비교 모델 뉴스 후보
    compare_news = data.get("비교뉴스요약", "")
    compare_signal = data.get("비교뉴스판정", "")
    compare_sources = data.get("비교뉴스출처", "")
    compare_keyword = data.get("비교핫키워드", "")

    compare_score = score_news_candidate(
        news_text=compare_news,
        news_signal=compare_signal,
        news_sources=compare_sources,
        keyword=compare_keyword,
    )
    if compare_score >= 0:
        candidates.append({
            "model": data.get("비교모델", "compare"),
            "keyword": compare_keyword,
            "summary": compare_news,
            "signal": compare_signal,
            "score": compare_score,
        })

    if not candidates:
        return {
            "대표뉴스키워드": "뉴스 부족",
            "대표뉴스요약": "관련 뉴스 부족",
            "대표뉴스판정": "뉴스 부족",
            "대표뉴스모델": "",
            "대표뉴스점수": "0",
        }

    candidates.sort(key=lambda x: x["score"], reverse=True)
    best = candidates[0]

    keyword = str(best["keyword"]).strip()
    if not keyword or keyword in ["뉴스수집실패", "분석실패", "#미분류"]:
        keyword = "대표 뉴스"

    return {
        "대표뉴스키워드": keyword,
        "대표뉴스요약": best["summary"],
        "대표뉴스판정": best["signal"] if best["signal"] else "뉴스 반영",
        "대표뉴스모델": best["model"],
        "대표뉴스점수": str(best["score"]),
    }


def calculate_news_importance(data: dict) -> int:
    """
    뉴스 중요도를 0~100으로 계산한다.
    """
    base_signal = data.get("뉴스판정", "")
    compare_signal = data.get("비교뉴스판정", "")
    base_weight = news_signal_weight(base_signal)
    compare_weight = news_signal_weight(compare_signal)

    score = 45
    if base_weight != 0:
        score += 20
    if compare_weight != 0:
        score += 20
    if base_weight != 0 and base_weight == compare_weight:
        score += 15
    elif base_weight != 0 and compare_weight != 0 and base_weight != compare_weight:
        score -= 15

    return max(0, min(100, score))


def add_ensemble_result(data: dict) -> dict:
    """
    기준 모델과 비교 모델 결과를 합쳐 최종 종합예측/종합점수를 만든다.
    """
    base_pred = data.get("AI예측", "━ 관망")
    compare_pred = data.get("비교AI예측", "")
    base_conf = to_int(data.get("확신도", 50))
    compare_conf = to_int(data.get("비교확신도", 0), default=0)

    base_dir = prediction_to_direction(base_pred)
    compare_dir = prediction_to_direction(compare_pred)

    has_compare = bool(str(data.get("비교모델", "")).strip())
    if has_compare:
        model_agreement = 100 if base_dir == compare_dir else 50 if 0 in [base_dir, compare_dir] else 0
        weighted_direction = (base_dir * base_conf * 0.5) + (compare_dir * compare_conf * 0.5)
        avg_conf = (base_conf + compare_conf) / 2
    else:
        model_agreement = 100
        weighted_direction = base_dir * base_conf
        avg_conf = base_conf

    news_importance = calculate_news_importance(data)

    if weighted_direction >= 25:
        ensemble_prediction = "▲ 상승"
    elif weighted_direction <= -25:
        ensemble_prediction = "▼ 하락"
    else:
        ensemble_prediction = "━ 관망"

    ensemble_score = round((avg_conf * 0.65) + (model_agreement * 0.2) + (news_importance * 0.15))

    if has_compare and model_agreement == 100:
        reason = "두 모델의 방향성이 일치하여 종합 신뢰도를 높게 반영함"
    elif has_compare and model_agreement == 0:
        reason = "두 모델의 방향성이 충돌하여 종합 판단을 보수적으로 반영함"
    elif has_compare:
        reason = "한 모델이 관망 또는 약한 신호를 제시하여 중간 수준으로 반영함"
    else:
        reason = "비교 모델 없이 기준 모델 결과를 중심으로 반영함"

    data.update({
        "종합예측": ensemble_prediction,
        "종합점수": str(int(ensemble_score)),
        "모델일치도": str(int(model_agreement)),
        "뉴스중요도": str(int(news_importance)),
        "종합사유": reason,
    })
    return data


# =========================================================
# 3. 차트 데이터 요약
# =========================================================
def get_stock_data_summary(stock_name: str) -> str:
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
def get_news_context(stock_name: str, model_name: str = MODEL_NAME) -> dict:
    """
    REST 방식으로 Google Search grounding을 사용해 최신 뉴스 수집
    실패해도 UI용 본문에는 실패 문구를 넣지 않는다.
    """
    api_key = os.getenv("GOOGLE_API_KEY")
    if not api_key:
        return {
            "keyword": "",
            "news_signal": "",
            "news_summary": "",
            "news_sources": "",
            "news_ok": False,
            "news_error": "GOOGLE_API_KEY가 없어 뉴스 수집 불가",
        }

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
        res = requests.post(
            get_gemini_api_url(model_name),
            headers=headers,
            data=json.dumps(payload),
            timeout=30
        )
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

        news_sources = ", ".join(source_titles[:3]) if source_titles else ""

        if parsed and isinstance(parsed, dict):
            return {
                "keyword": parsed.get("keyword", ""),
                "news_signal": parsed.get("news_signal", ""),
                "news_summary": parsed.get("news_summary", ""),
                "news_sources": news_sources,
                "news_ok": True,
                "news_error": "",
            }

        return {
            "keyword": "",
            "news_signal": "",
            "news_summary": "",
            "news_sources": news_sources,
            "news_ok": False,
            "news_error": "응답은 받았지만 JSON 파싱 실패",
        }

    except Exception:
        return {
            "keyword": "",
            "news_signal": "",
            "news_summary": "",
            "news_sources": "",
            "news_ok": False,
            "news_error": "REST 방식 뉴스 수집 실패",
        }


# =========================================================
# 6. 최종 AI 분석
# =========================================================
def get_ai_analysis(stock_name: str, model_name: str = MODEL_NAME):
    chart_info = get_stock_data_summary(stock_name)
    historical_context = get_historical_context(stock_name)
    news_data = get_news_context(stock_name, model_name=model_name)

    news_keyword = news_data.get("keyword", "")
    news_signal = news_data.get("news_signal", "")
    news_summary = news_data.get("news_summary", "")
    news_sources = news_data.get("news_sources", "")
    news_ok = news_data.get("news_ok", False)
    news_error = news_data.get("news_error", "")

    model = get_model_with_tools(None, model_name=model_name)

    prompt = f"""
너는 과거 패턴, 뉴스 재료, 기술적 지표를 함께 해석하는 냉정한 단기 주식 애널리스트다.

오늘 날짜: {today_date}
분석 종목: {stock_name}

[현재 차트 요약]
{chart_info}

[과거 유사 패턴 참고]
{historical_context}

[오늘/최근 뉴스 요약]
핵심키워드: {news_keyword if news_keyword else "없음"}
뉴스판정: {news_signal if news_signal else "없음"}
뉴스요약: {news_summary if news_summary else "관련 뉴스 부족"}

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
            parsed["model_name"] = model_name
            parsed["news_summary"] = news_summary
            parsed["collected_news_keyword"] = news_keyword
            parsed["news_sources"] = news_sources
            parsed["news_ok"] = news_ok
            parsed["news_error"] = news_error
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
    if not ACTIVE_STOCKS:
        raise ValueError("STOCK_INCLUDE/STOCK_EXCLUDE 설정 후 실행할 종목이 없습니다.")
    print(f"[STOCKS] {describe_stock_filter(len(MY_STOCKS), len(ACTIVE_STOCKS))}")
    print(f"[MODEL] base={MODEL_NAME}")
    print(f"[MODEL] compare={COMPARE_MODEL_NAME or '(disabled)'}")
    if COMPARE_MODEL_NAME and COMPARE_MODEL_NAME != MODEL_NAME:
        print(f"[MODEL] compare mode ON: {MODEL_NAME} vs {COMPARE_MODEL_NAME}")
    else:
        print("[MODEL] compare mode OFF")

    ensure_directory_exists(REPORT_PATH)

    results = []

    for stock in ACTIVE_STOCKS.keys():
        print(f"🔍 {stock} 분석 중...")
        analysis = get_ai_analysis(stock, model_name=MODEL_NAME)

        compare_analysis = None
        if COMPARE_MODEL_NAME and COMPARE_MODEL_NAME != MODEL_NAME:
            print(f"   -> compare model running... ({COMPARE_MODEL_NAME})")
            compare_analysis = get_ai_analysis(stock, model_name=COMPARE_MODEL_NAME)

        if analysis:
            data = {
                "날짜": today_date,
                "종목명": stock,
                "티커": ACTIVE_STOCKS[stock],
                "기준모델": analysis.get("model_name", MODEL_NAME),
                "AI예측": analysis.get("prediction", "━ 관망"),
                "확신도": str(analysis.get("confidence", "50")).replace("%", ""),
                "핫키워드": analysis.get("keyword", "#미분류"),
                "뉴스판정": analysis.get("news_signal", "단순 기대감"),
                "뉴스요약": analysis.get("news_summary", ""),
                "뉴스출처": analysis.get("news_sources", ""),
                "패턴판정": analysis.get("pattern_match", "유사패턴 혼조"),
                "차트판정": analysis.get("chart_score", "혼조"),
                "핵심사유": analysis.get("final_reason", "내용 없음"),
                "뉴스수집성공": "Y" if analysis.get("news_ok", False) else "N",
                "뉴스수집오류": analysis.get("news_error", ""),
            }
        else:
            data = {
                "날짜": today_date,
                "종목명": stock,
                "티커": ACTIVE_STOCKS[stock],
                "기준모델": MODEL_NAME,
                "AI예측": "━ 관망",
                "확신도": "0",
                "핫키워드": "분석실패",
                "뉴스판정": "",
                "뉴스요약": "",
                "뉴스출처": "",
                "패턴판정": "유사패턴 혼조",
                "차트판정": "혼조",
                "핵심사유": "서버 응답 오류",
                "뉴스수집성공": "N",
                "뉴스수집오류": "최종 분석 실패",
            }

        if compare_analysis:
            data.update({
                "비교모델": compare_analysis.get("model_name", COMPARE_MODEL_NAME),
                "비교AI예측": compare_analysis.get("prediction", "━ 관망"),
                "비교확신도": str(compare_analysis.get("confidence", "50")).replace("%", ""),
                "비교핫키워드": compare_analysis.get("keyword", "#미분류"),
                "비교뉴스판정": compare_analysis.get("news_signal", ""),
                "비교뉴스요약": compare_analysis.get("news_summary", ""),
                "비교뉴스출처": compare_analysis.get("news_sources", ""),
                "비교패턴판정": compare_analysis.get("pattern_match", "유사패턴 혼조"),
                "비교차트판정": compare_analysis.get("chart_score", "혼조"),
                "비교핵심사유": compare_analysis.get("final_reason", "내용 없음"),
                "비교뉴스수집성공": "Y" if compare_analysis.get("news_ok", False) else "N",
                "비교뉴스수집오류": compare_analysis.get("news_error", ""),
            })
        else:
            data.update({
                "비교모델": "",
                "비교AI예측": "",
                "비교확신도": "",
                "비교핫키워드": "",
                "비교뉴스판정": "",
                "비교뉴스요약": "",
                "비교뉴스출처": "",
                "비교패턴판정": "",
                "비교차트판정": "",
                "비교핵심사유": "",
                "비교뉴스수집성공": "",
                "비교뉴스수집오류": "",
            })

        data = add_ensemble_result(data)
        data.update(pick_featured_news(data))

        results.append(data)
        time.sleep(2)

    df = pd.DataFrame(results)

    target_columns = [
        "날짜",
        "종목명",
        "티커",
        "기준모델",
        "AI예측",
        "확신도",
        "핫키워드",
        "뉴스판정",
        "뉴스요약",
        "뉴스출처",
        "패턴판정",
        "차트판정",
        "핵심사유",
        "뉴스수집성공",
        "뉴스수집오류",
        "비교모델",
        "비교AI예측",
        "비교확신도",
        "비교핫키워드",
        "비교뉴스판정",
        "비교뉴스요약",
        "비교뉴스출처",
        "비교패턴판정",
        "비교차트판정",
        "비교핵심사유",
        "비교뉴스수집성공",
        "비교뉴스수집오류",
        "종합예측",
        "종합점수",
        "대표뉴스키워드",
        "대표뉴스요약",
        "대표뉴스판정",
        "대표뉴스모델",
        "대표뉴스점수",
        "모델일치도",
        "뉴스중요도",
        "종합사유",
    ]
    df = normalize_report_columns(df, target_columns)

    if (not os.path.exists(REPORT_PATH)) or os.path.getsize(REPORT_PATH) == 0:
        df.to_csv(REPORT_PATH, index=False, encoding="utf-8-sig")
    else:
        old_df = pd.read_csv(REPORT_PATH, encoding="utf-8-sig")
        old_df = normalize_report_columns(old_df, target_columns)
        combined_df = pd.concat([old_df, df], ignore_index=True)
        combined_df.drop_duplicates(subset=["날짜", "종목명"], keep="last", inplace=True)
        combined_df.to_csv(REPORT_PATH, index=False, encoding="utf-8-sig")

    print(f"✅ 분석 완료! [ {REPORT_PATH} ] 파일을 확인하십시오.")
    print(df[[
        "종목명",
        "종합예측",
        "종합점수",
        "대표뉴스키워드",
        "대표뉴스판정",
        "대표뉴스요약",
    ]])


# =========================================================
# 8. 실행
# =========================================================
if __name__ == "__main__":
    run_auto_analysis()