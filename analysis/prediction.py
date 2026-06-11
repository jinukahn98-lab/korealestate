"""가격 예측 모듈 — 선형 회귀 기반 3개월 가격 예측"""
import pandas as pd
import numpy as np
from sklearn.linear_model import LinearRegression
from data.database import get_conn


def predict_region_price(region, months_ahead=3):
    """지역별 평균 매매가 3개월 예측"""
    conn = get_conn()
    
    query = """
    SELECT strftime('%Y-%m', deal_date) as month,
           ROUND(AVG(price), 0) as avg_price,
           COUNT(*) as trade_count
    FROM apt_trade
    WHERE region LIKE ? AND deal_date >= date('now', '-24 months')
    GROUP BY month
    ORDER BY month
    """
    df = pd.read_sql_query(query, conn, params=[f'%{region}%'])
    conn.close()
    
    if len(df) < 6:
        return {'region': region, 'error': '데이터 부족 (6개월 이상 필요)'}
    
    # 특성 생성
    df['month_num'] = range(len(df))
    df['month_sin'] = np.sin(2 * np.pi * df['month_num'] / 12)
    df['month_cos'] = np.cos(2 * np.pi * df['month_num'] / 12)
    df['lag_1'] = df['avg_price'].shift(1).bfill()
    df['lag_3'] = df['avg_price'].shift(3).bfill()
    df['volume_norm'] = df['trade_count'] / df['trade_count'].max()
    
    # 학습
    features = ['month_num', 'month_sin', 'month_cos', 'lag_1', 'lag_3', 'volume_norm']
    X = df[features].values
    y = df['avg_price'].values
    
    model = LinearRegression()
    model.fit(X, y)
    
    # 예측
    last = df.iloc[-1]
    predictions = []
    current_month_num = last['month_num']
    
    for i in range(1, months_ahead + 1):
        next_num = current_month_num + i
        next_sin = np.sin(2 * np.pi * next_num / 12)
        next_cos = np.cos(2 * np.pi * next_num / 12)
        next_lag1 = predictions[-1] if predictions else last['avg_price']
        next_lag3 = predictions[-3] if len(predictions) >= 3 else (predictions[0] if predictions else last['avg_price'])
        
        x_pred = np.array([[next_num, next_sin, next_cos, next_lag1, next_lag3, 0.5]])
        pred_price = model.predict(x_pred)[0]
        predictions.append(pred_price)
    
    # 평가
    y_pred = model.predict(X)
    mape = float(np.mean(np.abs((y - y_pred) / y)) * 100)
    
    latest_price = float(last['avg_price'])
    
    # 결과 정리
    pred_months = []
    for i, p in enumerate(predictions):
        month_offset = i + 1
        target_month = pd.Timestamp.now() + pd.DateOffset(months=month_offset)
        pred_months.append({
            'pred_month': target_month.strftime('%Y-%m'),
            'pred_price': int(p),
            'outlook': 'up' if p > latest_price else ('down' if p < latest_price else 'flat')
        })
    
    trend = 'up' if predictions[-1] > latest_price else ('down' if predictions[-1] < latest_price else 'flat')
    
    return {
        'region': region,
        'latest_price': int(latest_price),
        'predicted_price': int(predictions[-1]),
        f'predicted_{months_ahead}m_change_pct': round((predictions[-1] - latest_price) / latest_price * 100, 1),
        'trend': trend,
        'mape_pct': round(mape, 1),
        'predictions': pred_months,
        'accuracy_note': f'MAPE {mape:.1f}% (lower is better)',
        'data_months': len(df)
    }


def predict_apt_price(apt_name, region, months_ahead=3):
    """특정 단지 가격 예측"""
    conn = get_conn()
    
    query = """
    SELECT strftime('%Y-%m', deal_date) as month,
           ROUND(AVG(price), 0) as avg_price,
           ROUND(AVG(area), 1) as avg_area,
           COUNT(*) as cnt
    FROM apt_trade
    WHERE apt_name = ? AND region LIKE ? AND deal_date >= date('now', '-18 months')
    GROUP BY month ORDER BY month
    """
    df = pd.read_sql_query(query, conn, params=[apt_name, f'%{region}%'])
    conn.close()
    
    if len(df) < 4:
        return {'apt_name': apt_name, 'error': '데이터 부족'}
    
    df['month_num'] = range(len(df))
    X = df[['month_num']].values
    y = df['avg_price'].values
    
    model = LinearRegression()
    model.fit(X, y)
    
    last_price = float(df['avg_price'].iloc[-1])
    last_num = float(df['month_num'].iloc[-1])
    pred_price = float(model.predict([[last_num + months_ahead]])[0])
    
    return {
        'apt_name': apt_name,
        'region': region,
        'current_price': int(last_price),
        f'predicted_{months_ahead}m_price': int(pred_price),
        f'change_{months_ahead}m_pct': round((pred_price - last_price) / last_price * 100, 1)
    }
