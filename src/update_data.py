import FinanceDataReader as fdr
import pandas as pd
from datetime import datetime, timedelta
import os
from stock_filter import describe_stock_filter, filter_stocks

"""
관심 종목의 최근 5년치 주가 데이터를 수집하고 기술적 지표를 계산하는 스크립트.

저장 위치는 logs/raw_data/이며, main_auto.py와 backfill_history.py가
이 CSV를 읽어 차트 요약과 실제 결과 평가에 사용한다.
"""

# 1. 강제 매핑 리스트 (이름: 코드)
MY_STOCKS = {
    "삼성전자": "005930",
    "NVDA": "NVDA",
    "TSLA": "TSLA",
    "AAPL": "AAPL",
    "GOOGL": "GOOGL",
    "삼진제약": "000520",
    "케이뱅크": "272210",
    "O": "O",
    "포스코DX": "022100",
    "카카오": "035720"
}

ACTIVE_STOCKS = filter_stocks(MY_STOCKS)

def update_stock_data():
    """종목별 5년치 OHLCV 데이터, 이동평균선, 다음날 방향(Target)을 저장한다."""
    if not os.path.exists('logs/raw_data'):
        os.makedirs('logs/raw_data')
        print("📁 'logs/raw_data' 폴더 생성 완료!")

    if not ACTIVE_STOCKS:
        raise ValueError("STOCK_INCLUDE/STOCK_EXCLUDE 설정 후 실행할 종목이 없습니다.")

    print(f"🚀 [데이터 동기화] {len(ACTIVE_STOCKS)}개 종목 수집 시작!")
    print(f"[STOCKS] {describe_stock_filter(len(MY_STOCKS), len(ACTIVE_STOCKS))}")

    for name, code in ACTIVE_STOCKS.items():
        try:
            file_path = f"logs/raw_data/{name}_5year_data.csv"
            
            # 수집 기간 설정
            end_date = datetime.now()
            start_date = end_date - timedelta(days=365 * 5)
            
            print(f"📡 [{name}]({code}) 수집 중...", end=" ")
            
            # 야후 파이낸스에서 숫자 코드로 데이터 호출
            df = fdr.DataReader(code, start_date, end_date)

            if df is None or df.empty:
                print("❌ 데이터 없음")
                continue

            # 분석/평가에 공통으로 쓰는 기술적 지표와 다음 거래일 방향 라벨
            df['MA5'] = df['Close'].rolling(window=5).mean()
            df['MA20'] = df['Close'].rolling(window=20).mean()
            df['MA60'] = df['Close'].rolling(window=60).mean()
            df['Target'] = (df['Close'].shift(-1) > df['Close']).astype(int)

            # 저장 (파일명은 name 변수 사용!)
            df.dropna().to_csv(file_path)
            print(f"✅ 저장 완료!")

        except Exception as e:
            print(f"❌ [{name}] 에러: {e}")

if __name__ == "__main__":
    update_stock_data()
