"""
백테스팅 엔진 — RecommendationEngine 기반 매매 시뮬레이션

월별 리밸런싱 전략:
• 매수 신호 (종합점수 65↑) → 해당 단지 매수
• 매도 신호 (종합점수 40↓) → 해당 단지 매도
• 부족한 현금 or 이미 보유 중이면 매수 스킵
"""
import pandas as pd
from datetime import datetime, timedelta
from data.database import get_conn
from strategy.recommender import RecommendationEngine
from strategy.portfolio import Portfolio


def _get_monthly_prices(region, start_date, end_date):
    """
    DB에서 지역 내 모든 단지의 월별 평균 매매가 조회

    Returns
    -------
    pd.DataFrame
        columns: apt_name, year_month, avg_price, trade_count
    """
    conn = get_conn()
    q = """
        SELECT
            apt_name,
            strftime('%Y-%m', deal_date) AS year_month,
            ROUND(AVG(price), 0) AS avg_price,
            COUNT(*) AS trade_count
        FROM apt_trade
        WHERE region LIKE ?
          AND deal_date >= ?
          AND deal_date <= ?
        GROUP BY apt_name, year_month
        ORDER BY apt_name, year_month
    """
    df = pd.read_sql_query(q, conn, params=[f'%{region}%', start_date, end_date])
    conn.close()

    if df.empty:
        return df

    df['avg_price'] = df['avg_price'].astype(int)
    df['trade_count'] = df['trade_count'].astype(int)
    return df


def _generate_month_list(start_date, end_date):
    """YYYY-MM 문자열 목록 생성"""
    start = datetime.strptime(start_date, '%Y-%m-%d')
    end = datetime.strptime(end_date, '%Y-%m-%d')
    months = []
    cursor = start.replace(day=1)
    while cursor <= end:
        months.append(cursor.strftime('%Y-%m'))
        # 다음 달 1일
        if cursor.month == 12:
            cursor = cursor.replace(year=cursor.year + 1, month=1)
        else:
            cursor = cursor.replace(month=cursor.month + 1)
    return months


def _find_price_for_month(price_df, apt_name, year_month):
    """
    특정 단지·월의 평균 가격 조회.
    데이터가 없으면 인접 월 보간.
    """
    row = price_df[(price_df['apt_name'] == apt_name) &
                   (price_df['year_month'] == year_month)]
    if not row.empty:
        return int(row['avg_price'].iloc[0])

    # 인접 월에서 가장 가까운 가격 찾기
    sub = price_df[price_df['apt_name'] == apt_name].copy()
    if sub.empty:
        return None
    # year_month를 datetime으로 변환
    sub['ym_dt'] = pd.to_datetime(sub['year_month'] + '-01')
    target = pd.Timestamp(year_month + '-01')
    sub['diff'] = (sub['ym_dt'] - target).abs()
    nearest = sub.loc[sub['diff'].idxmin()]
    return int(nearest['avg_price'])


