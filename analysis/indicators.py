"""
투자 지표 분석 모듈 - 수익률, 변동성, 위험 분석
"""

import pandas as pd
from data.database import get_conn
from analysis.statistics import print_summary


def get_yield_analysis(region=None):
    """매매/전세 수익률 분석"""
    conn = get_conn()
    query = '''
        SELECT 
            t.region,
            t.apt_name,
            ROUND(AVG(t.area), 1) as 전용면적,
            ROUND(AVG(t.price), 0) as 평균매매가,
            ROUND(AVG(r.deposit), 0) as 평균전세가,
            ROUND(AVG(r.rent), 0) as 평균월세,
            ROUND(AVG(r.deposit) * 100.0 / NULLIF(AVG(t.price), 0), 1) as 전세가율,
            ROUND(AVG(r.rent) * 12 * 10000.0 / NULLIF(AVG(t.price) - AVG(r.deposit), 0), 1) as 월세수익률_퍼센트,
            ROUND(AVG(t.price) - AVG(r.deposit), 0) as 갭투자금액
        FROM apt_trade t
        JOIN apt_rent r ON t.apt_name = r.apt_name 
            AND ABS(t.area - r.area) < 5
    '''
    params = []
    if region:
        query += ' WHERE t.region LIKE ?'
        params.append(f'%{region}%')
    query += ''' GROUP BY t.region, t.apt_name 
                 HAVING COUNT(*) > 2 AND 평균매매가 > 0
                 ORDER BY 월세수익률_퍼센트 DESC'''
    df = pd.read_sql_query(query, conn, params=params)
    conn.close()
    return df


def get_price_volatility(region=None, months=12):
    """가격 변동성 분석"""
    conn = get_conn()
    query = '''
        SELECT 
            region,
            apt_name,
            substr(deal_date, 1, 7) as 월,
            ROUND(AVG(price), 0) as 월평균가
        FROM apt_trade
    '''
    params = []
    if region:
        query += ' WHERE region LIKE ?'
        params.append(f'%{region}%')
    query += ' GROUP BY region, apt_name, 월 ORDER BY region, apt_name, 월'
    df = pd.read_sql_query(query, conn, params=params)
    conn.close()

    if df.empty:
        return pd.DataFrame()

    # 월별 변동률 계산
    results = []
    for (reg, apt), group in df.groupby(['region', 'apt_name']):
        if len(group) < 2:
            continue
        group = group.sort_values('월')
        first_price = group['월평균가'].iloc[0]
        last_price = group['월평균가'].iloc[-1]
        change_rate = ((last_price - first_price) / first_price * 100) if first_price > 0 else 0

        # 표준편차로 변동성 측정
        std = group['월평균가'].std()
        mean = group['월평균가'].mean()
        volatility = (std / mean * 100) if mean > 0 else 0

        results.append({
            '지역': reg,
            '아파트': apt,
            '분석개월': len(group),
            '초기가격': int(first_price),
            '최종가격': int(last_price),
            '변동률_퍼센트': round(change_rate, 1),
            '변동성_퍼센트': round(volatility, 1),
        })

    result_df = pd.DataFrame(results)
    if not result_df.empty:
        result_df = result_df.sort_values('변동률_퍼센트', ascending=False)

    return result_df


def get_reverse_jeonse_risk(region=None):
    """역전세 위험 탐지"""
    conn = get_conn()
    query = '''
        SELECT 
            t.region,
            t.apt_name,
            ROUND(AVG(t.area), 1) as 전용면적,
            ROUND(AVG(t.price), 0) as 최근매매가,
            ROUND(AVG(r.deposit), 0) as 최근전세가,
            ROUND(AVG(r.deposit) * 100.0 / NULLIF(AVG(t.price), 0), 1) as 전세가율,
            ROUND(AVG(t.price) - AVG(r.deposit), 0) as 갭,
            COUNT(*) as 분석건수
        FROM apt_trade t
        JOIN apt_rent r ON t.apt_name = r.apt_name 
            AND ABS(t.area - r.area) < 5
    '''
    params = []
    conditions = []
    if region:
        conditions.append('(t.region LIKE ? OR r.region LIKE ?)')
        params.extend([f'%{region}%', f'%{region}%'])
    conditions.append('t.price < r.deposit')
    if conditions:
        query += ' WHERE ' + ' AND '.join(conditions)
    query += ''' GROUP BY t.region, t.apt_name 
                 HAVING COUNT(*) > 2
                 ORDER BY 전세가율 DESC'''
    df = pd.read_sql_query(query, conn, params=params)
    conn.close()
    return df


def get_trade_volume_trend(region=None, months=12):
    """거래량 추이 분석"""
    conn = get_conn()
    query = '''
        SELECT 
            region,
            substr(deal_date, 1, 7) as 월,
            COUNT(*) as 거래건수,
            ROUND(AVG(price), 0) as 평균매매가
        FROM apt_trade
    '''
    params = []
    if region:
        query += ' WHERE region LIKE ?'
        params.append(f'%{region}%')
    query += ' GROUP BY region, 월 ORDER BY 월'
    df = pd.read_sql_query(query, conn, params=params)
    conn.close()
    return df


def get_investment_summary(region):
    """투자 종합 요약"""
    print(f"\n{'='*60}")
    print(f"  📋 {region} 투자 분석 종합 요약")
    print(f"{'='*60}")

    # 1. 전세가율
    jeonse = get_yield_analysis(region)
    if jeonse is not None and not jeonse.empty:
        avg_rate = jeonse['전세가율'].mean()
        print(f"\n  📊 평균 전세가율: {avg_rate:.1f}%")
        print(f"     분석 단지 수: {len(jeonse)}개")
        high_risk = jeonse[jeonse['전세가율'] > 80]
        if not high_risk.empty:
            print(f"     ⚠ 전세가율 80% 이상 단지: {len(high_risk)}개")

    # 2. 갭 분석
    gap = get_yield_analysis(region)
    if gap is not None and not gap.empty:
        avg_gap = gap['갭투자금액'].mean()
        print(f"\n  💰 평균 갭투자 금액: {avg_gap:.0f}만원")

    # 3. 월세수익률
    if gap is not None and not gap.empty:
        avg_yield = gap['월세수익률_퍼센트'].mean()
        print(f"\n  💵 평균 월세수익률: {avg_yield:.1f}%")

    # 4. 역전세 위험
    risk = get_reverse_jeonse_risk(region)
    if risk is not None and not risk.empty:
        print(f"\n  🚨 역전세 위험 단지: {len(risk)}개")
        for _, r in risk.head(3).iterrows():
            print(f"     - {r['아파트']}: 전세가율 {r['전세가율']:.1f}%")

    return {
        'region': region,
        'jeonse_rate': round(avg_rate, 1) if 'avg_rate' in dir() else 0,
    }
