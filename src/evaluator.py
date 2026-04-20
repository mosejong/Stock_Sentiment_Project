import os

import pandas as pd

"""
AI 예측 리포트와 실제 주가 데이터를 대조해 통합 성과표를 만드는 스크립트.

backfill_analysis_report.csv는 과거 검증용 데이터, daily_analysis_report.csv는
오늘 기준 운영 데이터다. 두 파일을 합쳐 logs/total_performance.csv로 저장하고,
예측일 다음 거래일의 종가 방향으로 실제결과/적중여부/수익률을 계산한다.
"""

REPORT_SOURCES = [
    ("레거시", "logs/old/backtest_log.csv"),
    ("백필", "logs/backfill_analysis_report.csv"),
    ("일일", "logs/daily_analysis_report.csv"),
]

MASTER_PATH = "logs/total_performance.csv"
RAW_DATA_DIR = "logs/raw_data"

FINAL_COLUMNS = [
    "데이터구분",
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
    "종합예측",
    "종합점수",
    "모델일치도",
    "뉴스중요도",
    "종합사유",
    "기준가",
    "평가일",
    "평가가",
    "수익률",
    "실제결과",
    "적중여부",
    "평가상태",
]


def clean_prediction(text):
    """예측 텍스트에서 특수문자와 공백을 제거하고 핵심 단어만 추출한다."""
    text = str(text)
    if "상승" in text or "▲" in text:
        return "상승"
    if "하락" in text or "▼" in text:
        return "하락"
    if "관망" in text or "━" in text:
        return "관망"
    return "알수없음"


def normalize_columns(df: pd.DataFrame, source_name: str = "") -> pd.DataFrame:
    """입력 데이터 컬럼명을 표준화하고 없는 컬럼은 빈값으로 채운다."""
    rename_map = {
        "예측": "AI예측",
        "확신도(%)": "확신도",
        "핵심 사유": "핵심사유",
    }
    df = df.rename(columns=rename_map)

    if "데이터구분" not in df.columns:
        df["데이터구분"] = source_name

    for col in FINAL_COLUMNS:
        if col not in df.columns:
            df[col] = ""

    return df[FINAL_COLUMNS].copy()


def load_report_sources() -> list:
    """백필/일일/레거시 리포트를 읽어 하나의 리스트로 반환한다."""
    all_dfs = []

    for source_name, path in REPORT_SOURCES:
        if not os.path.exists(path):
            continue

        try:
            df = pd.read_csv(path, encoding="utf-8-sig")
            df = normalize_columns(df, source_name)
            all_dfs.append(df)
            print(f"[로드] {source_name} 데이터: {path} ({len(df)}건)")
        except Exception as e:
            print(f"[경고] {source_name} 데이터 로드 실패: {path} / {e}")

    return all_dfs


def load_stock_price_data(stock_name: str, ticker: str) -> pd.DataFrame | None:
    """종목명 또는 티커 기준 raw_data CSV를 찾아 날짜/종가 컬럼을 정리한다."""
    possible_paths = [
        os.path.join(RAW_DATA_DIR, f"{stock_name}_5year_data.csv"),
        os.path.join(RAW_DATA_DIR, f"{ticker}_5year_data.csv"),
    ]

    for path in possible_paths:
        if not path or not os.path.exists(path):
            continue

        try:
            df = pd.read_csv(path, encoding="utf-8-sig")
            df.columns = [str(col).strip().replace("\ufeff", "") for col in df.columns]

            # 일부 해외주식 CSV는 첫 날짜 컬럼명이 비어 H1 등으로 들어온다.
            if "Date" not in df.columns:
                df = df.rename(columns={df.columns[0]: "Date"})

            if "Date" not in df.columns or "Close" not in df.columns:
                continue

            df["Date"] = pd.to_datetime(df["Date"], errors="coerce")
            df["Close"] = pd.to_numeric(df["Close"], errors="coerce")
            df = df.dropna(subset=["Date", "Close"]).sort_values("Date").reset_index(drop=True)

            if not df.empty:
                return df
        except Exception:
            continue

    return None


