"""
포트폴리오 시뮬레이터 — 가상 매매 내역 관리
"""
from datetime import datetime


class Holding:
    """보유 단지 정보"""
    def __init__(self, apt_name, region, buy_price, buy_date, quantity=1):
        self.apt_name = apt_name
        self.region = region
        self.buy_price = buy_price      # 매수 당시 가격 (만원)
        self.buy_date = buy_date
        self.quantity = quantity

    def current_value(self, current_price):
        """현재 평가액 (만원)"""
        return current_price * self.quantity

    def profit_pct(self, current_price):
        """수익률 (%)"""
        if self.buy_price == 0:
            return 0.0
        return (current_price - self.buy_price) / self.buy_price * 100

    def __repr__(self):
        return (f"Holding({self.apt_name}, buy={self.buy_price}만원, "
                f"qty={self.quantity}, date={self.buy_date})")


class Portfolio:
    """
    가상 부동산 포트폴리오

    Parameters
    ----------
    budget : int
        초기 예산 (억원, 기본 5 → 5억원)
    """

    def __init__(self, budget=5):
        self.initial_budget = budget * 10000          # 만원 단위
        self.cash = self.initial_budget               # 가용 현금 (만원)
        self.holdings = []                            # 보유 단지 목록
        self.trade_log = []                           # 매매 내역
        self._current_prices = {}                     # 최신 가격 캐시

    # ── 매수 ──────────────────────────────────────────

    def buy(self, apt_name, region, price, date):
        """
        단지 매수

        Parameters
        ----------
        apt_name : str
        region : str
        price : int
            매수 가격 (만원)
        date : str
            YYYY-MM-DD

        Returns
        -------
        bool : 성공 여부
        """
        if self.cash < price:
            return False

        holding = Holding(apt_name, region, price, date)
        self.holdings.append(holding)
        self.cash -= price
        self._current_prices[apt_name] = price
        self.trade_log.append({
            'type': 'BUY',
            'apt_name': apt_name,
            'region': region,
            'price': price,
            'date': date,
            'cash_after': self.cash,
        })
        return True

    # ── 매도 ──────────────────────────────────────────

    def sell(self, apt_name, price, date):
        """
        단지 매도

        Returns
        -------
        bool : 성공 여부
        """
        for i, h in enumerate(self.holdings):
            if h.apt_name == apt_name:
                proceeds = price * h.quantity
                self.cash += proceeds
                self._current_prices.pop(apt_name, None)
                self.trade_log.append({
                    'type': 'SELL',
                    'apt_name': apt_name,
                    'region': h.region,
                    'price': price,
                    'date': date,
                    'profit_pct': round(h.profit_pct(price), 2),
                    'cash_after': self.cash,
                })
                self.holdings.pop(i)
                return True
        return False

    # ── 평가 ──────────────────────────────────────────

    def total_value(self, price_map=None):
        """
        총 포트폴리오 가치 (현금 + 보유 단지 평가액)

        Parameters
        ----------
        price_map : dict, optional
            {apt_name: current_price} — 없으면 매수 가격 그대로 사용

        Returns
        -------
        int : 총 평가액 (만원)
        """
        total = self.cash
        for h in self.holdings:
            cp = (price_map or {}).get(h.apt_name, h.buy_price)
            total += h.current_value(cp)
        return total

    def total_return_pct(self, price_map=None):
        """전체 수익률 (%)"""
        tv = self.total_value(price_map)
        if self.initial_budget == 0:
            return 0.0
        return (tv - self.initial_budget) / self.initial_budget * 100

    def update_price(self, apt_name, price):
        """현재가 업데이트 (평가용)"""
        self._current_prices[apt_name] = price

    # ── 리포트 ────────────────────────────────────────

    def report(self, price_map=None):
        """
        포트폴리오 리포트 반환

        Returns
        -------
        dict
        """
        tv = self.total_value(price_map)
        pm = price_map or self._current_prices
        holding_details = []
        for h in self.holdings:
            cp = pm.get(h.apt_name, h.buy_price)
            holding_details.append({
                'apt_name': h.apt_name,
                'region': h.region,
                'buy_price': h.buy_price,
                'current_price': cp,
                'profit_pct': round(h.profit_pct(cp), 2),
                'buy_date': h.buy_date,
            })

        return {
            'initial_budget_ok': round(self.initial_budget / 10000, 1),
            'cash_ok': round(self.cash / 10000, 1),
            'holdings_value_ok': round((tv - self.cash) / 10000, 1),
            'total_value_ok': round(tv / 10000, 1),
            'total_return_pct': round(self.total_return_pct(pm), 2),
            'num_holdings': len(self.holdings),
            'num_trades': len(self.trade_log),
            'holdings': holding_details,
        }

    def print_report(self, price_map=None):
        """CLI용 리포트 출력"""
        r = self.report(price_map)
        print(f"\n{'='*55}")
        print(f"  📊 포트폴리오 리포트")
        print(f"{'='*55}")
        print(f"  초기 예산:     {r['initial_budget_ok']}억원")
        print(f"  가용 현금:     {r['cash_ok']}억원")
        print(f"  보유 자산:     {r['holdings_value_ok']}억원")
        print(f"  총 평가액:     {r['total_value_ok']}억원")
        print(f"  총 수익률:     {r['total_return_pct']:+.2f}%")
        print(f"  보유 단지:     {r['num_holdings']}개")
        print(f"  총 거래:       {r['num_trades']}회")
        if r['holdings']:
            print(f"\n  ── 보유 내역 ──")
            for h in r['holdings']:
                bar_len = int(min(abs(h['profit_pct']), 50) / 5)
                bar = '█' * bar_len if h['profit_pct'] >= 0 else '░' * bar_len
                print(f"  {h['apt_name']:12s} | 매수 {h['buy_price']/10000:.1f}억 → "
                      f"{h['current_price']/10000:.1f}억 | {h['profit_pct']:+.2f}% {bar}")
        print(f"{'='*55}")
        return r

    def trade_history(self):
        """거래 내역 DataFrame (list of dict)"""
        return self.trade_log
