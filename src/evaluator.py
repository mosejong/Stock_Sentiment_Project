import pandas as pd
import os

FINAL_COLUMNS = [
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
    "실제결과",
    "적중여부",
]

def clean_prediction(text):
    """예측 텍스트에서 특수문자와 공백을 제거하고 핵심 단어만 추출"""
    text = str(text)
    if '상승' in text or '▲' in text:
        return "상승"
    if '하락' in text or '▼' in text:
        return "하락"
    if '관망' in text or '━' in text:
        return "관망"
    return "알수없음"

def normalize_columns(df: pd.DataFrame) -> pd.DataFrame:
    """입력 데이터 컬럼명을 표준화하고, 없는 컬럼은 빈값으로 채움"""
    rename_map = {
        '예측': 'AI예측',
        '확신도(%)': '확신도',
        '핵심 사유': '핵심사유',
    }
    df = df.rename(columns=rename_map)

    for col in FINAL_COLUMNS:
        if col not in df.columns:
            df[col] = ""

    df = df[FINAL_COLUMNS]
    return df

def integrate_all_performance():
    master_path = 'logs/total_performance.csv'
    report_path = 'logs/daily_analysis_report.csv'
    old_backtest_path = 'logs/old/backtest_log.csv'

    all_dfs = []

    # 1. 과거 데이터 로드 및 전처리
    if os.path.exists(old_backtest_path):
        df_old = pd.read_csv(old_backtest_path, encoding='utf-8-sig')
        df_old = normalize_columns(df_old)
        all_dfs.append(df_old)
        print(f"📂 과거 데이터({len(df_old)}건) 로드 및 컬럼 보정 완료!")

    # 2. 현재 데이터 로드 및 전처리
    if os.path.exists(report_path):
        df_new = pd.read_csv(report_path, encoding='utf-8-sig')
        df_new = normalize_columns(df_new)
        all_dfs.append(df_new)
        print(f"📂 현재 데이터({len(df_new)}건) 로드 및 컬럼 보정 완료!")

    if not all_dfs:
        print("❌ 불러올 데이터가 없습니다.")
        return

    # 3. 통합
    df_combined = pd.concat(all_dfs, ignore_index=True)
    df_combined.drop_duplicates(subset=['날짜', '종목명'], keep='last', inplace=True)

    results = []
    print("🔄 주가 데이터와 정밀 대조 중 (로직 보정 버전)...")

    for _, row in df_combined.iterrows():
        row = row.copy()

        name = row['종목명']
        date = str(row['날짜']).replace('/', '-')

        raw_pred = row.get('AI예측', '')
        pred = clean_prediction(raw_pred)

        file_path = f"logs/raw_data/{name}_5year_data.csv"

        if os.path.exists(file_path):
            try:
                df_stock = pd.read_csv(file_path, encoding='utf-8-sig')
                stock_row = df_stock[df_stock['Date'] >= date].iloc[0]
                actual_change = "상승" if stock_row['Target'] == 1 else "하락"

                if pred in ["관망", "알수없음"]:
                    is_correct = "━"
                else:
                    is_correct = "O" if pred == actual_change else "X"

                row['실제결과'] = actual_change
                row['적중여부'] = is_correct

            except Exception:
                if row.get('실제결과', '') == "":
                    row['실제결과'] = "대기중"
                if row.get('적중여부', '') == "":
                    row['적중여부'] = "-"
        else:
            if row.get('실제결과', '') == "":
                row['실제결과'] = "대기중"
            if row.get('적중여부', '') == "":
                row['적중여부'] = "-"

        results.append(row)

    # 4. 저장
    df_final = pd.DataFrame(results)
    df_final = normalize_columns(df_final)
    df_final.to_csv(master_path, index=False, encoding='utf-8-sig')

    valid = df_final[df_final['적중여부'].isin(['O', 'X'])]
    if not valid.empty:
        win_rate = (len(valid[valid['적중여부'] == 'O']) / len(valid)) * 100
        print(f"🎯 보정 후 적중률: {win_rate:.1f}% (총 {len(valid)}건 확정)")

    print(f"✅ 성과표 업데이트 완료: {master_path}")

if __name__ == "__main__":
    integrate_all_performance()