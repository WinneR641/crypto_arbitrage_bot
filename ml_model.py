import pandas as pd
import numpy as np
from sklearn.ensemble import RandomForestRegressor
from sklearn.model_selection import train_test_split
import os
import logging

logging.basicConfig(filename='logs/ml_model.log', level=logging.INFO, encoding='utf-8')

class ArbitragePredictor:
    def __init__(self):
        self.model = RandomForestRegressor(n_estimators=100, random_state=42)
        self.data_dir = 'data'

    def load_data(self, exchange, symbol):
        file_path = f'{self.data_dir}/prices_{exchange}_{symbol.replace("/", "_")}.csv'
        if os.path.exists(file_path):
            df = pd.read_csv(file_path)
            df['timestamp'] = pd.to_datetime(df['timestamp'])
            df['spread'] = df['ask'] - df['bid']
            df['price_change'] = df['bid'].pct_change()
            df['spread_change'] = df['spread'].pct_change()
            df = df.dropna()
            return df
        return None

    def train_model(self, exchange, symbol):
        df = self.load_data(exchange, symbol)
        if df is None or len(df) < 100:
            logging.warning(f"Недостатньо даних для {exchange} {symbol}")
            return False

        X = df[['bid', 'ask', 'spread', 'price_change', 'spread_change']]
        y = df['spread'].shift(-1)  # Прогнозуємо наступний спред
        X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.2, random_state=42)

        self.model.fit(X_train, y_train)
        score = self.model.score(X_test, y_test)
        logging.info(f"Модель для {exchange} {symbol} навчена, R^2: {score}")
        return score > 0.5

    def predict_spread(self, exchange, symbol, current_data):
        df = self.load_data(exchange, symbol)
        if df is None or not self.train_model(exchange, symbol):
            return None

        latest_data = {
            'bid': current_data['bid'],
            'ask': current_data['ask'],
            'spread': current_data['ask'] - current_data['bid'],
            'price_change': current_data['bid'] / df['bid'].iloc[-1] - 1 if len(df) > 1 else 0,
            'spread_change': (current_data['ask'] - current_data['bid']) / df['spread'].iloc[-1] - 1 if len(df) > 1 else 0
        }
        X = pd.DataFrame([latest_data])
        predicted_spread = self.model.predict(X)[0]
        logging.info(f"Прогноз спреду для {exchange} {symbol}: {predicted_spread}")
        return predicted_spread

    def is_profitable(self, exchange, symbol, current_data):
        predicted_spread = self.predict_spread(exchange, symbol, current_data)
        if predicted_spread is None:
            return False
        current_spread = current_data['ask'] - current_data['bid']
        return predicted_spread > current_spread * 1.1  # Очікуємо зростання спреду на 10%