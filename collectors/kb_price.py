"""
KB부동산 시세 수집 모듈 (Mock)
TODO: KB부동산 API 연동 필요
"""

from datetime import datetime


def collect_kb_price(region):
    """KB부동산 시세 수집 (Mock)

    Args:
        region: 지역명 (예: '서울특별시 강남구')

    Returns:
        dict: 시세 정보
    """
    # TODO: KB부동산 API 연동 필요. 현재는 Mock 반환
    return {
        'region': region,
        'avg_price': 0,
        'low_price': 0,
        'high_price': 0,
        'collected_at': datetime.now().isoformat()
    }


def get_kb_price_from_db(region, apt_name=None):
    """저장된 KB 시세 조회

    Args:
        region: 지역명
        apt_name: 아파트명 (선택)

    Returns:
        list: 시세 정보 리스트
    """
    # TODO: DB 조회 로직 구현 필요
    pass
