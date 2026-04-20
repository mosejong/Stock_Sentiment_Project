import streamlit as st
import pandas as pd
import os
from datetime import datetime
import plotly.graph_objects as go

"""
Streamlit 대시보드.

daily_analysis_report.csv의 최신 날짜 데이터를 읽어 종목별 AI 예측,
확신도, 뉴스 요약, 판단 근거, 최근 차트를 보여준다.
분석 생성 로직은 main_auto.py/backfill_history.py에 있고,
이 파일은 저장된 결과를 사용자가 보기 좋게 표시하는 역할만 담당한다.
"""

# 1. 페이지 설정
st.set_page_config(page_title="Gemini Pro Insight", layout="wide", page_icon="💎")

# 2. 커스텀 CSS
st.markdown("""
    <style>
    .stApp {
        background-color: #0E1117;
        color: #E0E0E0;
    }

    div[data-testid="stMetric"] {
        background-color: #161B22;
        border: 1px solid #30363D;
        padding: 20px;
        border-radius: 12px;
        box-shadow: 0 4px 10px rgba(0,0,0,0.3);
    }

    .main-title {
        font-size: 3rem;
        font-weight: 800;
        background: -webkit-linear-gradient(#60EFFF, #00A3FF);
        -webkit-background-clip: text;
        -webkit-text-fill-color: transparent;
        margin-bottom: 0.5rem;
    }

    .mini-badge {
        display: inline-block;
        padding: 6px 12px;
        margin-right: 8px;
        margin-bottom: 8px;
        border-radius: 999px;
        font-size: 0.85rem;
        font-weight: 700;
        color: white;
    }

    .badge-keyword { background-color: #F59E0B; color: black; }
    .badge-chart { background-color: #0EA5E9; }
    .badge-pattern { background-color: #10B981; }

    .section-title {
        font-size: 1.05rem;
        font-weight: 700;
        margin-top: 12px;
        margin-bottom: 8px;
        color: #FFFFFF;
    }

    .reason-box {
        background-color: #0F172A;
        border: 1px solid #334155;
        padding: 14px;
        border-radius: 10px;
        line-height: 1.8;
    }

    .source-box {
        background-color: #111827;
        border: 1px solid #374151;
        padding: 12px;
        border-radius: 10px;
        color: #CBD5E1;
        font-size: 0.9rem;
        line-height: 1.6;
    }

    .stTabs [data-baseweb="tab-list"] {
        gap: 10px;
    }

    .stTabs [data-baseweb="tab"] {
        height: 50px;
        background-color: #161B22;
        border-radius: 5px 5px 0px 0px;
        color: white;
    }
    </style>
""", unsafe_allow_html=True)

REPORT_PATH = "logs/daily_analysis_report.csv"


def load_stock_chart_data(stock_name: str, ticker: str):
    """종목명 파일을 우선 찾고, 없으면 티커 파일에서 차트 데이터를 불러온다."""
    possible_paths = [
        f"logs/raw_data/{stock_name}_5year_data.csv",
        f"logs/raw_data/{ticker}_5year_data.csv",
    ]

    for path in possible_paths:
        if os.path.exists(path):
            try:
                df = pd.read_csv(path, encoding="utf-8-sig")
                df.columns = df.columns.str.strip()

                if "Date" in df.columns:
                    df["Date"] = pd.to_datetime(df["Date"], errors="coerce")
                    df = df.dropna(subset=["Date"])

                return df
            except Exception:
                return None
    return None


