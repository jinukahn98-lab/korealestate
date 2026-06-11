#!/usr/bin/env python3
"""
모바일/데스크탑 모두에서 볼 수 있는 HTML 리포트 생성
python main.py report html --region "서울특별시 강남구"
"""

import os
import sys
import sqlite3
import pandas as pd
from datetime import datetime

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
from data.database import DB_PATH

REPORT_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'reports')
CHART_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'charts')


def generate_html_report(region):
    """HTML 리포트 생성"""
    os.makedirs(REPORT_DIR, exist_ok=True)
    os.makedirs(CHART_DIR, exist_ok=True)

    conn = sqlite3.connect(DB_PATH)

    chart_prefix = region.replace(' ', '_')

    html = f'''<!DOCTYPE html>
<html lang="ko">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>부동산 리포트 - {region}</title>
<style>
* {{ margin: 0; padding: 0; box-sizing: border-box; }}
body {{ font-family: -apple-system, 'Noto Sans KR', sans-serif; background: #0f0f23; color: #e0e0e0; padding: 16px; }}
h1 {{ font-size: 22px; color: #fff; margin-bottom: 4px; }}
.sub {{ color: #888; font-size: 13px; margin-bottom: 20px; }}
.card {{ background: #1a1a2e; border-radius: 12px; padding: 16px; margin-bottom: 12px; }}
.card h2 {{ font-size: 15px; color: #64b5f6; margin-bottom: 10px; }}
.stat-row {{ display: flex; justify-content: space-between; padding: 6px 0; border-bottom: 1px solid #2a2a3e; font-size: 14px; }}
.stat-label {{ color: #999; }}
.stat-value {{ color: #fff; font-weight: 600; }}
img {{ width: 100%; border-radius: 8px; margin-top: 8px; }}
table {{ width: 100%; border-collapse: collapse; font-size: 13px; }}
th {{ text-align: left; color: #888; padding: 6px 4px; border-bottom: 1px solid #333; }}
td {{ padding: 6px 4px; border-bottom: 1px solid #222; }}
.positive {{ color: #4caf50; }}
.negative {{ color: #f44336; }}
.footer {{ text-align: center; color: #555; font-size: 11px; margin-top: 24px; }}
</style>
</head>
<body>
<h1>🏠 {region.replace('서울특별시 ', '')}</h1>
<p class="sub">부동산 시장 리포트 · {datetime.now().strftime('%Y년 %m월 %d일')}</p>
'''

    # 1. 주요 지표
    t = conn.execute("SELECT COUNT(*) FROM apt_trade WHERE region=?", (region,)).fetchone()[0]
    r = conn.execute("SELECT COUNT(*) FROM apt_rent WHERE region=?", (region,)).fetchone()[0]
    avg_p = conn.execute("SELECT ROUND(AVG(price)) FROM apt_trade WHERE region=?", (region,)).fetchone()[0] or 0
    avg_a = conn.execute("SELECT ROUND(AVG(area),1) FROM apt_trade WHERE region=?", (region,)).fetchone()[0] or 0
    avg_r = conn.execute("SELECT ROUND(AVG(deposit)) FROM apt_rent WHERE region=?", (region,)).fetchone()[0] or 0

    html += f'''
<div class="card">
  <h2>📊 주요 지표</h2>
  <div class="stat-row"><span class="stat-label">📈 매매 거래</span><span class="stat-value">{t:,}건</span></div>
  <div class="stat-row"><span class="stat-label">💰 평균 매매가</span><span class="stat-value">{avg_p/10000:.1f}억</span></div>
  <div class="stat-row"><span class="stat-label">📐 평균 면적</span><span class="stat-value">{avg_a:.0f}m²</span></div>
  <div class="stat-row"><span class="stat-label">🏢 전월세 거래</span><span class="stat-value">{r:,}건</span></div>
  <div class="stat-row"><span class="stat-label">🔵 평균 전세가</span><span class="stat-value">{avg_r/10000:.1f}억</span></div>
</div>
'''

    # 2. 동별 매매가 순위
    html += '<div class="card"><h2>📍 동별 평균 매매가</h2><table><tr><th>동</th><th>평균가</th><th>거래</th><th>면적</th></tr>'
    rows = conn.execute('''
        SELECT dong, ROUND(AVG(price)) as p, COUNT(*) as c, ROUND(AVG(area),1) as a 
        FROM apt_trade WHERE region=? AND dong != '' 
        GROUP BY dong ORDER BY p DESC LIMIT 15
    ''', (region,)).fetchall()
    for row in rows:
        html += f'<tr><td>{row[0]}</td><td>{row[1]/10000:.1f}억</td><td>{row[2]}건</td><td>{row[3]}m²</td></tr>'
    html += '</table></div>'

    # 3. 전세가율
    html += '<div class="card"><h2>🔵 전세가율 TOP 10</h2><table><tr><th>단지</th><th>전세가율</th><th>매매가</th><th>전세가</th></tr>'
    rows = conn.execute('''
        SELECT t.apt_name, 
               ROUND(AVG(r.deposit)*100.0/AVG(t.price),1) as rate,
               ROUND(AVG(t.price)) as tp, ROUND(AVG(r.deposit)) as rp,
               COUNT(*) as c
        FROM apt_trade t JOIN apt_rent r ON t.apt_name=r.apt_name AND ABS(t.area-r.area)<5
        WHERE t.region=? GROUP BY t.apt_name HAVING c>3 AND rate>0
        ORDER BY rate DESC LIMIT 10
    ''', (region,)).fetchall()
    for row in rows:
        html += f'<tr><td>{row[0]}</td><td class="negative">{row[1]:.1f}%</td><td>{row[2]/10000:.1f}억</td><td>{row[3]/10000:.1f}억</td></tr>'
    html += '</table></div>'

    # 4. 차트
    for chart_name, chart_title in [
        ('price_trend', '매매가 추이'),
        ('jeonse_rate', '전세가율'),
        ('gap', '갭 분석'),
    ]:
        chart_path = os.path.join(CHART_DIR, f"{chart_name}_{chart_prefix}_{datetime.now().strftime('%Y%m%d')}.png")
        if os.path.exists(chart_path):
            # 이미지를 data URI로 인코딩
            import base64
            with open(chart_path, 'rb') as f:
                b64 = base64.b64encode(f.read()).decode()
            html += f'<div class="card"><h2>📈 {chart_title}</h2><img src="data:image/png;base64,{b64}" alt="{chart_title}"></div>'

    html += f'''</div>
<p class="footer">🔄 매일 오전 8시 자동 업데이트 · 한국 부동산 전략 시스템</p>
</body>
</html>'''

    conn.close()

    out_path = os.path.join(REPORT_DIR, f"{region.replace(' ', '_')}_{datetime.now().strftime('%Y%m%d')}.html")
    with open(out_path, 'w', encoding='utf-8') as f:
        f.write(html)

    print(f"✅ HTML 리포트 생성 완료: {out_path}")
    print(f"   파일로 열거나 웹서버로 호스팅하세요")
    return out_path


if __name__ == '__main__':
    import sys
    region = sys.argv[1] if len(sys.argv) > 1 else '서울특별시 강남구'
    generate_html_report(region)
