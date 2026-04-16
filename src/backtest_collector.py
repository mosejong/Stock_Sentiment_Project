import os
import pandas as pd
import google.generativeai as genai  # 경고는 뜨지만 현재 라이브러리 유지
from datetime import datetime, timedelta
import time
from dotenv import load_dotenv

# 1. 설정 로드
load_dotenv()
api_key = os.getenv("GOOGLE_API_KEY")
genai.configure(api_key=api_key)
model = genai.GenerativeModel('gemini-2.5-flash')

def get_past_analysis(stock_name, target_date):
    """과거 특정 날짜의 데이터를 기반으로 AI 분석 요청"""
    file_path = f"logs/raw_data/{stock_name}_5year_data.csv"
    if not os.path.exists(file_path):
        print(f"⚠️ {stock_name} 파일이 없습니다. 패스합니다.")
        return None
    
    # CSV 읽기
    df = pd.read_csv(file_path)

    # [핵심] KeyError 방지: 어떤 이름으로 되어있든 첫 번째 컬럼을 'Date'로 강제 지정
    if 'Date' not in df.columns:
        if 'date' in df.columns:
            df.rename(columns={'date': 'Date'}, inplace=True)
        else:
            # 첫 번째 열이 보통 날짜이므로 강제 매핑
            df.rename(columns={df.columns[0]: 'Date'}, inplace=True)
    
    try:
        # 날짜 비교를 위해 형식 통일
        df['Date'] = pd.to_datetime(df['Date']).dt.date
        day_data = df[df['Date'] == target_date]
        
        if day_data.empty:
            return None
            
        latest = day_data.iloc[0]
        
        # 지표 추출 (대소문자 무관하게 가져오기)
        def get_val(row, names):
            for name in names:
                if name in row: return row[name]
            return 0

        close = get_val(latest, ['Close', 'close', 'Adj Close'])
        ma20 = get_val(latest, ['MA20', 'ma20'])
        ma60 = get_val(latest, ['MA60', 'ma60'])
        
        stock_info = f"종가: {close:.2f}, 20일선: {ma20:.2f}, 60일선: {ma60:.2f}"
        
        # [프롬프트] 형님이 정하신 표준 양식으로 요청
        prompt = f"""
        당신은 냉철한 주식 전략가입니다. {target_date} 당일 지표만 보고 분석하세요.
        [지표]: {stock_info}
        
        지침:
        1. 확신도는 85%를 제외하고 50~95 사이로 산출할 것.
        2. 호재/악재 무게를 따져서 관망(━)도 적극 사용할 것.
        3. 반드시 JSON 형식으로 답변할 것.

        형식:
        {{
            "prediction": "▲ 상승/▼ 하락/━ 관망",
            "confidence": "숫자만",
            "keyword": "핫키워드",
            "reason": "한줄사유"
        }}
        """
        
        response = model.generate_content(prompt, generation_config={"temperature": 0.0})
        # JSON 파싱 (문자열에서 JSON 부분만 추출)
        import re
        json_match = re.search(r'\{.*\}', response.text, re.DOTALL)
        if json_match:
            import json
            return json.loads(json_match.group())
        return None

    except Exception as e:
        print(f"❌ {stock_name} 처리 중 에러: {e}")
        return None

def run_backtest(days_back=30):
    # 형님의 10대 천왕 종목
    MY_STOCKS = ["삼성전자", "NVDA", "TSLA", "AAPL", "GOOGL", "삼진제약", "케이뱅크", "O", "포스코DX", "카카오"]
    
    end_date = datetime.now().date()
    start_date = end_date - timedelta(days=days_back)
    
    all_results = []
    
    print(f"🚀 [백테스트 엔진] {start_date}부터 오늘까지 데이터 복구 시작!")
    
    current_date = start_date
    while current_date <= end_date:
        # 주말 제외 (토=5, 일=6)
        if current_date.weekday() < 5:
            print(f"📅 {current_date} 데이터 스캔 중...", end="\r")
            for stock in MY_STOCKS:
                res = get_past_analysis(stock, current_date)
                if res:
                    all_results.append({
                        "날짜": current_date,
                        "종목명": stock,
                        "예측": res['prediction'],
                        "확신도": res['confidence'],
                        "핫키워드": f"#{res['keyword']}",
                        "핵심사유": res['reason']
                    })
                time.sleep(0.5) # 유료 계정 속도감
        current_date += timedelta(days=1)
    
    # 결과 저장 (정제 코드와 호환되도록 저장)
    if all_results:
        df = pd.DataFrame(all_results)
        df.to_csv("logs/backtest_log.csv", index=False, encoding='utf-8-sig')
        print(f"\n🏁 백테스트 완료! {len(df)}개의 과거 판단이 logs/backtest_log.csv에 저장되었습니다.")
    else:
        print("\n❌ 분석된 데이터가 없습니다.")

if __name__ == "__main__":
    run_backtest(30)