"""매수/매도 타이밍 신호 생성기

거래량 변동, 전세가율, 계절성 기반 BUY/HOLD/SELL 신호
"""
import pandas as pd
from data.database import get_conn


def get_timing_signal(region):
    """지역별 매수/매도 타이밍 신호 생성
    
    Returns: dict with signal, score, reasons
    """
    conn = get_conn()
    
    # 1. 거래량 추이 (전월 대비)
    vol_query = """
    SELECT strftime('%Y-%m', deal_date) as month, COUNT(*) as cnt
    FROM apt_trade WHERE region LIKE ? AND deal_date >= date('now', '-6 months')
    GROUP BY month ORDER BY month
    """
    vol_df = pd.read_sql_query(vol_query, conn, params=[f'%{region}%'])
    
    # 2. 전세가율 추이  
    rate_query = """
    SELECT AVG(r.deposit * 100.0 / NULLIF(t.price, 0)) as jeonse_rate
    FROM apt_trade t JOIN apt_rent r ON t.apt_name = r.apt_name AND ABS(t.area - r.area) < 5
    WHERE t.region LIKE ? AND t.deal_date >= date('now', '-3 months')
      AND r.deal_date >= date('now', '-3 months')
    """
    current_rate = pd.read_sql_query(rate_query, conn, params=[f'%{region}%']).iloc[0,0] or 0
    
    rate_query_prev = """
    SELECT AVG(r.deposit * 100.0 / NULLIF(t.price, 0)) as jeonse_rate
    FROM apt_trade t JOIN apt_rent r ON t.apt_name = r.apt_name AND ABS(t.area - r.area) < 5
    WHERE t.region LIKE ? AND t.deal_date BETWEEN date('now', '-6 months') AND date('now', '-3 months')
      AND r.deal_date BETWEEN date('now', '-6 months') AND date('now', '-3 months')
    """
    prev_rate = pd.read_sql_query(rate_query_prev, conn, params=[f'%{region}%']).iloc[0,0] or 0
    
    # 3. 거래 공백 (최근 거래일)
    recency_query = """
    SELECT MAX(deal_date) as last_trade FROM apt_trade WHERE region LIKE ?
    """
    last_trade = pd.read_sql_query(recency_query, conn, params=[f'%{region}%']).iloc[0,0]
    
    conn.close()
    
    # 점수 계산
    score = 50  # baseline neutral
    reasons = []
    details = {}
    
    # 거래량 분석
    if len(vol_df) >= 2:
        recent = vol_df['cnt'].iloc[-1]
        prev = vol_df['cnt'].iloc[-2]
        vol_change = (recent - prev) / max(prev, 1) * 100
        details['vol_change_pct'] = round(vol_change, 1)
        if vol_change > 20:
            score += 15
            reasons.append(f"거래량 {vol_change:.0f}%↑ 매수 활발")
        elif vol_change > 0:
            score += 5
            reasons.append(f"거래량 소폭 증가")
        elif vol_change < -20:
            score -= 10
            reasons.append(f"거래량 {abs(vol_change):.0f}%↓ 시장 위축")
    
    # 전세가율 분석
    details['current_rate'] = round(current_rate, 1)
    details['prev_rate'] = round(prev_rate, 1)
    if current_rate > 80:
        score -= 15
        reasons.append(f"전세가율 {current_rate:.1f}% 과열")
    elif current_rate > 70:
        score += 10
        reasons.append(f"전세가율 {current_rate:.1f}% 안정적 갭투자 가능")
    elif current_rate > 0:
        score += 5
        reasons.append(f"전세가율 {current_rate:.1f}% 보통")
    
    # 전세가율 상승 추세
    if prev_rate > 0 and current_rate > prev_rate:
        score += 5
        reasons.append("전세가율 상승 중 → 매수 압력 증가")
    
    # 신호 결정
    if score >= 65:
        signal = "BUY"
    elif score >= 45:
        signal = "HOLD"
    else:
        signal = "SELL"
    
    return {
        'region': region,
        'signal': signal,
        'score': score,
        'reasons': reasons,
        'details': details,
        'last_trade': last_trade
    }


def get_timing_summary(regions=None):
    """여러 지역 신호 요약"""
    if not regions:
        conn = get_conn()
        regions_df = pd.read_sql_query(
            "SELECT DISTINCT region FROM apt_trade ORDER BY region", conn
        )
        conn.close()
        regions = regions_df['region'].tolist()[:30]  # top 30
    
    results = []
    for r in regions:
        results.append(get_timing_signal(r))
    return pd.DataFrame(results).sort_values('score', ascending=False)
