# 🏠 아파트 단위 매수/매도 자동 의사결정 시스템 로드맵

> **목표:** "지금 이 아파트를 사야 하나, 팔아야 하나"를 자동으로 판단해주는 시스템
> **현재:** 지역 단위(강남구 63점) → **목표:** 단지 단위(래미안퍼스티지 78점 ✅매수)

---

## Phase 0: 현재 상태 진단

| 항목 | 상태 | 문제점 |
|------|:----:|:-------|
| `recommender.py` | ✅ 지역 단위 | 단지 단위 미지원 |
| `timing.py` | ✅ 지역 단위 BUY/HOLD/SELL | 단지 단위 미지원 |
| `prediction.py` | ✅ 지역+단지 예측 | 단지 예측 단순회귀 |
| `gap_scanner.py` | ✅ 단지 단위 갭 분석 | 리스크 점수만 있음 |
| `alert_engine.py` | ✅ 조건 등록 | 가격변동 알림 없음 |
| DB (apt_trade + apt_rent) | ✅ 384,708건 | 단지별 분석 가능 |

**핵심 통찰:** DB에는 이미 개별 아파트 단지 데이터(apt_name)가 있다. `strategy/recommender.py`만 단지 단위로 내리면 된다.

---

## Phase 1: 지역 → 단지 단위 추천 진화 🎯

**핵심:** `recommender.py`에 `score_apt()` 메서드 추가 (기존 `score_region()`과 100% 호환)

### 수정 파일
| 파일 | 변경량 | 설명 |
|------|:------:|:-----|
| `strategy/recommender.py` | +200줄 | `score_apt()`, `rank_apts()`, `find_best_apts()` 추가 |
| `main.py` | +30줄 | `python main.py 추천 단지 --지역 강남구` |
| `dashboard.py` | +100줄 | "🏢 지금 사야 할 아파트 TOP 20" 탭 |

### 핵심 로직 (recommender.py에 추가)

```python
def score_apt(self, apt_name, region):
    """단지별 8개 요소 점수 계산 (score_region과 동일 구조)"""
    conn = self.conn

    # 1. 전세가율
    q1 = """
    SELECT COALESCE(AVG(r.deposit * 100.0 / NULLIF(t.price, 0)), 0)
    FROM apt_trade t JOIN apt_rent r ON ABS(t.area - r.area) < 5
    WHERE t.apt_name = ? AND t.region LIKE ?
      AND t.deal_date >= ? AND r.deal_date >= ?
    """
    rate = conn.execute(q1, [apt_name, f'%{region}%', self.d6, self.d6]).fetchone()[0]

    # 2. 거래량 모멘텀 (최근 3개월 vs 이전 3개월)
    q2 = """
    SELECT
      SUM(CASE WHEN deal_date >= ? THEN 1 ELSE 0 END),
      SUM(CASE WHEN deal_date >= ? AND deal_date < ? THEN 1 ELSE 0 END)
    FROM apt_trade WHERE apt_name = ? AND region LIKE ?
    """
    recent, prev = conn.execute(q2, [self.d3, self.d6, self.d3, apt_name, f'%{region}%']).fetchone()

    # 3-8: 동일한 패턴으로 나머지 요소 계산
    # ...
    # 점수 합산 (score_region과 동일한 WEIGHTS 사용)
    total = sum(...)
    return {'apt_name': apt_name, 'region': region, 'total_score': total, ...}
```

### SQL 인덱스 최적화
```sql
-- 단지명 검색 속도 10배 향상
CREATE INDEX IF NOT EXISTS idx_apt_trade_apt_name ON apt_trade(apt_name);
CREATE INDEX IF NOT EXISTS idx_apt_rent_apt_name ON apt_rent(apt_name);
```

