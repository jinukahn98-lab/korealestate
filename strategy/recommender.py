"""매매 추천 시스템 — 지역별 Buy/Sell 순위 엔진

8개 요소를 종합 점수화(0-100)하여 매수 추천 지역/단지 순위 제공
"""
import pandas as pd
import numpy as np
from datetime import datetime
from data.database import get_conn


class RecommendationEngine:
    """매매 추천 엔진"""

    # 가중치 설정 (합계 100)
    WEIGHTS = {
        "jeonse_rate": 20,      # 전세가율 (낮을수록 좋음)
        "volume_momentum": 15,  # 거래량 모멘텀
        "price_trend": 20,      # 가격 추세
        "gap_size": 10,         # 갭 크기 (매매-전세)
        "trade_stability": 10,  # 거래 안정성 (최근 거래일)
        "seasonal_boost": 10,   # 계절성 보정
        "diversity": 5,        # 단지 분산도
        "pyung_value": 10,     # 평당가 매력도
    }

    def __init__(self):
        self.conn = get_conn()
        # DB 내 최신 거래일 기준 (MOLIT API 다운으로 date('now') 사용 불가)
        row = self.conn.execute(
            "SELECT MAX(deal_date) FROM apt_trade WHERE deal_date IS NOT NULL"
        ).fetchone()
        self.ref_date = row[0] if row and row[0] else "2025-05-31"
        # 기준일 기반 상대 날짜들 미리 계산
        self._cache_dates()

    def _cache_dates(self):
        """ref_date 기준 상대일 캐싱"""
        rd = self.ref_date
        q = self.conn.execute
        self.d6 = q(f"SELECT date('{rd}', '-6 months')").fetchone()[0]
        self.d3 = q(f"SELECT date('{rd}', '-3 months')").fetchone()[0]
        self.d12 = q(f"SELECT date('{rd}', '-12 months')").fetchone()[0]
        self.d24 = q(f"SELECT date('{rd}', '-24 months')").fetchone()[0]
        self.d6_to_3_start = q(f"SELECT date('{rd}', '-6 months')").fetchone()[0]
        self.d6_to_3_end = q(f"SELECT date('{rd}', '-3 months')").fetchone()[0]

    def close(self):
        if self.conn:
            self.conn.close()

    # ─── 개별 요소 점수 ──────────────────────────────

    def score_jeonse_rate(self, region):
        """전세가율 점수 (0-100, 낮을수록 고득점)"""
        q = """
        SELECT COALESCE(AVG(r.deposit * 100.0 / NULLIF(t.price, 0)), 0) as rate
        FROM apt_trade t
        JOIN apt_rent r ON t.apt_name = r.apt_name AND ABS(t.area - r.area) < 5
        WHERE t.region LIKE ? AND t.deal_date >= ?
          AND r.deal_date >= ?
        """
        rate = pd.read_sql_query(q, self.conn, params=[f'%{region}%', self.d6, self.d6]).iloc[0, 0]
        if rate == 0:
            return 50, 0

        score = max(0, min(100, 100 - (rate - 30) * 2))
        return round(score, 1), round(rate, 1)

    def score_volume_momentum(self, region):
        """거래량 모멘텀 (0-100)"""
        q = """
        SELECT
          SUM(CASE WHEN deal_date >= ? THEN 1 ELSE 0 END) as recent,
          SUM(CASE WHEN deal_date >= ? AND deal_date < ? THEN 1 ELSE 0 END) as prev
        FROM apt_trade WHERE region LIKE ?
        """
        row = pd.read_sql_query(q, self.conn, params=[self.d3, self.d6, self.d3, f'%{region}%']).iloc[0]
        recent, prev = int(row['recent'] or 0), int(row['prev'] or 0)

        if prev == 0:
            return 60, 0, 0

        change_pct = (recent - prev) / prev * 100
        score = max(0, min(100, 50 + change_pct))
        return round(score, 1), round(change_pct, 1), recent

    def score_price_trend(self, region):
        """가격 추세 (0-100, 안정적 상승 + 과열 아님)"""
        q = """
        SELECT strftime('%Y-%m', deal_date) as month, ROUND(AVG(price), 0) as avg_p
        FROM apt_trade WHERE region LIKE ? AND deal_date >= ?
        GROUP BY month ORDER BY month
        """
        df = pd.read_sql_query(q, self.conn, params=[f'%{region}%', self.d6])
        if len(df) < 2:
            return 50, 0, 0

        p1 = df['avg_p'].iloc[0]
        p2 = df['avg_p'].iloc[-1]
        change_pct = (p2 - p1) / p1 * 100 if p1 > 0 else 0

        if change_pct > 20:
            score = max(0, 100 - (change_pct - 20) * 5)
        elif change_pct > 5:
            score = 80
        elif change_pct > 0:
            score = 70
        elif change_pct > -5:
            score = 50
        else:
            score = max(0, 50 + change_pct * 2)

        return round(score, 1), round(change_pct, 1), int(p2)

    def score_gap_size(self, region):
        """갭 크기 점수 (0-100, 갭이 적절히 클수록 좋음)"""
        q = """
        SELECT
          ROUND(AVG(t.price), 0) as avg_price,
          ROUND(AVG(r.deposit), 0) as avg_deposit
        FROM apt_trade t
        JOIN apt_rent r ON t.apt_name = r.apt_name AND ABS(t.area - r.area) < 5
        WHERE t.region LIKE ? AND t.deal_date >= ?
          AND r.deal_date >= ?
        """
        row = pd.read_sql_query(q, self.conn, params=[f'%{region}%', self.d6, self.d6]).iloc[0]
        avg_price = row['avg_price'] or 0
        avg_deposit = row['avg_deposit'] or 0
        gap = avg_price - avg_deposit

        if avg_price == 0:
            return 50, 0, 0

        gap_ratio = gap / avg_price * 100
        if 10 <= gap_ratio <= 30:
            score = 90
        elif gap_ratio < 5:
            score = 30
        elif gap_ratio < 10:
            score = 60
        elif gap_ratio <= 40:
            score = 70
        else:
            score = 40

        return round(score, 1), int(gap), round(gap_ratio, 1)

    def score_trade_stability(self, region):
        """거래 안정성 (0-100, 최근 거래일이 가까울수록 좋음)"""
        q = """
        SELECT MAX(deal_date) as last_trade,
               COUNT(*) as trade_count,
               COUNT(DISTINCT apt_name) as apt_count
        FROM apt_trade WHERE region LIKE ? AND deal_date >= ?
        """
        row = pd.read_sql_query(q, self.conn, params=[f'%{region}%', self.d12]).iloc[0]
        last_trade = row['last_trade']
        trade_count = int(row['trade_count'] or 0)
        apt_count = int(row['apt_count'] or 0)

        if not last_trade:
            return 0, 0, 0

        ref = datetime.strptime(self.ref_date, '%Y-%m-%d')
        last = datetime.strptime(last_trade, '%Y-%m-%d')
        days_since = (ref - last).days

        if days_since <= 30:
            stability_score = 100
        elif days_since <= 90:
            stability_score = 80
        elif days_since <= 180:
            stability_score = 50
        else:
            stability_score = max(0, 50 - (days_since - 180) * 0.3)

        return round(stability_score, 1), days_since, trade_count

    def score_seasonal(self, region):
        """계절성 보정 (0-100, 현재월이 거래 성수기인가)"""
        ref_month = datetime.strptime(self.ref_date, '%Y-%m-%d').month

        q = """
        SELECT CAST(strftime('%m', deal_date) AS INTEGER) as m, COUNT(*) as cnt
        FROM apt_trade WHERE region LIKE ? AND deal_date >= ?
        GROUP BY m
        """
        df = pd.read_sql_query(q, self.conn, params=[f'%{region}%', self.d24])
        if df.empty:
            return 50, 0

        max_cnt = df['cnt'].max()
        row = df[df['m'] == ref_month]
        current_cnt = row['cnt'].iloc[0] if not row.empty else 0

        ratio = current_cnt / max_cnt if max_cnt > 0 else 0.5
        score = ratio * 100
        return round(score, 1), round(ratio * 100, 1)

    def score_diversity(self, region):
        """단지 분산도 (0-100)"""
        q = """
        SELECT COUNT(DISTINCT apt_name) as apt_count,
               COUNT(*) as total_trades
        FROM apt_trade WHERE region LIKE ? AND deal_date >= ?
        """
        row = pd.read_sql_query(q, self.conn, params=[f'%{region}%', self.d6]).iloc[0]
        apt_count = int(row['apt_count'] or 0)
        total = int(row['total_trades'] or 0)

        if apt_count == 0:
            return 30, 0, 0

        density = total / apt_count

        if apt_count >= 20:
            diversity_score = 100
        elif apt_count >= 10:
            diversity_score = 80
        elif apt_count >= 5:
            diversity_score = 60
        else:
            diversity_score = 30

        if density > 50:
            diversity_score *= 0.7
        elif density > 20:
            diversity_score *= 0.9

        return round(diversity_score, 1), apt_count, round(density, 1)

    def score_pyung_value(self, region):
        """평당가 매력도 (0-100)"""
        q = """
        SELECT
          ROUND(AVG(price / NULLIF(area, 0) * 3.3), 0) as avg_pyung,
          ROUND(AVG(price), 0) as avg_price,
          COUNT(DISTINCT apt_name) as apt_count
        FROM apt_trade WHERE region LIKE ? AND deal_date >= ?
        """
        row = pd.read_sql_query(q, self.conn, params=[f'%{region}%', self.d6]).iloc[0]
        avg_pyung = row['avg_pyung'] or 0
        apt_count = int(row['apt_count'] or 0)

        if avg_pyung == 0 or apt_count < 3:
            return 50, 0

        sido = region[:2]
        q2 = """
        SELECT ROUND(AVG(price / NULLIF(area, 0) * 3.3), 0) as sido_avg_pyung
        FROM apt_trade WHERE region LIKE ? AND deal_date >= ?
        """
        sido_row = pd.read_sql_query(q2, self.conn, params=[f'{sido}%', self.d6]).iloc[0]
        sido_avg = sido_row['sido_avg_pyung'] or avg_pyung

        ratio = avg_pyung / sido_avg * 100 if sido_avg > 0 else 100
        if ratio <= 80:
            score = 100
        elif ratio <= 100:
            score = 100 - (ratio - 80) * 2
        elif ratio <= 120:
            score = max(0, 60 - (ratio - 100) * 2)
        else:
            score = 20

        return round(score, 1), int(avg_pyung)

    # ─── 종합 점수 ────────────────────────────────────

    def score_region(self, region):
        """지역 종합 점수 계산"""
        factors = {}

        s1, v1 = self.score_jeonse_rate(region)
        factors['전세가율'] = {'score': s1, 'value': f'{v1}%'}

        s2, v2, v2b = self.score_volume_momentum(region)
        factors['거래량모멘텀'] = {'score': s2, 'value': f'{v2:+.1f}% ({v2b}건)'}

        s3, v3, v3b = self.score_price_trend(region)
        factors['가격추세'] = {'score': s3, 'value': f'{v3:+.1f}% → {v3b//10000}억'}

        s4, v4, v4b = self.score_gap_size(region)
        factors['갭크기'] = {'score': s4, 'value': f'{v4//10000}억 (갭비율 {v4b}%)'}

        s5, v5, v5b = self.score_trade_stability(region)
        factors['거래안정성'] = {'score': s5, 'value': f'{v5}일 전 / 연 {v5b}건'}

        s6, v6 = self.score_seasonal(region)
        factors['계절성'] = {'score': s6, 'value': f'성수기지수 {v6}%'}

        s7, v7, v7b = self.score_diversity(region)
        factors['단지분산도'] = {'score': s7, 'value': f'{v7}개 단지 (집중도 {v7b})'}

        s8, v8 = self.score_pyung_value(region)
        factors['평당가매력'] = {'score': s8, 'value': f'평균 {v8}만원/평'}

        scores_map = {
            'jeonse_rate': s1, 'volume_momentum': s2, 'price_trend': s3,
            'gap_size': s4, 'trade_stability': s5, 'seasonal_boost': s6,
            'diversity': s7, 'pyung_value': s8
        }

        total = sum(
            scores_map[k] * (self.WEIGHTS[k] / 100.0)
            for k in self.WEIGHTS
        )

        if total >= 80:
            grade = '🔥 강력매수'
        elif total >= 65:
            grade = '✅ 매수'
        elif total >= 50:
            grade = '➡️ 관망'
        elif total >= 35:
            grade = '⚠️ 매도'
        else:
            grade = '🔴 긴급매도'

        return {
            'region': region,
            'total_score': round(total, 1),
            'grade': grade,
            'factors': factors,
            'time': datetime.now().strftime('%Y-%m-%d %H:%M'),
        }

    def rank_regions(self, regions=None, limit=20):
        """전체/선택 지역 순위표"""
        if not regions:
            df = pd.read_sql_query(
                "SELECT DISTINCT region FROM apt_trade ORDER BY region", self.conn
            )
            regions = df['region'].tolist()

        results = []
        for r in regions:
            try:
                result = self.score_region(r)
                results.append(result)
            except Exception as e:
                continue

        df_result = pd.DataFrame([{
            '순위': i + 1,
            '지역': r['region'].replace('서울특별시 ', '').replace('경기도 ', '').replace('부산광역시 ', ''),
            '종합점수': r['total_score'],
            '등급': r['grade'],
            '전세가율': r['factors']['전세가율']['value'],
            '가격추세': r['factors']['가격추세']['value'],
            '거래량': r['factors']['거래량모멘텀']['value'],
            '갭크기': r['factors']['갭크기']['value'],
            '평당가': r['factors']['평당가매력']['value'],
        } for i, r in enumerate(sorted(results, key=lambda x: x['total_score'], reverse=True)[:limit])])

        return df_result

    def find_best_deals(self, top_n=10):
        """최고 매수 추천 지역"""
        df = self.rank_regions(limit=50)
        filtered = df[df['종합점수'] >= 60].head(top_n)
        return filtered

    def find_sell_alerts(self, top_n=10):
        """매도 경보 지역"""
        df = self.rank_regions(limit=50)
        filtered = df[df['종합점수'] < 40].head(top_n)
        return filtered


