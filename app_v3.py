"""
🏠 부동산 전략 시스템 v3.0 — Streamlit 대시보드

실행: streamlit run app_v3.py

v3.0 신규 기능:
  - ScorerV3 통합 점수 (12개 요소)
  - 백테스트 상관관계 분석
  - ML 가중치 최적화 UI
  - 외부 데이터 소스 현황
"""
import streamlit as st
import sqlite3
import pandas as pd
import numpy as np
import os
import sys
from datetime import datetime

sys.path.insert(0, os.path.dirname(__file__))
from data.database import DB_PATH, get_conn
from strategy.scorer_v3 import ScorerV3

# ─── Page config ─────────────────────────────────────
st.set_page_config(
    page_title="부동산 v3.0",
    page_icon="🏠",
    layout="wide",
    initial_sidebar_state="expanded"
)

# ─── CSS (기존 dashboard.py 스타일 통일) ────────────
st.markdown("""
<style>
    .main > div { padding: 0.5rem 0.5rem; }
    .stTabs [data-baseweb="tab-list"] { gap: 4px; }
    .stTabs [data-baseweb="tab"] { padding: 8px 12px; font-size: 13px; }
    .block-container { max-width: 100%; padding: 1rem; }
    h1 { font-size: 1.4rem !important; }
    h2 { font-size: 1.1rem !important; }
    h3 { font-size: 0.95rem !important; }
    .metric-card {
        background: #f0f2f6;
        border-radius: 10px;
        padding: 12px;
        margin-bottom: 8px;
        border: 1px solid #e0e0e0;
    }
    .metric-label { color: #666; font-size: 12px; }
    .metric-value { color: #1a1a2e; font-size: 20px; font-weight: 700; }
    .metric-sub { color: #0f7b3e; font-size: 12px; }
    .highlight-box {
        background: #e8f0fe;
        border-left: 3px solid #1a73e8;
        padding: 10px 14px;
        border-radius: 6px;
        margin: 8px 0;
    }
    .badge-up { color: #d32f2f; font-weight: 700; }
    .badge-down { color: #1976d2; font-weight: 700; }
    .badge-hold { color: #666; font-weight: 700; }
    .score-bar { display: flex; align-items: center; margin: 2px 0; }
    .score-bar-fill { height: 18px; border-radius: 3px; background: #1a73e8; }
    .score-bar-bg { flex: 1; background: #e8eaed; border-radius: 3px; margin: 0 8px; }
</style>
""", unsafe_allow_html=True)


# ─── Cached helpers ──────────────────────────────────
@st.cache_resource
def get_scorer():
    return ScorerV3()


@st.cache_data(ttl=300)
def get_all_region_scores():
    """Score all regions and return sorted results."""
    s = get_scorer()
    regions = [r[0] for r in s.conn.execute(
        "SELECT DISTINCT region FROM apt_trade ORDER BY region"
    ).fetchall()]
    results = []
    for r in regions:
        try:
            results.append(s.score_region(r))
        except Exception:
            continue
    results.sort(key=lambda x: x['total_score'], reverse=True)
    return results


@st.cache_data(ttl=300)
def get_backtest_data():
    """Get backtest data: scores vs actual returns."""
    s = get_scorer()
    regions = [r[0] for r in s.conn.execute(
        "SELECT DISTINCT region FROM apt_trade ORDER BY region"
    ).fetchall()]
    scores, actuals, names = [], [], []
    for region in regions:
        try:
            result = s.score_region(region)
            row = s.conn.execute("""
                SELECT ROUND(AVG(CASE WHEN deal_date >= ? THEN price/10000.0 END), 1),
                       ROUND(AVG(CASE WHEN deal_date >= ? AND deal_date < ? THEN price/10000.0 END), 1)
                FROM apt_trade WHERE region = ? AND price BETWEEN 10000 AND 300000 AND deal_date >= ?
            """, (s.d3, s.d12, s.d3, region, s.d12)).fetchone()
            p3 = row[0] or 0
            p12_3 = row[1] or 0
            if p12_3 > 0:
                scores.append(result['total_score'])
                actuals.append(round((p3 - p12_3) * 100.0 / p12_3, 1))
                short = region.replace('서울특별시 ', '').replace('경기도 ', '')
                names.append(short)
        except Exception:
            continue
    return scores, actuals, names


