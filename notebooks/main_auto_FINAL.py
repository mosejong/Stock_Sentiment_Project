import os
import pandas as pd
import google.generativeai as genai
from datetime import datetime
import time
import json
import re
from dotenv import load_dotenv

# 1. 환경 설정
load_dotenv()
api_key = os.getenv("GOOGLE_API_KEY")
genai.configure(api_key=api_key)

# 모델 및 경로 설정
MODEL_NAME = 'gemini-2.5-flash'
REPORT_PATH = "logs/daily_analysis_report.csv"
today_date = datetime.now().strftime("%Y-%m-%d")

# 10대 천왕 종목 리스트
MY_STOCKS = {
    "삼성전자": "005930", "NVDA": "NVDA", "TSLA": "TSLA", "AAPL": "AAPL", "GOOGL": "GOOGL",
    "삼진제약": "000520", "케이뱅크": "272210", "리얼티인컴": "O", "포스코DX": "022100", "카카오": "035720"
}

def get_stock_data_summary(stock_name):
    ticker = MY_STOCKS.get(stock_name, stock_name)
    file_path = f"logs/raw_data/{stock_name}_5year_data.csv"
    if not os.path.exists(file_path):
        file_path = f"logs/raw_data/{ticker}_5year_data.csv"
    
    if os.path.exists(file_path):
        try:
            df = pd.read_csv(file_path, index_col=0)
            latest = df.iloc[-1]
            return f"현재가: {latest['Close']:.2f}, 20일선: {latest['MA20']:.2f}, 60일선: {latest['MA60']:.2f}"
        except: return "차트 데이터 읽기 오류"
    return "차트 데이터 없음"

def get_ai_analysis(stock_name):
    chart_info = get_stock_data_summary(stock_name)
    
    # [긴급 수정] 에러 메시지에 따라 google_search로 명칭 변경 및 다중 시도 로직
    # 형님의 환경에서 가장 확실하게 작동하는 도구를 자동으로 찾습니다.
    tools_to_try = [
        [{"google_search": {}}],           # 1순위: 에러 메시지가 요청한 이름
        [{"google_search_retrieval": {}}], # 2순위: 최신 SDK 표준
        None                               # 3순위: 도구 없이 기본 분석
    ]
    
    response_text = ""
    for tool_set in tools_to_try:
        try:
            model = genai.GenerativeModel(model_name=MODEL_NAME, tools=tool_set)
            prompt = f"""
            너는 대한민국 수석 애널리스트다. {today_date} 기준 '{stock_name}'을 분석하라.
            [차트 정보]: {chart_info}
            [보고 지침]:
            1. Google 검색으로 주가에 영향 주는 실시간 핵심 뉴스 재료를 반드시 포함하라.
            2. 핵심 사유는 팩트와 결론 위주로 가독성 좋게 요약하라.
            3. 핵심 사유(reason)는 줄바꿈(\\\\n)을 활용해 4~5줄 이내의 불렛 포인트로 작성하라.
            4. 반드시 JSON으로만 답하라. (마크다운 금지)

            {{
                "prediction": "▲ 상승 / ▼ 하락 / ━ 관망",
                "confidence": "90",
                "keyword": "핵심키워드",
                "reason": "• 뉴스: 내용\\\\n• 차트: 분석\\\\n• 결론: 전략"
            }}
            """
            response = model.generate_content(prompt)
            response_text = response.text
            break # 성공하면 루프 탈출
        except Exception as e:
            if tool_set == None: # 마지막 시도까지 실패하면
                print(f"❌ {stock_name} 최종 분석 실패: {e}")
                return None
            continue # 다음 도구 이름으로 재시도
            
    try:
        # JSON 텍스트 정제
        clean_text = re.sub(r'```json|```', '', response_text).strip()
        return json.loads(clean_text)
    except:
        return None

def run_auto_analysis():
    print(f"🚀 {today_date} 전 종목 자동화 기강 잡기 시작 (뉴스 검색 모드)...")
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
                "핵심사유": analysis.get("reason", "내용 없음").replace("\n", " ")
            }
        else:
            data = {
                "날짜": today_date, "종목명": stock, "티커": MY_STOCKS[stock],
                "AI예측": "━ 관망", "확신도": "0", "핫키워드": "분석실패", "핵심사유": "서버 응답 오류"
            }
        
        results.append(data)
        time.sleep(2) # 할당량 보호
        
    df = pd.DataFrame(results)
    target_columns = ["날짜", "종목명", "티커", "AI예측", "확신도", "핫키워드", "핵심사유"]
    df = df[target_columns]
    
    # 저장 시 encoding 옵션으로 한글 깨짐 방지
    if not os.path.exists(REPORT_PATH):
        df.to_csv(REPORT_PATH, index=False, encoding='utf-8-sig')
    else:
        df.to_csv(REPORT_PATH, mode='a', header=False, index=False, encoding='utf-8-sig')
        
    print(f"✅ 분석 완료! [ {REPORT_PATH} ] 파일을 확인하십시오.")

if __name__ == "__main__":
    run_auto_analysis()