### 대시보드 UI
```
🏢 아파트 단위 추천 (Phase 1)
┌─────────────────────────────────────────┐
│  🔍 아파트 검색: [________________]    │
│  📍 지역 필터: [강남구 ▼]              │
├─────────────────────────────────────────┤
│ 🏆 매수 추천 아파트 TOP 20             │
│ ┌──────┬──────────────┬────┬────┬────┐  │
│ │ 순위 │ 아파트명     │ 점수│등급│갭  │  │
│ ├──────┼──────────────┼────┼────┼────┤  │
│ │ 1    │ 래미안퍼스티지│ 78 │✅매수│3.2억│  │
│ │ 2    │ 은마아파트   │ 72 │✅매수│2.1억│  │
│ │ ...  │              │    │    │    │  │
│ └──────┴──────────────┴────┴────┴────┘  │
└─────────────────────────────────────────┘
```

**우선순위: ⭐⭐⭐⭐⭐ (5/5)**
**예상 작업량: ~300줄, 2-3일**
**리스크:** 단지별 데이터 부족 시 처리 (거래 3건 미만 = 점수 불신)

---

## Phase 2: Watchlist + 가격 변동 알림 🔔

**핵심:** 사용자가 "관심 단지"를 등록하면, 가격 변동/신호 변화를 자동 알림

### DB 변경
```sql
CREATE TABLE watchlist (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id TEXT DEFAULT 'default',
    apt_name TEXT NOT NULL,
    region TEXT NOT NULL,
    alert_on_price_change BOOLEAN DEFAULT 1,
    alert_threshold_pct REAL DEFAULT 3.0,  -- 3% 이상 변동 시 알림
    last_score REAL,     -- 마지막 추천 점수
    last_price REAL,     -- 마지막 매매가
    created_at TEXT DEFAULT (datetime('now')),
    UNIQUE(user_id, apt_name, region)
);

CREATE TABLE price_alerts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    watchlist_id INTEGER,
    alert_type TEXT,  -- 'price_up', 'price_down', 'signal_change'
    old_value REAL,
    new_value REAL,
    message TEXT,
    created_at TEXT DEFAULT (datetime('now')),
    notified BOOLEAN DEFAULT 0
);
```

### 수정 파일
| 파일 | 변경량 | 설명 |
|------|:------:|:-----|
| `data/database.py` | +30줄 | watchlist 테이블 생성 |
| `strategy/recommender.py` | +50줄 | `check_watchlist()` + `alert_on_change()` |
| `scripts/alert_engine.py` | +80줄 | watchlist 체크 + 가격변동 감지 |
| `dashboard.py` | +60줄 | 관심 단지 등록 UI |
| `main.py` | +20줄 | `python main.py watchlist add/remove/list/check` |

### 알림 로직
```python
def check_watchlist():
    """모든 watchlist 단지의 가격/점수 변동 체크"""
    rows = conn.execute("SELECT * FROM watchlist").fetchall()
    alerts = []
    for row in rows:
        # 현재 가격 조회
        cur_price = conn.execute("""
            SELECT AVG(price) FROM apt_trade
            WHERE apt_name = ? AND region LIKE ? AND deal_date >= ?
        """, [row.apt_name, f'%{row.region}%', d6]).fetchone()[0]

        # 현재 점수 조회
        engine = RecommendationEngine()
        cur_score = engine.score_apt(row.apt_name, row.region)['total_score']

        # 변동 체크
        if cur_price and row.last_price:
            pct = (cur_price - row.last_price) / row.last_price * 100
            if abs(pct) >= row.alert_threshold_pct:
                msg = f"🚨 {row.apt_name} 가격 {pct:+.1f}% 변동!"
                alerts.append(msg)

        if row.last_score and abs(cur_score - row.last_score) > 10:
            msg = f"📊 {row.apt_name} 추천점수 {row.last_score}→{cur_score}점 변동!"
            alerts.append(msg)

    return alerts
```

### 텔레그램 알림 예시
```
🔔 관심 단지 알림 — 2026-06-12

🚨 래미안퍼스티지 가격 변동
  • 기존: 25.3억 → 현재: 26.8억 (+5.9%)
  • 전세가율: 68% → 65%
  • 추천: ➡️ 관망 (점수 72점)

📊 은마아파트 추천 점수 변동
  • 기존: 45점 (⚠️ 매도) → 현재: 68점 (✅ 매수)
  • 이유: 전세가율 82%→74% 하락, 갭 1.8억 발생
```

