import FinanceDataReader as fdr
import pandas as pd
from datetime import datetime, timedelta
import os

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

def update_stock_data():
    if not os.path.exists('logs/raw_data'):
        os.makedirs('logs/raw_data')
        print("📁 'logs/raw_data' 폴더 생성 완료!")

    print(f"🚀 [데이터 동기화] {len(MY_STOCKS)}개 종목 수집 시작!")

    for name, code in MY_STOCKS.items():
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

            # 기술적 지표 계산
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