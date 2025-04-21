# arbitrage.py
import ccxt.async_support as ccxt
import aiohttp
import asyncio
import logging
from config import BINANCE_API_KEY, BINANCE_API_SECRET, BYBIT_API_KEY, BYBIT_API_SECRET, OKX_API_KEY, OKX_API_SECRET, NBU_API_URL, SUPPORTED_PAIRS

logging.basicConfig(filename='logs/arbitrage.log', level=logging.INFO)

class ArbitrageBot:
    def __init__(self):
        self.exchanges = {
            'binance': ccxt.binance({'apiKey': BINANCE_API_KEY, 'secret': BINANCE_API_SECRET, 'enableRateLimit': True}),
            'bybit': ccxt.bybit({'apiKey': BYBIT_API_KEY, 'secret': BYBIT_API_SECRET, 'enableRateLimit': True}),
            'okx': ccxt.okx({'apiKey': OKX_API_KEY, 'secret': OKX_API_SECRET, 'enableRateLimit': True})
        }
        self.fees = {
            'binance': {'spot': {'maker': 0.001, 'taker': 0.001}, 'p2p': 0.0, 'network': {'USDT': 1.0}},
            'bybit': {'spot': {'maker': 0.001, 'taker': 0.001}, 'p2p': 0.0, 'network': {'USDT': 0.8}},
            'okx': {'spot': {'maker': 0.0008, 'taker': 0.001}, 'p2p': 0.0, 'network': {'USDT': 0.9}}
        }
        self.uah_usd = 0.0

    async def fetch_uah_usd_rate(self):
        async with aiohttp.ClientSession() as session:
            async with session.get(NBU_API_URL) as response:
                data = await response.json()
                for rate in data:
                    if rate['cc'] == 'USD':
                        self.uah_usd = rate['rate']
                        return self.uah_usd
        return 0.0

    async def fetch_prices(self, symbol):
        prices = {}
        for ex_name, ex in self.exchanges.items():
            try:
                ticker = await ex.fetch_ticker(symbol)
                order_book = await ex.fetch_order_book(symbol, limit=10)
                liquidity = sum([bid[1] for bid in order_book['bids'][:5]])  # Ліквідність на покупку
                prices[ex_name] = {'bid': ticker['bid'], 'ask': ticker['ask'], 'liquidity': liquidity}
            except Exception as e:
                logging.error(f"Помилка отримання {symbol} з {ex_name}: {e}")
        return prices

    async def fetch_p2p_prices(self, crypto='USDT', fiat='UAH', amount=10000):
        p2p_prices = {}
        for ex_name, ex in self.exchanges.items():
            try:
                # Приклад для Binance P2P (інші біржі потребують окремої реалізації)
                if ex_name == 'binance':
                    p2p_data = await ex.private_post_p2p_order_list({'fiat': fiat, 'transAmount': amount})
                    p2p_prices[ex_name] = {'buy': p2p_data['data'][0]['price'], 'sell': p2p_data['data'][0]['price']}
                # Додайте P2P для Bybit, OKX
            except Exception as e:
                logging.error(f"Помилка отримання P2P {crypto}/{fiat} з {ex_name}: {e}")
        return p2p_prices

    async def calculate_inter_exchange_arbitrage(self, symbol, amount):
        prices = await self.fetch_prices(symbol)
        opportunities = []
        for buy_ex, buy_data in prices.items():
            for sell_ex, sell_data in prices.items():
                if buy_ex != sell_ex and buy_data['liquidity'] > amount:
                    buy_price = buy_data['ask']
                    sell_price = sell_data['bid']
                    if buy_price and sell_price:
                        buy_fee = buy_price * amount * self.fees[buy_ex]['spot']['taker']
                        sell_fee = sell_price * amount * self.fees[sell_ex]['spot']['taker']
                        network_fee = self.fees[buy_ex]['network']['USDT'] + self.fees[sell_ex]['network']['USDT']
                        profit = (sell_price * amount - sell_fee) - (buy_price * amount + buy_fee + network_fee)
                        profit_percent = (profit / (buy_price * amount)) * 100
                        if profit_percent > 0:
                            opportunities.append({
                                'buy_exchange': buy_ex,
                                'sell_exchange': sell_ex,
                                'buy_price': buy_price,
                                'sell_price': sell_price,
                                'profit': profit,
                                'profit_percent': profit_percent
                            })
        return sorted(opportunities, key=lambda x: x['profit_percent'], reverse=True)

    async def calculate_intra_exchange_arbitrage(self, ex_name, symbols=['BTC/USDT', 'ETH/USDT', 'BTC/ETH']):
        ex = self.exchanges[ex_name]
        try:
            prices = {s: await ex.fetch_ticker(s) for s in symbols}
            btc_usdt = prices['BTC/USDT']['ask']
            btc_eth = prices['BTC/ETH']['ask']
            eth_usdt = prices['ETH/USDT']['bid']
            amount = 1  # 1 BTC
            eth_amount = amount / btc_eth
            usdt_amount = eth_amount * eth_usdt
            final_btc = usdt_amount / prices['BTC/USDT']['bid']
            profit = final_btc - amount
            fees = (btc_usdt * self.fees[ex_name]['spot']['taker'] +
                    eth_amount * prices['ETH/USDT']['ask'] * self.fees[ex_name]['spot']['taker'] +
                    usdt_amount * self.fees[ex_name]['spot']['taker'])
            profit_percent = ((profit - fees) / amount) * 100
            if profit_percent > 0:
                return [{
                    'exchange': ex_name,
                    'path': 'BTC -> ETH -> USDT -> BTC',
                    'profit': profit - fees,
                    'profit_percent': profit_percent
                }]
        except Exception as e:
            logging.error(f"Помилка внутрішньобіржового арбітражу на {ex_name}: {e}")
        return []

    async def calculate_p2p_arbitrage(self, crypto='USDT', fiat='UAH', amount=10000):
        p2p_prices = await self.fetch_p2p_prices(crypto, fiat, amount)
        opportunities = []
        for buy_ex, buy_data in p2p_prices.items():
            for sell_ex, sell_data in p2p_prices.items():
                if buy_ex != sell_ex:
                    buy_price = buy_data['buy']
                    sell_price = sell_data['sell']
                    if buy_price and sell_price:
                        profit = (sell_price * amount) - (buy_price * amount)
                        profit_percent = (profit / (buy_price * amount)) * 100
                        if profit_percent > 0:
                            opportunities.append({
                                'buy_exchange': buy_ex,
                                'sell_exchange': sell_ex,
                                'buy_price': buy_price,
                                'sell_price': sell_price,
                                'profit': profit,
                                'profit_percent': profit_percent
                            })
        return sorted(opportunities, key=lambda x: x['profit_percent'], reverse=True)

    async def close_exchanges(self):
        for ex in self.exchanges.values():
            await ex.close()