def evaluate_prediction(row: pd.Series) -> pd.Series:
    """
    예측일의 종가와 다음 거래일 종가를 비교해 실제 방향과 수익률을 계산한다.

    상승/하락 예측은 O/X로 평가하고, 관망은 방향을 맞히는 문제가 아니므로
    적중여부를 ━ 로 둔다. 다음 거래일 데이터가 없으면 대기중으로 남긴다.
    """
    row = row.copy()

    stock_name = str(row.get("종목명", "")).strip()
    ticker = str(row.get("티커", "")).strip()
    analysis_date = pd.to_datetime(row.get("날짜", ""), errors="coerce")
    prediction = clean_prediction(row.get("AI예측", ""))

    if pd.isna(analysis_date):
        row["평가상태"] = "날짜오류"
        row["실제결과"] = "대기중"
        row["적중여부"] = "-"
        return row

    price_df = load_stock_price_data(stock_name, ticker)
    if price_df is None or price_df.empty:
        row["평가상태"] = "주가데이터없음"
        row["실제결과"] = "대기중"
        row["적중여부"] = "-"
        return row

    candidates = price_df[price_df["Date"] >= analysis_date].copy()
    if candidates.empty:
        row["평가상태"] = "평가대기"
        row["실제결과"] = "대기중"
        row["적중여부"] = "-"
        return row

    entry_index = candidates.index[0]
    next_index = entry_index + 1

    if next_index >= len(price_df):
        row["평가상태"] = "다음거래일대기"
        row["실제결과"] = "대기중"
        row["적중여부"] = "-"
        return row

    entry_row = price_df.loc[entry_index]
    next_row = price_df.loc[next_index]

    entry_close = float(entry_row["Close"])
    next_close = float(next_row["Close"])
    return_rate = ((next_close - entry_close) / entry_close) * 100 if entry_close else 0
    actual_result = "상승" if next_close > entry_close else "하락"

    if prediction in ["관망", "알수없음"]:
        is_correct = "━"
    else:
        is_correct = "O" if prediction == actual_result else "X"

    row["기준가"] = round(entry_close, 4)
    row["평가일"] = next_row["Date"].strftime("%Y-%m-%d")
    row["평가가"] = round(next_close, 4)
    row["수익률"] = round(return_rate, 2)
    row["실제결과"] = actual_result
    row["적중여부"] = is_correct
    row["평가상태"] = "평가완료"

    return row


def print_summary(df: pd.DataFrame):
    """전체/데이터구분별 적중률과 평균 수익률을 터미널에 요약 출력한다."""
    valid = df[df["적중여부"].isin(["O", "X"])].copy()
    evaluated = df[df["평가상태"] == "평가완료"].copy()

    if valid.empty:
        print("[경고] O/X로 평가 가능한 상승/하락 예측이 아직 없습니다.")
    else:
        win_rate = (valid["적중여부"] == "O").mean() * 100
        print(f"[적중률] 전체: {win_rate:.1f}% ({len(valid)}건)")

    if not evaluated.empty:
        evaluated["수익률"] = pd.to_numeric(evaluated["수익률"], errors="coerce")
        avg_return = evaluated["수익률"].mean()
        print(f"[수익률] 전체 평균 다음 거래일 수익률: {avg_return:.2f}% ({len(evaluated)}건)")

    for source_name, group in df.groupby("데이터구분"):
        source_valid = group[group["적중여부"].isin(["O", "X"])]
        if source_valid.empty:
            continue
        source_win_rate = (source_valid["적중여부"] == "O").mean() * 100
        print(f"   - {source_name}: {source_win_rate:.1f}% ({len(source_valid)}건)")


def integrate_all_performance():
    """모든 분석 리포트를 통합하고 실제 다음 거래일 결과를 붙여 저장한다."""
    all_dfs = load_report_sources()

    if not all_dfs:
        print("[오류] 불러올 분석 리포트가 없습니다.")
        return

    df_combined = pd.concat(all_dfs, ignore_index=True)
    df_combined["날짜"] = pd.to_datetime(df_combined["날짜"], errors="coerce").dt.strftime("%Y-%m-%d")

    # 같은 날짜/종목이 여러 파일에 있으면 뒤쪽 소스가 우선된다.
    # 우선순위: 레거시 < 백필 < 일일
    df_combined.drop_duplicates(subset=["날짜", "종목명"], keep="last", inplace=True)
    df_combined = df_combined.sort_values(["날짜", "종목명"]).reset_index(drop=True)

    print("[계산] 주가 데이터와 대조해 성과를 계산합니다...")
    df_final = df_combined.apply(evaluate_prediction, axis=1)
    df_final = normalize_columns(pd.DataFrame(df_final))

    os.makedirs(os.path.dirname(MASTER_PATH), exist_ok=True)
    df_final.to_csv(MASTER_PATH, index=False, encoding="utf-8-sig")

    print_summary(df_final)
    print(f"[완료] 통합 성과표 저장: {MASTER_PATH} ({len(df_final)}건)")


if __name__ == "__main__":
    integrate_all_performance()
