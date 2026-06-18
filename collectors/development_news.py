"""
개발호재 수집기 — GTX, 재건축, 신도시, 재개발 정보
Source: 네이버 뉴스, 국토교통부 발표 (seed data 기반)
"""
from collectors.base_collector import BaseCollector
from datetime import datetime


class DevelopmentCollector(BaseCollector):
    TABLE_NAME = 'external_development'

    PROJECT_SCORES = {
        'gtx': 30, 'reconstruction': 20, 'new-town': 25,
        'regeneration': 15, 'metro': 25, 'complex': 10,
    }
    PROGRESS = {
        'planned': 0.3, 'approved': 0.5,
        'under-construction': 0.7, 'completed': 1.0,
    }

    def _ensure_table(self):
        self.conn.execute(f"""
            CREATE TABLE IF NOT EXISTS {self.TABLE_NAME} (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                region TEXT,
                project_name TEXT,
                project_type TEXT,
                status TEXT,
                expected_completion TEXT,
                impact_score INTEGER,
                collected_at TEXT
            )
        """)
        self.conn.commit()

    def collect(self):
        data = [
            ('서울특별시 강남구', 'GTX-A 개통', 'gtx', 'under-construction', '2028', 5),
            ('서울특별시 서초구', 'GTX-A 개통', 'gtx', 'under-construction', '2028', 5),
            ('서울특별시 송파구', 'GTX-C 개통', 'gtx', 'under-construction', '2029', 5),
            ('서울특별시 강동구', 'GTX-C 개통', 'gtx', 'under-construction', '2029', 4),
            ('경기도 수원시', 'GTX-C 개통', 'gtx', 'under-construction', '2029', 4),
            ('경기도 화성시', 'GTX-A 개통', 'gtx', 'under-construction', '2028', 4),
            ('경기도 성남시', 'GTX-A 개통', 'gtx', 'under-construction', '2028', 4),
            ('경기도 안산시', '신안산선 복선전철', 'metro', 'under-construction', '2027', 4),
            ('서울특별시 용산구', '용산국제업무지구', 'complex', 'under-construction', '2030', 5),
            ('서울특별시 마포구', '마포 재정비촉진지구', 'regeneration', 'under-construction', '2028', 3),
            ('서울특별시 은평구', '은평뉴타운 마무리', 'new-town', 'completed', '2026', 3),
            ('서울특별시 관악구', '관악구 주거환경개선', 'regeneration', 'approved', '2028', 2),
            ('경기도 성남시', '분당 재건축 선도지구', 'reconstruction', 'approved', '2030', 4),
            ('경기도 수원시', '수원 당수지구 개발', 'new-town', 'under-construction', '2027', 3),
            ('부산광역시', '부산 GTX-B', 'gtx', 'planned', '2032', 3),
            ('대전광역시', '대전 도시철도 2호선', 'metro', 'under-construction', '2028', 3),
            ('대구광역시', '대구 도시철도 1호선 연장', 'metro', 'under-construction', '2027', 2),
        ]
        now = datetime.now().strftime('%Y-%m-%d %H:%M')
        inserted = 0
        for row in data:
            self.conn.execute(f"""
                INSERT OR IGNORE INTO {self.TABLE_NAME}
                (region, project_name, project_type, status, expected_completion, impact_score, collected_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (*row, now))
            inserted += 1
        self.conn.commit()
        return inserted

    def get_score(self, region, date=None):
        """개발호재 총점 (0-100), active 프로젝트 weighted sum"""
        rows = self.conn.execute(f"""
            SELECT project_type, status, impact_score
            FROM {self.TABLE_NAME}
            WHERE region = ?
        """, (region,)).fetchall()

        if not rows:
            return 0, 0

        total = 0
        for ptype, status, impact in rows:
            base = self.PROJECT_SCORES.get(ptype, 10)
            progress = self.PROGRESS.get(status, 0.3)
            total += base * progress * (impact / 5)

        score = min(100, total)
        return round(score, 1), len(rows)


if __name__ == '__main__':
    c = DevelopmentCollector()
    n = c.collect()
    print(f"✅ 개발호재 {n}건 저장 완료")
    for region in ['서울특별시 강남구', '서울특별시 관악구', '경기도 수원시', '경기도 화성시']:
        score, cnt = c.get_score(region)
        print(f"  {region}: {cnt}개 프로젝트 → {score}점")
    c.close()