@st.cache_data(ttl=300)
def get_external_data():
    """Collect all external data sources for tab 4."""
    conn = get_conn()
    tables = {
        'KB 수급지수': 'external_kb_index',
        '개발호재': 'external_development',
        '공급데이터': 'external_supply',
        '학군정보': 'external_school',
        '뉴스감성': 'external_news_sentiment',
    }
    result = {}
    for name, table in tables.items():
        try:
            df = pd.read_sql_query(f"SELECT * FROM {table} LIMIT 100", conn)
            result[name] = df
        except Exception:
            result[name] = pd.DataFrame()
    conn.close()
    return result


def _short_name(region):
    for p in ['서울특별시 ', '경기도 ', '부산광역시 ', '대전광역시 ',
              '대구광역시 ', '인천광역시 ', '광주광역시 ', '울산광역시 ',
              '세종특별자치시 ']:
        region = region.replace(p, '')
    return region


# ─── Sidebar ─────────────────────────────────────────
st.sidebar.title("🏠 부동산 v3.0")
st.sidebar.caption(f"기준일: {datetime.now().strftime('%Y-%m-%d %H:%M')}")
st.sidebar.markdown("---")

# Scoring options
st.sidebar.subheader("설정")
top_n = st.sidebar.slider("표시할 지역 수", 5, 50, 20)

# Load ML optimizer if available
try:
    from strategy.ml_optimizer import MLOptimizer
    ml_available = st.sidebar.checkbox("ML 가중치 활성화", value=False)
except ImportError:
    ml_available = False
    st.sidebar.info("ML 옵티마이저 미설치")

st.sidebar.markdown("---")
st.sidebar.caption("Data Source: 국토교통부 실거래가")


# ─── Main Tabs ───────────────────────────────────────
tab1, tab2, tab3, tab4 = st.tabs([
    "📊 v3.0 스코어",
    "📈 백테스트",
    "🤖 ML 가중치",
    "🗄️ 외부데이터"
])


# ===== TAB 1: v3.0 스코어 =====
with tab1:
    st.subheader("🏆 v3.0 통합 스코어 — 지역별 순위")

    with st.spinner("점수 계산 중..."):
        results = get_all_region_scores()

    if not results:
        st.warning("⚠️ 점수를 계산할 수 있는 지역이 없습니다.")
        st.stop()

    # Top metrics
    top = results[:top_n]
    cols = st.columns(4)
    with cols[0]:
        st.markdown(f'<div class="metric-card"><div class="metric-label">분석 지역</div><div class="metric-value">{len(results)}</div></div>',
                    unsafe_allow_html=True)
    with cols[1]:
        avg_score = np.mean([r['total_score'] for r in results])
        st.markdown(f'<div class="metric-card"><div class="metric-label">평균 점수</div><div class="metric-value">{avg_score:.1f}</div></div>',
                    unsafe_allow_html=True)
    with cols[2]:
        top_region = _short_name(results[0]['region'])
        st.markdown(f'<div class="metric-card"><div class="metric-label">1위</div><div class="metric-value">{top_region}</div><div class="metric-sub">{results[0]["total_score"]}점</div></div>',
                    unsafe_allow_html=True)
    with cols[3]:
        st.markdown(f'<div class="metric-card"><div class="metric-label">등급 분포</div><div class="metric-value" style="font-size:14px">{" | ".join(r["grade"][:2] for r in results[:5])}</div></div>',
                    unsafe_allow_html=True)

    # Score table with factor breakdown
    st.markdown("### 지역별 점수 상세")
    for i, r in enumerate(top):
        short = _short_name(r['region'])
        grade_icon = r['grade'][:2]  # emoji
        with st.expander(f"**{i+1:>2}. {short:<15} {r['total_score']:>5.1f}점 {grade_icon}**", expanded=(i < 3)):
            # Factor bars
            factors = r['factors']
            max_score = max(v['score'] for v in factors.values()) or 1

            for fname, fdata in factors.items():
                fscore = fdata['score']
                fval = fdata['value']
                pct = min(fscore / (max_score * 1.2), 1.0)
                color = "#d32f2f" if fscore < 3 else "#e37400" if fscore < 6 else "#1a73e8" if fscore < 10 else "#0f7b3e"
                st.markdown(f"""
                <div class="score-bar">
                    <span style="width:110px;font-size:12px">{fname}</span>
                    <div class="score-bar-bg">
                        <div class="score-bar-fill" style="width:{pct*100:.0f}%;background:{color}"></div>
                    </div>
                    <span style="width:60px;text-align:right;font-size:12px;font-weight:600">{fscore:.1f}</span>
                    <span style="width:80px;text-align:right;font-size:11px;color:#666">{fval}</span>
                </div>
                """, unsafe_allow_html=True)

    # Raw score table
    st.markdown("---")
    st.markdown("### 전체 순위 테이블")
    table_data = []
    for i, r in enumerate(results[:top_n]):
        table_data.append({
            '순위': i + 1,
            '지역': _short_name(r['region']),
            '점수': r['total_score'],
            '등급': r['grade'],
        })
    df_rank = pd.DataFrame(table_data)
    st.dataframe(df_rank, use_container_width=True, hide_index=True)


