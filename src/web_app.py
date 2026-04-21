import os
from datetime import datetime

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

"""
Streamlit 대시보드.

1페이지 · 오늘의 요약
2페이지 · 결과 정리
3페이지 · 종목 상세

- 페이지 이동은 상단 버튼형 네비게이션 사용
- 대표 뉴스 중심으로 표시
- 카드 클릭 시 종목 상세 페이지로 이동
"""

# =========================================================
# 1. 페이지 설정 / 스타일
# =========================================================
st.set_page_config(page_title="Gemini Pro Insight", layout="wide", page_icon="💎")

st.markdown(
    """
    <style>
    .stApp {
        background-color: #0E1117;
        color: #E0E0E0;
    }

    div[data-testid="stMetric"] {
        background-color: #161B22;
        border: 1px solid #30363D;
        padding: 20px;
        border-radius: 14px;
        box-shadow: 0 4px 10px rgba(0,0,0,0.25);
    }

    .main-title {
        font-size: 2.8rem;
        font-weight: 800;
        background: -webkit-linear-gradient(#60EFFF, #00A3FF);
        -webkit-background-clip: text;
        -webkit-text-fill-color: transparent;
        margin-bottom: 0.35rem;
    }

    .sub-title {
        color: #94A3B8;
        margin-bottom: 1rem;
    }

    .card-wrap {
        background-color: #161B22;
        border: 1px solid #2B3442;
        border-radius: 16px;
        padding: 18px;
        min-height: 240px;
        box-shadow: 0 6px 16px rgba(0,0,0,0.18);
        margin-bottom: 14px;
    }

    .card-title {
        font-size: 1.2rem;
        font-weight: 800;
        color: white;
        margin-bottom: 6px;
    }

    .card-ticker {
        color: #94A3B8;
        font-size: 0.9rem;
    }

    .mini-badge {
        display: inline-block;
        padding: 6px 12px;
        margin-right: 8px;
        margin-bottom: 8px;
        border-radius: 999px;
        font-size: 0.84rem;
        font-weight: 700;
        color: white;
    }

    .badge-keyword { background-color: #F59E0B; color: black; }
    .badge-chart { background-color: #0EA5E9; }
    .badge-pattern { background-color: #10B981; }

    .section-title {
        font-size: 1.03rem;
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

    .group-box {
        background-color: #111827;
        border: 1px solid #263041;
        border-radius: 14px;
        padding: 14px;
        margin-bottom: 12px;
    }

    .small-muted {
        color: #94A3B8;
        font-size: 0.88rem;
    }
    </style>
    """,
    unsafe_allow_html=True,
)

REPORT_PATH = "logs/daily_analysis_report.csv"
PAGE_OPTIONS = [
    "1페이지 · 오늘의 요약",
    "2페이지 · 결과 정리",
    "3페이지 · 종목 상세",
]


# =========================================================
# 2. 상태 / 유틸
# =========================================================
if "current_page" not in st.session_state:
    st.session_state["current_page"] = PAGE_OPTIONS[0]

if "selected_stock" not in st.session_state:
    st.session_state["selected_stock"] = "전체"


def go_to_page(page_name: str):
    st.session_state["current_page"] = page_name
    st.rerun()


def move_to_detail(stock_name: str):
    st.session_state["selected_stock"] = stock_name
    st.session_state["current_page"] = PAGE_OPTIONS[2]
    st.rerun()


