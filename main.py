#!/usr/bin/env python3
"""
🏠 한국 부동산 전략 시스템 (Korean Real Estate Strategy System)

사용법:
  python main.py <명령어> [옵션]

명령어:
  수집 (collect)    - 부동산 데이터 수집
  분석 (analyze)    - 데이터 분석
  전략 (strategy)   - 투자 전략
  리포트 (report)   - 리포트 생성
  지역 (region)     - 지역 정보
  초기화 (init)     - DB 초기화
"""

import sys
import os
import argparse
from datetime import datetime

# 프로젝트 루트를 sys.path에 추가
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from data.database import init_db, get_db_stats, save_apt_trades, save_apt_rents, save_zigbang_items
from data.legal_dong_codes import (
    search_region, get_region_name, get_all_regions,
    get_cities, get_districts, find_code_by_name, save_to_db
)
from collectors.molit import fetch_trades, fetch_rents, collect_recent_months
from collectors.zigbang import collect_zigbang_items, search_by_dong
from analysis.statistics import (
    get_region_trade_summary, get_apt_detail, get_jeonse_rate_analysis,
    get_monthly_trend, get_area_distribution, get_hot_areas,
    get_gap_analysis, print_summary,
    get_pyoung_price, get_floor_premium, get_seasonal_pattern,
    get_trade_gap_alert, get_quantile_picks, get_jeonse_momentum,
)
from analysis.indicators import (
    get_yield_analysis, get_price_volatility,
    get_reverse_jeonse_risk, get_investment_summary
)
from strategy.buy import analyze_fair_price, search_by_condition, get_buy_strategy, compare_regions
from strategy.jeonse import analyze_jeonse, get_jeonse_strategy, detect_reverse_jeonse_risk
from report.report import generate_weekly_report, generate_monthly_report, generate_summary_report
from utils.config import check_api_key, get_molit_api_key


def cmd_init(args):
    """데이터베이스 초기화"""
    init_db()
    save_to_db()
    print("✅ 초기화 완료! 데이터 수집을 시작하세요.")


def cmd_collect(args):
    """데이터 수집"""
    if args.type == 'molit' or args.type == '실거래':
        _collect_molit(args)
    elif args.type == 'zigbang' or args.type == '직방':
        _collect_zigbang(args)
    else:
        print(f"❌ 알 수 없는 수집 타입: {args.type}")
        print("   가능: molit(실거래), zigbang(직방)")


def _collect_molit(args):
    """MOLIT 실거래가 수집"""
    if not check_api_key():
        return

    # 지역코드 찾기
    lawd_cd = args.code
    region_name = args.region or get_region_name(lawd_cd)

    if not lawd_cd or lawd_cd == '11680':
        if args.region:
            lawd_cd = find_code_by_name(args.region)
            if not lawd_cd:
                print(f"❌ '{args.region}' 코드를 찾을 수 없습니다.")
                return
        else:
            lawd_cd = '11680'  # 기본: 강남구
            region_name = '강남구'

    region_name = get_region_name(lawd_cd)
    print(f"\n🏢 {region_name} 아파트 {'매매' if args.data_type != 'rent' else '전월세'} 데이터 수집")

    if args.data_type == 'rent' or args.data_type == '전월세':
        if args.months:
            df = collect_recent_months(lawd_cd, args.months, 'rent')
        else:
            ym = f"{args.year}{args.month:02d}"
            df = fetch_rents(lawd_cd, ym)
        if df is not None:
            saved = save_apt_rents(df, lawd_cd, region_name)
            print(f"  💾 {saved}건 DB 저장 완료")
    else:
        if args.months:
            df = collect_recent_months(lawd_cd, args.months, 'trade')
        else:
            ym = f"{args.year}{args.month:02d}"
            df = fetch_trades(lawd_cd, ym)
        if df is not None:
            saved = save_apt_trades(df, lawd_cd, region_name)
            print(f"  💾 {saved}건 DB 저장 완료")


def _collect_zigbang(args):
    """직방 매물 수집"""
    if args.dong:
        items = search_by_dong(args.dong)
    else:
        lat = args.lat or 37.497
        lng = args.lng or 127.027
        items = collect_zigbang_items(lat, lng)

    if items:
        saved = save_zigbang_items(items, args.dong or '')
        print(f"\n  💾 {saved}개 DB 저장 완료")

        # 타입별 요약
        from collections import Counter
        types = Counter(item['sales_type'] for item in items)
        for t, c in types.items():
            print(f"     - {t}: {c}개")