def backtest_strategy(region, start_date='2020-01-01', end_date='2025-05-31',
                      budget_ok=5, buy_threshold=65, sell_threshold=40,
                      max_holdings=5, verbose=False):
    """
    RecommendationEngine.score_apt() 기반 백테스팅

    Parameters
    ----------
    region : str
        지역명 (예: '서울특별시 강남구')
    start_date : str
        시작일 (YYYY-MM-DD)
    end_date : str
        종료일 (YYYY-MM-DD)
    budget_ok : int
        초기 예산 (억원)
    buy_threshold : int
        매수 임계 점수 (기본 65)
    sell_threshold : int
        매도 임계 점수 (기본 40)
    max_holdings : int
        최대 동시 보유 단지 수
    verbose : bool
        상세 로그 출력 여부

    Returns
    -------
    dict
        백테스트 결과 리포트
    """
    # 1. 엔진 초기화 및 단지 스코어링
    engine = RecommendationEngine()

    # 분석 가능한 단지 목록 (최소 5건 이상)
    all_apts = engine.list_apts(region, min_trades=5)
    if not all_apts:
        engine.close()
        return {
            'status': 'error',
            'message': f"'{region}'에 분석 가능한 단지가 없습니다 (최소 5건 이상 거래 필요)",
        }

    if verbose:
        print(f"📋 분석 대상 단지: {len(all_apts)}개")

    # 각 단지별 종합 점수 계산
    apt_scores = {}
    for apt in all_apts:
        try:
            result = engine.score_apt(apt, region)
            apt_scores[apt] = result['total_score']
        except Exception:
            continue

    engine.close()

    if not apt_scores:
        return {
            'status': 'error',
            'message': f"'{region}' 단지 점수 계산 실패",
        }

    if verbose:
        print(f"✅ 점수 계산 완료: {len(apt_scores)}개 단지")

    # 2. 월별 가격 데이터 로드
    price_df = _get_monthly_prices(region, start_date, end_date)
    if price_df.empty:
        return {
            'status': 'error',
            'message': f"'{region}'에 {start_date}~{end_date} 기간 거래 데이터가 없습니다",
        }

    # 3. 포트폴리오 초기화
    portfolio = Portfolio(budget=budget_ok)
    months = _generate_month_list(start_date, end_date)

    if verbose:
        print(f"📅 백테스트 기간: {start_date} ~ {end_date} ({len(months)}개월)")
        print(f"💰 초기 예산: {budget_ok}억원")
        print(f"🎯 매수 기준: {buy_threshold}↑  |  매도 기준: {sell_threshold}↓")

    # 4. 월별 리밸런싱 시뮬레이션
    monthly_values = []

    for month_idx, ym in enumerate(months):
        # 해당 월의 첫 거래일 (price 조회용)
        current_ym_date = ym + '-01'

        # === 매도 단계: 보유 단지 중 점수가 sell_threshold 미만이면 매도 ===
        to_sell = []
        for h in portfolio.holdings:
            score = apt_scores.get(h.apt_name, 50)
            if score < sell_threshold:
                to_sell.append(h.apt_name)

        for apt_name in to_sell:
            price = _find_price_for_month(price_df, apt_name, ym)
            if price is not None and price > 0:
                success = portfolio.sell(apt_name, price, current_ym_date)
                if success and verbose:
                    score = apt_scores.get(apt_name, 0)
                    print(f"  [{ym}] 🔴 매도 {apt_name} (score={score}, price={price/10000:.1f}억)")

        # === 매수 단계: 점수가 buy_threshold 이상인 단지 매수 ===
        if len(portfolio.holdings) < max_holdings:
            # 매수 후보: 점수 높은 순, 이미 보유 중이 아닌 것
            candidates = [
                (apt, score) for apt, score in apt_scores.items()
                if score >= buy_threshold
                and not any(h.apt_name == apt for h in portfolio.holdings)
            ]
            candidates.sort(key=lambda x: x[1], reverse=True)

            for apt_name, score in candidates:
                if len(portfolio.holdings) >= max_holdings:
                    break
                price = _find_price_for_month(price_df, apt_name, ym)
                if price is None or price <= 0:
                    continue
                # 예산 내에서 매수 가능?
                if portfolio.cash < price:
                    continue
                success = portfolio.buy(apt_name, region, price, current_ym_date)
                if success and verbose:
                    print(f"  [{ym}] 🟢 매수 {apt_name} (score={score}, price={price/10000:.1f}억)")

        # === 월별 포트폴리오 가치 기록 ===
        # 현재 월의 가격 맵
        price_map = {}
        for h in portfolio.holdings:
            p = _find_price_for_month(price_df, h.apt_name, ym)
            if p is not None:
                price_map[h.apt_name] = p

        tv = portfolio.total_value(price_map)
        monthly_values.append({
            'month': ym,
            'total_value_ok': round(tv / 10000, 2),
            'cash_ok': round(portfolio.cash / 10000, 2),
            'holdings_count': len(portfolio.holdings),
        })

    # 5. 최종 평가
    # 마지막 월의 가격으로 평가
    final_ym = months[-1]
    final_price_map = {}
    for h in portfolio.holdings:
        p = _find_price_for_month(price_df, h.apt_name, final_ym)
        if p is not None:
            final_price_map[h.apt_name] = p

    final_value = portfolio.total_value(final_price_map)
    total_return = portfolio.total_return_pct(final_price_map)

    # 연환산 수익률 (CAGR)
    start_dt = datetime.strptime(start_date, '%Y-%m-%d')
    end_dt = datetime.strptime(end_date, '%Y-%m-%d')
    years = (end_dt - start_dt).days / 365.25
    if years > 0 and portfolio.initial_budget > 0:
        cagr = ((final_value / portfolio.initial_budget) ** (1 / years) - 1) * 100
    else:
        cagr = 0.0

    # MDD 계산 (최대 낙폭)
    values = [m['total_value_ok'] * 10000 for m in monthly_values]
    peak = values[0] if values else 0
    max_drawdown = 0.0
    for v in values:
        if v > peak:
            peak = v
        dd = (peak - v) / peak * 100 if peak > 0 else 0
        if dd > max_drawdown:
            max_drawdown = dd

    # 승률
    wins = sum(1 for t in portfolio.trade_log if t['type'] == 'SELL' and t.get('profit_pct', 0) > 0)
    sells = sum(1 for t in portfolio.trade_log if t['type'] == 'SELL')
    win_rate = wins / sells * 100 if sells > 0 else 0.0

    result = {
        'status': 'success',
        'region': region,
        'start_date': start_date,
        'end_date': end_date,
        'period_years': round(years, 2),
        'budget_ok': budget_ok,
        'buy_threshold': buy_threshold,
        'sell_threshold': sell_threshold,
        # 성과 지표
        'initial_value_ok': budget_ok,
        'final_value_ok': round(final_value / 10000, 2),
        'total_return_pct': round(total_return, 2),
        'cagr_pct': round(cagr, 2),
        'max_drawdown_pct': round(max_drawdown, 2),
        'win_rate_pct': round(win_rate, 2),
        # 거래 통계
        'total_buys': sum(1 for t in portfolio.trade_log if t['type'] == 'BUY'),
        'total_sells': sum(1 for t in portfolio.trade_log if t['type'] == 'SELL'),
        'num_holdings': len(portfolio.holdings),
        'final_cash_ok': round(portfolio.cash / 10000, 2),
        # 상세 데이터
        'monthly_values': monthly_values,
        'trade_log': portfolio.trade_log,
        'holdings': [{
            'apt_name': h.apt_name,
            'region': h.region,
            'buy_price_ok': round(h.buy_price / 10000, 2),
            'buy_date': h.buy_date,
        } for h in portfolio.holdings],
    }

    return result


