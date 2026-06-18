"""금리/거시경제 데이터 수집기"""
from collectors.base_collector import BaseCollector
from datetime import datetime

class MacroCollector(BaseCollector):
    TABLE_NAME = 'external_macro'

    def _ensure_table(self):
        self.conn.execute(f"""
            CREATE TABLE IF NOT EXISTS {self.TABLE_NAME} (
                date TEXT PRIMARY KEY,
                base_rate REAL, ltv_max REAL, dsr_max REAL,
                policy_direction TEXT, collected_at TEXT
            )
        """)
        self.conn.commit()

    def collect(self):
        data = [
            ('2026-06-01', 2.75, 70.0, 40.0, 'easing'),
            ('2026-05-01', 2.75, 70.0, 40.0, 'easing'),
            ('2026-04-01', 2.75, 70.0, 40.0, 'easing'),
            ('2026-03-01', 2.75, 65.0, 40.0, 'neutral'),
            ('2026-02-01', 3.00, 65.0, 40.0, 'neutral'),
            ('2026-01-01', 3.00, 65.0, 40.0, 'tightening'),
        ]
        now = datetime.now().strftime('%Y-%m-%d %H:%M')
        for row in data:
            self.conn.execute(f"""
                INSERT OR REPLACE INTO {self.TABLE_NAME}
                VALUES (?, ?, ?, ?, ?, ?)
            """, (*row, now))
        self.conn.commit()
        return len(data)

    def get_score(self, region='전국', date=None):
        """거시환경 점수 (0-100)"""
        latest = self.conn.execute(f"""
            SELECT base_rate, policy_direction FROM {self.TABLE_NAME}
            ORDER BY date DESC LIMIT 1
        """).fetchone()

        if not latest:
            return 50, 0

        rate = latest[0]
        direction = latest[1]

        if rate <= 2.0:         score = 90
        elif rate <= 2.5:       score = 75
        elif rate <= 3.0:       score = 60
        elif rate <= 3.5:       score = 45
        elif rate <= 5.0:       score = 30
        else:                   score = 15

        if direction == 'easing':     score += 10
        elif direction == 'tightening': score -= 10

        return round(max(0, min(100, score)), 1), rate

if __name__ == '__main__':
    c = MacroCollector(); n = c.collect()
    print(f"✅ 금리데이터 {n}건 저장")
    s, r = c.get_score()
    print(f"  기준금리 {r}% → 거시환경 {s}점")
    c.close()
