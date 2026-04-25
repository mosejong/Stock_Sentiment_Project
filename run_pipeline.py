import subprocess
import time
import sys

def run_script(script_path, description):
    print(f"\n{'-'*50}")
    print(f"🔄 {description} 시작...")
    print(f"{'-'*50}")
    
    # 가상환경의 python 실행 파일을 사용하도록 설정
    result = subprocess.run([sys.executable, script_path])
    
    if result.returncode == 0:
        print(f"✅ {description} 완료!")
    else:
        print(f"❌ {description} 중 에러 발생!")
        return False
    return True

def main():
    print("AI 주식 분석 파이프라인을 시작합니다.")
    
    # 1단계: 데이터 최신화
    if not run_script("src/update_data.py", "1단계: 주가 데이터 업데이트"):
        return

    # 2단계: AI 분석 리포트 생성
    if not run_script("src/main_auto.py", "2단계: AI 시장 분석 및 리포트 생성"):
        return

    # 3단계: 성과 통합 및 적중률 계산
    if not run_script("src/evaluator.py", "3단계: 어제 예측 적중률 계산 및 통합"):
        return

    print(f"\n{'-'*50}")
    print("모든 분석 작업이 완료되었습니다.")
    print(f"{'-'*50}\n")

    # 4단계: Git push → Streamlit Cloud 자동 반영
    print("🔄 GitHub 업로드 중...")
    git_result = subprocess.run(
        'git add logs/daily_analysis_report.csv logs/total_performance.csv '
        '&& git commit -m "data: 일일 분석 업데이트" '
        '&& git push origin main',
        shell=True
    )
    if git_result.returncode == 0:
        print("✅ GitHub 업로드 완료! Streamlit 대시보드가 자동 반영됩니다.")
    else:
        print("⚠️ GitHub 업로드 실패 (변경사항 없거나 네트워크 오류)")

    time.sleep(2)

    # 5단계: 로컬 웹 앱 실행 (선택)
    subprocess.run([sys.executable, "-m", "streamlit", "run", "src/web_app.py"])

if __name__ == "__main__":
    main()
