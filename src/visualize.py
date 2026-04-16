import pandas as pd
import matplotlib.pyplot as plt
import os
from matplotlib import rc

# 폰트 설정 (윈도우 맑은 고딕)
plt.rcParams['font.family'] = 'Malgun Gothic'
plt.rcParams['axes.unicode_minus'] = False  # 마이너스 기호 깨짐 방지

def plot_stock_trend(stock_name="삼성전자"):

    file_path = f"logs/raw_data/{stock_name}_5year_data.csv"
    
    if not os.path.exists(file_path):
        print(f"❌ {stock_name} 데이터 파일이 없어! 먼저 수집기를 돌려줘.")
        return

    # 데이터 로드
    df = pd.read_csv(file_path, index_col=0, parse_dates=True)

    # 차트 그리기
    plt.figure(figsize=(12, 6))
    plt.plot(df['Close'], label='Close Price', color='gray', alpha=0.5)
    plt.plot(df['MA20'], label='20일 이동평균선(한달 추세)', color='blue')
    plt.plot(df['MA60'], label='60일 이동평균선(분기 추세)', color='red')

    plt.title(f"[{stock_name}] 5-Year Trend with Moving Averages")
    plt.legend()
    plt.grid(True, alpha=0.3)
    
    # 결과 저장
    output_path = f"logs/{stock_name}_trend.png"
    plt.savefig(output_path)
    print(f"✅ {stock_name} 추세 차트가 {output_path}에 저장됐어!")
    plt.show()

if __name__ == "__main__":
    plot_stock_trend("삼성전자")