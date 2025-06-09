#!/usr/bin/env python3
import os
import time
import json
import hmac
import hashlib
import asyncio
import requests
import psutil
import platform
import pandas as pd
import numpy as np
import pickle
import random
from typing import Dict, Optional, Tuple, List
from loguru import logger
from datetime import datetime
from telegram import Bot
from telegram.error import TelegramError
import websockets
from sklearn.ensemble import RandomForestClassifier
from sklearn.preprocessing import StandardScaler
from collections import deque
from bot_monitor import TigerBotMonitor

class BinanceScalperBot:
    def __init__(self):
        self.config = self.load_config()
        if self.config['demo_mode']:
            logger.info("Running in DEMO MODE - no real trades will be executed")
        self.session = self.init_session()
        self.positions = {}
        self.tg_bot = Bot(token=self.config['api']['telegram_token'])
        self.tg_chat_id = self.config['api']['telegram_chat_id']
        self.start_time = datetime.now()
        self.last_stats_sent = datetime.now()
        self.last_signal = None
        self.daily_stats = {'trades': 0, 'wins': 0, 'losses': 0, 'profit': 0.0}
        self.model = None
        self.scaler = StandardScaler()
        self.data_window = deque(maxlen=100)
        self.model_file = 'trading_model.pkl'
        self.scaler_file = 'scaler.pkl'
        self.monitor = TigerBotMonitor()
        self.load_models()

    def load_config(self) -> Dict:
        with open('config.json', 'r', encoding='utf-8') as f:
            return json.load(f)

    def init_session(self) -> requests.Session:
        session = requests.Session()
        session.headers.update({
            'Content-Type': 'application/json',
            'X-MBX-APIKEY': self.config['api']['binance_key']
        })
        return session

    def load_models(self):
        try:
            if os.path.exists(self.model_file):
                with open(self.model_file, 'rb') as f:
                    self.model = pickle.load(f)
                logger.info("Model loaded successfully")

            if os.path.exists(self.scaler_file):
                with open(self.scaler_file, 'rb') as f:
                    self.scaler = pickle.load(f)
                logger.info("Scaler loaded successfully")

        except Exception as e:
            logger.error(f"Error loading models: {str(e)}")
            self.model = RandomForestClassifier(n_estimators=100)
            self.scaler = StandardScaler()

    def prepare_features(self, data_window: List[Dict]) -> np.array:
        if len(data_window) < 50:
            return np.array([])

        df = pd.DataFrame(data_window)
        features = []

        features.append(df['close'].pct_change().iloc[-1] * 100)
        features.append(df['close'].pct_change().rolling(5).mean().iloc[-1] * 100)
        features.append((df['high'].iloc[-1] - df['low'].iloc[-1]) / df['close'].iloc[-1] * 100)

        features.append(df['volume'].pct_change().iloc[-1] * 100)
        features.append(df['volume'].rolling(5).mean().iloc[-1])

        features.append(self._calculate_rsi(df['close'], 14).iloc[-1])
        features.append(self._calculate_ema(df['close'], 3).iloc[-1] - self._calculate_ema(df['close'], 9).iloc[-1])

        return np.array(features)

    def _calculate_rsi(self, series: pd.Series, period: int) -> pd.Series:
        delta = series.diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
        rs = gain / loss
        return 100 - (100 / (1 + rs))

    def _calculate_ema(self, series: pd.Series, period: int) -> pd.Series:
        return series.ewm(span=period, adjust=False).mean()

    def reinforcement_learning(self, market_data: Dict):
        if len(self.data_window) < 50 or not hasattr(self.model, 'partial_fit'):
            return

        try:
            features = self.prepare_features(list(self.data_window))
            if len(features) == 0:
                return

            current_price = market_data['close']
            future_price = self.data_window[-1]['close'] if len(self.data_window) > 0 else current_price
            label = 1 if future_price > current_price else -1

            features_scaled = self.scaler.transform([features])
            self.model.partial_fit(features_scaled, [label], classes=[-1, 1])

            with open(self.model_file, 'wb') as f:
                pickle.dump(self.model, f)

            logger.info("Model updated with new data")

        except Exception as e:
            logger.error(f"RL error: {str(e)}")

    async def generate_demo_data(self):
        price = 50000
        while self.config['demo_mode']:
            price += random.uniform(-100, 100)
            price = max(10000, min(100000, price))
            market_data = {
                'timestamp': int(time.time()),
                'open': price,
                'high': price + random.uniform(0, 50),
                'low': price - random.uniform(0, 50),
                'close': price,
                'volume': random.uniform(1, 10)
            }
            await self.process_market_data(market_data)
            await asyncio.sleep(15)

    async def process_market_data(self, market_data: Dict):
        try:
            self.data_window.append(market_data)

            if len(self.data_window) >= 50:
                features = self.prepare_features(list(self.data_window))

                if len(features) > 0:
                    features_scaled = self.scaler.transform([features])
                    prediction = self.model.predict(features_scaled)[0]

                    if prediction == 1 and not self.positions.get('long'):
                        await self.place_order('BUY', market_data['close'])
                    elif prediction == -1 and self.positions.get('long'):
                        await self.place_order('SELL', market_data['close'])

                    self.reinforcement_learning(market_data)

        except Exception as e:
            logger.error(f"Data processing error: {str(e)}")

    async def place_order(self, side: str, price: float):
        try:
            if self.config['demo_mode']:
                logger.info(f"DEMO TRADE: {side} at {price}")

                if side == 'BUY':
                    self.positions['long'] = {
                        'entry_price': price,
                        'size': self.calculate_position_size(price),
                        'timestamp': datetime.now().timestamp()
                    }
                    self.daily_stats['trades'] += 1
                else:
                    if 'long' in self.positions:
                        position = self.positions['long']
                        profit = (price - position['entry_price']) / position['entry_price'] * 100
                        self.daily_stats['profit'] += profit
                    self.positions.pop('long', None)
                return

        except Exception as e:
            logger.error(f"Order placement failed: {str(e)}")

    async def start_websocket(self):
        uri = "wss://stream.binance.com:9443/ws/btcusdt@kline_15m"
        while True:
            try:
                async with websockets.connect(uri) as websocket:
                    logger.info("WebSocket connected")
                    while True:
                        data = await websocket.recv()
                        data = json.loads(data)
                        kline = data['k']
                        market_data = {
                            'timestamp': kline['t'],
                            'open': float(kline['o']),
                            'high': float(kline['h']),
                            'low': float(kline['l']),
                            'close': float(kline['c']),
                            'volume': float(kline['v'])
                        }
                        await self.process_market_data(market_data)
            except Exception as e:
                logger.error(f"WebSocket error: {str(e)}")
                await asyncio.sleep(30)

    async def send_telegram_message(self, message: str):
        try:
            await self.tg_bot.send_message(
                chat_id=self.tg_chat_id,
                text=message
            )
        except TelegramError as e:
            logger.error(f"Telegram send error: {str(e)}")

    def get_server_stats(self) -> str:
        stats = [
            self.monitor.get_server_stats(),
            "
📈 Trading Performance:",
            f"Trades Today: {self.daily_stats['trades']}",
            f"Win Rate: {self.daily_stats['wins'] / self.daily_stats['trades'] * 100 if self.daily_stats['trades'] > 0 else 0:.2f}%",
            f"Daily P&L: {self.daily_stats['profit']:.2f}%",
            f"Uptime: {datetime.now() - self.start_time}"
        ]
        return "
".join(stats)

    async def run(self):
        logger.info("Starting Binance Scalper Bot")
        await self.send_telegram_message("🟢 Binance Scalper Bot started!")

        if self.config['demo_mode']:
            asyncio.create_task(self.generate_demo_data())
        else:
            if self.config['timeframe'] == '15s':
                asyncio.create_task(self.start_websocket())

        while True:
            try:
                if (datetime.now() - self.last_stats_sent).seconds >= 3600:
                    stats = self.get_server_stats()
                    await self.send_telegram_message(stats)
                    self.last_stats_sent = datetime.now()

                await asyncio.sleep(1)

            except Exception as e:
                logger.error(f"Main loop error: {str(e)}")
                await asyncio.sleep(30)

if __name__ == "__main__":
    bot = BinanceScalperBot()
    asyncio.run(bot.run())