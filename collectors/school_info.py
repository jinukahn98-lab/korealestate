"""학군 데이터 수집기 — 학교 분포 및 학군 점수"""
from collectors.base_collector import BaseCollector
from datetime import datetime

class SchoolCollector(BaseCollector):
    TABLE_NAME = 'external_school'

    def _ensure_table(self):
        self.conn.execute(f"""
            CREATE TABLE IF NOT EXISTS {self.TABLE_NAME} (
                region TEXT PRIMARY KEY,
                school_count INTEGER,
                special_school_count INTEGER,
                avg_rating REAL,
                district_score INTEGER,
                collected_at TEXT
            )
        """)
        self.conn.commit()

    def collect(self):
        data = [
            ('서울특별시 강남구', 42, 8, 4.5, 10),
            ('서울특별시 서초구', 38, 7, 4.4, 10),
            ('서울특별시 송파구', 35, 5, 4.2, 9),
            ('서울특별시 용산구', 28, 4, 4.0, 8),
            ('서울특별시 마포구', 30, 3, 3.8, 7),
            ('서울특별시 동작구', 25, 2, 3.5, 6),
            ('서울특별시 관악구', 24, 1, 3.2, 5),
            ('서울특별시 강서구', 26, 1, 3.1, 5),
            ('서울특별시 은평구', 22, 1, 3.0, 4),
            ('서울특별시 강동구', 23, 2, 3.3, 5),
            ('서울특별시 노원구', 28, 2, 3.4, 6),
            ('경기도 성남시', 35, 4, 3.8, 7),
            ('경기도 수원시', 40, 3, 3.5, 6),
            ('경기도 화성시', 25, 2, 3.2, 5),
            ('경기도 안산시', 22, 1, 2.8, 3),
            ('부산광역시 해운대구', 20, 2, 3.5, 6),
            ('대구광역시 수성구', 18, 3, 3.8, 7),
            ('대전광역시 유성구', 15, 2, 3.5, 6),
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
        """학군 점수 (district_score * 10, 0-100)"""
        row = self.conn.execute(f"""
            SELECT district_score, special_school_count, avg_rating
            FROM {self.TABLE_NAME} WHERE region = ?
        """, (region,)).fetchone()
        if not row:
            parent = region.split()[0] if ' ' in region else region
            row = self.conn.execute(f"""
                SELECT district_score, special_school_count, avg_rating
                FROM {self.TABLE_NAME} WHERE region = ?
            """, (parent,)).fetchone()
        if not row:
            return 30, 0
        score = row[0] * 10
        return round(score, 1), row[2]

if __name__ == '__main__':
    c = SchoolCollector(); n = c.collect()
    print(f"✅ 학군데이터 {n}건 저장")
    for r in ['서울특별시 강남구', '서울특별시 관악구', '경기도 화성시', '대구광역시 수성구']:
        s, v = c.get_score(r)
        print(f"  {r}: 평점{v} → {s}점")
    c.close()