def load_stock_chart_data(stock_name: str, ticker: str):
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
    expected_columns = [
        "날짜", "종목명", "티커", "기준모델", "AI예측", "확신도",
        "핫키워드", "뉴스판정", "뉴스요약", "뉴스출처",
        "패턴판정", "차트판정", "핵심사유",
        "뉴스수집성공", "뉴스수집오류",
        "비교모델", "비교AI예측", "비교확신도", "비교핫키워드",
        "비교뉴스판정", "비교뉴스요약", "비교뉴스출처",
        "비교패턴판정", "비교차트판정", "비교핵심사유",
        "비교뉴스수집성공", "비교뉴스수집오류",
        "종합예측", "종합점수",
        "대표뉴스키워드", "대표뉴스요약", "대표뉴스판정", "대표뉴스모델", "대표뉴스점수",
        "모델일치도", "뉴스중요도", "종합사유",
    ]

    if not os.path.exists(REPORT_PATH):
        return None

    try:
        df = pd.read_csv(REPORT_PATH, encoding="utf-8-sig")
        df.columns = df.columns.str.strip()
        df.columns = df.columns.str.replace("\ufeff", "", regex=False)

        for col in expected_columns:
            if col not in df.columns:
                df[col] = None

        numeric_cols = ["확신도", "비교확신도", "종합점수", "대표뉴스점수", "모델일치도", "뉴스중요도"]
        for col in numeric_cols:
            df[col] = pd.to_numeric(df[col], errors="coerce")

        df["확신도"] = df["확신도"].fillna(50)
        df["종합점수"] = df["종합점수"].fillna(0)
        df["대표뉴스점수"] = df["대표뉴스점수"].fillna(0)
        df["날짜"] = pd.to_datetime(df["날짜"], errors="coerce")
        df = df.dropna(subset=["날짜"])

        text_cols = [
            "종목명", "티커", "기준모델", "AI예측", "핫키워드",
            "뉴스판정", "뉴스요약", "뉴스출처",
            "패턴판정", "차트판정", "핵심사유",
            "뉴스수집성공", "뉴스수집오류",
            "비교모델", "비교AI예측", "비교핫키워드",
            "비교뉴스판정", "비교뉴스요약", "비교뉴스출처",
            "비교패턴판정", "비교차트판정", "비교핵심사유",
            "비교뉴스수집성공", "비교뉴스수집오류",
            "종합예측", "종합사유",
            "대표뉴스키워드", "대표뉴스요약", "대표뉴스판정", "대표뉴스모델",
        ]
        for col in text_cols:
            df[col] = df[col].fillna("").astype(str)

        df["대표뉴스키워드"] = df["대표뉴스키워드"].replace("", pd.NA).fillna(df["핫키워드"])
        df["대표뉴스요약"] = df["대표뉴스요약"].replace("", pd.NA).fillna(df["뉴스요약"])
        df["대표뉴스판정"] = df["대표뉴스판정"].replace("", pd.NA).fillna(df["뉴스판정"])

        df["화면예측"] = df["종합예측"].replace("", pd.NA).fillna(df["AI예측"])
        df["화면점수"] = df["종합점수"].where(df["종합점수"] > 0, df["확신도"])
        df["테마"] = df["대표뉴스키워드"].apply(classify_theme)

        return df

    except Exception as e:
        st.error(f"🚨 데이터 로딩 실패: {e}")
        return None


def get_prediction_color(pred_val: str):
    pred_val = str(pred_val)
    if "상승" in pred_val:
        return "#FF4B4B"
    if "하락" in pred_val:
        return "#3182CE"
    return "#E5E7EB"


def get_news_signal_color(signal: str):
    signal = str(signal).strip()
    if "호재" in signal:
        return "#22C55E"
    if "악재" in signal:
        return "#EF4444"
    if "기대감" in signal:
        return "#F59E0B"
    if "혼재" in signal:
        return "#8B5CF6"
    if "부족" in signal:
        return "#64748B"
    return "#94A3B8"


def get_confidence_color(score):
    try:
        score = float(score)
    except Exception:
        return "#94A3B8"
    if score >= 85:
        return "#22C55E"
    if score >= 70:
        return "#F59E0B"
    if score >= 50:
        return "#FB923C"
    return "#EF4444"


def shorten_text(text: str, limit: int = 72):
    text = str(text).strip()
    if len(text) > limit:
        return text[:limit] + "..."
    return text


def classify_theme(keyword: str) -> str:
    keyword = str(keyword).strip()
    if any(k in keyword for k in ["HBM", "반도체", "NPU", "AI 가속기", "칩"]):
        return "반도체/AI"
    if any(k in keyword for k in ["실적", "어닝", "수익성", "턴어라운드"]):
        return "실적"
    if any(k in keyword for k in ["배당", "파트너십", "투자 확대", "포트폴리오"]):
        return "배당/투자"
    if any(k in keyword for k in ["신약", "ADC", "항암", "플랫폼"]):
        return "바이오/신약"
    if any(k in keyword for k in ["로보택시", "자율주행", "인도량"]):
        return "모빌리티"
    if any(k in keyword for k in ["AI", "클라우드", "제미나이", "피지컬 AI"]):
        return "AI/클라우드"
    if "의견 충돌" in keyword:
        return "모델 충돌"
    return "기타"


