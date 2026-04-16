import time
from old.main_logic import run_stock_analysis

# 미국 주식은 티커(Ticker)로 적어주는 게 가장 확실해!
MY_STOCKS = [
    "삼성전자", "NVDA", "TSLA", "AAPL", "GOOGL", 
    "삼진제약", "케이뱅크", "O", "포스코DX", "카카오"
]
def start_macro():
    print(f"🚀 [강력 매크로] 총 {len(MY_STOCKS)}개 종목 분석을 시작합니다.")
    
    for stock in MY_STOCKS:
        success = False
        retry_count = 0
        
        while not success and retry_count < 5:
            print(f"\n--- [{stock}] 분석 시도 ({retry_count + 1}/5) ---")
            
            report = run_stock_analysis(stock)
            
            if report and "🕵️" not in report and "❌" not in report:
                success = True
                print(f"✅ {stock} 분석 성공 및 저장 완료!")
            else:
                retry_count += 1
                # 429 에러가 떴다면 구글이 화난 상태니까 아주 길게 쉬어줌
                wait_time = 65 # 65초로 늘려서 쿼터 초기화를 기다림
                print(f"⚠️ 쿼터 초과 또는 서버 지연! {wait_time}초 동안 강제 휴식합니다...")
                time.sleep(wait_time)
        
        if not success:
            print(f"❌ {stock}은 5번 시도했으나 서버 폭주로 실패했습니다. 다음으로 넘어갑니다.")
            
        time.sleep(5) # 종목 간 휴식

if __name__ == "__main__":
    start_macro()