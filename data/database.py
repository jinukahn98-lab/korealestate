"""
데이터베이스 모듈 - SQLite 기반 부동산 데이터 저장/조회
"""

import sqlite3
import os
from datetime import datetime

DB_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'realestate.db')


def get_conn():
    """데이터베이스 연결 반환 (WAL + 64MB cache)"""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA cache_size=-64000")     # 64MB
    conn.execute("PRAGMA synchronous=OFF")       # 읽기 전용 최적화
    conn.execute("PRAGMA temp_store=MEMORY")     # temp table in memory
    conn.execute("PRAGMA mmap_size=268435456")   # 256MB memory-mapped I/O
    return conn


def init_db():
    """데이터베이스 테이블 생성"""
    conn = get_conn()
    cur = conn.cursor()

    cur.executescript('''
        CREATE TABLE IF NOT EXISTS legal_dong_codes (
            code TEXT PRIMARY KEY,
            region_1depth TEXT NOT NULL,
            region_2depth TEXT NOT NULL,
            region_3depth TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS apt_trade (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            lawd_cd TEXT NOT NULL,
            region TEXT,
            apt_name TEXT NOT NULL,
            area REAL,
            floor INTEGER,
            price INTEGER,
            build_year INTEGER,
            deal_date TEXT NOT NULL,
            dong TEXT,
            road TEXT,
            deal_type TEXT DEFAULT '매매',
            collected_at TEXT DEFAULT (datetime('now', 'localtime')),
            UNIQUE(lawd_cd, apt_name, area, floor, deal_date, price)
        );

        CREATE TABLE IF NOT EXISTS apt_rent (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            lawd_cd TEXT NOT NULL,
            region TEXT,
            apt_name TEXT NOT NULL,
            area REAL,
            floor INTEGER,
            deposit INTEGER,
            rent INTEGER DEFAULT 0,
            build_year INTEGER,
            deal_date TEXT NOT NULL,
            dong TEXT,
            rent_type TEXT,
            collected_at TEXT DEFAULT (datetime('now', 'localtime')),
            UNIQUE(lawd_cd, apt_name, area, floor, deal_date, deposit, rent)
        );

        CREATE TABLE IF NOT EXISTS zigbang_items (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            item_id TEXT UNIQUE,
            apt_name TEXT,
            lat REAL,
            lng REAL,
            address TEXT,
            sales_type TEXT,
            deposit INTEGER,
            rent INTEGER,
            price INTEGER,
            area REAL,
            floor INTEGER,
            dong TEXT,
            collected_at TEXT DEFAULT (datetime('now', 'localtime'))
        );

        CREATE TABLE IF NOT EXISTS watchlist (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id TEXT DEFAULT 'default',
            apt_name TEXT NOT NULL,
            region TEXT NOT NULL,
            alert_on_price_change BOOLEAN DEFAULT 1,
            alert_threshold_pct REAL DEFAULT 3.0,
            last_score REAL,
            last_price REAL,
            created_at TEXT DEFAULT (datetime('now', 'localtime')),
            UNIQUE(user_id, apt_name, region)
        );

        CREATE TABLE IF NOT EXISTS price_alerts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            watchlist_id INTEGER,
            alert_type TEXT,
            old_value REAL,
            new_value REAL,
            message TEXT,
            created_at TEXT DEFAULT (datetime('now', 'localtime')),
            notified BOOLEAN DEFAULT 0
        );

        CREATE TABLE IF NOT EXISTS kb_price (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            region TEXT,
            apt_name TEXT,
            price_type TEXT,
            low_price REAL,
            avg_price REAL,
            high_price REAL,
            collected_at TEXT DEFAULT (datetime('now', 'localtime'))
        );

        CREATE TABLE IF NOT EXISTS school_districts (
            apt_name TEXT,
            region TEXT,
            elementary_school TEXT,
            middle_school TEXT,
            school_rating REAL,
            distance_km REAL,
            UNIQUE(apt_name, region)
        );

        CREATE INDEX IF NOT EXISTS idx_trade_date ON apt_trade(deal_date);
        CREATE INDEX IF NOT EXISTS idx_trade_region ON apt_trade(region);
        CREATE INDEX IF NOT EXISTS idx_trade_lawd ON apt_trade(lawd_cd);
        CREATE INDEX IF NOT EXISTS idx_rent_date ON apt_rent(deal_date);
        CREATE INDEX IF NOT EXISTS idx_rent_region ON apt_rent(region);
        CREATE INDEX IF NOT EXISTS idx_zigbang_type ON zigbang_items(sales_type);

        -- 성능 인덱스
        CREATE INDEX IF NOT EXISTS idx_trade_apt_name ON apt_trade(apt_name);
        CREATE INDEX IF NOT EXISTS idx_rent_apt_name ON apt_rent(apt_name);
        CREATE INDEX IF NOT EXISTS idx_trade_region_date ON apt_trade(region, deal_date);
        CREATE INDEX IF NOT EXISTS idx_rent_region_date ON apt_rent(region, deal_date);
    ''')

    conn.commit()
    conn.close()
    print(f"✅ 데이터베이스 초기화 완료: {DB_PATH}")