def cmd_analyze(args):
    """데이터 분석"""
    region = args.region

    if args.type == 'stats' or args.type == '통계':
        df = get_region_trade_summary(region, args.months)
        print_summary(df, f"📊 {region or '전체'} 매매 통계")

        # 추이
        if args.trend:
            trend = get_monthly_trend(region)
            print_summary(trend, "월별 추이")

    elif args.type == 'jeonse' or args.type == '전세':
        df = get_jeonse_rate_analysis(region)
        print_summary(df, f"🔵 {region or '전체'} 전세가율 분석")
        if df is not None and not df.empty:
            avg = df['전세가율'].mean()
            print(f"  평균 전세가율: {avg:.1f}%")

    elif args.type == 'area' or args.type == '면적':
        df = get_area_distribution(region)
        print_summary(df, f"📐 {region or '전체'} 면적별 분포")

    elif args.type == 'gap' or args.type == '갭':
        df = get_gap_analysis(region)
        print_summary(df, f"💰 {region or '전체'} 갭 분석")

    elif args.type == 'hot' or args.type == '핫플':
        df = get_hot_areas(args.months)
        print_summary(df, "🔥 거래 활발 지역")

    elif args.type == 'yield' or args.type == '수익률':
        df = get_yield_analysis(region)
        print_summary(df, f"💵 {region or '전체'} 수익률 분석")

    elif args.type == 'volatility' or args.type == '변동성':
        df = get_price_volatility(region, args.months)
        print_summary(df, f"📈 {region or '전체'} 가격 변동성")

    elif args.type == 'reverse' or args.type == '역전세':
        df = get_reverse_jeonse_risk(region)
        print_summary(df, f"🚨 {region or '전체'} 역전세 위험")

    elif args.type == 'detail' or args.type == '상세':
        if args.apt:
            df = get_apt_detail(args.apt, region)
            print_summary(df, f"🏢 {args.apt} 거래 내역")
        else:
            print("❌ --apt 옵션으로 아파트명을 입력하세요")

    elif args.type == 'pyoung' or args.type == '평당가':
        df = get_pyoung_price(region)
        print_summary(df, f"💰 {region or '전체'} 평당가 분석 (낮은 순)")

    elif args.type == 'floor' or args.type == '층수':
        df = get_floor_premium(region)
        print_summary(df, f"🏢 {region or '전체'} 층수별 가격 프리미엄")
        if df is not None and not df.empty and '고층_저층_프리미엄' in df.attrs:
            print(f"  고층/저층 프리미엄: {df.attrs['고층_저층_프리미엄']:+.1f}%")

    elif args.type == 'seasonal' or args.type == '계절':
        df = get_seasonal_pattern(region)
        print_summary(df, f"📅 {region or '전체'} 월별 계절성 분석")
        if df is not None and not df.empty:
            cheap = df.attrs.get('가장_싼_달')
            pricey = df.attrs.get('가장_비싼_달')
            peak = df.attrs.get('거래량_피크_달')
            if cheap:
                print(f"  가장 싼 달: {cheap}월 | 가장 비싼 달: {pricey}월 | 거래량 피크: {peak}월")

    elif args.type == 'gap_alert' or args.type == '공백':
        df = get_trade_gap_alert(args.months)
        print_summary(df, f"⚠️  거래 공백 단지 (최근 {args.months * 30}일 이상 거래 없음)")

    elif args.type == 'quantile' or args.type == '저평가':
        if not region:
            print("❌ --region 옵션으로 지역을 입력하세요")
        else:
            q = getattr(args, 'quantile', 0.25)
            df = get_quantile_picks(region, q)
            print_summary(df, f"📉 {region} 하위 {int(q*100)}% 저평가 단지")

    elif args.type == 'momentum' or args.type == '모멘텀':
        df = get_jeonse_momentum(region, args.months)
        print_summary(df, f"📈 {region or '전체'} 전세가율 모멘텀 (최근 {args.months}개월)")

    elif args.type == 'all' or args.type == '전체':
        print(f"\n{'='*60}")
        print(f"  📋 {region or '전체'} 종합 분석")
        print(f"{'='*60}")
        cmd_analyze(argparse.Namespace(type='stats', region=region, months=args.months, trend=True))
        cmd_analyze(argparse.Namespace(type='jeonse', region=region, months=args.months, trend=False, apt=None, quantile=0.25))
        cmd_analyze(argparse.Namespace(type='hot', region=region, months=args.months, trend=False, apt=None, quantile=0.25))

    else:
        print(f"❌ 알 수 없는 분석 타입: {args.type}")
        print("   가능: stats(통계), jeonse(전세), area(면적), gap(갭),")
        print("         hot(핫플), yield(수익률), volatility(변동성),")
        print("         reverse(역전세), detail(상세), all(전체),")
        print("         pyoung(평당가), floor(층수), seasonal(계절),")
        print("         gap_alert(공백), quantile(저평가), momentum(모멘텀)")


