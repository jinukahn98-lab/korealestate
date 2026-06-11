"""
전세/월세 전략 모듈 - 전세가율, 적정 전세가, 역전세 위험
"""

import pandas as pd
from data.database import get_conn
from analysis.statistics import print_summary


def analyze_jeonse(region, deposit=None, area_pyeong=None):
    """전세 전략 분석"""
    print(f"\n{'='*60}")
    print(f"  🏠 전세 전략 분석: {region}")
    if deposit:
        print(f"     예산: {deposit}억원")
    print(f"{'='*60}")

    conn = get_conn()

    query = '''
        SELECT region, apt_name, dong, 
               ROUND(AVG(area), 1) as avg_area,
               ROUND(AVG(deposit), 0) as avg_deposit,
               ROUND(AVG(rent), 0) as avg_rent,
               COUNT(*) as trade_count,
               MIN(deposit) as min_deposit,
               MAX(deposit) as max_deposit
        FROM apt_rent
        WHERE region LIKE ? AND (rent_type IS NULL OR rent_type = '전세' OR deposit > 0)
    '''
    params = [f'%{region}%']

    if deposit:
        deposit_m = deposit * 10000
        query += ' AND deposit <= ?'
        params.append(deposit_m)

    if area_pyeong:
        min_area = area_pyeong[0] * 3.3
        max_area = area_pyeong[1] * 3.3
        query += ' AND area BETWEEN ? AND ?'
        params.extend([min_area, max_area])

    query += ' GROUP BY apt_name ORDER BY avg_deposit DESC LIMIT 30'
    df = pd.read_sql_query(query, conn, params=params)
    conn.close()

    if df.empty:
        print(f"\n  ❌ '{region}' 전세 데이터가 없습니다.")
        return None

    print(f"\n  ✅ {len(df)}개 단지 분석 완료")
    print(f"\n  {'단지명':12s} {'보증금':>10s} {'면적':>6s} {'건수':>4s}")
    print(f"  {'-'*40}")
    for _, row in df.head(15).iterrows():
        print(f"  {row['apt_name']:12s} {row['avg_deposit']/10000:>8.1f}억 {row['avg_area']:>5.0f}m² {row['trade_count']:>4d}")

    return df


def analyze_wolse(region, deposit=None):
    """월세 시장 분석 (전환율 포함)"""
    conn = get_conn()
    query = '''
        SELECT region, apt_name, 
               ROUND(AVG(deposit), 0) as avg_deposit,
               ROUND(AVG(rent), 0) as avg_rent,
               ROUND(AVG(area), 1) as avg_area,
               COUNT(*) as cnt
        FROM apt_rent
        WHERE region LIKE ? AND rent > 0
    '''
    params = [f'%{region}%']
    if deposit:
        params.append(deposit * 10000)
        query += ' AND deposit <= ?'
    query += ' GROUP BY apt_name HAVING cnt > 2 ORDER BY avg_rent DESC'
    df = pd.read_sql_query(query, conn, params=params)
    conn.close()

    if not df.empty:
        df['전월세전환율'] = df.apply(
            lambda r: round(r['avg_rent'] * 12 / (r['avg_deposit'] or 1) * 100, 2), axis=1
        )
        print_summary(df, f"📊 월세 분석: {region}")

    return df


def detect_reverse_jeonse_risk(region=None, threshold=80):
    """역전세 위험 단지 탐지"""
    from analysis.indicators import get_reverse_jeonse_risk
    risk = get_reverse_jeonse_risk(region)
    if risk is not None and not risk.empty:
        print(f"\n🚨 역전세 위험 단지 TOP 10")
        print(f"{'='*60}")
        for i, (_, row) in enumerate(risk.head(10).iterrows(), 1):
            print(f"  {i}. {row['아파트']} ({row['지역']})")
            print(f"     전세가율: {row['전세가율']:.1f}% | 갭: {row['갭']:,.0f}만원")
            print(f"     최근매매: {row['최근매매가']:,.0f}만원 / 전세: {row['최근전세가']:,.0f}만원")
    return risk


def jeonse_to_monthly_ratio(region=None, months=6):
    """전세/월세 전환율 분석"""
    conn = get_conn()
    query = '''
        SELECT region, apt_name, 
               ROUND(AVG(deposit), 0) as avg_deposit,
               ROUND(AVG(rent), 0) as avg_rent,
               ROUND(AVG(rent) * 12 * 100.0 / NULLIF(AVG(deposit), 0), 2) as 전환율
        FROM apt_rent
        WHERE rent > 0 AND deposit > 0
    '''
    params = []
    if region:
        query += ' AND region LIKE ?'
        params.append(f'%{region}%')
    query += ' GROUP BY apt_name HAVING COUNT(*) > 2 ORDER BY 전환율 DESC'
    df = pd.read_sql_query(query, conn, params=params)
    conn.close()

    if not df.empty:
        avg_rate = df['전환율'].mean()
        print(f"\n📊 {region or '전체'} 전월세 전환율")
        print(f"   평균 전환율: {avg_rate:.2f}%")
        print(f"   (법정 전환율: 4.0% 기준)")
        print(f"   분석 단지: {len(df)}개")
        for _, row in df.head(5).iterrows():
            print(f"   {row['apt_name']}: {row['전환율']:.2f}%")
    return df


def alert_reverse_jeonse(threshold=80, min_trades=3):
    """역전세 위험 단지 탐색 + 텔레그램용 경보 메시지 생성"""
    from analysis.indicators import get_reverse_jeonse_risk
    from datetime import date

    risk = get_reverse_jeonse_risk()
    if risk is None or risk.empty:
        return None

    filtered = risk[
        (risk['전세가율'] >= threshold) &
        (risk['분석건수'] >= min_trades)
    ]
    if filtered.empty:
        return None

    lines = [f"🚨 역전세 경보 — {date.today().strftime('%Y-%m-%d')}", "━" * 20]
    for _, row in filtered.iterrows():
        gap_eok = row['갭'] / 10000
        lines.append(
            f"{row['apt_name']} ({row['region']}): "
            f"전세가율 {row['전세가율']:.1f}% / 갭 {gap_eok:.1f}억"
        )
    return "\n".join(lines)


def get_jeonse_strategy(region, deposit_budget=None):
    """종합 전세 전략 추천"""
    print(f"\n{'='*60}")
    print(f"  🎯 {region} 전세 전략")
    print(f"{'='*60}")

    # 1. 전세 가능 단지
    jeonse_df = analyze_jeonse(region, deposit_budget)

    # 2. 전세가율 (매매가 대비)
    from analysis.indicators import get_yield_analysis
    yield_df = get_yield_analysis(region)
    if yield_df is not None and not yield_df.empty:
        avg_rate = yield_df['전세가율'].mean()
        print(f"\n  📊 {region} 평균 전세가율: {avg_rate:.1f}%")
        if avg_rate > 80:
            print(f"     ⚠ 전세가율이 높습니다. 역전세 위험에 주의하세요.")
        elif avg_rate < 60:
            print(f"     ✅ 전세가율이 낮아 안정적입니다.")

        # 전세가율 TOP/BOTTOM
        print(f"\n  📈 전세가율 높은 단지 (TOP 5):")
        for _, row in yield_df.head(5).iterrows():
            print(f"     {row['아파트']}: {row['전세가율']:.1f}%")

        print(f"\n  📉 전세가율 낮은 단지 (BOTTOM 5):")
        for _, row in yield_df.tail(5).iterrows():
            print(f"     {row['아파트']}: {row['전세가율']:.1f}%")

    # 3. 역전세 위험
    detect_reverse_jeonse_risk(region)

    return jeonse_df