def print_recommendation(region):
    """CLI용 추천 출력"""
    engine = RecommendationEngine()
    result = engine.score_region(region)
    engine.close()

    print(f"\n{'='*50}")
    print(f"📍 {result['region']}")
    print(f"📊 종합점수: {result['total_score']}/100  |  등급: {result['grade']}")
    print(f"🕐 {result['time']}")
    print(f"{'='*50}")

    for name, data in result['factors'].items():
        bar_len = int(data['score'] / 10)
        bar = '█' * bar_len + '░' * (10 - bar_len)
        print(f"  {name:8s} |{bar}| {data['score']:.1f}점 ({data['value']})")

    print()
    return result


def print_ranking(limit=20):
    """CLI용 순위표 출력"""
    engine = RecommendationEngine()
    df = engine.rank_regions(limit=limit)
    engine.close()

    print(f"\n{'='*80}")
    print(f"🏆 매매 추천 지역 순위 (ref: {engine.ref_date})")
    print(f"{'='*80}")
    print(df.to_string(index=False))
    print(f"\n🔥 강력매수: 80↑  ✅ 매수: 65↑  ➡️ 관망: 50↑  ⚠️ 매도: 35↑  🔴 긴급매도: 35↓")
    return df


def rank_by_budget(budget_ok=5):
    """예산 기반 매수 추천"""
    engine = RecommendationEngine()
    conn = engine.conn

    q = """
    SELECT region, ROUND(AVG(price), 0) as avg_price,
           ROUND(AVG(area), 1) as avg_area,
           COUNT(*) as cnt
    FROM apt_trade
    WHERE deal_date >= ?
    GROUP BY region
    HAVING avg_price BETWEEN ? AND ?
    ORDER BY cnt DESC
    """
    low = (budget_ok - 1) * 10000
    high = budget_ok * 10000
    df = pd.read_sql_query(q, conn, params=[engine.d6, low, high])

    if df.empty:
        engine.close()
        return pd.DataFrame()

    scores = []
    for _, row in df.iterrows():
        try:
            result = engine.score_region(row['region'])
            scores.append({
                '지역': row['region'].replace('서울특별시 ', ''),
                '평균가(억)': f"{row['avg_price']/10000:.1f}",
                '평균면적': f"{row['avg_area']:.0f}m²",
                '거래건수': int(row['cnt']),
                '추천점수': result['total_score'],
                '등급': result['grade'],
            })
        except Exception as e:
            continue

    engine.close()
    df_result = pd.DataFrame(scores)
    if not df_result.empty:
        df_result = df_result.sort_values('추천점수', ascending=False).reset_index(drop=True)
        df_result.index = df_result.index + 1
        df_result.index.name = '순위'

    return df_result


if __name__ == '__main__':
    import sys
    if len(sys.argv) > 1 and sys.argv[1] == 'rank':
        print_ranking()
    elif len(sys.argv) > 1:
        print_recommendation(sys.argv[1])
    else:
        print_recommendation('서울특별시 강남구')
        print_ranking(10)
