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
                 ORDER BY 갑 ASC'''
    df = pd.read_sql_query(query, conn, params=params)
    conn.close()
    return df


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
