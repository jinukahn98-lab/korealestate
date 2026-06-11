#!/usr/bin/env python3
"""
부동산 리포트 자동 생성 + 텔레그램 전송 스크립트
cron job에서 실행되어 결과를 텔레그램으로 푸시합니다.
"""
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from datetime import datetime
from data.database import get_conn
from report.report import generate_weekly_report, generate_monthly_report, generate_summary_report
from charts import generate_all_charts
import pandas as pd


def send_telegram(message, image_path=None):
    """결과를 텔레그램으로 전송"""
    # 메시지와 이미지 경로를 stdout으로 출력
    # cron job이 이 출력을 잡아서 텔레그램으로 전송
    print(f"MSG:{message}")
    if image_path and os.path.exists(image_path):
        print(f"MEDIA:{os.path.abspath(image_path)}")


def daily_briefing():
    """일일 브리핑 생성"""
    today = datetime.now().strftime('%Y-%m-%d %H:%M')

    conn = get_conn()
    regions = ['서울특별시 강남구', '서울특별시 서초구', '서울특별시 송파구']

    msg = f"🏠 **일일 부동산 브리핑** ({today})\n\n"

    for region in regions:
        # 지역별 요약
        t = conn.execute("SELECT COUNT(*) FROM apt_trade WHERE region=? AND deal_date >= date('now', '-3 months')", (region,)).fetchone()[0]
        avg_p = conn.execute("SELECT ROUND(AVG(price)) FROM apt_trade WHERE region=? AND deal_date >= date('now', '-3 months')", (region,)).fetchone()[0]
        avg_a = conn.execute("SELECT ROUND(AVG(area),1) FROM apt_trade WHERE region=? AND deal_date >= date('now', '-3 months')", (region,)).fetchone()[0]
        r = conn.execute("SELECT COUNT(*) FROM apt_rent WHERE region=? AND deal_date >= date('now', '-3 months')", (region,)).fetchone()[0]

        name = region.replace('서울특별시 ', '')
        msg += f"📍 **{name}**\n"
        msg += f"   매매 {t}건 | 평균 {avg_p//10000:.1f}억 | {avg_a:.0f}m² | 전월세 {r}건\n\n"

    conn.close()

    # 차트 생성
    chart_dir = os.path.join(os.path.dirname(__file__), '..', 'charts')
    os.makedirs(chart_dir, exist_ok=True)

    # 전체 요약 리포트
    summary_output = []
    import io
    from contextlib import redirect_stdout

    f = io.StringIO()
    with redirect_stdout(f):
        generate_summary_report()
    summary_output = f.getvalue()

    msg += f"```\n{summary_output[:1000]}\n```"
    send_telegram(msg)


def weekly_report(region):
    """주간 리포트 생성 + 차트 전송"""
    chart_dir = os.path.join(os.path.dirname(__file__), '..', 'charts')
    os.makedirs(chart_dir, exist_ok=True)

    from contextlib import redirect_stdout
    import io

    # 리포트 텍스트
    f = io.StringIO()
    with redirect_stdout(f):
        generate_weekly_report(region)
    report_text = f.getvalue()

    # 차트 생성
    chart_paths = generate_all_charts(region)

    # 텔레그램 전송
    msg = f"📋 **주간 부동산 리포트**\n📍 {region}\n\n"
    msg += f"```\n{report_text}\n```"
    send_telegram(msg)

    # 차트 전송
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