**우선순위: ⭐⭐⭐⭐ (4/5)**
**예상 작업량: ~250줄, 3-4일**
**리스크:** 알림 과다 발생 가능 (threshold 조절 필요)

---

## Phase 3: ML 고도화 + 예측 정확도 향상 🤖

**핵심:** 단순 선형회귀 → XGBoost + 특성 공학

### 수정 파일
| 파일 | 변경량 | 설명 |
|------|:------:|:-----|
| `analysis/prediction.py` | +200줄 | XGBoost 예측 모델 |
| `analysis/features.py` | 신규 +150줄 | 특성 엔지니어링 |
| `strategy/recommender.py` | +50줄 | ML 점수 보정 |
| `requirements.txt` | +2줄 | `xgboost`, `scipy` |

### 특성 엔지니어링 (features.py)
```python
def build_features(apt_name, region):
    """단지별 ML 학습 특성 벡터 생성"""
    features = {
        # 가격 특성
        'price_3m_avg': ...,    # 3개월 평균 매매가
        'price_6m_trend': ...,  # 6개월 가격 추세 (기울기)
        'price_volatility': ...,# 가격 변동성 (std/mean)
        'last_price': ...,      # 최근 거래가
        'days_since_last_trade': ...,

        # 전세 특성
        'jeonse_rate': ...,     # 현재 전세가율
        'jeonse_rate_3m_change': ..., # 전세가율 3개월 변화
        'jeonse_rate_6m_trend': ...,  # 전세가율 추세

        # 거래 특성
        'trade_volume_3m': ..., # 3개월 거래량
        'trade_volume_momentum': ..., # 거래량 모멘텀
        'avg_trade_size': ...,  # 평균 거래 금액

        # 외부 특성 (추후)
        'interest_rate': ...,   # 한국은행 기준금리
        'school_score': ...,    # 학군 점수
        'subway_dist': ...,     # 역세권 거리

        # 계절성
        'month_sin': np.sin(2*np.pi*month/12),
        'month_cos': np.cos(2*np.pi*month/12),
    }
    return features
```

### XGBoost 학습 파이프라인
```python
from xgboost import XGBRegressor
from sklearn.model_selection import TimeSeriesSplit

def train_price_model(region):
    """지역별 가격 예측 모델 학습"""
    df = load_training_data(region)  # 5년치 데이터
    X = build_feature_matrix(df)
    y = df['price_3m_future']  # 3개월 후 가격

    tscv = TimeSeriesSplit(n_splits=5)
    model = XGBRegressor(
        n_estimators=200,
        max_depth=6,
        learning_rate=0.05,
        early_stopping_rounds=20
    )

    for train_idx, val_idx in tscv.split(X):
        X_train, X_val = X[train_idx], X[val_idx]
        y_train, y_val = y[train_idx], y[val_idx]
        model.fit(X_train, y_train, eval_set=[(X_val, y_val)])

    return model
```

### 점수 보정 (Recommender 보강)
```python
def score_apt_with_ml(self, apt_name, region):
    # 8개 요소 점수 (기존)
    base_result = self.score_apt(apt_name, region)

    # ML 예측 점수 (신규)
    ml_pred = predict_apt_price_ml(apt_name, region)
    ml_score = normalize_to_0_100(ml_pred)

    # 가중 합산 (기존 70% + ML 30%)
    final_score = base_result['total_score'] * 0.7 + ml_score * 0.3
    return {**base_result, 'total_score': final_score, 'ml_prediction': ml_pred}
```

**우선순위: ⭐⭐⭐ (3/5)**
**예상 작업량: ~400줄, 1-2주**
**리스크:** 과적합 위험, 데이터 부족 단지 (거래 10건 미만) 처리 필요

---

## Phase 4: 포트폴리오 시뮬레이터 + 백테스팅 📊

