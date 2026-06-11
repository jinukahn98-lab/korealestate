#!/bin/bash
# 🏠 부동산 웹 대시보드 실행 스크립트 (원클릭 실행)
# 사용법: bash start.sh

cd "$(dirname "$0")"
source venv/bin/activate

# 1. 차트 생성
echo "📈 차트 생성중..."
python3 main.py 차트 --region "서울특별시 강남구" 2>/dev/null | grep -E "차트"

# 2. HTML 리포트 생성
echo "📄 HTML 리포트 생성중..."
python3 report/html_report.py "서울특별시 강남구" 2>/dev/null
python3 report/html_report.py "서울특별시 서초구" 2>/dev/null
python3 report/html_report.py "서울특별시 송파구" 2>/dev/null

# 3. Streamlit 대시보드 실행
echo ""
echo "========================================================"
echo "  🏠 부동산 대시보드 실행"
echo "========================================================"
echo ""
echo "  📱 로컬 접속: http://localhost:8501"
echo ""

# 로컬 IP 찾기
IP=$(ifconfig | grep "inet " | grep -v 127.0.0.1 | awk '{print $2}' | head -1)
if [ -n "$IP" ]; then
    echo "  📱 같은 와이파이 접속: http://${IP}:8501"
fi

# 터널링 시도
echo ""
echo "  🔗 외부 접속을 원하면: npx localtunnel --port 8501"
echo "     (npx localtunnel --port 8501 --subdomain korealestate)"
echo ""
echo "========================================================"

# 대시보드 실행
streamlit run dashboard.py --server.port 8501 --server.headless true
