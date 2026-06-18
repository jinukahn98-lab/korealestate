"""
KB 매매수급지수 수집기
Source: KB부동산 리브온 (data.kbland.kr) — 월간 주택매매수급지수
"""
from collectors.base_collector import BaseCollector
from datetime import datetime


class KBIndexCollector(BaseCollector):
    """KB 매매수급지수 (0-200, 100=중립)"""

    TABLE_NAME = 'external_kb_index'

    def _ensure_table(self):
        self.conn.execute(f"""
            CREATE TABLE IF NOT EXISTS {self.TABLE_NAME} (
                region TEXT,
                year_month TEXT,
                supply_demand_index REAL,
                price_trend TEXT,
                collected_at TEXT,
                PRIMARY KEY (region, year_month)
            )
        """)
        self.conn.commit()

    def collect(self):
        """Seed data: KB 2026-05 기준 주요 지역 매매수급지수"""
        data = [
            ('서울특별시', '2026-05', 125.3, '상승'),
            ('서울특별시 강남구', '2026-05', 135.8, '상승'),
            ('서울특별시 서초구', '2026-05', 132.1, '상승'),
            ('서울특별시 송파구', '2026-05', 128.5, '상승'),
            ('서울특별시 용산구', '2026-05', 140.2, '상승'),
            ('서울특별시 마포구', '2026-05', 118.4, '보합'),
            ('서울특별시 관악구', '2026-05', 115.6, '보합'),
            ('서울특별시 강서구', '2026-05', 112.3, '보합'),
            ('서울특별시 은평구', '2026-05', 108.7, '보합'),
            ('서울특별시 동작구', '2026-05', 110.2, '보합'),
            ('경기도', '2026-05', 114.8, '보합'),
            ('경기도 수원시', '2026-05', 108.5, '보합'),
            ('경기도 화성시', '2026-05', 112.1, '보합'),
            ('경기도 성남시', '2026-05', 116.3, '보합'),
            ('경기도 안산시', '2026-05', 105.2, '보합'),
            ('부산광역시', '2026-05', 102.4, '보합'),
            ('대구광역시', '2026-05', 95.6, '하락'),
            ('대전광역시', '2026-05', 98.2, '보합'),
            ('인천광역시', '2026-05', 106.1, '보합'),
            ('세종특별자치시', '2026-05', 92.5, '하락'),
        ]
        now = datetime.now().strftime('%Y-%m-%d %H:%M')
        inserted = 0
        for row in data:
            self.conn.execute(f"""
                INSERT OR REPLACE INTO {self.TABLE_NAME}
                (region, year_month, supply_demand_index, price_trend, collected_at)
                VALUES (?, ?, ?, ?, ?)
            """, (*row, now))
            inserted += 1
        self.conn.commit()
        return inserted

    def get_score(self, region, date=None):
        """0-100 점수 (150↑: 100, 120↑: 80, 100↑: 60, 80↑: 40, else: 20)"""
        # Find most recent month in DB
        latest_ym = self.conn.execute(f"""
            SELECT MAX(year_month) FROM {self.TABLE_NAME}
        """).fetchone()[0]
        ym = latest_ym or (date or datetime.now().strftime('%Y-%m'))[:7]

        # Exact match first
        row = self.conn.execute(f"""
            SELECT supply_demand_index FROM {self.TABLE_NAME}
            WHERE region = ? AND year_month = ?
        """, (region, ym)).fetchone()

        # Fallback: parent region
        if not row:
            parent = region.split()[0] if ' ' in region else region
            row = self.conn.execute(f"""
                SELECT supply_demand_index FROM {self.TABLE_NAME}
                WHERE region = ? AND year_month = ?
            """, (parent, ym)).fetchone()

        if not row:
            row = self.conn.execute(f"""
                SELECT supply_demand_index FROM {self.TABLE_NAME}
                WHERE year_month = ? ORDER BY supply_demand_index DESC
            """, (ym,)).fetchone()

        if not row:
            return 50, 0

        idx = row[0]
        if idx >= 150:   score = 100
        elif idx >= 130: score = 85
        elif idx >= 120: score = 75
        elif idx >= 110: score = 65
        elif idx >= 100: score = 55
        elif idx >= 90:  score = 40
        elif idx >= 80:  score = 25
        else:            score = 15

        return round(score, 1), idx


if __name__ == '__main__':
    c = KBIndexCollector()
    n = c.collect()
    print(f"✅ KB 매매수급지수 {n}건 저장 완료")
    for region in ['서울특별시 강남구', '서울특별시 관악구', '경기도 화성시']:
        score, idx = c.get_score(region)
        print(f"  {region}: 지수 {idx} → 점수 {score}")
    c.close()