def load_data():
    """대시보드에 필요한 분석 CSV를 읽고 컬럼/타입을 표준화한다."""
    expected_columns = [
        "날짜", "종목명", "티커", "기준모델", "AI예측", "확신도",
        "핫키워드", "뉴스판정", "뉴스요약", "뉴스출처",
        "패턴판정", "차트판정", "핵심사유",
        "비교모델", "비교AI예측", "비교확신도", "비교핫키워드",
        "비교뉴스판정", "비교뉴스요약", "비교뉴스출처",
        "비교패턴판정", "비교차트판정", "비교핵심사유",
        "종합예측", "종합점수", "모델일치도", "뉴스중요도", "종합사유"
    ]

    if not os.path.exists(REPORT_PATH):
        return None

    try:
        df = pd.read_csv(REPORT_PATH, encoding="utf-8-sig")
        df.columns = df.columns.str.strip()
        df.columns = df.columns.str.replace("\ufeff", "", regex=False)

        if "확신도" not in df.columns:
            df = pd.read_csv(
                REPORT_PATH,
                encoding="utf-8-sig",
                header=None,
                names=expected_columns
            )

        for col in expected_columns:
            if col not in df.columns:
                df[col] = None

        df["확신도"] = pd.to_numeric(df["확신도"], errors="coerce").fillna(50)
        df["날짜"] = pd.to_datetime(df["날짜"], errors="coerce")
        df = df.dropna(subset=["날짜"])

        text_cols = [
            "종목명", "티커", "기준모델", "AI예측", "핫키워드",
            "뉴스판정", "뉴스요약", "뉴스출처",
            "패턴판정", "차트판정", "핵심사유",
            "비교모델", "비교AI예측", "비교핫키워드",
            "비교뉴스판정", "비교뉴스요약", "비교뉴스출처",
            "비교패턴판정", "비교차트판정", "비교핵심사유",
            "종합예측", "종합점수", "모델일치도", "뉴스중요도", "종합사유"
        ]
        for col in text_cols:
            df[col] = df[col].fillna("").astype(str)

        return df

    except Exception as e:
        st.error(f"🚨 데이터 로딩 실패: {e}")
        return None


def get_prediction_color(pred_val: str):
    """예측 방향에 따라 카드 강조 색상을 반환한다."""
    if "상승" in pred_val:
        return "#FF4B4B"   # 한국 주식 스타일: 상승 빨강
    elif "하락" in pred_val:
        return "#3182CE"   # 하락 파랑
    return "#E5E7EB"


def get_news_signal_color(signal: str):
    """뉴스판정 값을 배지 색상으로 변환한다."""
    signal = str(signal).strip()
    if "호재" in signal:
        return "#22C55E"   # 초록
    if "악재" in signal:
        return "#EF4444"   # 빨강
    if "기대감" in signal:
        return "#F59E0B"   # 노랑
    return "#94A3B8"       # 회색


def get_confidence_color(score):
    """확신도 구간별 표시 색상을 반환한다."""
    try:
        score = float(score)
    except Exception:
        return "#94A3B8"

    if score >= 85:
        return "#22C55E"   # 초록
    elif score >= 70:
        return "#F59E0B"   # 노랑
    elif score >= 50:
        return "#FB923C"   # 주황
    return "#EF4444"       # 빨강


def shorten_text(text: str, limit: int = 20):
    """표 형태에서 긴 뉴스 요약이 화면을 밀어내지 않도록 줄인다."""
    text = str(text).strip()
    if len(text) > limit:
        return text[:limit] + "..."
    return text


df = load_data()

if "selected_stock" not in st.session_state:
    st.session_state["selected_stock"] = "전체"

if "stock_filter_widget" not in st.session_state:
    st.session_state["stock_filter_widget"] = "전체"

# 헤더
st.markdown('<p class="main-title">💎 Gemini AI Strategy Report</p>', unsafe_allow_html=True)
st.markdown(f"🗓️ **Market Data Updated:** `{datetime.now().strftime('%Y-%m-%d %H:%M')}`")
st.divider()