**핵심:** 가상 예산으로 매수/매도 시뮬레이션, 과거 데이터로 알고리즘 검증

### 수정 파일
| 파일 | 변경량 | 설명 |
|------|:------:|:-----|
| `strategy/portfolio.py` | 신규 +300줄 | 포트폴리오 시뮬레이터 |
| `strategy/backtest.py` | 신규 +250줄 | 백테스팅 엔진 |
| `dashboard.py` | +150줄 | "📊 포트폴리오" 탭 |
| `main.py` | +30줄 | CLI 명령어 |

### 포트폴리오 시뮬레이터 (portfolio.py)
```python
class Portfolio:
    def __init__(self, budget=5):  # 5억 시작
        self.cash = budget * 10000  # 만원 단위
        self.holdings = []  # [{'apt': '래미안', 'bought_at': 250000, 'qty': 1, 'date': '...'}]
        self.trade_log = []

    def buy(self, apt_name, region, price, date):
        """매수 실행"""
        if price > self.cash:
            return False, "잔액 부족"
        self.holdings.append({
            'apt': apt_name, 'region': region,
            'bought_at': price, 'qty': 1, 'date': date
        })
        self.cash -= price
        self.trade_log.append({'type': 'BUY', 'apt': apt_name, 'price': price, 'date': date})
        return True, "매수 완료"

    def sell(self, apt_name, price, date):
        """매도 실행"""
        for h in self.holdings:
            if h['apt'] == apt_name:
                profit = price - h['bought_at']
                self.cash += price
                self.holdings.remove(h)
                self.trade_log.append({
                    'type': 'SELL', 'apt': apt_name,
                    'price': price, 'profit': profit, 'date': date
                })
                return True, f"매도 완료 (수익 {profit/10000:.1f}억)"
        return False, "보유 단지 없음"

    def total_value(self):
        """총 자산 = 현금 + 보유 단지 평가액"""
        holdings_value = sum(h['bought_at'] for h in self.holdings)
        return self.cash + holdings_value

    def report(self):
        """성과 리포트"""
        total_invested = sum(t['price'] for t in self.trade_log if t['type'] == 'BUY')
        total_profit = sum(t.get('profit', 0) for t in self.trade_log if t['type'] == 'SELL')
        return {
            'cash': self.cash / 10000,
            'holdings': len(self.holdings),
            'total_value': self.total_value() / 10000,
            'return_pct': (total_profit / total_invested * 100) if total_invested > 0 else 0,
            'trade_count': len(self.trade_log)
        }
```

### 백테스팅 (backtest.py)
```python
def backtest_strategy(region, start_date='2020-01-01', end_date='2025-05-31'):
    """과거 데이터로 추천 알고리즘 백테스팅"""
    engine = RecommendationEngine()
    portfolio = Portfolio(budget=10)  # 10억으로 시작

    # 월별 리밸런싱 시뮬레이션
    months = get_month_range(start_date, end_date)
    for month in months:
        # 해당 월의 추천 단지 조회
        engine.ref_date = month  # 기준일 변경
        recommendations = engine.find_best_apts(region, top_n=3)

        # 추천 단지 매수
        for apt in recommendations:
            if apt['total_score'] >= 65:  # 매수 신호
                price = get_price_at(apt['apt_name'], month)
                portfolio.buy(apt['apt_name'], region, price, month)

        # 매도 신호 체크
        for holding in portfolio.holdings[:]:
            score = engine.score_apt(holding['apt'], region)['total_score']
            if score < 40:  # 매도 신호
                price = get_price_at(holding['apt'], month)
                portfolio.sell(holding['apt'], price, month)

    return portfolio.report()
```

**우선순위: ⭐⭐⭐ (3/5)**
**예상 작업량: ~550줄, 2-3주**
**리스크:** 과최적화(backtest overfitting) 위험, 실제 거래와 괴리 가능

---

## Phase 5: 데이터 소스 확장 🌐

