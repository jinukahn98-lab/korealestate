"""가격 예측 모듈 — 선형 회귀 + XGBoost 기반 가격 예측"""
import pandas as pd
import numpy as np
from sklearn.linear_model import LinearRegression
from sklearn.model_selection import TimeSeriesSplit
from sklearn.metrics import mean_absolute_percentage_error
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


def predict_apt_price_xgb(apt_name, region, months_ahead=3, min_samples=10):
    """XGBoost 기반 단지별 가격 예측 (TimeSeriesSplit CV).

    단지당 거래 데이터가 min_samples(기본 10)건 이상일 때 XGBoost 사용,
    부족할 경우 기존 LinearRegression으로 fallback.

    Parameters
    ----------
    apt_name : str
        아파트 단지명
    region : str
        지역명 (LIKE 검색)
    months_ahead : int
        예측할 개월 수 (기본 3)
    min_samples : int
        XGBoost 사용 최소 샘플 수 (기본 10)

    Returns
    -------
    dict
        예측 결과 또는 fallback 결과
    """
    conn = get_conn()

    query = """
    SELECT strftime('%Y-%m', deal_date) as month,
           ROUND(AVG(price), 0) as avg_price,
           ROUND(AVG(area), 1) as avg_area,
           COUNT(*) as cnt
    FROM apt_trade
    WHERE apt_name = ? AND region LIKE ?
      AND deal_date >= date('now', '-24 months')
    GROUP BY month ORDER BY month
    """
    df = pd.read_sql_query(query, conn, params=[apt_name, f'%{region}%'])
    conn.close()

    if len(df) < 4:
        return {'apt_name': apt_name, 'region': region, 'error': '데이터 부족 (4개월 이상 필요)'}

    # --- 특성 생성 ---
    df['month_num'] = range(len(df))
    df['month_sin'] = np.sin(2 * np.pi * df['month_num'] / 12)
    df['month_cos'] = np.cos(2 * np.pi * df['month_num'] / 12)
    df['lag_1'] = df['avg_price'].shift(1).bfill()
    df['lag_3'] = df['avg_price'].shift(3).bfill()
    df['volume_norm'] = df['cnt'] / df['cnt'].max()

    features = ['month_num', 'month_sin', 'month_cos', 'lag_1', 'lag_3', 'volume_norm']
    X = df[features].values
    y = df['avg_price'].values

    latest_price = float(df['avg_price'].iloc[-1])

    # --- XGBoost (10건↑) vs LinearRegression fallback ---
    if len(df) >= min_samples:
        try:
            import xgboost as xgb

            # TimeSeriesSplit CV
            tscv = TimeSeriesSplit(n_splits=min(5, len(df) // 2))
            cv_models = []
            cv_scores = []

            for train_idx, val_idx in tscv.split(X):
                X_train, X_val = X[train_idx], X[val_idx]
                y_train, y_val = y[train_idx], y[val_idx]

                model = xgb.XGBRegressor(
                    n_estimators=200,
                    max_depth=4,
                    learning_rate=0.08,
                    subsample=0.8,
                    colsample_bytree=0.8,
                    random_state=42,
                    verbosity=0,
                )
                model.fit(X_train, y_train, eval_set=[(X_val, y_val)], verbose=False)
                y_pred_val = model.predict(X_val)
                mape = float(mean_absolute_percentage_error(y_val, y_pred_val)) * 100
                cv_models.append(model)
                cv_scores.append(mape)

            # 최고 성능 모델 선택 (가장 낮은 MAPE)
            best_idx = int(np.argmin(cv_scores))
            best_model = cv_models[best_idx]
            avg_cv_mape = float(np.mean(cv_scores))

            # 예측 (iterative)
            last = df.iloc[-1]
            predictions = []
            current_month_num = last['month_num']

            for i in range(1, months_ahead + 1):
                next_num = current_month_num + i
                next_sin = np.sin(2 * np.pi * next_num / 12)
                next_cos = np.cos(2 * np.pi * next_num / 12)
                next_lag1 = predictions[-1] if predictions else last['avg_price']
                next_lag3 = predictions[-3] if len(predictions) >= 3 else (
                    predictions[0] if predictions else last['avg_price']
                )
                x_pred = np.array([[next_num, next_sin, next_cos, next_lag1, next_lag3, 0.5]])
                pred_price = float(best_model.predict(x_pred)[0])
                predictions.append(pred_price)

            model_used = 'XGBoost'
            cv_note = f'TimeSeriesSplit CV avg MAPE {avg_cv_mape:.1f}%'

        except ImportError:
            # xgboost 미설치 시 fallback
            model = LinearRegression()
            model.fit(X, y)
            predictions = _iterative_predict(model, df, months_ahead)
            model_used = 'LinearRegression (xgboost 미설치)'
            cv_note = 'xgboost 미설치로 LR 사용'
    else:
        # 데이터 부족 → LinearRegression
        model = LinearRegression()
        model.fit(X, y)
        predictions = _iterative_predict(model, df, months_ahead)
        model_used = 'LinearRegression (데이터 부족)'
        cv_note = f'샘플 {len(df)}건으로 LR 사용 (XGBoost 필요 {min_samples}건)'

    # --- 평가 (in-sample MAPE) ---
    y_pred_all = model.predict(X) if 'model' in dir() else best_model.predict(X)
    in_sample_mape = float(mean_absolute_percentage_error(y, y_pred_all)) * 100

    # --- 결과 정리 ---
    pred_months = []
    for i, p in enumerate(predictions):
        target_month = pd.Timestamp.now() + pd.DateOffset(months=i + 1)
        pred_months.append({
            'pred_month': target_month.strftime('%Y-%m'),
            'pred_price': int(p),
            'outlook': 'up' if p > latest_price else ('down' if p < latest_price else 'flat'),
        })

    trend = 'up' if predictions[-1] > latest_price else (
        'down' if predictions[-1] < latest_price else 'flat'
    )

    return {
        'apt_name': apt_name,
        'region': region,
        'current_price': int(latest_price),
        'predicted_price': int(predictions[-1]),
        f'predicted_{months_ahead}m_change_pct': round(
            (predictions[-1] - latest_price) / latest_price * 100, 1
        ),
        'trend': trend,
        'predictions': pred_months,
        'model_used': model_used,
        'cv_note': cv_note,
        'in_sample_mape_pct': round(in_sample_mape, 1),
        'data_months': len(df),
    }


def _iterative_predict(model, df, months_ahead):
    """iterative prediction helper for LinearRegression models."""
    last = df.iloc[-1]
    predictions = []
    current_month_num = last['month_num']

    for i in range(1, months_ahead + 1):
        next_num = current_month_num + i
        next_sin = np.sin(2 * np.pi * next_num / 12)
        next_cos = np.cos(2 * np.pi * next_num / 12)
        next_lag1 = predictions[-1] if predictions else last['avg_price']
        next_lag3 = predictions[-3] if len(predictions) >= 3 else (
            predictions[0] if predictions else last['avg_price']
        )
        x_pred = np.array([[next_num, next_sin, next_cos, next_lag1, next_lag3, 0.5]])
        pred_price = float(model.predict(x_pred)[0])
        predictions.append(pred_price)

    return predictions