def cmd_strategy(args):
    """투자 전략"""
    region = args.region

    if args.type == 'buy' or args.type == '매매':
        get_buy_strategy(region, args.budget, args.area)

    elif args.type == 'fair' or args.type == '적정가':
        if args.apt:
            analyze_fair_price(args.apt, region)
        else:
            print("❌ --apt 옵션으로 아파트명을 입력하세요")

    elif args.type == 'jeonse' or args.type == '전세':
        get_jeonse_strategy(region, args.budget)

    elif args.type == 'search' or args.type == '검색':
        search_by_condition(region, args.min_price, args.max_price, args.min_area, args.max_area)

    elif args.type == 'compare' or args.type == '비교':
        if args.regions:
            compare_regions(args.regions)
        else:
            print("❌ --regions 옵션으로 비교할 지역을 입력하세요 (예: --regions 강남구 서초구 송파구)")

    else:
        print(f"❌ 알 수 없는 전략 타입: {args.type}")
        print("   가능: buy(매매), fair(적정가), jeonse(전세), search(검색), compare(비교)")


def cmd_report(args):
    """리포트 생성"""
    if args.type == 'weekly' or args.type == '주간':
        generate_weekly_report(args.region)
    elif args.type == 'monthly' or args.type == '월간':
        generate_monthly_report(args.region)
    elif args.type == 'summary' or args.type == '요약':
        generate_summary_report()
    else:
        print(f"❌ 알 수 없는 리포트 타입: {args.type}")
        print("   가능: weekly(주간), monthly(월간), summary(요약)")


def cmd_region(args):
    """지역 정보"""
    if args.search:
        results = search_region(args.search)
        print(f"\n🔍 '{args.search}' 검색 결과 ({len(results)}건):")
        for r in results:
            print(f"  {r['code']}: {r['full_name']}")
    elif args.city:
        districts = get_districts(args.city)
        print(f"\n📍 {args.city} 구/군 목록 ({len(districts)}건):")
        for d in districts:
            print(f"  {d['code']}: {d['name']}")
    elif args.code:
        name = get_region_name(args.code)
        print(f"\n  코드 {args.code}: {name}")
    else:
        cities = get_cities()
        print(f"\n📍 시/도 목록 ({len(cities)}건):")
        for c in cities:
            print(f"  - {c}")


def cmd_status(args):
    """시스템 상태"""
    stats = get_db_stats()
    total = sum(stats.values())

    print(f"\n{'='*60}")
    print(f"  🏠 한국 부동산 전략 시스템")
    print(f"{'='*60}")
    print(f"\n  💾 데이터베이스 현황")
    print(f"     파일: {os.path.join(os.path.dirname(__file__), 'realestate.db')}")
    print(f"     총 {total:,}건")
    print(f"     - 아파트 매매: {stats.get('apt_trade', 0):,}건")
    print(f"     - 아파트 전월세: {stats.get('apt_rent', 0):,}건")
    print(f"     - 직방 현재매물: {stats.get('zigbang_items', 0):,}건")

    check_api_key()
    print(f"\n  📂 프로젝트: {os.path.dirname(__file__)}")
    print(f"{'='*60}")


def cmd_alerts(args):
    """조건 알림 관리"""
    from scripts.alert_engine import register_condition, list_conditions, remove_condition, check_conditions
    if args.action == "list":
        rows = list_conditions(args.chat_id)
        if rows:
            for r in rows:
                print(f"  #{r[0]} | {r[2]} | 지역:{r[4]} | 전세가율:{r[5]}~{r[6]} | 갭:{r[7]/10000:.0f}억 | 거래:{r[8]}건")
        else:
            print("📭 등록된 조건 없음")
    elif args.action == "register":
        cid = register_condition(args.chat_id, args.type, region=args.region,
                                 min_rate=args.min_rate, max_rate=args.max_rate,
                                 max_gap=args.max_gap*10000, min_trades=args.min_trades)
        print(f"✅ 조건 등록 완료 (#{cid})")
    elif args.action == "remove":
        remove_condition(args.id)
        print(f"✅ 조건 #{args.id} 삭제 완료")
    elif args.action == "check":
        results = check_conditions()
        if results:
            for chat_id, msg in results:
                print(f"--- TO: {chat_id} ---")
                print(msg)
        else:
            print("✅ 매칭된 조건 없음")