def save_apt_trades(df, lawd_cd, region):
    """아파트 매매 실거래가 저장 (한글/영문 컬럼명 모두 지원)"""
    if df is None or df.empty:
        return 0
    conn = get_conn()
    cur = conn.cursor()
    count = 0
    for _, row in df.iterrows():
        try:
            apt_name = _get_val(row, '단지명', '아파트', 'aptNm', default='')
            dong = _get_val(row, '법정동', 'umdNm', default='')
            area = _get_val(row, '전용면적', 'excluUseAr', default=0, cast=float)
            floor = _get_val(row, '층', 'floor', default=0, cast=int)
            price = _get_val(row, '거래금액', 'dealAmount', default=0, cast=int)
            build_year = _get_val(row, '건축년도', 'buildYear', default=0, cast=int)
            deal_date = _get_val(row, '거래일', default='')
            road = _get_val(row, '도로명', 'roadNm', default='')
            if not deal_date:
                deal_date = _build_deal_date(row)

            if not apt_name:
                continue

            cur.execute('''
                INSERT OR IGNORE INTO apt_trade
                (lawd_cd, region, apt_name, area, floor, price, build_year, deal_date, dong, road)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (lawd_cd, region, apt_name, area, floor, price, build_year, deal_date, dong, road))
            if cur.rowcount > 0:
                count += 1
        except Exception as e:
            pass
    conn.commit()
    conn.close()
    print(f"  💾 매매 {count}건 저장 완료 (총 {len(df)}건 중)")
    return count


def _get_val(row, *keys, default='', cast=None):
    """여러 키로 값 조회 (한글/영문 컬럼명 모두 지원)"""
    for key in keys:
        if key in row:
            val = row[key]
            if cast == int:
                try:
                    return int(str(val).replace(',', '').strip())
                except (ValueError, TypeError):
                    return 0
            if cast == float:
                try:
                    return float(val)
                except (ValueError, TypeError):
                    return 0.0
            return val if val is not None else default
    return default


def _build_deal_date(row):
    """거래일자 조합 (다양한 컬럼명 지원)"""
    y = _get_val(row, '년', 'dealYear', default='0', cast=int)
    m = _get_val(row, '월', 'dealMonth', default='1', cast=int)
    d = _get_val(row, '일', 'dealDay', default='1', cast=int)
    if y == 0:
        return ''
    return f"{y}-{m:02d}-{d:02d}"


def save_apt_rents(df, lawd_cd, region):
    """아파트 전월세 실거래가 저장 (한글/영문 컬럼명 모두 지원)"""
    if df is None or df.empty:
        return 0
    conn = get_conn()
    cur = conn.cursor()
    count = 0

    # 컬럼명 알림
    _cols = list(df.columns[:5]) if len(df.columns) > 5 else list(df.columns)
    print(f"  컬럼명: {_cols}...")

    for _, row in df.iterrows():
        try:
            apt_name = _get_val(row, '단지명', '아파트', 'aptNm', default='')
            dong = _get_val(row, '법정동', 'umdNm', default='')
            area = _get_val(row, '전용면적', 'excluUseAr', default=0, cast=float)
            floor = _get_val(row, '층', 'floor', default=0, cast=int)
            deposit = _get_val(row, '보증금액', '보증금', 'deposit', default=0, cast=int)
            rent = _get_val(row, '월세금액', '월세', 'monthlyRent', default=0, cast=int)
            build_year = _get_val(row, '건축년도', 'buildYear', default=0, cast=int)
            deal_date = _get_val(row, '거래일', default='')
            if not deal_date:
                y = _get_val(row, '계약년도', '년', 'dealYear', default='0', cast=int)
                m = _get_val(row, '계약월', '월', 'dealMonth', default='1', cast=int)
                d = _get_val(row, '계약일', '일', 'dealDay', default='1', cast=int)
                if y > 0:
                    deal_date = f"{y}-{m:02d}-{d:02d}"

            if not apt_name:
                continue

            cur.execute('''
                INSERT OR IGNORE INTO apt_rent
                (lawd_cd, region, apt_name, area, floor, deposit, rent, build_year, deal_date, dong)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (lawd_cd, region, apt_name, area, floor, deposit, rent, build_year, deal_date, dong))
            if cur.rowcount > 0:
                count += 1
        except Exception as e:
            pass
    conn.commit()
    conn.close()
    print(f"  💾 전월세 {count}건 저장 완료 (총 {len(df)}건 중)")
    return count


