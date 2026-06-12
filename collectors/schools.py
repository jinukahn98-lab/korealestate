"""
학군정보 수집 모듈 (Mock)
TODO: 교육부 API 연동 필요
"""


def get_school_rating(apt_name, region):
    """학군 평점 조회 (Mock)

    Args:
        apt_name: 아파트명
        region: 지역명

    Returns:
        dict: 학군 정보
    """
    # TODO: 교육부 API 연동 필요
    return {
        'apt_name': apt_name,
        'elementary': '',
        'middle': '',
        'rating': 0.0
    }