def cmd_recommend(args):
    """매매 추천 엔진"""
    from strategy.recommender import RecommendationEngine, print_ranking, print_recommendation, rank_by_budget

    if args.action == 'rank':
        print_ranking(limit=args.limit or 20)
    elif args.action == 'region':
        if args.region:
            print_recommendation(args.region)
        else:
            print("❌ --region (-r) 옵션으로 지역을 입력하세요")
    elif args.action == 'best':
        engine = RecommendationEngine()
        df = engine.find_best_deals(top_n=args.limit or 10)
        engine.close()
        print(f"\n{'='*70}")
        print(f"🏆 TOP {args.limit or 10} 매수 추천 지역 ({datetime.now().strftime('%Y-%m-%d')})")
        print(f"{'='*70}")
        print(df.to_string(index=False))
    elif args.action == 'sell':
        engine = RecommendationEngine()
        df = engine.find_sell_alerts(top_n=args.limit or 10)
        engine.close()
        print(f"\n{'='*70}")
        print(f"🚨 매도 경보 지역 TOP {args.limit or 10}")
        print(f"{'='*70}")
        print(df.to_string(index=False))
    elif args.action == 'budget' or args.action == '예산':
        budget = args.budget or 5
        df = rank_by_budget(budget_ok=budget)
        if not df.empty:
            print(f"\n{'='*80}")
            print(f"💡 {budget}억 예산 매수 추천 순위")
            print(f"{'='*80}")
            print(df.to_string())
        else:
            print(f"📭 {budget}억 예산에 맞는 지역이 없습니다.")
    elif args.action == 'apt-recommend' or args.action == 'apt-search':
        if args.action == 'apt-recommend':
            cmd_recommend_apt(args)
        else:
            cmd_search_apt(args)
    else:
        print(f"❌ 알 수 없는 액션: {args.action}")


def cmd_recommend_apt(args):
    '''단지 단위 추천'''
    region = args.region or '서울특별시 강남구'
    from strategy.recommender import RecommendationEngine, print_apt_ranking
    print_apt_ranking(region, limit=args.limit or 20)


def cmd_search_apt(args):
    '''단지 검색'''
    from strategy.recommender import RecommendationEngine
    engine = RecommendationEngine()
    df = engine.search_apts(args.keyword)
    for _, r in df.iterrows():
        print(f'{r["apt_name"]} ({r["region"]}) - {r["cnt"]}건')
    engine.close()


def cmd_watchlist(args):
    '''Watchlist 관리'''
    from scripts.alert_engine import register_watchlist, remove_watchlist, list_watchlists, check_watchlist, get_price_alerts
    if args.action == 'add':
        register_watchlist('default', args.apt_name, args.region)
        print(f'✅ {args.apt_name} 등록 완료')
    elif args.action == 'remove':
        remove_watchlist(args.id)
    elif args.action == 'list':
        items = list_watchlists()
        for i in items:
            print(f'{i["id"]}: {i["apt_name"]} ({i["region"]}) - 점수 {i["last_score"]}')
    elif args.action == 'check':
        alerts = check_watchlist()
        for a in alerts:
            print(a)
    elif args.action == 'alerts':
        alerts = get_price_alerts(limit=20)
        for a in alerts:
            print(f'{a["alert_type"]}: {a["message"]}')


def cmd_portfolio(args):
    '''포트폴리오 시뮬레이션'''
    from strategy.portfolio import Portfolio
    p = Portfolio(budget=args.budget or 5)
    print(p.report())


def cmd_backtest(args):
    '''백테스트 실행'''
    from strategy.backtest import backtest_strategy, print_backtest_result
    result = backtest_strategy(args.region or '서울특별시 강남구',
                                budget_ok=args.budget or 5)
    print_backtest_result(result)


def cmd_chart(args):
    """차트 생성"""
    from charts.chart_generator import generate_all_charts, chart_region_comparison
    if args.region:
        generate_all_charts(args.region)
    else:
        for r in ['서울특별시 강남구', '서울특별시 서초구', '서울특별시 송파구', '서울특별시 관악구']:
            generate_all_charts(r)
    chart_region_comparison()