# ===== TAB 2: 백테스트 =====
with tab2:
    st.subheader("📈 백테스트 — Score vs Actual Return")

    with st.spinner("백테스트 데이터 계산 중..."):
        scores, actuals, names = get_backtest_data()

    if len(scores) < 5:
        st.warning(f"⚠️ 백테스트에 충분한 데이터가 없습니다. (n={len(scores)})")
        st.stop()

    corr = np.corrcoef(scores, actuals)[0, 1]

    col1, col2, col3 = st.columns(3)
    with col1:
        st.markdown(f'<div class="metric-card"><div class="metric-label">상관계수</div><div class="metric-value">{corr:.4f}</div></div>',
                    unsafe_allow_html=True)
    with col2:
        st.markdown(f'<div class="metric-card"><div class="metric-label">분석 지역</div><div class="metric-value">{len(scores)}</div></div>',
                    unsafe_allow_html=True)
    with col3:
        st.markdown(f'<div class="metric-card"><div class="metric-label">평균 점수</div><div class="metric-value">{np.mean(scores):.1f}</div><div class="metric-sub">평균 수익률 {np.mean(actuals):.1f}%</div></div>',
                    unsafe_allow_html=True)

    # Scatter plot: Score vs Actual Return
    import plotly.graph_objects as go

    scatter_df = pd.DataFrame({
        'score': scores,
        'actual': actuals,
        'region': names,
    })

    fig_scatter = go.Figure()
    fig_scatter.add_trace(go.Scatter(
        x=scatter_df['score'],
        y=scatter_df['actual'],
        mode='markers+text',
        text=scatter_df['region'],
        textposition='top center',
        marker=dict(
            size=10,
            color=scatter_df['actual'],
            colorscale='RdYlGn',
            showscale=True,
            colorbar_title='수익률 %',
            line=dict(width=1, color='darkgray'),
        ),
        hovertemplate=(
            '<b>%{text}</b><br>'
            '점수: %{x:.1f}<br>'
            '실제수익률: %{y:.1f}%<br>'
        ),
    ))

    # Add trend line
    if len(scatter_df) > 2:
        z = np.polyfit(scatter_df['score'], scatter_df['actual'], 1)
        p = np.poly1d(z)
        x_range = np.linspace(scatter_df['score'].min(), scatter_df['score'].max(), 100)
        fig_scatter.add_trace(go.Scatter(
            x=x_range, y=p(x_range),
            mode='lines',
            name=f'추세선 (기울기={z[0]:.3f})',
            line=dict(dash='dash', color='gray', width=1),
        ))

    fig_scatter.update_layout(
        title=f'점수 vs 실제 수익률 (상관계수: {corr:.4f})',
        xaxis_title='v3.0 통합 점수',
        yaxis_title='실제 수익률 (%)',
        hovermode='closest',
        template='plotly_white',
        height=500,
    )
    st.plotly_chart(fig_scatter, use_container_width=True)

    # Correlation bar chart: factor-level correlation
    st.markdown("### 요소별 상관계수")
    st.caption("각 평가 요소가 실제 수익률과 얼마나 상관관계가 있는지")

    # Calculate per-factor correlations
    s = get_scorer()
    factor_names = [
        '가격모멘텀', '중기추세', '전세가율', '거래안정성', '갭매력도',
        '리버전', 'KB수급지수', '개발호재', '공급리스크', '학군',
        '거시환경', '지역계층'
    ]
    factor_corrs = {}
    for fname in factor_names:
        f_scores = []
        f_actuals = []
        for region_name, score, actual in zip(names, scores, actuals):
            try:
                result = s.score_region(region_name)
                fs = result['factors'].get(fname, {}).get('score', 0)
                f_scores.append(fs)
                f_actuals.append(actual)
            except Exception:
                continue
        if len(f_scores) > 5 and np.std(f_scores) > 0 and np.std(f_actuals) > 0:
            factor_corrs[fname] = np.corrcoef(f_scores, f_actuals)[0, 1]
        else:
            factor_corrs[fname] = 0

    # Sort by abs correlation
    sorted_factors = sorted(factor_corrs.items(), key=lambda x: abs(x[1]), reverse=True)

    fig_corr = go.Figure()
    colors = ['#d32f2f' if v > 0 else '#1976d2' for _, v in sorted_factors]
    fig_corr.add_trace(go.Bar(
        x=[k for k, _ in sorted_factors],
        y=[v for _, v in sorted_factors],
        marker_color=colors,
        text=[f'{v:.3f}' for _, v in sorted_factors],
        textposition='outside',
    ))
    fig_corr.update_layout(
        title='요소별 실제 수익률 상관계수',
        xaxis_title='평가 요소',
        yaxis_title='상관계수',
        template='plotly_white',
        height=400,
    )
    st.plotly_chart(fig_corr, use_container_width=True)