if df is not None and not df.empty:
    latest_date = df["날짜"].max()
    latest_df = df[df["날짜"] == latest_date].copy()

    st.markdown(f"📅 **Latest Report Date:** `{latest_date.strftime('%Y-%m-%d')}`")

    # KPI
    col1, col2, col3, col4 = st.columns(4)
    with col1:
        st.metric("Total Analysis", f"{len(latest_df)} stocks")
    with col2:
        up_count = len(latest_df[latest_df["AI예측"].str.contains("상승", na=False)])
        st.metric("Bullish (상승)", f"{up_count}", delta=f"{(up_count / len(latest_df) * 100):.1f}%")
    with col3:
        down_count = len(latest_df[latest_df["AI예측"].str.contains("하락", na=False)])
        st.metric("Bearish (하락)", f"{down_count}", delta=f"-{(down_count / len(latest_df) * 100):.1f}%")
    with col4:
        avg_conf = latest_df["확신도"].mean()
        st.metric("Avg. Confidence", f"{avg_conf:.1f}%")

    st.write("")

    # 사이드바 필터
    with st.sidebar:
        st.subheader("🔧 필터")
        st.caption("예측 결과가 모두 선택되어 있으면 전체 보기입니다.")

        pred_filter = st.multiselect(
            "예측 결과",
            ["▲ 상승", "▼ 하락", "━ 관망"],
            default=["▲ 상승", "▼ 하락", "━ 관망"]
        )

        stock_list = ["전체"] + sorted(latest_df["종목명"].unique().tolist())
        stock_filter = st.selectbox(
            "종목 선택",
            stock_list,
            key="stock_filter_widget"
        )

        min_conf = st.slider("최소 확신도", 0, 100, 0)

    # multiselect 전부 해제 방어
    if not pred_filter:
        pred_filter = ["▲ 상승", "▼ 하락", "━ 관망"]

    filtered_df = latest_df.copy()
    # 사이드바 조건을 최신 리포트에 적용한다.
    filtered_df = filtered_df[filtered_df["AI예측"].isin(pred_filter)]
    filtered_df = filtered_df[filtered_df["확신도"] >= min_conf]

    if stock_filter != "전체":
        filtered_df = filtered_df[filtered_df["종목명"] == stock_filter]

    tab1, tab2 = st.tabs(["📊 Market Overview", "🔍 Deep Dive Analysis"])

    with tab1:
        def style_df(row):
            styles = [''] * len(row)

            # 컬럼 순서:
            # 종목명, AI예측, 확신도, 핫키워드, 주요뉴스, 뉴스판정
            pred = str(row["AI예측"])
            conf = row["확신도"]
            news_signal = str(row["뉴스판정"])

            # AI예측 색상
            if "상승" in pred:
                styles[1] = "color: #FF4B4B; font-weight: bold;"
            elif "하락" in pred:
                styles[1] = "color: #3182CE; font-weight: bold;"
            else:
                styles[1] = "color: #E5E7EB; font-weight: bold;"

            # 확신도 색상
            conf_color = get_confidence_color(conf)
            styles[2] = f"color: {conf_color}; font-weight: bold;"

            # 뉴스판정 색상
            news_color = get_news_signal_color(news_signal)
            styles[5] = f"color: {news_color}; font-weight: bold;"

            return styles

        display_df = filtered_df[[
            "종목명", "AI예측", "확신도", "핫키워드", "뉴스요약", "뉴스판정",
            "비교AI예측", "비교확신도", "종합예측", "종합점수"
        ]].copy()

        display_df["주요뉴스"] = display_df["뉴스요약"].apply(lambda x: shorten_text(x, 35))

        display_df = display_df[[
            "종목명", "AI예측", "확신도", "핫키워드", "주요뉴스", "뉴스판정",
            "비교AI예측", "비교확신도", "종합예측", "종합점수"
        ]]

        st.dataframe(
            display_df.style.apply(style_df, axis=1),
            use_container_width=True,
            height=620,
            column_config={
                "종목명": st.column_config.TextColumn("종목명", width="small"),
                "AI예측": st.column_config.TextColumn("AI예측", width="small"),
                "확신도": st.column_config.NumberColumn("확신도", width="small"),
                "핫키워드": st.column_config.TextColumn("핫키워드", width="medium"),
                "주요뉴스": st.column_config.TextColumn("주요뉴스", width="large"),
                "뉴스판정": st.column_config.TextColumn("뉴스판정", width="medium"),
                "비교AI예측": st.column_config.TextColumn("비교AI예측", width="small"),
                "비교확신도": st.column_config.TextColumn("비교확신도", width="small"),
                "종합예측": st.column_config.TextColumn("종합예측", width="small"),
                "종합점수": st.column_config.TextColumn("종합점수", width="small"),
            }
        )

        st.write("### 🔎 종목 바로 보기")

        button_cols = st.columns(5)
        stock_names = filtered_df["종목명"].tolist()

        for i, stock_name in enumerate(stock_names):
            with button_cols[i % 5]:
                if st.button(f"{stock_name}", key=f"btn_{stock_name}"):
                    st.session_state["selected_stock"] = stock_name
                    st.rerun()

    with tab2:
        detail_df = latest_df.copy()

        selected_stock = st.session_state.get("selected_stock", "전체")

        # 버튼으로 고른 종목 우선
        if selected_stock != "전체":
            detail_df = detail_df[detail_df["종목명"] == selected_stock]

        # 사이드바 종목 선택도 추가 필터로 반영
        if stock_filter != "전체":
            detail_df = detail_df[detail_df["종목명"] == stock_filter]

        detail_df = detail_df[detail_df["AI예측"].isin(pred_filter)]
        detail_df = detail_df[detail_df["확신도"] >= min_conf]

        if detail_df.empty:
            st.warning("조건에 맞는 종목이 없습니다.")
        else:
            current_label = selected_stock if selected_stock != "전체" else stock_filter
            st.markdown(f"### 현재 선택된 종목: {current_label}")

            for _, row in detail_df.iterrows():
                pred_val = str(row["AI예측"])
                accent_color = get_prediction_color(pred_val)
                news_color = get_news_signal_color(row["뉴스판정"])
                conf_color = get_confidence_color(row["확신도"])

                reason_text = str(row["핵심사유"]).replace("\\n", "<br>").replace("•", "<br>•")
                news_text = str(row["뉴스요약"]).replace("\\n", "<br>")
                compare_model = str(row.get("비교모델", "")).strip()
                compare_block = ""
                ensemble_block = ""

                if str(row.get("종합예측", "")).strip():
                    ensemble_block = f"""
    <div class="section-title">종합 판단</div>
    <div class="reason-box">
        <b>종합예측:</b> {row.get('종합예측', '')} /
        <b>종합점수:</b> {row.get('종합점수', '')} /
        <b>모델일치도:</b> {row.get('모델일치도', '')} /
        <b>뉴스중요도:</b> {row.get('뉴스중요도', '')}<br>
        {row.get('종합사유', '')}
    </div>
"""

                if compare_model:
                    compare_reason = str(row.get("비교핵심사유", "")).replace("\\n", "<br>").replace("•", "<br>•")
                    compare_news = str(row.get("비교뉴스요약", "")).replace("\\n", "<br>")
                    compare_block = f"""
    <div class="section-title">비교 모델 결과 ({compare_model})</div>
    <div class="reason-box">
        <b>예측:</b> {row.get('비교AI예측', '')} /
        <b>확신도:</b> {row.get('비교확신도', '')}% /
        <b>뉴스:</b> {row.get('비교뉴스판정', '')}<br>
        <b>뉴스요약:</b> {compare_news}<br>
        <b>판단이유:</b> {compare_reason}
    </div>
"""

                with st.container():
                    st.html(f"""
<div style="background-color: #161B22; border-left: 5px solid {accent_color}; padding: 22px; border-radius: 12px; margin-bottom: 22px;">
    <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 15px;">
        <span style="font-size: 1.5rem; font-weight: bold; color: white;">
            {row['종목명']} <small style="color: #888; font-weight: normal;">({row['티커']})</small>
        </span>
        <span style="background-color: {accent_color}; color: white; padding: 6px 16px; border-radius: 20px; font-weight: bold; font-size: 0.95rem;">
            {pred_val}
        </span>
    </div>

    <div style="margin-bottom: 8px;">
        <span class="mini-badge badge-keyword">키워드: {row['핫키워드']}</span>
        <span class="mini-badge" style="background-color: {news_color};">뉴스: {row['뉴스판정']}</span>
        <span class="mini-badge badge-chart">차트: {row['차트판정']}</span>
        <span class="mini-badge badge-pattern">패턴: {row['패턴판정']}</span>
        <span class="mini-badge" style="background-color: #6366F1;">종합: {row.get('종합예측', '')} {row.get('종합점수', '')}</span>
    </div>

    <div class="section-title">주요 뉴스</div>
    <div class="reason-box">
        {news_text}
    </div>

    <div class="section-title">뉴스 출처</div>
    <div class="source-box">
        {row['뉴스출처']}
    </div>

    <div class="section-title">판단 이유</div>
    <div class="reason-box">
        {reason_text}
    </div>

    {compare_block}

    {ensemble_block}

    <div style="margin-top: 15px; border-top: 1px solid #30363D; padding-top: 10px;">
        <span style="color: {conf_color}; font-size: 0.95rem; font-weight: bold;">AI 확신도: {row['확신도']}%</span>
    </div>
</div>
""")

                with st.expander(f"📉 {row['종목명']} 차트 보기"):
                    chart_df = load_stock_chart_data(row["종목명"], row["티커"])

                    if chart_df is not None and not chart_df.empty:
                        # raw_data 파일마다 날짜 컬럼 형태가 조금 달라서 여기서 한 번 보정한다.
                        # 첫 컬럼이 날짜인데 이름이 비어있는 해외주식 데이터 보정
                        if "Date" not in chart_df.columns:
                            chart_df = chart_df.rename(columns={chart_df.columns[0]: "Date"})

                        required_cols = ["Date", "Close", "MA20", "MA60"]
                        missing_cols = [col for col in required_cols if col not in chart_df.columns]

                        if missing_cols:
                            st.warning(f"차트 컬럼 부족: {missing_cols}")
                            st.write("현재 컬럼:", chart_df.columns.tolist())
                        else:
                            chart_df["Date"] = pd.to_datetime(chart_df["Date"], errors="coerce")
                            chart_df = chart_df.dropna(subset=["Date"])
                            chart_df = chart_df.sort_values("Date").copy()

                            chart_view = chart_df[["Date", "Close", "MA20", "MA60"]].copy()

                            fig = go.Figure()

                            fig.add_trace(go.Scatter(
                                x=chart_view["Date"],
                                y=chart_view["Close"],
                                mode="lines",
                                name="Close"
                            ))

                            fig.add_trace(go.Scatter(
                                x=chart_view["Date"],
                                y=chart_view["MA20"],
                                mode="lines",
                                name="MA20"
                            ))

                            fig.add_trace(go.Scatter(
                                x=chart_view["Date"],
                                y=chart_view["MA60"],
                                mode="lines",
                                name="MA60"
                            ))

                            if len(chart_view) >= 60:
                                start_date = chart_view["Date"].iloc[-60]
                            else:
                                start_date = chart_view["Date"].iloc[0]

                            end_date = chart_view["Date"].iloc[-1]

                            fig.update_layout(
                                xaxis=dict(
                                    range=[start_date, end_date],
                                    rangeslider=dict(visible=True)
                                ),
                                margin=dict(l=20, r=20, t=30, b=20),
                                height=400,
                                legend=dict(orientation="h")
                            )

                            st.plotly_chart(fig, use_container_width=True)

                            latest_row = chart_df.iloc[-1]
                            st.caption(
                                f"현재가: {latest_row['Close']:.2f} / "
                                f"MA20: {latest_row['MA20']:.2f} / "
                                f"MA60: {latest_row['MA60']:.2f}"
                            )
                    else:
                        st.info("차트 데이터를 찾을 수 없습니다.")

else:
    st.error("🚨 분석 데이터를 찾을 수 없습니다. 경로와 파일명을 확인해 주세요.")
