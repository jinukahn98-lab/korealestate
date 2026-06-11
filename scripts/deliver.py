#!/usr/bin/env python3
"""
부동산 리포트 자동 생성 + 텔레그램 전송 스크립트
갭 투자 TOP, 역전세 경보, 예산 추천 포함 고도화 버전
"""
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from datetime import datetime
from data.database import get_conn
from report.report import generate_weekly_report, generate_summary_report
from charts import generate_all_charts
import pandas as pd


def send_telegram(message, image_path=None):
    """결과를 텔레그램으로 전송"""
    print(f"MSG:{message}")
    if image_path and os.path.exists(image_path):
        print(f"MEDIA:{os.path.abspath(image_path)}")


def daily_briefing():
    """일일 브리핑 생성 (고도화)"""
    today = datetime.now().strftime('%Y-%m-%d %H:%M')

    conn = get_conn()
    regions = ['서울특별시 강남구', '서울특별시 서초구', '서울특별시 송파구',
               '서울특별시 관악구', '서울특별시 마포구', '서울특별시 노원구']

    msg = f"🏠 **일일 부동산 브리핑** ({today})\n\n"

    for region in regions:
        t = conn.execute("SELECT COUNT(*) FROM apt_trade WHERE region=? AND deal_date >= date('now', '-3 months')", (region,)).fetchone()[0]
        avg_p = conn.execute("SELECT ROUND(AVG(price)) FROM apt_trade WHERE region=? AND deal_date >= date('now', '-3 months')", (region,)).fetchone()[0]
        avg_a = conn.execute("SELECT ROUND(AVG(area),1) FROM apt_trade WHERE region=? AND deal_date >= date('now', '-3 months')", (region,)).fetchone()[0]
        r = conn.execute("SELECT COUNT(*) FROM apt_rent WHERE region=? AND deal_date >= date('now', '-3 months')", (region,)).fetchone()[0]
        name = region.replace('서울특별시 ', '')
        msg += f"📍 **{name}**\n   매매 {t}건 | 평균 {avg_p//10000:.1f}억 | {avg_a:.0f}m² | 전월세 {r}건\n\n"

    conn.close()

    # 갭 투자 TOP 5
    try:
        from strategy.gap_scanner import scan_gap_opportunities
        df = scan_gap_opportunities(min_rate=65, max_rate=85, max_gap=50000, min_trades=3)
        if df is not None and not df.empty:
            msg += f"💰 **갭 투자 HOT5**\n"
            for _, r in df.head(5).iterrows():
                region_short = r['region'].replace('서울특별시 ', '').replace('경기도 ', '')
                msg += f"   {region_short} {r['apt_name']} | 전세가율 {r['jeonse_rate']:.1f}% | 갭 {r['gap']/10000:.1f}억\n"
            msg += "\n"
    except Exception as e:
        msg += f"⚠️ 갭 분석 오류: {e}\n\n"

    # 역전세 경보
    try:
        from strategy.jeonse import alert_reverse_jeonse
        alert = alert_reverse_jeonse(threshold=85)
        if alert:
            lines = alert.strip().split('\n')
            msg += f"{lines[0]}\n"
            for l in lines[1:7]:  # TOP 5만
                if l.strip():
                    msg += f"   {l.strip()}\n"
        else:
            msg += f"✅ 역전세 위험 없음 (85%↑ 기준)\n"
        msg += "\n"
    except Exception as e:
        msg += f"⚠️ 역전세 오류: {e}\n\n"

    # 예산 기반 추천
    try:
        from strategy.region_planner import find_regions_by_budget
        df5 = find_regions_by_budget(budget_ok=5)
        if df5 is not None and not df5.empty:
            msg += f"💡 **5억 예산 TOP 3**\n"
            for _, r in df5.head(3).iterrows():
                name = r['region'].replace('서울특별시 ', '')
                msg += f"   {name}: 평균 {r['avg_price']/10000:.1f}억 / 전세가율 {r['jeonse_rate']:.1f}%\n"
    except:
        pass

    # 매수/매도 타이밍 신호
    try:
        from strategy.timing import get_timing_signal
        msg += "📊 **매수/매도 타이밍**\n"
        for region in regions[:3]:
            sig = get_timing_signal(region)
            emoji = {"BUY": "🟢", "HOLD": "🟡", "SELL": "🔴"}
            short = region.replace('서울특별시 ', '').replace('경기도 ', '')
            msg += f"   {emoji.get(sig['signal'], '⚪')} {short}: {sig['signal']} ({sig['score']}점)\n"
            for r in sig['reasons'][:2]:
                msg += f"      └ {r}\n"
        msg += "\n"
    except Exception as e:
        msg += f"⚠️ 타이밍 오류: {e}\n\n"

    # 가격 예측
    try:
        from analysis.prediction import predict_region_price
        msg += "🔮 **가격 예측 (3개월)**\n"
        for region in regions[:3]:
            pred = predict_region_price(region)
            if "error" not in pred:
                short = region.replace('서울특별시 ', '')
                emoji = {"up": "📈", "down": "📉", "flat": "➡️"}
                change = pred.get('predicted_3m_change_pct', 0)
                msg += f"   {short}: 현재 {pred['latest_price']/10000:.1f}억 → {pred['predicted_price']/10000:.1f}억 ({change:+.1f}%)\n"
        msg += "\n"
    except Exception as e:
        msg += f"⚠️ 예측 오류: {e}\n\n"

    # 갭 리스크 스코어링 (안전한 갭투자)
    try:
        from strategy.gap_scanner import scan_gap_opportunities, score_gap_risk
        df = scan_gap_opportunities(min_rate=65, max_rate=85, max_gap=50000, min_trades=3)
        if df is not None and not df.empty:
            df = score_gap_risk(df)
            safe = df[df['risk_level'] == 'safe'].head(3)
            if not safe.empty:
                msg += "✅ **안전 갭투자 TOP 3** (리스크 최저)\n"
                for _, r in safe.iterrows():
                    short = r['region'].replace('서울특별시 ', '')
                    msg += f"   {short} {r['apt_name']} | 갭 {r['gap']/10000:.1f}억 | 전세가율 {r['jeonse_rate']:.1f}%\n"
                msg += "\n"
    except Exception as e:
        msg += f"⚠️ 리스크 오류: {e}\n\n"

    send_telegram(msg)

    # 차트 생성 + 전송
    try:
        chart_dir = os.path.join(os.path.dirname(__file__), '..', 'charts')
        for region in ['서울특별시 강남구', '서울특별시 서초구', '서울특별시 송파구']:
            paths = generate_all_charts(region)
            if paths:
                for p in paths[:2]:
                    send_telegram("", p)
    except Exception as e:
        send_telegram(f"⚠️ 차트 생성 오류: {e}")


def weekly_report(region):
    """주간 리포트 생성 + 차트 전송"""
    from contextlib import redirect_stdout
    import io

    f = io.StringIO()
    with redirect_stdout(f):
        generate_weekly_report(region)
    report_text = f.getvalue()

    chart_paths = generate_all_charts(region)

    msg = f"📋 **주간 부동산 리포트**\n📍 {region}\n\n```\n{report_text}\n```"
    send_telegram(msg)

    for path in chart_paths:
        send_telegram("", path)


if __name__ == '__main__':
    if len(sys.argv) < 2:
        print("사용법: python deliver.py daily|weekly [region]")
        sys.exit(1)

    command = sys.argv[1]

    if command == 'daily':
        daily_briefing()
    elif command == 'weekly':
        region = sys.argv[2] if len(sys.argv) > 2 else '서울특별시 강남구'
        weekly_report(region)
    else:
        print(f"알 수 없는 명령: {command}")