def print_backtest_result(result):
    """백테스트 결과 CLI 출력"""
    if result.get('status') == 'error':
        print(f"\n❌ {result['message']}")
        return

    print(f"\n{'='*55}")
    print(f"  📊 백테스트 결과: {result['region']}")
    print(f"{'='*55}")
    print(f"  기간:          {result['start_date']} ~ {result['end_date']} ({result['period_years']}년)")
    print(f"  초기 예산:     {result['initial_value_ok']}억원")
    print(f"  최종 가치:     {result['final_value_ok']}억원")
    print(f"  총 수익률:     {result['total_return_pct']:+.2f}%")
    print(f"  CAGR:          {result['cagr_pct']:+.2f}%")
    print(f"  MDD:           {result['max_drawdown_pct']:.2f}%")
    print(f"  승률:          {result['win_rate_pct']:.1f}%")
    print(f"  매수:          {result['total_buys']}회")
    print(f"  매도:          {result['total_sells']}회")
    print(f"  보유 단지:     {result['num_holdings']}개")
    print(f"  잔여 현금:     {result['final_cash_ok']}억원")

    # 보유 단지 상세
    if result['holdings']:
        print(f"\n  ── 보유 단지 ──")
        for h in result['holdings']:
            print(f"  {h['apt_name']:12s} | 매수 {h['buy_price_ok']:.1f}억 ({h['buy_date']})")

    # 연도별 추이
    mv = result.get('monthly_values', [])
    if mv:
        print(f"\n  ── 분기별 포트폴리오 가치 추이 ──")
        for m in mv[::3]:  # 3개월 간격
            bar_len = int(m['total_value_ok'] / 1)
            bar = '█' * min(bar_len, 40)
            print(f"  {m['month']} | {m['total_value_ok']:>5.1f}억 {bar}")

    print(f"{'='*55}")

    return result


def compare_backtests(results):
    """여러 백테스트 결과 비교"""
    if not results:
        return

    print(f"\n{'='*65}")
    print(f"  📊 백테스트 비교")
    print(f"{'='*65}")
    print(f"  {'지역':20s} {'초기':>6s} {'최종':>6s} {'수익률':>8s} {'CAGR':>7s} {'MDD':>7s} {'승률':>6s}")
    print(f"  {'─'*20} {'─'*6} {'─'*6} {'─'*8} {'─'*7} {'─'*7} {'─'*6}")
    for r in results:
        if r.get('status') != 'success':
            continue
        print(f"  {r['region']:20s} {r['initial_value_ok']:>5.0f}억 "
              f"{r['final_value_ok']:>5.1f}억 "
              f"{r['total_return_pct']:>+7.2f}% "
              f"{r['cagr_pct']:>+6.2f}% "
              f"{r['max_drawdown_pct']:>6.2f}% "
              f"{r['win_rate_pct']:>5.1f}%")
    print(f"{'='*65}")
