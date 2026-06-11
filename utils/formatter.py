"""
출력 포맷팅 유틸리티
"""

from tabulate import tabulate


def print_table(df, title="", max_rows=20):
    """데이터프레임을 예쁜 테이블로 출력"""
    if df is None or df.empty:
        print(f"\n📭 {title}: 데이터 없음")
        return

    print(f"\n📊 {title}")
    print(tabulate(df.head(max_rows), headers='keys', tablefmt='simple',
                   numalign='right', stralign='left',
                   floatfmt='.1f'))
    if len(df) > max_rows:
        print(f"... 외 {len(df) - max_rows}건")
    print()


def print_section(title):
    """섹션 헤더 출력"""
    print(f"\n{'='*60}")
    print(f"  {title}")
    print(f"{'='*60}")


def print_progress(msg):
    """진행 메시지 출력"""
    print(f"  ⏳ {msg}")


def print_success(msg):
    """성공 메시지 출력"""
    print(f"  ✅ {msg}")


def print_warning(msg):
    """경고 메시지 출력"""
    print(f"  ⚠️ {msg}")


def print_error(msg):
    """오류 메시지 출력"""
    print(f"  ❌ {msg}")


def format_price(price_m):
    """가격 포맷팅 (만원 -> 억/만)"""
    if price_m >= 10000:
        ok = price_m // 10000
        rest = price_m % 10000
        if rest > 0:
            return f"{ok}억 {rest}만원"
        return f"{ok}억"
    return f"{price_m:,}만원"


def format_py(price_m, area_m2):
    """평당가 계산 및 포맷팅"""
    if area_m2 <= 0:
        return "N/A"
    py = price_m * 3.3 / area_m2
    return f"{py:,.0f}만원/평"


def bar_chart(value, max_value, width=20):
    """텍스트 막대 그래프"""
    bar_len = int(value / max_value * width) if max_value > 0 else 0
    return '█' * bar_len + '░' * (width - bar_len)
