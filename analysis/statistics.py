"""
통계 분석 모듈 - 지역별 가격 통계, 전세가율, 추이 분석
"""

import pandas as pd
import sqlite3
from datetime import datetime, timedelta
from data.database import get_conn, DB_PATH


def get_region_trade_summary(region=None, months=6):
    """지역별 매매가 요약 통계"""
    conn = get_conn()
    query = '''
        SELECT 
            region,
            COUNT(*) as 거래건수,
            ROUND(AVG(price), 0) as 평균매매가,
            ROUND(MIN(price), 0) as 최저가,
            ROUND(MAX(price), 0) as 최고가,
            ROUND(AVG(area), 1) as 평균전용면적,
            ROUND(AVG(price) / AVG(area), 0) as 평당가
        FROM apt_trade
    '''
    params = []
    if region:
        query += ' WHERE region LIKE ?'
        params.append(f'%{region}%')
    query += ' GROUP BY region ORDER BY 평균매매가 DESC'
    df = pd.read_sql_query(query, conn, params=params)
    conn.close()
    return df


def get_apt_detail(apt_name, region=None):
    """특정 아파트 상세 거래 내역"""
    conn = get_conn()
    query = "SELECT * FROM apt_trade WHERE apt_name LIKE ?"
    params = [f'%{apt_name}%']
    if region:
        query += ' AND region LIKE ?'
        params.append(f'%{region}%')
    query += ' ORDER BY deal_date DESC LIMIT 100'
    df = pd.read_sql_query(query, conn, params=params)
    conn.close()
    return df