# =========================================================
# 3. 공통 렌더링
# =========================================================
def render_top_navigation():
    nav_cols = st.columns(3)
    for idx, page_name in enumerate(PAGE_OPTIONS):
        with nav_cols[idx]:
            button_type = "primary" if st.session_state["current_page"] == page_name else "secondary"
            if st.button(page_name, use_container_width=True, type=button_type, key=f"nav_{idx}"):
                go_to_page(page_name)


def render_filter_panel(latest_df: pd.DataFrame):
    with st.sidebar:
        st.subheader("🔧 필터")
        st.caption("페이지는 상단 버튼으로 이동합니다.")

        pred_filter = st.multiselect(
            "예측 결과",
            ["▲ 상승", "▼ 하락", "━ 관망"],
            default=["▲ 상승", "▼ 하락", "━ 관망"],
        )

        stock_list = ["전체"] + sorted(latest_df["종목명"].unique().tolist())
        stock_filter = st.selectbox("종목 선택", stock_list, key="stock_filter_widget_v3")

        min_conf = st.slider("최소 점수", 0, 100, 0)

    if not pred_filter:
        pred_filter = ["▲ 상승", "▼ 하락", "━ 관망"]

    return pred_filter, stock_filter, min_conf


def apply_filters(df: pd.DataFrame, pred_filter, stock_filter, min_conf):
    filtered_df = df.copy()
    filtered_df = filtered_df[filtered_df["화면예측"].isin(pred_filter)]
    filtered_df = filtered_df[filtered_df["화면점수"] >= min_conf]
    if stock_filter != "전체":
        filtered_df = filtered_df[filtered_df["종목명"] == stock_filter]
    return filtered_df


