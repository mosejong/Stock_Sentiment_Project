import FinanceDataReader as fdr
from datetime import datetime, timedelta

def get_stock_trend(stock_name):
    try:
        # 1. 한국 종목 리스트 로드 (캐싱을 위해 한번만 불러오는게 좋지만 일단 진행)
        df_krx = fdr.StockListing('KRX')
        
        # 2. 종목 코드 찾기
        # 한글 이름인 경우 한국 시장에서 코드를 찾음
        target = df_krx[df_krx['Name'] == stock_name]
        
        if not target.empty:
            # 한국 주식은 '005930' 같은 코드를 사용
            stock_code = target['Code'].values[0]
        else:
            # 리스트에 없으면 미국 티커(NVDA, TSLA 등)라고 가정
            stock_code = stock_name

        # 3. 데이터 가져오기 (기간 30일)
        end_date = datetime.now()
        start_date = end_date - timedelta(days=30)
        
        # 한국 주식은 뒤에 시장 구분자를 붙여야 야후 파이낸스에서 잘 읽음
        # 예: 삼성전자 -> 005930.KS
        if stock_code.isdigit():
            # 유가증권(KS)인지 코스닥(KQ)인지 구분하면 좋지만, 보통 .KS나 .KQ를 붙임
            # FinanceDataReader가 내부적으로 처리 못할 때를 대비해 보정
            full_code = f"{stock_code}" 
            df = fdr.DataReader(full_code, start_date, end_date)
        else:
            # 미국 주식은 티커 그대로 사용
            df = fdr.DataReader(stock_code, start_date, end_date)

        if df.empty:
            return None

        # 4. 결과 정리
        current_price = int(df['Close'].iloc[-1])
        prev_price = int(df['Close'].iloc[-2])
        change_percent = ((current_price - prev_price) / prev_price) * 100
        ma5 = df['Close'].rolling(window=5).mean().iloc[-1]
        
        return {
            "current": current_price,
            "change": change_percent,
            "trend": "상승세" if current_price > ma5 else "하락/보합세",
            "raw_df": df
        }

    except Exception as e:
        print(f"주가 데이터 수집 실패 ({stock_name}): {e}")
        return None