# ===== TAB 3: ML 가중치 =====
with tab3:
    st.subheader("🤖 ML 가중치 최적화")

    try:
        from strategy.ml_optimizer import MLOptimizer
        import plotly.graph_objects as go

        opt = MLOptimizer()

        col1, col2 = st.columns([1, 2])

        with col1:
            st.markdown("#### 최적화 실행")
            if st.button("🚀 가중치 최적화 실행", type="primary", use_container_width=True):
                with st.spinner("학습 데이터 수집 중..."):
                    data = opt.collect_training_data()
                    st.success(f"✅ {len(data)}개 지역 데이터 수집 완료")

                with st.spinner("그리드 서치 최적화 중..."):
                    result = opt.optimize_weights()

                st.session_state['ml_result'] = result
                st.session_state['ml_data_collected'] = True

                if result['correlation'] > 0:
                    st.success(f"✅ 최적화 완료! 상관계수: {result['correlation']:.4f}")
                else:
                    st.warning("⚠️ 최적화 결과가 미흡합니다. 더 많은 데이터가 필요할 수 있습니다.")

            st.markdown("#### 가중치 적용")
            if st.button("💾 최적 가중치 저장", use_container_width=True):
                with st.spinner("저장 중..."):
                    success = opt.apply_weights()
                    if success:
                        st.success("✅ 가중치가 DB에 저장되었습니다.")
                    else:
                        st.error("❌ 가중치 저장 실패")

            st.markdown("#### 특징 분석")
            if st.button("🔬 특징 중요도 분석", use_container_width=True):
                with st.spinner("분석 중..."):
                    analysis = opt.analyze_features()
                st.session_state['ml_analysis'] = analysis
                st.success("✅ 분석 완료")

        with col2:
            # Show optimization results
            if 'ml_result' in st.session_state:
                result = st.session_state['ml_result']
                st.markdown("#### 최적화 결과")

                metrics_cols = st.columns(3)
                with metrics_cols[0]:
                    st.markdown(f'<div class="metric-card"><div class="metric-label">상관계수</div><div class="metric-value">{result["correlation"]:.4f}</div></div>',
                                unsafe_allow_html=True)
                with metrics_cols[1]:
                    st.markdown(f'<div class="metric-card"><div class="metric-label">데이터 수</div><div class="metric-value">{result["count"]}</div></div>',
                                unsafe_allow_html=True)
                with metrics_cols[2]:
                    st.markdown(f'<div class="metric-card"><div class="metric-label">방법</div><div class="metric-value" style="font-size:14px">{result["method"]}</div></div>',
                                unsafe_allow_html=True)

                # Weight comparison chart
                weight_map = result.get('weight_map', {})
                if weight_map:
                    names = list(weight_map.keys())
                    opt_vals = list(weight_map.values())
                    default_vals = [opt.DEFAULT_WEIGHTS[opt.FACTOR_NAMES.index(n)] for n in names]

                    fig_weights = go.Figure()
                    fig_weights.add_trace(go.Bar(
                        name='기본 가중치',
                        x=names, y=default_vals,
                        marker_color='lightgray',
                    ))
                    fig_weights.add_trace(go.Bar(
                        name='최적 가중치',
                        x=names, y=opt_vals,
                        marker_color='#1a73e8',
                    ))
                    fig_weights.update_layout(
                        title='가중치 비교 (기본 vs 최적)',
                        barmode='group',
                        template='plotly_white',
                        height=400,
                    )
                    st.plotly_chart(fig_weights, use_container_width=True)

            # Feature importance chart
            if 'ml_analysis' in st.session_state:
                analysis = st.session_state['ml_analysis']
                st.markdown("#### 특징 중요도")

                imp_names = [x[0] for x in analysis['top_features']]
                imp_vals = [x[1] for x in analysis['top_features']]
                corr_vals = [analysis['correlation_matrix'].get(n, 0) for n in imp_names]

                fig_imp = go.Figure()
                fig_imp.add_trace(go.Bar(
                    x=imp_vals,
                    y=imp_names,
                    orientation='h',
                    marker_color=['#d32f2f' if c > 0 else '#1976d2' for c in corr_vals],
                    text=[f'{c:+.3f}' for c in corr_vals],
                    textposition='outside',
                ))
                fig_imp.update_layout(
                    title='Feature Importance (가중치 기반)',
                    xaxis_title='중요도 (%)',
                    yaxis_title='요소',
                    template='plotly_white',
                    height=400,
                )
                st.plotly_chart(fig_imp, use_container_width=True)

        # Show optimization history
        st.markdown("---")
        st.markdown("#### 최적화 이력")
        history = opt.get_optimization_history()
        if history:
            df_hist = pd.DataFrame(history)
            st.dataframe(df_hist, use_container_width=True, hide_index=True)
        else:
            st.caption("아직 최적화 이력이 없습니다.")

        # Show current weights
        st.markdown("#### 저장된 가중치")
        weights = opt.get_current_weights()
        if weights:
            df_weights = pd.DataFrame(weights)
            st.dataframe(df_weights, use_container_width=True, hide_index=True)
        else:
            st.caption("저장된 가중치가 없습니다.")

        opt.close()

    except ImportError as e:
        st.warning(f"⚠️ MLOptimizer를 불러올 수 없습니다: {e}")
        st.info("`pip install numpy`로 numpy를 설치하세요. sklearn/scipy는 선택사항입니다.")


