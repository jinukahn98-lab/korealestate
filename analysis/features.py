"""ML 학습 특성 벡터 — 단지별 시계열/전세/거래 특성"""
import numpy as np
import pandas as pd


def build_features(apt_name, region, conn):
    """단지별 ML 학습 특성 벡터를 생성한다.

    Parameters
    ----------
    apt_name : str
        아파트 단지명
    region : str
        지역명 (LIKE 검색에 사용)
    conn : sqlite3.Connection
        DB 연결 객체

    Returns
    -------
    dict
        특성 벡터. 데이터 부족 시 빈 dict 반환.
    """
    # ----------------------------------------------------------------
    # 1. 가격 특성 (매매 18개월)
    # ----------------------------------------------------------------
    trade_df = pd.read_sql_query(
        """
        SELECT deal_date, price, area
        FROM apt_trade
        WHERE apt_name = ? AND region LIKE ?
          AND deal_date >= date('now', '-18 months')
        ORDER BY deal_date ASC
        """,
        conn,
        params=[apt_name, f'%{region}%'],
    )

    if trade_df.empty:
        return {}

    trade_df['deal_date'] = pd.to_datetime(trade_df['deal_date'])
    now = pd.Timestamp.now()

    # 최근 거래일
    last_trade_date = trade_df['deal_date'].max()
    days_since_last_trade = (now - last_trade_date).days

    # 최근 3개월 평균가
    cutoff_3m = now - pd.DateOffset(months=3)
    recent_3m = trade_df[trade_df['deal_date'] >= cutoff_3m]
    price_3m_avg = float(recent_3m['price'].mean()) if not recent_3m.empty else float(trade_df['price'].iloc[-1])

    # 최근 6개월 추세 (선형회귀 기울기 → 월별 변화량)
    cutoff_6m = now - pd.DateOffset(months=6)
    df_6m = trade_df[trade_df['deal_date'] >= cutoff_6m].copy()
    if len(df_6m) >= 3:
        df_6m['day_num'] = (df_6m['deal_date'] - df_6m['deal_date'].min()).dt.days
        xs = df_6m['day_num'].values.reshape(-1, 1)
        ys = df_6m['price'].values
        from sklearn.linear_model import LinearRegression
        trend_model = LinearRegression()
        trend_model.fit(xs, ys)
        price_6m_trend = float(trend_model.coef_[0]) * 30  # 일별 → 월별 변화량
    else:
        price_6m_trend = 0.0

    # 변동성 (최근 6개월 price CV)
    price_volatility = float(df_6m['price'].std() / df_6m['price'].mean()) if len(df_6m) >= 3 and df_6m['price'].mean() > 0 else 0.0

    last_price = float(trade_df['price'].iloc[-1])

    # ----------------------------------------------------------------
    # 2. 전세 특성
    # ----------------------------------------------------------------
    rent_df = pd.read_sql_query(
        """
        SELECT deal_date, deposit
        FROM apt_rent
        WHERE apt_name = ? AND region LIKE ?
          AND deal_date >= date('now', '-18 months')
        ORDER BY deal_date ASC
        """,
        conn,
        params=[apt_name, f'%{region}%'],
    )

    if not rent_df.empty and not trade_df.empty:
        rent_df['deal_date'] = pd.to_datetime(rent_df['deal_date'])

        # 전세가율 = 평균 전세보증금 / 평균 매매가 (동기간)
        avg_jeonse_deposit = float(rent_df['deposit'].mean())
        avg_trade_price = float(trade_df['price'].mean())
        jeonse_rate = round(avg_jeonse_deposit / avg_trade_price * 100, 1) if avg_trade_price > 0 else 0.0

        # 전세가율 3개월 변화
        cutoff_3m_rent = now - pd.DateOffset(months=3)
        recent_rent_3m = rent_df[rent_df['deal_date'] >= cutoff_3m_rent]
        recent_trade_3m = trade_df[trade_df['deal_date'] >= cutoff_3m_rent]

        if not recent_rent_3m.empty and not recent_trade_3m.empty:
            recent_jeonse = float(recent_rent_3m['deposit'].mean())
            recent_trade = float(recent_trade_3m['price'].mean())
            recent_rate = round(recent_jeonse / recent_trade * 100, 1) if recent_trade > 0 else 0.0
        else:
            recent_rate = jeonse_rate

        # 전세가율 6개월 추세
        cutoff_6m_rent = now - pd.DateOffset(months=6)
        df_rent_6m = rent_df[rent_df['deal_date'] >= cutoff_6m_rent].copy()
        df_trade_6m_rent = trade_df[trade_df['deal_date'] >= cutoff_6m_rent].copy()

        if len(df_rent_6m) >= 3 and len(df_trade_6m_rent) >= 3:
            df_rent_6m['month'] = df_rent_6m['deal_date'].dt.to_period('M')
            monthly_rent = df_rent_6m.groupby('month')['deposit'].mean().reset_index()
            monthly_rent['month_num'] = range(len(monthly_rent))

            df_trade_6m_rent['month'] = df_trade_6m_rent['deal_date'].dt.to_period('M')
            monthly_trade = df_trade_6m_rent.groupby('month')['price'].mean().reset_index()
            monthly_trade['month_num'] = range(len(monthly_trade))

            merged = pd.merge(monthly_rent, monthly_trade, on='month', suffixes=('_rent', '_trade'))
            if len(merged) >= 3:
                merged['rate'] = merged['deposit'] / merged['price'] * 100
                xs = merged['month_num'].values.reshape(-1, 1)
                ys = merged['rate'].values
                from sklearn.linear_model import LinearRegression
                rate_model = LinearRegression()
                rate_model.fit(xs, ys)
                jeonse_rate_6m_trend = float(rate_model.coef_[0])  # 월별 변화량 (%p)
            else:
                jeonse_rate_6m_trend = 0.0
        else:
            jeonse_rate_6m_trend = 0.0

        jeonse_rate_3m_change = round(recent_rate - jeonse_rate, 1)
    else:
        jeonse_rate = 0.0
        jeonse_rate_3m_change = 0.0
        jeonse_rate_6m_trend = 0.0

    # ----------------------------------------------------------------
    # 3. 거래 특성
    # ----------------------------------------------------------------
    # 최근 3개월 거래량
    trade_volume_3m = len(recent_3m)

    # 거래량 모멘텀 (최근 3개월 / 그 이전 3개월)
    cutoff_6m_vol = now - pd.DateOffset(months=6)
    prev_3m = trade_df[(trade_df['deal_date'] >= cutoff_6m_vol) & (trade_df['deal_date'] < cutoff_3m)]
    prev_volume = len(prev_3m)
    trade_volume_momentum = round(trade_volume_3m / prev_volume, 2) if prev_volume > 0 else 1.0

    # 평균 거래면적
    avg_trade_size = float(recent_3m['area'].mean()) if not recent_3m.empty else float(trade_df['area'].mean())

    # ----------------------------------------------------------------
    # 4. 계절성 (현재 월 기준)
    # ----------------------------------------------------------------
    current_month = now.month
    month_sin = float(np.sin(2 * np.pi * current_month / 12))
    month_cos = float(np.cos(2 * np.pi * current_month / 12))

    return {
        # 가격 특성
        'price_3m_avg': int(round(price_3m_avg)),
        'price_6m_trend': round(price_6m_trend, 0),
        'price_volatility': round(price_volatility, 4),
        'last_price': int(round(last_price)),
        'days_since_last_trade': days_since_last_trade,
        # 전세 특성
        'jeonse_rate': jeonse_rate,
        'jeonse_rate_3m_change': jeonse_rate_3m_change,
        'jeonse_rate_6m_trend': round(jeonse_rate_6m_trend, 2),
        # 거래 특성
        'trade_volume_3m': trade_volume_3m,
        'trade_volume_momentum': trade_volume_momentum,
        'avg_trade_size': round(avg_trade_size, 1),
        # 계절성
        'month_sin': month_sin,
        'month_cos': month_cos,
    }