def save_zigbang_items(items, dong=''):
    """직방 매물 저장"""
    if not items:
        return 0
    conn = get_conn()
    cur = conn.cursor()
    count = 0
    for item in items:
        try:
            item_id = str(item.get('item_id', ''))
            if not item_id:
                continue
            cur.execute('''
                INSERT OR IGNORE INTO zigbang_items
                (item_id, apt_name, lat, lng, address, sales_type, deposit, rent, price, area, floor, dong)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                item_id,
                item.get('title', '') or item.get('name', ''),
                float(item.get('lat', 0)),
                float(item.get('lng', 0)),
                item.get('address', ''),
                item.get('sales_type', ''),
                int(item.get('deposit', 0) or 0),
                int(item.get('rent', 0) or 0),
                int(item.get('price', 0) or 0),
                float(item.get('area', 0) or 0),
                int(item.get('floor', 0) or 0),
                dong
            ))
            if cur.rowcount > 0:
                count += 1
        except Exception as e:
            pass
    conn.commit()
    conn.close()
    return count


def get_trade_stats(region=None, months=6):
    """지역별 매매 통계 조회"""
    conn = get_conn()
    query = '''
        SELECT region, apt_name, 
               ROUND(AVG(price), 0) as avg_price, 
               ROUND(AVG(area), 1) as avg_area,
               COUNT(*) as trade_count,
               MIN(price) as min_price,
               MAX(price) as max_price
        FROM apt_trade
    '''
    params = []
    if region:
        query += ' WHERE region LIKE ?'
        params.append(f'%{region}%')
    query += ' GROUP BY region, apt_name ORDER BY trade_count DESC LIMIT 50'
    df = pd.read_sql_query(query, conn, params=params)
    conn.close()
    return df


def get_jeonse_rate(region=None, months=6):
    """지역별 전세가율 조회"""
    conn = get_conn()
    query = '''
        SELECT 
            t.region,
            t.apt_name,
            t.area,
            ROUND(AVG(t.price), 0) as avg_trade_price,
            ROUND(AVG(r.deposit), 0) as avg_jeonse_deposit,
            ROUND(AVG(r.deposit) * 100.0 / AVG(t.price), 1) as jeonse_rate
        FROM apt_trade t
        JOIN apt_rent r ON t.apt_name = r.apt_name 
            AND ABS(t.area - r.area) < 5
            AND t.region = r.region
    '''
    params = []
    if region:
        query += ' WHERE t.region LIKE ?'
        params.append(f'%{region}%')
    query += ' GROUP BY t.region, t.apt_name, t.area HAVING COUNT(*) > 2 ORDER BY jeonse_rate DESC'
    df = pd.read_sql_query(query, conn, params=params)
    conn.close()
    return df


# pandas import는 함수 내에서 lazy import
import pandas as pd


def get_db_stats():
    """DB 통계 정보"""
    conn = get_conn()
    cur = conn.cursor()
    stats = {}
    for table in ['apt_trade', 'apt_rent', 'zigbang_items']:
        cur.execute(f'SELECT COUNT(*) FROM {table}')
        stats[table] = cur.fetchone()[0]
    conn.close()
    return stats


# Streamlit 연결 풀 (선택적 — st 없어도 작동)
try:
    import streamlit as st
    @st.cache_resource
    def get_shared_conn():
        """Streamlit 세션 간 공유 connection (WAL + 64MB cache)"""
        return get_conn()
except ImportError:
    def get_shared_conn():
        return get_conn()