def get_jeonse_rate_analysis(region=None, area_range=None):
    """전세가율 분석"""
    conn = get_conn()
    query = '''
        SELECT 
            t.region,
            t.apt_name,
            ROUND(AVG(t.area), 1) as 전용면적,
            ROUND(AVG(t.price), 0) as 평균매매가,
            ROUND(AVG(r.deposit), 0) as 평균전세보증금,
            ROUND(AVG(r.deposit) * 100.0 / NULLIF(AVG(t.price), 0), 1) as 전세가율,
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

    if area_range:
        min_area, max_area = area_range
        conditions.append('(t.area BETWEEN ? AND ? AND r.area BETWEEN ? AND ?)')
        params.extend([min_area, max_area, min_area, max_area])

    if conditions:
        query += ' WHERE ' + ' AND '.join(conditions)

    query += ''' GROUP BY t.region, t.apt_name 
                 HAVING COUNT(*) > 2 AND 평균매매가 > 0
                 ORDER BY 전세가율 DESC'''

    df = pd.read_sql_query(query, conn, params=params)
    conn.close()
    return df


def get_monthly_trend(region=None, months=12):
    """월별 가격 추이 분석"""
    conn = get_conn()
    query = '''
        SELECT 
            substr(deal_date, 1, 7) as 월,
            COUNT(*) as 거래건수,
            ROUND(AVG(price), 0) as 평균매매가,
            ROUND(AVG(area), 1) as 평균면적,
            ROUND(AVG(price) / NULLIF(AVG(area), 0), 0) as 평당가
        FROM apt_trade
    '''
    params = []
    if region:
        query += ' WHERE region LIKE ?'
        params.append(f'%{region}%')
    query += ' GROUP BY 월 ORDER BY 월'
    df = pd.read_sql_query(query, conn, params=params)
    conn.close()

    if not df.empty:
        df['월'] = df['월'].astype(str)
    return df


def get_area_distribution(region=None):
    """면적별 가격 분포"""
    conn = get_conn()
    area_bins = """
        CASE 
            WHEN area < 20 THEN '10~20평'
            WHEN area < 30 THEN '20~30평'
            WHEN area < 40 THEN '30~40평'
            WHEN area < 50 THEN '40~50평'
            WHEN area < 60 THEN '50~60평'
            ELSE '60평+'
        END as 면적구간
    """

    # 평당 가격 = area in m² -> pyeong (1평 = 3.3m²)
    query = f'''
        SELECT 
            {area_bins},
            COUNT(*) as 거래건수,
            ROUND(AVG(price), 0) as 평균매매가,
            ROUND(AVG(price) * 3.3 / NULLIF(AVG(area), 0), 0) as 평당가,
            ROUND(MIN(price), 0) as 최저가,
            ROUND(MAX(price), 0) as 최고가
        FROM apt_trade
    '''
    params = []
    if region:
        query += ' WHERE region LIKE ?'
        params.append(f'%{region}%')
    query += ' GROUP BY 면적구간 ORDER BY MIN(area)'
    df = pd.read_sql_query(query, conn, params=params)
    conn.close()
    return df


def get_hot_areas(months=3, min_trades=3):
    """최근 거래 급증 지역 분석"""
    conn = get_conn()
    query = '''
        SELECT 
            region,
            COUNT(*) as 거래건수,
            ROUND(AVG(price), 0) as 평균매매가,
            ROUND(AVG(price * 3.3 / NULLIF(area, 0)), 0) as 평당가
        FROM apt_trade
        WHERE deal_date >= date('now', ?)
        GROUP BY region
        HAVING COUNT(*) >= ?
        ORDER BY 거래건수 DESC
        LIMIT 20
    '''
    start_date = f'-{months} months'
    df = pd.read_sql_query(query, conn, params=[start_date, min_trades])
    conn.close()
    return df


def get_gap_analysis(region=None):
    """갭 분석 (매매가 - 전세보증금)"""
    conn = get_conn()
    query = '''
        SELECT 
            t.region,
            t.apt_name,
            ROUND(AVG(t.area), 1) as 전용면적,
            ROUND(AVG(t.price), 0) as 평균매매가,
            ROUND(AVG(r.deposit), 0) as 평균전세가,
            ROUND(AVG(t.price) - AVG(r.deposit), 0) as 갭,
            ROUND(AVG(r.deposit) * 100.0 / NULLIF(AVG(t.price), 0), 1) as 전세가율,
            COUNT(*) as 분석건수
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
                 ORDER BY 갭 ASC'''
    df = pd.read_sql_query(query, conn, params=params)
    conn.close()
    return df


def get_pyoung_price(region=None):
    """평당가 기준 단지 분석 (낮은 순 = 저평가 단지)"""
    conn = get_conn()
    query = '''
        SELECT region, apt_name, dong,
            ROUND(AVG(price * 3.3 / NULLIF(area, 0)), 0) as 평당가,
            ROUND(AVG(price), 0) as 평균매매가,
            ROUND(AVG(area), 1) as 평균면적,
            COUNT(*) as cnt
        FROM apt_trade
    '''
    params = []
    if region:
        query += ' WHERE region LIKE ?'
        params.append(f'%{region}%')
    query += ' GROUP BY region, apt_name HAVING cnt > 2 ORDER BY 평당가 ASC'
    df = pd.read_sql_query(query, conn, params=params)
    conn.close()
    return df


def get_floor_premium(region=None):
    """층수별 가격 프리미엄 분석 (저층/중층/고층)"""
    conn = get_conn()
    query = '''
        SELECT
            CASE
                WHEN floor BETWEEN 1 AND 5 THEN '저층(1~5층)'
                WHEN floor BETWEEN 6 AND 15 THEN '중층(6~15층)'
                ELSE '고층(16층+)'
            END as 층구분,
            COUNT(*) as 거래건수,
            ROUND(AVG(price), 0) as 평균매매가,
            ROUND(AVG(price * 3.3 / NULLIF(area, 0)), 0) as 평당가
        FROM apt_trade
        WHERE floor IS NOT NULL AND floor > 0
    '''
    params = []
    if region:
        query += ' AND region LIKE ?'
        params.append(f'%{region}%')
    query += ' GROUP BY 층구분 ORDER BY MIN(floor)'
    df = pd.read_sql_query(query, conn, params=params)
    conn.close()

    if not df.empty and len(df) >= 2:
        low = df[df['층구분'].str.startswith('저층')]['평균매매가'].values
        high = df[df['층구분'].str.startswith('고층')]['평균매매가'].values
        if len(low) > 0 and len(high) > 0 and low[0] > 0:
            premium = round((high[0] - low[0]) / low[0] * 100, 1)
            df.attrs['고층_저층_프리미엄'] = premium
    return df


def get_seasonal_pattern(region=None):
    """월별 계절성 분석 — 가장 싼 달/비싼 달 식별"""
    conn = get_conn()
    query = '''
        SELECT
            CAST(substr(deal_date, 6, 2) AS INTEGER) as 월,
            COUNT(*) as 거래건수,
            ROUND(AVG(price), 0) as 평균매매가,
            ROUND(AVG(price * 3.3 / NULLIF(area, 0)), 0) as 평당가
        FROM apt_trade
    '''
    params = []
    if region:
        query += ' WHERE region LIKE ?'
        params.append(f'%{region}%')
    query += ' GROUP BY 월 ORDER BY 월'
    df = pd.read_sql_query(query, conn, params=params)
    conn.close()

    if not df.empty:
        cheapest = df.loc[df['평균매매가'].idxmin(), '월']
        priciest = df.loc[df['평균매매가'].idxmax(), '월']
        peak_vol = df.loc[df['거래건수'].idxmax(), '월']
        df.attrs['가장_싼_달'] = int(cheapest)
        df.attrs['가장_비싼_달'] = int(priciest)
        df.attrs['거래량_피크_달'] = int(peak_vol)
    return df


def get_trade_gap_alert(months=6):
    """180일 이상 거래 없는 유동성 위험 단지 탐지"""
    conn = get_conn()
    threshold_days = months * 30
    query = f'''
        SELECT
            region, apt_name,
            MAX(deal_date) as last_trade_date,
            CAST(julianday('now') - julianday(MAX(deal_date)) AS INTEGER) as days_since_last_trade,
            (SELECT price FROM apt_trade t2
             WHERE t2.apt_name = apt_trade.apt_name AND t2.region = apt_trade.region
             ORDER BY t2.deal_date DESC LIMIT 1) as last_price
        FROM apt_trade
        GROUP BY region, apt_name
        HAVING days_since_last_trade >= {threshold_days}
        ORDER BY days_since_last_trade DESC
    '''
    df = pd.read_sql_query(query, conn)
    conn.close()
    return df


def get_quantile_picks(region, quantile=0.25):
    """지역 내 하위 N% 저평가 단지 — 평균 대비 할인율 포함"""
    conn = get_conn()
    query = '''
        SELECT
            t.region, t.apt_name, t.dong,
            ROUND(AVG(t.price), 0) as 평균매매가,
            ROUND(AVG(t.price * 3.3 / NULLIF(t.area, 0)), 0) as 평당가,
            COUNT(*) as 거래건수
        FROM apt_trade t
        WHERE t.region LIKE ?
        GROUP BY t.region, t.apt_name
        HAVING 거래건수 > 1
        ORDER BY 평균매매가 ASC
    '''
    df = pd.read_sql_query(query, conn, params=[f'%{region}%'])
    conn.close()

    if df.empty:
        return df

    cutoff = df['평균매매가'].quantile(quantile)
    df = df[df['평균매매가'] <= cutoff].copy()
    region_avg = df['평균매매가'].mean()
    if region_avg > 0:
        # 전체 지역 평균을 다시 구하기 위해 원본 기준 할인율 계산
        conn2 = get_conn()
        full_avg = pd.read_sql_query(
            'SELECT ROUND(AVG(price), 0) as avg FROM apt_trade WHERE region LIKE ?',
            conn2, params=[f'%{region}%']
        )['avg'].iloc[0]
        conn2.close()
        if full_avg and full_avg > 0:
            df['할인율(%)'] = ((1 - df['평균매매가'] / full_avg) * 100).round(1)
    return df


def get_jeonse_momentum(region=None, months=3):
    """전세가율 모멘텀 — 최근 N개월 vs 이전 N개월 변화 추이"""
    conn = get_conn()
    base_query = '''
        SELECT t.region, t.apt_name,
            ROUND(AVG(r.deposit) * 100.0 / NULLIF(AVG(t.price), 0), 1) as 전세가율,
            COUNT(*) as cnt
        FROM apt_trade t
        JOIN apt_rent r ON t.apt_name = r.apt_name AND ABS(t.area - r.area) < 5
        WHERE {date_cond}
        GROUP BY t.region, t.apt_name
        HAVING cnt >= 2
    '''
    params_recent = []
    params_prev = []
    recent_cond = "t.deal_date >= date('now', ?) AND r.deal_date >= date('now', ?)"
    prev_cond = ("t.deal_date BETWEEN date('now', ?) AND date('now', ?)"
                 " AND r.deal_date BETWEEN date('now', ?) AND date('now', ?)")

    if region:
        recent_cond += ' AND t.region LIKE ?'
        params_recent = [f'-{months} months', f'-{months} months', f'%{region}%']
        prev_cond += ' AND t.region LIKE ?'
        params_prev = [f'-{months * 2} months', f'-{months} months',
                       f'-{months * 2} months', f'-{months} months', f'%{region}%']
    else:
        params_recent = [f'-{months} months', f'-{months} months']
        params_prev = [f'-{months * 2} months', f'-{months} months',
                       f'-{months * 2} months', f'-{months} months']

    df_recent = pd.read_sql_query(
        base_query.format(date_cond=recent_cond), conn, params=params_recent
    ).rename(columns={'전세가율': '최근전세가율', 'cnt': 'cnt_recent'})

    df_prev = pd.read_sql_query(
        base_query.format(date_cond=prev_cond), conn, params=params_prev
    ).rename(columns={'전세가율': '이전전세가율', 'cnt': 'cnt_prev'})

    conn.close()

    if df_recent.empty:
        return df_recent

    df = df_recent.merge(df_prev[['region', 'apt_name', '이전전세가율']],
                         on=['region', 'apt_name'], how='left')
    df['전세가율변화'] = (df['최근전세가율'] - df['이전전세가율']).round(1)
    df['추세'] = df['전세가율변화'].apply(
        lambda x: '상승▲' if x > 0 else ('하락▼' if x < 0 else '보합-') if pd.notna(x) else '-'
    )
    return df.sort_values('전세가율변화', ascending=False)


def print_summary(df, title="분석 결과"):
    """데이터프레임을 예쁘게 출력"""
    if df is None or df.empty:
        print(f"\n📭 {title}: 데이터가 없습니다.")
        print("   먼저 `collect` 명령어로 데이터를 수집해주세요.")
        return

    print(f"\n📊 {title}")
    print(f"   총 {len(df)}건")
    print("-" * 60)

    # 모든 컬럼 출력
    pd.set_option('display.max_columns', None)
    pd.set_option('display.width', 120)
    pd.set_option('display.max_colwidth', 20)
    pd.set_option('display.float_format', '{:,.0f}'.format)

    print(df.to_string(index=False))
    print("-" * 60)