# ===== TAB 4: 외부데이터 =====
with tab4:
    st.subheader("🗄️ 외부 데이터 소스 원본")

    with st.spinner("외부 데이터 로딩 중..."):
        ext_data = get_external_data()

    tabs_ext = st.tabs(list(ext_data.keys()))

    for tab, (name, df) in zip(tabs_ext, ext_data.items()):
        with tab:
            if df.empty:
                st.warning(f"⚠️ '{name}' 테이블에 데이터가 없습니다.")
                st.info("collectors의 해당 수집기를 먼저 실행하세요.")
            else:
                st.caption(f"총 {len(df)}건")
                st.dataframe(df, use_container_width=True, hide_index=True)

                # Summary stats
                st.markdown("#### 요약 통계")
                num_cols = df.select_dtypes(include=['number']).columns
                if len(num_cols) > 0:
                    stats_df = df[num_cols].describe().reset_index()
                    st.dataframe(stats_df, use_container_width=True, hide_index=True)

                # Region distribution
                if 'region' in df.columns:
                    st.markdown("#### 지역 분포")
                    region_counts = df['region'].value_counts().reset_index()
                    region_counts.columns = ['지역', '건수']
                    st.dataframe(region_counts, use_container_width=True, hide_index=True)

    # Data source health
    st.markdown("---")
    st.markdown("#### 📡 데이터 소스 상태")

    # Check all external tables
    conn = get_conn()
    tables_info = {
        'external_kb_index': 'KB 매매수급지수',
        'external_development': '개발호재 정보',
        'external_supply': '공급 데이터',
        'external_school': '학군 정보',
        'external_news_sentiment': '뉴스 감성',
    }
    health_data = []
    for table, label in tables_info.items():
        try:
            row = conn.execute(f"SELECT COUNT(*) as cnt, MAX(updated_at) as last FROM {table}").fetchone()
            cnt = row[0] if row else 0
            last = row[1] if row else '-'
            health_data.append({'소스': label, '레코드': cnt, '최종 업데이트': str(last)[:16] if last else '-'})
        except Exception:
            health_data.append({'소스': label, '레코드': 0, '최종 업데이트': '-'})
    conn.close()

    df_health = pd.DataFrame(health_data)
    st.dataframe(df_health, use_container_width=True, hide_index=True)


# ─── Footer ──────────────────────────────────────────
st.markdown("---")
st.caption(f"🏠 한국 부동산 전략 시스템 v3.0 | 기준일: {datetime.now().strftime('%Y-%m-%d %H:%M')} | Data: 국토교통부 실거래가 API")
