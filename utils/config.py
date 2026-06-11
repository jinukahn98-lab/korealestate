"""
설정 관리 모듈
"""

import os
import yaml
from dotenv import load_dotenv

load_dotenv()

CONFIG_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'config.yaml')

DEFAULT_CONFIG = {
    'default_region': '강남구',
    'data_retention_months': 24,
    'zigbang': {
        'geo_precision': 6,
    },
    'analysis': {
        'default_months': 6,
        'min_trades': 3,
    },
    'alert': {
        'jeonse_rate_warning': 80,
        'reverse_jeonse_check': True,
    },
}


def load_config():
    """설정 파일 로드"""
    if os.path.exists(CONFIG_PATH):
        with open(CONFIG_PATH, 'r', encoding='utf-8') as f:
            user_config = yaml.safe_load(f)
            if user_config:
                return {**DEFAULT_CONFIG, **user_config}
    return DEFAULT_CONFIG


def get_molit_api_key():
    """MOLIT API 키 조회"""
    return os.getenv('MOLIT_API_KEY', '')


def check_api_key():
    """API 키 설정 확인"""
    key = get_molit_api_key()
    if key:
        print("✅ MOLIT_API_KEY 설정됨")
        return True
    else:
        print("⚠ MOLIT_API_KEY가 설정되지 않았습니다")
        print("  .env 파일에 다음을 추가하세요:")
        print('  MOLIT_API_KEY=your_decoding_key_here')
        print("  (공공데이터포털 www.data.go.kr 에서 발급)")
        return False