def render_stock_card(row, button_key: str):
    pred_color = get_prediction_color(row["화면예측"])
    news_color = get_news_signal_color(row["대표뉴스판정"])
    score_color = get_confidence_color(row["화면점수"])

    st.markdown(
        f"""
        <div class="card-wrap" style="border-left: 5px solid {pred_color};">
            <div class="card-title">{row['종목명']} <span class="card-ticker">({row['티커']})</span></div>
            <div style="margin-bottom: 10px;">
                <span class="mini-badge" style="background-color:{pred_color};">{row['화면예측']}</span>
                <span class="mini-badge" style="background-color:{score_color};">점수 {int(row['화면점수'])}</span>
                <span class="mini-badge badge-keyword">{row['대표뉴스키워드']}</span>
                <span class="mini-badge" style="background-color:{news_color};">{row['대표뉴스판정']}</span>
            </div>
            <div class="small-muted" style="line-height:1.7;">{shorten_text(row['대표뉴스요약'], 120)}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )
    if st.button(f"{row['종목명']} 상세 보기", key=button_key, use_container_width=True):
        move_to_detail(row["종목명"])


# =========================================================
# 4. 페이지 렌더링
# =========================================================
def render_overview_page(filtered_df: pd.DataFrame):
    st.markdown("### 1페이지 · 오늘의 요약")
    st.caption("대표 뉴스와 종합 판단을 한눈에 보는 요약 화면")

    if filtered_df.empty:
        st.warning("조건에 맞는 종목이 없습니다.")
        return

    cols = st.columns(2)
    for idx, (_, row) in enumerate(filtered_df.sort_values(["화면점수", "종목명"], ascending=[False, True]).iterrows()):
        with cols[idx % 2]:
            render_stock_card(row, button_key=f"overview_{row['종목명']}_{idx}")


def render_summary_page(filtered_df: pd.DataFrame):
    st.markdown("### 2페이지 · 결과 정리")
    st.caption("오늘 결과를 카테고리별로 나눠서 보는 정리 화면")

    if filtered_df.empty:
        st.warning("조건에 맞는 종목이 없습니다.")
        return

    bullish_df = filtered_df[filtered_df["화면예측"].str.contains("상승", na=False)].sort_values("화면점수", ascending=False)
    neutral_df = filtered_df[filtered_df["화면예측"].str.contains("관망", na=False)].sort_values("화면점수", ascending=False)
    bearish_df = filtered_df[filtered_df["화면예측"].str.contains("하락", na=False)].sort_values("화면점수", ascending=False)
    conflict_df = filtered_df[filtered_df["대표뉴스키워드"].str.contains("의견 충돌", na=False)]
    strong_news_df = filtered_df[filtered_df["대표뉴스판정"].str.contains("실질", na=False)].sort_values("화면점수", ascending=False)

    sec1, sec2 = st.columns(2)
    with sec1:
        st.markdown("#### ▲ 상승 우세 종목")
        if bullish_df.empty:
            st.info("해당 없음")
        else:
            st.dataframe(
                bullish_df[["종목명", "화면예측", "화면점수", "대표뉴스키워드", "대표뉴스판정"]]
                .rename(columns={"화면예측": "종합예측", "화면점수": "종합점수"}),
                use_container_width=True,
                hide_index=True,
            )

        st.markdown("#### ━ 관망 종목")
        if neutral_df.empty:
            st.info("해당 없음")
        else:
            st.dataframe(
                neutral_df[["종목명", "화면예측", "화면점수", "대표뉴스키워드", "대표뉴스판정"]]
                .rename(columns={"화면예측": "종합예측", "화면점수": "종합점수"}),
                use_container_width=True,
                hide_index=True,
            )

    with sec2:
        st.markdown("#### ▼ 하락 주의 종목")
        if bearish_df.empty:
            st.info("해당 없음")
        else:
            st.dataframe(
                bearish_df[["종목명", "화면예측", "화면점수", "대표뉴스키워드", "대표뉴스판정"]]
                .rename(columns={"화면예측": "종합예측", "화면점수": "종합점수"}),
                use_container_width=True,
                hide_index=True,
            )

        st.markdown("#### ⚠️ 모델 충돌 종목")
        if conflict_df.empty:
            st.info("해당 없음")
        else:
            st.dataframe(
                conflict_df[["종목명", "AI예측", "비교AI예측", "대표뉴스요약"]],
                use_container_width=True,
                hide_index=True,
            )

    st.markdown("#### 🌟 뉴스 신뢰도 높은 종목")
    if strong_news_df.empty:
        st.info("해당 없음")
    else:
        st.dataframe(
            strong_news_df[["종목명", "화면예측", "화면점수", "대표뉴스키워드", "대표뉴스요약"]]
            .rename(columns={"화면예측": "종합예측", "화면점수": "종합점수"}),
            use_container_width=True,
            hide_index=True,
        )

    st.markdown("#### 🧩 테마별 묶음")
    theme_summary = (
        filtered_df.groupby("테마")
        .agg(
            종목수=("종목명", "count"),
            평균점수=("화면점수", "mean"),
        )
        .reset_index()
        .sort_values(["종목수", "평균점수"], ascending=[False, False])
    )
    theme_summary["평균점수"] = theme_summary["평균점수"].round(1)
    st.dataframe(theme_summary, use_container_width=True, hide_index=True)


def render_detail_page(latest_df: pd.DataFrame, filtered_df: pd.DataFrame):
    st.markdown("### 3페이지 · 종목 상세")
    st.caption("대표 뉴스와 종합 판단을 보고, 필요할 때만 상세 내용을 펼쳐보는 화면")

    selected_stock = st.session_state.get("selected_stock", "전체")

    detail_df = latest_df.copy()
    if selected_stock != "전체":
        detail_df = detail_df[detail_df["종목명"] == selected_stock]

    if detail_df.empty:
        st.warning("선택된 종목이 없습니다. 1페이지에서 종목 카드를 눌러 이동하세요.")
        if not filtered_df.empty:
            quick_cols = st.columns(3)
            for idx, stock_name in enumerate(filtered_df["종목명"].tolist()[:9]):
                with quick_cols[idx % 3]:
                    if st.button(stock_name, key=f"quick_detail_{stock_name}", use_container_width=True):
                        move_to_detail(stock_name)
        return

    row = detail_df.iloc[0]
    pred_val = str(row["화면예측"])
    accent_color = get_prediction_color(pred_val)
    news_color = get_news_signal_color(row["대표뉴스판정"])
    score_color = get_confidence_color(row["화면점수"])

    st.markdown(
        f"""
        <div class="card-wrap" style="border-left: 6px solid {accent_color}; min-height: 0;">
            <div class="card-title" style="font-size:1.5rem;">{row['종목명']} <span class="card-ticker">({row['티커']})</span></div>
            <div style="margin-bottom: 10px;">
                <span class="mini-badge" style="background-color:{accent_color};">{row['화면예측']}</span>
                <span class="mini-badge" style="background-color:{score_color};">종합점수 {int(row['화면점수'])}</span>
                <span class="mini-badge badge-keyword">{row['대표뉴스키워드']}</span>
                <span class="mini-badge" style="background-color:{news_color};">{row['대표뉴스판정']}</span>
                <span class="mini-badge badge-chart">차트: {row['차트판정']}</span>
                <span class="mini-badge badge-pattern">패턴: {row['패턴판정']}</span>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    col1, col2 = st.columns([1.3, 1])
    with col1:
        st.markdown("#### 대표 뉴스")
        st.markdown(f"<div class='reason-box'>{row['대표뉴스요약'] if row['대표뉴스요약'] else '관련 뉴스 부족'}</div>", unsafe_allow_html=True)

        rep_source = str(row.get("뉴스출처", "")).strip()
        if str(row.get("대표뉴스모델", "")).strip() and str(row.get("대표뉴스모델", "")).strip() != str(row.get("기준모델", "")).strip():
            rep_source = str(row.get("비교뉴스출처", "")).strip()
        if not rep_source:
            rep_source = "출처 정보 없음"

        st.markdown("#### 대표 뉴스 출처")
        st.markdown(f"<div class='source-box'>{rep_source}</div>", unsafe_allow_html=True)

    with col2:
        st.markdown("#### 종합 판단")
        st.markdown(
            f"""
            <div class='reason-box'>
                <b>종합예측:</b> {row.get('종합예측', row['화면예측'])}<br>
                <b>종합점수:</b> {int(row['화면점수'])}<br>
                <b>모델일치도:</b> {row.get('모델일치도', '')}<br>
                <b>뉴스중요도:</b> {row.get('뉴스중요도', '')}<br><br>
                {row.get('종합사유', row.get('핵심사유', ''))}
            </div>
            """,
            unsafe_allow_html=True,
        )

    st.markdown("#### 핵심 판단 이유")
    reason_text = str(row["핵심사유"]).replace("\\n", "<br>").replace("•", "<br>•")
    st.markdown(f"<div class='reason-box'>{reason_text}</div>", unsafe_allow_html=True)

    with st.expander(f"기준 모델 상세 · {row['기준모델']}"):
        base_news = row["뉴스요약"] if row["뉴스요약"] else "관련 뉴스 부족"
        base_source = row["뉴스출처"] if row["뉴스출처"] else "출처 정보 없음"
        st.markdown(
            f"""
            <div class='reason-box'>
                <b>예측:</b> {row['AI예측']} / <b>확신도:</b> {row['확신도']}% / <b>뉴스:</b> {row['뉴스판정'] if row['뉴스판정'] else '뉴스 부족'}<br><br>
                <b>뉴스요약:</b> {base_news}<br><br>
                <b>판단이유:</b> {row['핵심사유']}
            </div>
            """,
            unsafe_allow_html=True,
        )
        st.markdown(f"<div class='source-box'>{base_source}</div>", unsafe_allow_html=True)

    if str(row.get("비교모델", "")).strip():
        with st.expander(f"비교 모델 상세 · {row['비교모델']}"):
            compare_news = row["비교뉴스요약"] if row["비교뉴스요약"] else "관련 뉴스 부족"
            compare_source = row["비교뉴스출처"] if row["비교뉴스출처"] else "출처 정보 없음"
            st.markdown(
                f"""
                <div class='reason-box'>
                    <b>예측:</b> {row['비교AI예측']} / <b>확신도:</b> {row['비교확신도']}% / <b>뉴스:</b> {row['비교뉴스판정'] if row['비교뉴스판정'] else '뉴스 부족'}<br><br>
                    <b>뉴스요약:</b> {compare_news}<br><br>
                    <b>판단이유:</b> {row['비교핵심사유']}
                </div>
                """,
                unsafe_allow_html=True,
            )
            st.markdown(f"<div class='source-box'>{compare_source}</div>", unsafe_allow_html=True)

    with st.expander(f"📉 {row['종목명']} 차트 보기"):
        chart_df = load_stock_chart_data(row["종목명"], row["티커"])
        if chart_df is not None and not chart_df.empty:
            if "Date" not in chart_df.columns:
                chart_df = chart_df.rename(columns={chart_df.columns[0]: "Date"})

            required_cols = ["Date", "Close", "MA20", "MA60"]
            missing_cols = [col for col in required_cols if col not in chart_df.columns]

            if missing_cols:
                st.warning(f"차트 컬럼 부족: {missing_cols}")
            else:
                chart_df["Date"] = pd.to_datetime(chart_df["Date"], errors="coerce")
                chart_df = chart_df.dropna(subset=["Date"])
                chart_df = chart_df.sort_values("Date").copy()

                chart_view = chart_df[["Date", "Close", "MA20", "MA60"]].copy()
                fig = go.Figure()
                fig.add_trace(go.Scatter(x=chart_view["Date"], y=chart_view["Close"], mode="lines", name="Close"))
                fig.add_trace(go.Scatter(x=chart_view["Date"], y=chart_view["MA20"], mode="lines", name="MA20"))
                fig.add_trace(go.Scatter(x=chart_view["Date"], y=chart_view["MA60"], mode="lines", name="MA60"))

                start_date = chart_view["Date"].iloc[-60] if len(chart_view) >= 60 else chart_view["Date"].iloc[0]
                end_date = chart_view["Date"].iloc[-1]

                fig.update_layout(
                    xaxis=dict(range=[start_date, end_date], rangeslider=dict(visible=True)),
                    margin=dict(l=20, r=20, t=30, b=20),
                    height=400,
                    legend=dict(orientation="h"),
                )
                st.plotly_chart(fig, use_container_width=True)

                latest_row = chart_df.iloc[-1]
                st.caption(
                    f"현재가: {latest_row['Close']:.2f} / MA20: {latest_row['MA20']:.2f} / MA60: {latest_row['MA60']:.2f}"
                )
        else:
            st.info("차트 데이터를 찾을 수 없습니다.")

    st.write("")
    st.markdown("#### 다른 종목 바로 이동")
    quick_cols = st.columns(5)
    candidates = latest_df.sort_values(["화면점수", "종목명"], ascending=[False, True])["종목명"].tolist()
    for idx, stock_name in enumerate(candidates[:10]):
        with quick_cols[idx % 5]:
            if st.button(stock_name, key=f"detail_jump_{stock_name}", use_container_width=True):
                move_to_detail(stock_name)


# =========================================================
# 5. 메인
# =========================================================
df = load_data()

st.markdown('<p class="main-title">💎 Gemini AI Strategy Report</p>', unsafe_allow_html=True)
st.markdown('<p class="sub-title">대표 뉴스 기반 종합 판단을 요약 · 정리 · 상세 흐름으로 확인하는 대시보드</p>', unsafe_allow_html=True)
st.markdown(f"🗓️ **Market Data Updated:** `{datetime.now().strftime('%Y-%m-%d %H:%M')}`")
st.divider()

if df is None or df.empty:
    st.error("🚨 분석 데이터를 찾을 수 없습니다. 경로와 파일명을 확인해 주세요.")
    st.stop()

latest_date = df["날짜"].max()
latest_df = df[df["날짜"] == latest_date].copy()

st.markdown(f"📅 **Latest Report Date:** `{latest_date.strftime('%Y-%m-%d')}`")

k1, k2, k3, k4 = st.columns(4)
with k1:
    st.metric("Total Analysis", f"{len(latest_df)} stocks")
with k2:
    up_count = len(latest_df[latest_df["화면예측"].str.contains("상승", na=False)])
    st.metric("Bullish (상승)", f"{up_count}", delta=f"{(up_count / len(latest_df) * 100):.1f}%")
with k3:
    down_count = len(latest_df[latest_df["화면예측"].str.contains("하락", na=False)])
    st.metric("Bearish (하락)", f"{down_count}", delta=f"-{(down_count / len(latest_df) * 100):.1f}%")
with k4:
    avg_conf = latest_df["화면점수"].mean()
    st.metric("Avg. Score", f"{avg_conf:.1f}")

st.write("")
render_top_navigation()
st.write("")

pred_filter, stock_filter, min_conf = render_filter_panel(latest_df)
filtered_df = apply_filters(latest_df, pred_filter, stock_filter, min_conf)

current_page = st.session_state["current_page"]
if current_page == PAGE_OPTIONS[0]:
    render_overview_page(filtered_df)
elif current_page == PAGE_OPTIONS[1]:
    render_summary_page(filtered_df)
else:
    render_detail_page(latest_df, filtered_df)
