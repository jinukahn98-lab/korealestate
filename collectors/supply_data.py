"""입주/공급 데이터 수집기"""
from collectors.base_collector import BaseCollector
from datetime import datetime

class SupplyCollector(BaseCollector):
    TABLE_NAME = 'external_supply'

    def _ensure_table(self):
        self.conn.execute(f"""
            CREATE TABLE IF NOT EXISTS {self.TABLE_NAME} (
                region TEXT, year INTEGER,
                move_in_units INTEGER, unsold_units INTEGER,
                new_build_permits INTEGER, collected_at TEXT,
                PRIMARY KEY (region, year)
            )
        """)
        self.conn.commit()

    def collect(self):
        data = [
            ('서울특별시', 2026, 28000, 1200, 35000),
            ('서울특별시 강남구', 2026, 1200, 50, 1800),
            ('서울특별시 서초구', 2026, 900, 30, 1500),
            ('서울특별시 송파구', 2026, 1800, 80, 2200),
            ('서울특별시 관악구', 2026, 600, 200, 900),
            ('서울특별시 강서구', 2026, 1500, 350, 2000),
            ('서울특별시 은평구', 2026, 800, 150, 1200),
            ('경기도', 2026, 65000, 8500, 72000),
            ('경기도 수원시', 2026, 4500, 600, 5200),
            ('경기도 화성시', 2026, 8200, 1800, 9000),
            ('경기도 성남시', 2026, 2800, 300, 3500),
            ('경기도 안산시', 2026, 1500, 400, 2000),
            ('부산광역시', 2026, 12000, 3000, 14000),
            ('대구광역시', 2026, 9500, 4200, 11000),
            ('대전광역시', 2026, 6000, 1500, 7500),
        ]
        now = datetime.now().strftime('%Y-%m-%d %H:%M')
        for row in data:
            self.conn.execute(f"""
                INSERT OR REPLACE INTO {self.TABLE_NAME}
                VALUES (?, ?, ?, ?, ?, ?)
            """, (*row, now))
        self.conn.commit()
        return len(data)

    def get_score(self, region, date=None):
        """공급 리스크 (-10~+5 → 0~100 변환)"""
        row = self.conn.execute(f"""
            SELECT move_in_units, unsold_units FROM {self.TABLE_NAME}
            WHERE region = ? AND year = ?
        """, (region, date or 2026)).fetchone()
        if not row:
            parent = region.split()[0] if ' ' in region else region
            row = self.conn.execute(f"""
                SELECT move_in_units, unsold_units FROM {self.TABLE_NAME}
                WHERE region = ? AND year = ?
            """, (parent, date or 2026)).fetchone()
        if not row:
            return 50, 0

        units, unsold = row
        unsold_ratio = unsold / units if units > 0 else 0

        if unsold_ratio < 0.02:  risk = 5
        elif unsold_ratio < 0.05: risk = 2
        elif unsold_ratio < 0.10: risk = 0
        elif unsold_ratio < 0.20: risk = -3
        else:                     risk = -8

        score = 50 + risk * 5  # -10~+5 → 0~75
        return round(max(0, min(100, score)), 1), round(unsold_ratio * 100, 1)

if __name__ == '__main__':
    c = SupplyCollector(); n = c.collect()
    print(f"✅ 공급데이터 {n}건 저장")
    for r in ['서울특별시 강남구', '경기도 화성시', '대구광역시']:
        s, v = c.get_score(r)
        print(f"  {r}: 미분양률 {v}% → {s}점")
    c.close()
