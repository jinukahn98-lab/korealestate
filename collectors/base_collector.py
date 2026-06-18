"""
BaseCollector — 모든 외부 수집기의 추상 기반 클래스.

수집기(Collector) → 정규화(Normalizer) → 통합점수(Aggregator) → 평가(Scorer) 4계층에서
첫 번째 계층을 담당. 각 외부 소스는 이 클래스를 상속하여 독립 모듈로 추가/제거 가능.
"""
from abc import ABC, abstractmethod
import sqlite3
from datetime import datetime


class BaseCollector(ABC):
    """모든 외부 수집기의 기본 클래스"""

    def __init__(self, db_path='realestate.db'):
        self.conn = sqlite3.connect(db_path)
        self.conn.row_factory = sqlite3.Row
        self._ensure_table()

    @abstractmethod
    def _ensure_table(self):
        """수집 데이터 저장용 테이블 생성"""
        pass

    @abstractmethod
    def collect(self):
        """데이터 수집 실행 → self.conn에 저장"""
        pass

    @abstractmethod
    def get_score(self, region, date=None):
        """특정 지역의 점수 반환 (0-100 정규화)"""
        pass

    def normalize(self, raw_value, min_val, max_val):
        """선형 0-100 스케일로 정규화"""
        if max_val == min_val:
            return 50
        return round((raw_value - min_val) / (max_val - min_val) * 100, 1)

    def _now(self):
        return datetime.now().strftime('%Y-%m-%d %H:%M:%S')

    def close(self):
        if self.conn:
            self.conn.close()

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.close()

    # ─── 공통 헬퍼 ──────────────────────────────────────────

    def _latest_date(self, table, date_col='collected_at'):
        """테이블에 마지막으로 저장된 날짜 반환"""
        row = self.conn.execute(
            f"SELECT MAX({date_col}) FROM {table}"
        ).fetchone()
        return row[0] if row else None

    def _staleness_days(self, table, date_col='collected_at'):
        """마지막 수집 이후 경과 일수 (데이터 없으면 999)"""
        latest = self._latest_date(table, date_col)
        if not latest:
            return 999
        try:
            last_dt = datetime.strptime(latest[:10], '%Y-%m-%d')
            return (datetime.now() - last_dt).days
        except ValueError:
            return 999

    def status(self):
        """수집기 상태 딕셔너리 — 대시보드 소스 현황 표에 사용"""
        raise NotImplementedError("서브클래스에서 구현하세요")