**핵심:** 실거래가(MOLIT)만으로는 부족. 호가/매물/학군/교통 데이터 통합

### 우선순위 데이터 소스

| 소스 | 데이터 | 난이도 | 우선순위 | 수집 방식 |
|:-----|:-------|:------:|:--------:|:---------|
| KB부동산 시세 | 호가/매물/실거래가 | 중 | 5 | OpenAPI (무료 신청) |
| 네이버 부동산 | 현재 매물/가격/매물건수 | 상 | 4 | 비공개 API/크롤링 |
| 직방 (기존) | 월세 매물 | 하 | 3 | 이미 구현됨 |
| 교육부 학교정보 | 학군/학교평가 | 중 | 3 | OpenAPI |
| 국토부 GTX/철도 | 역세권/개통예정 | 중 | 2 | GeoJSON |
| 네이버 뉴스 | 부동산 뉴스 센티멘트 | 상 | 2 | RSS/크롤링 |
| 한국은행 | 기준금리 | 하 | 1 | CSV 다운로드 |

### DB 스키마 확장
```sql
-- KB부동산 시세
CREATE TABLE kb_price (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    apt_name TEXT,
    region TEXT,
    price_type TEXT,  -- '매매', '전세', '월세'
    low_price REAL,
    avg_price REAL,
    high_price REAL,
    collected_at TEXT DEFAULT (datetime('now'))
);

-- 학군 정보
CREATE TABLE school_districts (
    apt_name TEXT,
    region TEXT,
    elementary_school TEXT,
    middle_school TEXT,
    school_rating REAL,  -- 1-10
    distance_km REAL,
    UNIQUE(apt_name, region)
);
```

**우선순위: ⭐⭐ (2/5) — Phase 1-4 완료 후 진행**
**예상 작업량: 소스당 200-500줄, 총 4-6주**

---

## 종합 타임라인

```
Phase 1 (단지 추천)    ████████████░░░░░░  2주  ← 지금 여기
Phase 2 (알림/모니터링)  ░░░░░░████████░░░░  3주
Phase 3 (ML 고도화)     ░░░░░░░░░░████████  2주
Phase 4 (백테스팅)      ░░░░░░░░░░░░░░████  3주
Phase 5 (데이터 확장)    ░░░░░░░░░░░░░░░░░░  6주 (병행 가능)
                      ─────────────────────
                       총 약 10-12주
```

### 전체 파일 변경 요약

| 파일 | Phase 1 | Phase 2 | Phase 3 | Phase 4 | Phase 5 |
|:-----|:-------:|:-------:|:-------:|:-------:|:-------:|
| `strategy/recommender.py` | ✅ +200 | ✅ +50 | ✅ +50 | | |
| `analysis/prediction.py` | | | ✅ +200 | | |
| `analysis/features.py` | | | 🆕 +150 | | |
| `strategy/portfolio.py` | | | | 🆕 +300 | |
| `strategy/backtest.py` | | | | 🆕 +250 | |
| `scripts/alert_engine.py` | | ✅ +80 | | | |
| `data/database.py` | ✅ +10 | ✅ +30 | | | ✅ +50 |
| `dashboard.py` | ✅ +100 | ✅ +60 | | ✅ +150 | |
| `main.py` | ✅ +30 | ✅ +20 | | ✅ +30 | |
| `collectors/kb.py` | | | | | 🆕 +200 |
| `requirements.txt` | | | ✅ +2 | | ✅ +3 |

### 핵심 권장사항

1. **Phase 1부터 시작** — 단지 단위 추천이 전체 시스템의 기초
2. **Phase 1 완료 후 바로 Phase 2** — 알림 기능이 실사용 가치를 높임
3. **Phase 3(ML)은 선택** — 충분한 데이터가 쌓인 후 진행 (단지당 10건 이상 거래)
4. **SQL 인덱스는 지금 바로** — `apt_name` 인덱스가 Phase 1-4 전체의 성능을 결정
5. **Phase 1+2 동시 진행 가능** — 파일이 겹치지 않아 병행 작업 가능