def main():
    parser = argparse.ArgumentParser(
        description='🏠 한국 부동산 전략 시스템',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
명령어 예시:
  python main.py init                          # DB 초기화
  python main.py status                        # 상태 확인
  python main.py collect molit --code 11680 --year 2025 --month 6
  python main.py collect 실거래 --code 11680 --months 6
  python main.py collect zigbang --dong 압구정
  python main.py analyze 통계 --region 강남구
  python main.py analyze 전세 --region 서초구
  python main.py strategy 매매 --region 강남구 --budget 10
  python main.py strategy 전세 --region 송파구
  python main.py strategy 적정가 --apt "래미안"
  python main.py report 주간 --region 강남구
  python main.py 지역 --search 강남
        """
    )
    sub = parser.add_subparsers(dest='command')

    # init
    p_init = sub.add_parser('init', help='DB 초기화')

    # status
    p_status = sub.add_parser('status', help='시스템 상태')

    # alerts
    p_alerts = sub.add_parser('alerts', aliases=['알림'], help='조건 알림 관리')
    p_alerts.add_argument('action', choices=['list', 'check', 'register', 'remove'])
    p_alerts.add_argument('--chat-id', default='telegram', help='채팅 ID')
    p_alerts.add_argument('--type', choices=['gap', 'jeonse_rate'], default='gap', help='알림 타입')
    p_alerts.add_argument('--region', '-r', default='', help='지역 필터')
    p_alerts.add_argument('--min-rate', type=float, default=65, help='최소 전세가율')
    p_alerts.add_argument('--max-rate', type=float, default=85, help='최대 전세가율')
    p_alerts.add_argument('--max-gap', type=float, default=3, help='최대 갭 (억원)')
    p_alerts.add_argument('--min-trades', type=int, default=3, help='최소 거래건수')
    p_alerts.add_argument('--id', type=int, default=0, help='조건 ID (remove용)')

    # collect
    p_collect = sub.add_parser('collect', aliases=['수집'], help='데이터 수집')
    p_collect.add_argument('type', choices=['molit', 'zigbang', '실거래', '직방'])
    p_collect.add_argument('--code', default='', help='법정동코드 5자리')
    p_collect.add_argument('--region', '-r', default='', help='지역명')
    p_collect.add_argument('--year', type=int, default=2025, help='년도')
    p_collect.add_argument('--month', type=int, default=datetime.now().month, help='월')
    p_collect.add_argument('--months', '-m', type=int, default=0, help='최근 N개월 수집')
    p_collect.add_argument('--data-type', '-t', default='trade', help='trade(매매) or rent(전월세)')
    p_collect.add_argument('--lat', type=float, help='위도 (zigbang)')
    p_collect.add_argument('--lng', type=float, help='경도 (zigbang)')
    p_collect.add_argument('--dong', help='동 이름 (zigbang)')

    # analyze
    p_analyze = sub.add_parser('analyze', aliases=['분석'], help='데이터 분석')
    p_analyze.add_argument('type', choices=[
        'stats', 'jeonse', 'area', 'gap', 'hot', 'yield',
        'volatility', 'reverse', 'detail', 'all',
        'pyoung', 'floor', 'seasonal', 'gap_alert', 'quantile', 'momentum',
        '통계', '전세', '면적', '갭', '핫플', '수익률',
        '변동성', '역전세', '상세', '전체',
        '평당가', '층수', '계절', '공백', '저평가', '모멘텀',
    ])
    p_analyze.add_argument('--region', '-r', default='', help='지역명')
    p_analyze.add_argument('--months', '-m', type=int, default=6, help='분석 기간(월)')
    p_analyze.add_argument('--apt', default='', help='아파트명')
    p_analyze.add_argument('--trend', action='store_true', help='추이 표시')
    p_analyze.add_argument('--quantile', type=float, default=0.25, help='분위수 (0.0~1.0, 기본 0.25)')

    # strategy
    p_strategy = sub.add_parser('strategy', aliases=['전략'], help='투자 전략')
    p_strategy.add_argument('type', choices=['buy', 'fair', 'jeonse', 'search', 'compare',
                                             '매매', '적정가', '전세', '검색', '비교'])
    p_strategy.add_argument('--region', '-r', default='', help='지역명')
    p_strategy.add_argument('--budget', '-b', type=float, default=0, help='예산(억원)')
    p_strategy.add_argument('--apt', default='', help='아파트명')
    p_strategy.add_argument('--area', '-a', type=float, nargs=2, default=None, metavar=('MIN', 'MAX'), help='면적 범위(평)')
    p_strategy.add_argument('--min-price', type=float, help='최소 가격(억원)')
    p_strategy.add_argument('--max-price', type=float, help='최대 가격(억원)')
    p_strategy.add_argument('--min-area', type=float, help='최소 면적(m²)')
    p_strategy.add_argument('--max-area', type=float, help='최대 면적(m²)')
    p_strategy.add_argument('--regions', nargs='+', help='비교할 지역 목록')

    # report
    p_report = sub.add_parser('report', aliases=['리포트'], help='리포트 생성')
    p_report.add_argument('type', choices=['weekly', 'monthly', 'summary', '주간', '월간', '요약'])
    p_report.add_argument('--region', '-r', default='', help='지역명')

    # region
    p_region = sub.add_parser('region', aliases=['지역'], help='지역 정보')
    p_region.add_argument('--search', '-s', default='', help='지역 검색')
    p_region.add_argument('--city', '-c', default='', help='시/도명')
    p_region.add_argument('--code', default='', help='법정동코드')

    # chart
    p_chart = sub.add_parser('chart', aliases=['차트'], help='차트 생성')
    p_chart.add_argument('--region', '-r', default='', help='지역명')

    # recommend
    p_recommend = sub.add_parser('recommend', aliases=['추천'], help='매매 추천 엔진')
    p_recommend.add_argument('action', choices=['rank', 'region', 'best', 'sell', 'budget', '예산',
                                                'apt-recommend', 'apt-search'],
                            help='rank(순위) / region(지역분석) / best(매수추천) / sell(매도경보) / budget(예산별) / apt-recommend(단지추천) / apt-search(단지검색)')
    p_recommend.add_argument('--region', '-r', default='', help='지역명 (region/apt-recommend 액션용)')
    p_recommend.add_argument('--budget', '-b', type=float, default=5, help='예산(억원, budget 액션용)')
    p_recommend.add_argument('--limit', '-l', type=int, default=0, help='출력 개수')
    p_recommend.add_argument('--keyword', '-k', default='', help='검색어 (apt-search 액션용)')

    # watchlist
    p_watchlist = sub.add_parser('watchlist', aliases=['워치'], help='Watchlist 관리')
    p_watchlist.add_argument('action', choices=['add', 'remove', 'list', 'check', 'alerts'],
                            help='add(등록) / remove(삭제) / list(목록) / check(체크) / alerts(알림)')
    p_watchlist.add_argument('--apt-name', default='', help='아파트명 (add 액션용)')
    p_watchlist.add_argument('--region', '-r', default='', help='지역명')
    p_watchlist.add_argument('--id', type=int, default=0, help='Watchlist ID (remove 액션용)')

    # portfolio
    p_portfolio = sub.add_parser('portfolio', aliases=['포트폴리오'], help='포트폴리오 시뮬레이션')
    p_portfolio.add_argument('--budget', '-b', type=float, default=5, help='예산(억원)')

    # backtest
    p_backtest = sub.add_parser('backtest', aliases=['백테스트'], help='백테스트 실행')
    p_backtest.add_argument('--region', '-r', default='', help='지역명')
    p_backtest.add_argument('--budget', '-b', type=float, default=5, help='예산(억원)')

    args = parser.parse_args()

    commands = {
        'init': cmd_init,
        'status': cmd_status,
        'collect': cmd_collect,
        '수집': cmd_collect,
        'analyze': cmd_analyze,
        '분석': cmd_analyze,
        'strategy': cmd_strategy,
        '전략': cmd_strategy,
        'report': cmd_report,
        '리포트': cmd_report,
        'region': cmd_region,
        '지역': cmd_region,
        'chart': cmd_chart,
        '차트': cmd_chart,
        'alerts': cmd_alerts,
        '알림': cmd_alerts,
        'recommend': cmd_recommend,
        '추천': cmd_recommend,
        'watchlist': cmd_watchlist,
        '워치': cmd_watchlist,
        'portfolio': cmd_portfolio,
        '포트폴리오': cmd_portfolio,
        'backtest': cmd_backtest,
        '백테스트': cmd_backtest,
    }

    if args.command in commands:
        commands[args.command](args)
    else:
        parser.print_help()


if __name__ == '__main__':
    main()
