import streamlit as st
import pandas as pd
import os
from datetime import datetime

# 1. 페이지 설정
st.set_page_config(page_title="Gemini 2.5 전략 대시보드", page_icon="📈", layout="wide")

# 스타일 적용
st.markdown("""
    <style>
    .stock-card { border-radius: 10px; padding: 15px; background-color: #f8f9fb; border-left: 5px solid #4e73df; margin-bottom: 10px; }
    .status-up { color: #e74a3b; font-weight: bold; }
    .status-down { color: #4e73df; font-weight: bold; }
    .status-wait { color: #858796; font-weight: bold; }
    </style>
    """, unsafe_allow_html=True)

def load_data():
    file_path = "logs/daily_analysis_report.csv"
    if os.path.exists(file_path):
        try:
            df = pd.read_csv(file_path)
            # 형님의 CSV 컬럼명인 'AI예측'을 '예측'으로 통일해서 코드 호환성 유지
            if 'AI예측' in df.columns:
                df = df.rename(columns={'AI예측': '예측'})
            return df.drop_duplicates(subset=['종목명'], keep='last')
        except: return pd.DataFrame()
    return pd.DataFrame()

st.title("🧠 Gemini 2.5 AI 주식 분석 센터")
df = load_data()

if df.empty:
    st.warning("📡 데이터를 불러올 수 없습니다. 파일 경로와 컬럼명을 확인해주세요!")
else:
    # 상단 요약 지표 (Metrics)
    # '예측' 컬럼에서 상승/하락 개수 체크 (없을 경우 대비 안전장치)
    total = len(df)
    ups = len(df[df['예측'].str.contains('상승', na=False)])
    waits = len(df[df['예측'].str.contains('관망', na=False)])
    
    m1, m2, m3 = st.columns(3)
    m1.metric("분석 종목", f"{total}개")
    m2.metric("상승 시그널", f"{ups}개", delta=f"관망 {waits}개")
    m3.metric("최근 업데이트", df['날짜'].iloc[-1] if '날짜' in df.columns else "미정")

    st.divider()

    # 종목별 카드 UI
    for _, row in df.iterrows():
        with st.container():
            c1, c2, c3, c4 = st.columns([1.5, 1, 1, 3])
            
            with c1:
                st.markdown(f"### {row['종목명']} `({row['티커']})`")
            
            with c2:
                pred = row['예측']
                if '상승' in pred: st.markdown(f"<h3 class='status-up'>▲ {pred}</h3>", unsafe_allow_html=True)
                elif '하락' in pred: st.markdown(f"<h3 class='status-down'>▼ {pred}</h3>", unsafe_allow_html=True)
                else: st.markdown(f"<h3 class='status-wait'>━ {pred}</h3>", unsafe_allow_html=True)
            
            with c3:
                conf = row['확신도']
                st.write("AI 확신도")
                st.progress(int(conf) / 100)
                st.caption(f"{conf}%")

            with c4:
                # 핫키워드와 요약 정보
                kw = row.get('핫키워드', '#정보없음')
                reason = row.get('핵심사유', '분석 데이터가 부족합니다.')
                st.info(f"**{kw}** | {reason[:60]}...")

            # 상세 정보 Expander
            with st.expander("🔍 심층 분석 리포트 확인"):
                st.write(f"**[전체 분석 내용]**")
                st.write(reason)
                if "에러" in kw:
                    st.error("⚠️ 구글 검색 연동 에러가 발생한 종목입니다. main_auto.py의 검색 도구 설정을 확인하세요.")
            
            st.markdown("<br>", unsafe_allow_html=True)