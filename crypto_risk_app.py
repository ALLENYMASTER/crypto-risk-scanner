"""
Crypto Risk Assessment Web Application
Flask server with real-time analysis API and Live Price Display
Run: python crypto_risk_web_app.py
Access: http://localhost:8000
"""

from flask import Flask, render_template_string, jsonify, request
from flask_cors import CORS
import json
import os
import threading
import webbrowser
import requests
from datetime import datetime
from functools import wraps
from collections import defaultdict
import time
# Import your comprehensive tracker
from crypto_risk_scanner import ComprehensiveCryptoRiskTracker

app = Flask(__name__)
CORS(app)

# Global tracker instance
tracker = None

ALLOWED_SYMBOLS = ['BTC', 'ETH']

# Track requests per IP: {ip: {'analyze': [timestamps], 'live_price': [timestamps]}}
request_history = defaultdict(lambda: defaultdict(list))

# Rate limit thresholds
RATE_LIMITS = {
    'analyze': {
        'max_per_hour': 10,
        'max_per_day': 50,
        'window_seconds': 3600  # 1 hour
    },
    'live_price': {
        'max_per_minute': 20,
        'max_per_hour': 500,
        'window_seconds': 60  # 1 minute
    }
}

def check_api_availability():
    """Check which APIs are available in user's region"""
    available_apis = {
        'coingecko': True,  # Usually available everywhere
        'binance': True,
        'okx': True
    }
    
    # Quick test for Binance
    try:
        response = requests.get('https://api.binance.com/api/v3/ping', timeout=5)
        if response.status_code == 451:
            available_apis['binance'] = False
            print("⚠️  Binance API blocked in your region (will use OKX for liquidity)")
    except:
        pass
    
    return available_apis

# Call this at startup (after app initialization, around line 100)
print("\n🔍 Checking API availability...")
api_status = check_api_availability()
if not api_status['binance']:
    print("   ℹ️  Note: Binance unavailable, using alternative data sources")
print()

# Rate limiting decorator
def rate_limit(endpoint_name):
    """
    Decorator to enforce rate limits on API endpoints
    
    Args:
        endpoint_name: 'analyze' or 'live_price'
    """
    def decorator(f):
        @wraps(f)
        def wrapped(*args, **kwargs):
            client_ip = request.remote_addr
            now = time.time()
            
            # Get rate limit config for this endpoint
            config = RATE_LIMITS.get(endpoint_name, {})
            window = config.get('window_seconds', 3600)
            max_requests = config.get('max_per_hour', 10)
            
            # Clean up old request timestamps (outside the time window)
            request_history[client_ip][endpoint_name] = [
                ts for ts in request_history[client_ip][endpoint_name]
                if now - ts < window
            ]
            
            # Check if rate limit exceeded
            request_count = len(request_history[client_ip][endpoint_name])
            
            if request_count >= max_requests:
                # Calculate when the user can retry
                oldest_request = min(request_history[client_ip][endpoint_name])
                retry_after = int(oldest_request + window - now)
                
                return jsonify({
                    'error': f'Rate limit exceeded for {endpoint_name}',
                    'message': f'Maximum {max_requests} requests per {window//60} minutes',
                    'retry_after_seconds': retry_after,
                    'current_count': request_count
                }), 429
            
            # Record this request
            request_history[client_ip][endpoint_name].append(now)
            
            # Execute the original function
            return f(*args, **kwargs)
        
        return wrapped
    return decorator

# Symbol validation function
def validate_symbol(symbol):
    """
    Validate cryptocurrency symbol
    
    Args:
        symbol: Cryptocurrency symbol string
        
    Returns:
        tuple: (is_valid: bool, error_message: str)
    """
    if not symbol:
        return False, "Symbol is required"
    
    # Convert to uppercase for consistency
    symbol = symbol.upper()
    
    # Check if symbol is in allowed list
    if symbol not in ALLOWED_SYMBOLS:
        return False, f"Invalid symbol '{symbol}'. Allowed symbols: {', '.join(ALLOWED_SYMBOLS)}"
    
    return True, symbol

# HTML Template 
HTML_TEMPLATE = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Crypto Risk Assessment System</title>
    <style>
        * {
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }

        body {
            font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
            background: linear-gradient(135deg, #1e3a8a 0%, #3b82f6 50%, #06b6d4 100%);
            min-height: 100vh;
            padding: 20px;
            color: #333;
        }

        .container {
            max-width: 1400px;
            margin: 0 auto;
        }

        .header {
            background: white;
            border-radius: 15px;
            padding: 30px;
            margin-bottom: 20px;
            box-shadow: 0 10px 30px rgba(0,0,0,0.2);
        }

        .header h1 {
            color: #1e3a8a;
            font-size: 2.5em;
            margin-bottom: 10px;
        }

        .header p {
            color: #666;
            font-size: 1.1em;
        }

        .status-indicator {
            display: inline-block;
            width: 12px;
            height: 12px;
            border-radius: 50%;
            margin-right: 8px;
            animation: pulse 2s infinite;
        }

        .status-online {
            background: #22c55e;
        }

        @keyframes pulse {
            0%, 100% {
                opacity: 1;
                transform: scale(1);
            }
            50% {
                opacity: 0.8;
                transform: scale(1.05);
            }
        }

        .controls {
            background: white;
            border-radius: 15px;
            padding: 20px;
            margin-bottom: 20px;
            box-shadow: 0 5px 15px rgba(0,0,0,0.1);
        }

        .input-group {
            display: flex;
            gap: 10px;
            flex-wrap: wrap;
            align-items: center;
        }

        input, select, button {
            padding: 12px 20px;
            border: 2px solid #e0e0e0;
            border-radius: 8px;
            font-size: 1em;
        }

        input:focus, select:focus {
            outline: none;
            border-color: #3b82f6;
        }

        button {
            background: linear-gradient(135deg, #1e3a8a 0%, #3b82f6 100%);
            color: white;
            border: none;
            cursor: pointer;
            font-weight: bold;
            transition: transform 0.2s;
        }

        button:hover {
            transform: translateY(-2px);
        }

        button:disabled {
            opacity: 0.6;
            cursor: not-allowed;
        }

        .dashboard {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(300px, 1fr));
            gap: 20px;
            margin-bottom: 20px;
        }

        .card {
            background: white;
            border-radius: 15px;
            padding: 25px;
            box-shadow: 0 5px 15px rgba(0,0,0,0.1);
        }

        .card h3 {
            color: #1e3a8a;
            margin-bottom: 15px;
            font-size: 1.3em;
        }

        .metric {
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin: 10px 0;
            padding: 10px;
            background: #f8f9fa;
            border-radius: 8px;
        }

        .metric-label {
            font-weight: 500;
            color: #555;
        }

        .metric-value {
            font-weight: bold;
            font-size: 1.1em;
        }

        .score-display {
            text-align: center;
            padding: 30px;
        }

        .score-circle {
            width: 200px;
            height: 200px;
            border-radius: 50%;
            margin: 0 auto 20px;
            display: flex;
            align-items: center;
            justify-content: center;
            flex-direction: column;
            font-size: 3em;
            font-weight: bold;
            color: white;
            box-shadow: 0 10px 30px rgba(0,0,0,0.2);
            transition: all 0.5s ease;
        }

        .action-badge {
            display: inline-block;
            padding: 8px 16px;
            border-radius: 20px;
            font-weight: bold;
            font-size: 1.1em;
            margin-top: 10px;
        }

        .signals-list {
            list-style: none;
        }

        .signals-list li {
            padding: 12px;
            margin: 8px 0;
            background: #f8f9fa;
            border-radius: 8px;
            border-left: 4px solid #3b82f6;
            animation: slideIn 0.3s ease;
        }

        @keyframes slideIn {
            from {
                opacity: 0;
                transform: translateX(-20px);
            }
            to {
                opacity: 1;
                transform: translateX(0);
            }
        }

        .progress-bar {
            width: 100%;
            height: 30px;
            background: #e0e0e0;
            border-radius: 15px;
            overflow: hidden;
            margin: 10px 0;
        }

        .progress-fill {
            height: 100%;
            background: linear-gradient(90deg, #1e3a8a 0%, #3b82f6 100%);
            transition: width 0.5s ease;
            display: flex;
            align-items: center;
            justify-content: flex-end;
            padding-right: 10px;
            color: white;
            font-weight: bold;
        }

        .loading {
            text-align: center;
            padding: 40px;
            font-size: 1.2em;
            color: #1e3a8a;
        }

        .spinner {
            border: 4px solid #f3f3f3;
            border-top: 4px solid #3b82f6;
            border-radius: 50%;
            width: 50px;
            height: 50px;
            animation: spin 1s linear infinite;
            margin: 20px auto;
        }

        @keyframes spin {
            0% { transform: rotate(0deg); }
            100% { transform: rotate(360deg); }
        }

        .positive { color: #22c55e; }
        .negative { color: #ef4444; }
        .neutral { color: #f59e0b; }

        .tabs {
            display: flex;
            gap: 10px;
            margin-bottom: 20px;
            flex-wrap: wrap;
        }

        .tab {
            padding: 12px 24px;
            background: white;
            border: 2px solid #e0e0e0;
            border-radius: 8px;
            cursor: pointer;
            transition: all 0.3s;
        }

        .tab.active {
            background: linear-gradient(135deg, #1e3a8a 0%, #3b82f6 100%);
            color: white;
            border-color: #3b82f6;
        }

        .tab-content {
            display: none;
        }

        .tab-content.active {
            display: block;
            animation: fadeIn 0.3s ease;
        }

        @keyframes fadeIn {
            from { opacity: 0; }
            to { opacity: 1; }
        }

        .suggestions-card {
            background: linear-gradient(135deg, #f093fb 0%, #f5576c 100%);
            color: white;
        }

        .suggestions-card h3 {
            color: white;
        }

        .suggestion-item {
            background: rgba(255,255,255,0.2);
            padding: 15px;
            border-radius: 8px;
            margin: 10px 0;
            backdrop-filter: blur(10px);
        }

        .disclaimer {
            background: #fff3cd;
            border: 2px solid #ffc107;
            border-radius: 10px;
            padding: 20px;
            margin-top: 20px;
            color: #856404;
        }

        .error-message {
            background: #fee;
            border: 2px solid #f88;
            border-radius: 10px;
            padding: 15px;
            margin: 10px 0;
            color: #c33;
        }

        .success-message {
            background: #efe;
            border: 2px solid #8f8;
            border-radius: 10px;
            padding: 15px;
            margin: 10px 0;
            color: #383;
        }

        .price-alert {
            position: fixed;
            top: 20px;
            right: 20px;
            background: white;
            border: 3px solid #3b82f6;
            border-radius: 15px;
            padding: 20px;
            box-shadow: 0 10px 40px rgba(0,0,0,0.3);
            z-index: 1000;
            min-width: 300px;
            animation: slideInRight 0.5s ease;
        }

        .price-alert.support {
            border-color: #22c55e;
        }

        .price-alert.resistance {
            border-color: #ef4444;
        }

        .price-alert h4 {
            margin: 0 0 10px 0;
            font-size: 1.3em;
        }

        .price-alert .close-btn {
            position: absolute;
            top: 10px;
            right: 10px;
            background: none;
            border: none;
            font-size: 1.5em;
            cursor: pointer;
            padding: 0;
            width: 30px;
            height: 30px;
            color: #666;
        }

        @keyframes slideInRight {
            from {
                transform: translateX(400px);
                opacity: 0;
            }
            to {
                transform: translateX(0);
                opacity: 1;
            }
        }

        /* UPDATED: Live price badge styling */
        .live-price-container {
            display: inline-flex;
            align-items: center;
            gap: 10px;
            margin-left: 10px;
        }

        .live-price-badge {
            display: inline-flex;
            align-items: center;
            gap: 8px;
            background: linear-gradient(135deg, #22c55e 0%, #16a34a 100%);
            color: white;
            padding: 8px 16px;
            border-radius: 20px;
            font-weight: bold;
            font-size: 1em;
            box-shadow: 0 4px 12px rgba(34, 197, 94, 0.3);
        }

        .live-indicator {
            width: 8px;
            height: 8px;
            background: white;
            border-radius: 50%;
            animation: livePulse 1.5s infinite;
        }

        @keyframes livePulse {
            0%, 100% {
                opacity: 1;
                transform: scale(1);
            }
            50% {
                opacity: 0.5;
                transform: scale(1.2);
            }
        }

        .live-price-value {
            font-size: 1.1em;
            font-weight: bold;
            transition: color 0.3s ease;
        }

        .price-change-indicator {
            font-size: 0.9em;
            margin-left: 5px;
        }

        @media (max-width: 768px) {
            .header h1 {
                font-size: 1.8em;
            }
            .dashboard {
                grid-template-columns: 1fr;
            }
            .score-circle {
                width: 150px;
                height: 150px;
                font-size: 2em;
            }
            .live-price-container {
                flex-direction: column;
                align-items: flex-start;
                margin-left: 0;
                margin-top: 10px;
            }
        }
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>🎯 Crypto Risk Assessment System</h1>
            <p>
                <span class="status-indicator status-online"></span>
                Live Analysis • Professional-grade comprehensive analysis
            </p>
        </div>

        <div class="controls">
            <div class="input-group">
                <select id="symbolSelect">
                    <option value="BTC">Bitcoin (BTC)</option>
                    <option value="ETH">Ethereum (ETH)</option>
                </select>
                <button id="analyzeBtn" onclick="analyzeSymbol()">🔍 Analyze Now</button>
                <span id="statusText" style="color: #666;"></span>
                <!-- UPDATED: Live price display area -->
                <div id="livePriceContainer" class="live-price-container" style="display: none;">
                    <div class="live-price-badge">
                        <span class="live-indicator"></span>
                        <span>LIVE</span>
                    </div>
                    <div>
                        <span id="livePrice" class="live-price-value">$0.00</span>
                        <span id="livePriceChange" class="price-change-indicator"></span>
                    </div>
                </div>
            </div>
        </div>

        <div id="loading" class="loading" style="display: none;">
            <div class="spinner"></div>
            <p>Analyzing <span id="loadingSymbol"></span>... Fetching data from multiple sources.</p>
            <p style="font-size: 0.9em; color: #999; margin-top: 10px;">This may take 3-4 minutes...</p>
        </div>

        <div id="results" style="display: none;">
            <div class="tabs">
                <div class="tab active" onclick="switchTab('overview')">📊 Overview</div>
                <div class="tab" onclick="switchTab('technical')">📈 Technical</div>
                <div class="tab" onclick="switchTab('onchain')">⛓️ On-Chain</div>
                <div class="tab" onclick="switchTab('returns')" id="returnsTab">
                    📊 Returns
                    <span id="returnsBadge" style="margin-left: 8px; padding: 2px 8px; background: #999; color: white; border-radius: 10px; font-size: 0.75em; font-weight: bold;">
                        ...
                    </span>
                </div>
                <div class="tab" onclick="switchTab('suggestions')">💡 Suggestions</div>
            </div>

            <div id="overview" class="tab-content active">
                <div class="dashboard">
                    <div class="card">
                        <div class="score-display">
                            <div id="scoreCircle" class="score-circle">
                                <div>
                                    <div id="scoreValue">0</div>
                                    <div style="font-size: 0.3em;">/ 100</div>
                                </div>
                            </div>
                            <div id="actionBadge" class="action-badge">ANALYZING...</div>
                            <div id="riskLevel" style="margin-top: 10px; color: #666;">Risk Level: -</div>
                        </div>
                    </div>

                    <div class="card">
                        <h3>💵 Market Data</h3>
                        <div class="metric">
                            <span class="metric-label">Price</span>
                            <span id="price" class="metric-value">-</span>
                        </div>
                        <div class="metric">
                            <span class="metric-label">24h Change</span>
                            <span id="change24h" class="metric-value">-</span>
                        </div>
                        <div class="metric">
                            <span class="metric-label">7d Change</span>
                            <span id="change7d" class="metric-value">-</span>
                        </div>
                        <div class="metric">
                            <span class="metric-label">Market Cap</span>
                            <span id="marketCap" class="metric-value">-</span>
                        </div>
                        <div class="metric">
                            <span class="metric-label">24h Volume</span>
                            <span id="volume" class="metric-value">-</span>
                        </div>
                    </div>

                    <div class="card">
                        <h3>🎯 Support/Resistance</h3>
                        <div class="metric">
                            <span class="metric-label">Nearest Resistance</span>
                            <span id="resistance" class="metric-value">-</span>
                        </div>
                        <div class="metric">
                            <span class="metric-label">Nearest Support</span>
                            <span id="support" class="metric-value">-</span>
                        </div>
                        <div class="metric">
                            <span class="metric-label">Range Position</span>
                            <span id="rangePosition" class="metric-value">-</span>
                        </div>
                        <div id="srProgress" class="progress-bar">
                            <div class="progress-fill" style="width: 50%;">50%</div>
                        </div>
                    </div>
                </div>

                <div class="dashboard">
                    <div class="card">
                        <h3>🎯 HODL Momentum</h3>
                        <div class="metric">
                            <span class="metric-label">Score</span>
                            <span id="hodlScore" class="metric-value">-</span>
                        </div>
                        <div class="metric">
                            <span class="metric-label">Level</span>
                            <span id="hodlLevel" class="metric-value">-</span>
                        </div>
                        <div id="hodlConsecutiveWarning" style="display: none; margin: 10px 0; padding: 10px; background: #fee; border: 2px solid #f88; border-radius: 8px; color: #c33; font-weight: bold;">
                            ⚠️ CONSECUTIVE HIGH SCORES (5+ days)
                        </div>
                        <div id="hodlInterpretation" style="margin-top: 10px; padding: 10px; background: #f8f9fa; border-radius: 8px;">
                            -
                        </div>
                        <div class="metric" id="hodlAvgContainer" style="display: none;">
                            <span class="metric-label">7-Day Average</span>
                            <span id="hodlAvg" class="metric-value">-</span>
                        </div>
                    </div>

                    <div class="card">
                        <h3>😨😃 Market Sentiment</h3>
                        <div class="metric">
                            <span class="metric-label">Fear & Greed Index</span>
                            <span id="fearGreed" class="metric-value">-</span>
                        </div>
                        <div id="fgProgress" class="progress-bar">
                            <div class="progress-fill" style="width: 50%;">50</div>
                        </div>
                        <div class="metric">
                            <span class="metric-label">Classification</span>
                            <span id="fgClass" class="metric-value">-</span>
                        </div>
                    </div>

                    <div class="card">
                        <h3>🦈 Long-Term Holders</h3>
                        <div class="metric">
                            <span class="metric-label">Behavior</span>
                            <span id="lthBehavior" class="metric-value">-</span>
                        </div>
                        <div class="metric">
                            <span class="metric-label">Signal Strength</span>
                            <span id="lthStrength" class="metric-value">-</span>
                        </div>
                        <div id="lthConfirmation" style="display: none; margin: 10px 0; padding: 8px; background: #efe; border: 2px solid #8f8; border-radius: 8px; color: #383; font-weight: bold; text-align: center;">
                        </div>
                        <div class="metric">
                            <span class="metric-label">Est. Supply</span>
                            <span id="lthSupply" class="metric-value">-</span>
                        </div>
                        <div class="metric" id="lthTrendContainer" style="display: none;">
                            <span class="metric-label">Supply Trend</span>
                            <span id="lthTrend" class="metric-value">-</span>
                        </div>
                    </div>
                </div>

                <div class="card">
                    <h3>🚨 Key Signals</h3>
                    <ul id="signalsList" class="signals-list">
                        <li>No signals available</li>
                    </ul>
                </div>
                <div class="card" id="divergenceCard" style="display: none; background: linear-gradient(135deg, #fbbf24 0%, #f59e0b 100%); color: white;">
                    <h3 style="color: white;">📉📈 Divergence Signals</h3>
                    <ul id="divergenceList" class="signals-list">
                        <li>No divergence signals detected</li>
                    </ul>
                </div>
            </div>

            <div id="technical" class="tab-content">
                <div class="dashboard">
                    <div class="card">
                        <h3>📊 Technical Indicators</h3>
                        <div class="metric">
                            <span class="metric-label">RSI (14)</span>
                            <span id="rsi" class="metric-value">-</span>
                        </div>
                        <div id="rsiProgress" class="progress-bar">
                            <div class="progress-fill" style="width: 50%;">50</div>
                        </div>
                        <div class="metric">
                            <span class="metric-label">MACD</span>
                            <span id="macd" class="metric-value">-</span>
                        </div>
                        <div class="metric">
                            <span class="metric-label">MACD Signal</span>
                            <span id="macdSignal" class="metric-value">-</span>
                        </div>
                    </div>

                    <div class="card">
                        <h3>📈 Moving Averages</h3>
                        <div class="metric">
                            <span class="metric-label">MA7</span>
                            <span id="ma7" class="metric-value">-</span>
                        </div>
                        <div class="metric">
                            <span class="metric-label">MA25</span>
                            <span id="ma25" class="metric-value">-</span>
                        </div>
                        <div class="metric">
                            <span class="metric-label">MA50</span>
                            <span id="ma50" class="metric-value">-</span>
                        </div>
                        <div class="metric">
                            <span class="metric-label">MA200</span>
                            <span id="ma200" class="metric-value">-</span>
                        </div>
                        <div id="maStatus" style="margin-top: 10px; padding: 10px; background: #f8f9fa; border-radius: 8px;">
                            -
                        </div>
                    </div>

                    <div class="card">
                        <h3>💧 Liquidity Analysis</h3>
                        <div class="metric">
                            <span class="metric-label">Source</span>
                            <span id="liqSource" class="metric-value">-</span>
                        </div>
                        <div class="metric">
                            <span class="metric-label">Bid/Ask Ratio</span>
                            <span id="bidAsk" class="metric-value">-</span>
                        </div>
                        <div class="metric">
                            <span class="metric-label">Imbalance</span>
                            <span id="imbalance" class="metric-value">-</span>
                        </div>
                        <div class="metric">
                            <span class="metric-label">Spread</span>
                            <span id="spread" class="metric-value">-</span>
                        </div>
                    </div>
                </div>
            </div>

            <div id="onchain" class="tab-content">
                <div class="dashboard">
                    <div class="card">
                        <h3>⛓️ On-Chain Metrics</h3>
                        <div class="metric">
                            <span class="metric-label">Exchange Flow</span>
                            <span id="exchangeFlow" class="metric-value">-</span>
                        </div>
                        <div class="metric">
                            <span class="metric-label">Active Addresses</span>
                            <span id="activeAddr" class="metric-value">-</span>
                        </div>
                        <div class="metric">
                            <span class="metric-label">MVRV Ratio</span>
                            <span id="mvrv" class="metric-value">-</span>
                        </div>
                    </div>

                    <div class="card">
                        <h3>📊 Derivatives Data</h3>
                        <div class="metric">
                            <span class="metric-label">Exchange</span>
                            <span id="derivExchange" class="metric-value">-</span>
                        </div>
                        <div class="metric">
                            <span class="metric-label">Funding Rate</span>
                            <span id="funding" class="metric-value">-</span>
                        </div>
                        <div class="metric">
                            <span class="metric-label">L/S Ratio</span>
                            <span id="lsRatio" class="metric-value">-</span>
                        </div>
                        <div class="metric">
                            <span class="metric-label">Open Interest</span>
                            <span id="openInterest" class="metric-value">-</span>
                        </div>
                    </div>

                    <div class="card" id="leverageCard" style="display: none;">
                        <h3>⚡ Market Leverage Estimation</h3>
                        <div class="metric">
                            <span class="metric-label">Risk Score</span>
                            <span id="leverageScore" class="metric-value">-</span>
                        </div>
                        <div id="leverageProgress" class="progress-bar">
                            <div class="progress-fill" style="width: 50%;">50</div>
                        </div>
                        <div class="metric">
                            <span class="metric-label">Risk Level</span>
                            <span id="leverageLevel" class="metric-value">-</span>
                        </div>
                        <div id="leverageInterpretation" style="margin-top: 10px; padding: 10px; background: #f8f9fa; border-radius: 8px; font-size: 0.9em;">
                            -
                        </div>
                        <div style="margin-top: 15px; padding-top: 15px; border-top: 1px solid #e0e0e0;">
                            <div class="metric">
                                <span class="metric-label">OI/Market Cap</span>
                                <span id="leverageOI" class="metric-value">-</span>
                            </div>
                            <div class="metric">
                                <span class="metric-label">Funding Pressure</span>
                                <span id="leverageFunding" class="metric-value">-</span>
                            </div>
                        </div>
                    </div>

                    <div class="card">
                        <h3>📊 Score Components</h3>
                        <div id="scoreBreakdown"></div>
                    </div>
                </div>
            </div>

            <div id="returns" class="tab-content">
                <div class="dashboard">
                    <div class="card" style="background: linear-gradient(135deg, #6366f1 0%, #8b5cf6 100%); color: white;">
                        <h3 style="color: white;">📊 10-Day Expected Returns</h3>
                        
                        <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 20px; margin: 20px 0;">
                            <div style="text-align: center; padding: 20px; background: rgba(255,255,255,0.15); border-radius: 10px; backdrop-filter: blur(10px);">
                                <div style="font-size: 0.9em; opacity: 0.9; margin-bottom: 5px;">Upside Probability</div>
                                <div id="upsideProbability" style="font-size: 2.5em; font-weight: bold;">-</div>
                            </div>
                            <div style="text-align: center; padding: 20px; background: rgba(255,255,255,0.15); border-radius: 10px; backdrop-filter: blur(10px);">
                                <div style="font-size: 0.9em; opacity: 0.9; margin-bottom: 5px;">Expected Value</div>
                                <div id="expectedValue" style="font-size: 2.5em; font-weight: bold;">-</div>
                            </div>
                        </div>
                        
                        <div class="metric" style="background: rgba(255,255,255,0.15); backdrop-filter: blur(10px);">
                            <span class="metric-label" style="color: white;">Expected Return (if up)</span>
                            <span id="expectedReturn" class="metric-value" style="color: white;">-</span>
                        </div>
                        <div class="metric" style="background: rgba(255,255,255,0.15); backdrop-filter: blur(10px);">
                            <span class="metric-label" style="color: white;">Expected Loss (if down)</span>
                            <span id="expectedLoss" class="metric-value" style="color: white;">-</span>
                        </div>
                        <div class="metric" style="background: rgba(255,255,255,0.15); backdrop-filter: blur(10px);">
                            <span class="metric-label" style="color: white;">Risk-Reward Ratio</span>
                            <span id="riskReward" class="metric-value" style="color: white;">-</span>
                        </div>
                        <div class="metric" style="background: rgba(255,255,255,0.15); backdrop-filter: blur(10px);">
                            <span class="metric-label" style="color: white;">Confidence Level</span>
                            <span id="confidenceLevel" class="metric-value" style="color: white;">-</span>
                        </div>
                        
                        <div id="returnsRecommendation" style="margin-top: 20px; padding: 15px; background: rgba(255,255,255,0.2); border-radius: 10px; backdrop-filter: blur(10px); font-size: 1.1em; font-weight: bold; text-align: center;">
                            -
                        </div>
                    </div>
                    
                    <div class="card">
                        <h3>📋 Probability Factors</h3>
                        <div id="probabilityFactors">
                            <p style="color: #999;">No factors available</p>
                        </div>
                    </div>
                </div>
            </div>
            <div id="suggestions" class="tab-content">
                <div class="card suggestions-card">
                    <h3>💡 Trading Suggestions & Strategy</h3>
                    <div id="suggestionsList">
                        <div class="suggestion-item">Run analysis to get personalized trading suggestions.</div>
                    </div>
                </div>
            </div>
        </div>

        <div class="disclaimer">
            <h3>⚠️ DISCLAIMER</h3>
            <p>This tool provides informational analysis only and is NOT financial advice. Cryptocurrency trading involves substantial risk of loss. Always do your own research (DYOR), use proper risk management, and never invest more than you can afford to lose. Consider consulting a financial advisor before making investment decisions.</p>
        </div>
    </div>

    <script>
        let currentTab = 'overview';

        function switchTab(tabName) {
            document.querySelectorAll('.tab').forEach(t => t.classList.remove('active'));
            document.querySelectorAll('.tab-content').forEach(c => c.classList.remove('active'));
            
            event.target.classList.add('active');
            document.getElementById(tabName).classList.add('active');
            currentTab = tabName;
        }

        function formatNumber(num, decimals = 2) {
            if (!num && num !== 0) return '-';
            return Number(num).toLocaleString('en-US', {
                minimumFractionDigits: decimals,
                maximumFractionDigits: decimals
            });
        }

        function formatCurrency(num) {
            if (!num && num !== 0) return '-';
            return '$' + formatNumber(num, 2);
        }

        function formatPercent(num) {
            if (!num && num !== 0) return '-';
            const formatted = formatNumber(num, 2) + '%';
            const className = num > 0 ? 'positive' : num < 0 ? 'negative' : 'neutral';
            return `<span class="${className}">${num > 0 ? '+' : ''}${formatted}</span>`;
        }

        function getScoreColor(score) {
            if (score >= 70) return 'linear-gradient(135deg, #22c55e 0%, #16a34a 100%)';
            if (score >= 60) return 'linear-gradient(135deg, #84cc16 0%, #65a30d 100%)';
            if (score >= 45) return 'linear-gradient(135deg, #f59e0b 0%, #d97706 100%)';
            if (score >= 35) return 'linear-gradient(135deg, #f97316 0%, #ea580c 100%)';
            return 'linear-gradient(135deg, #ef4444 0%, #dc2626 100%)';
        }

        function getActionColor(action) {
            if (action.includes('STRONG BUY')) return '#22c55e';
            if (action.includes('BUY')) return '#84cc16';
            if (action.includes('HOLD')) return '#f59e0b';
            if (action.includes('REDUCE')) return '#f97316';
            return '#ef4444';
        }

        function updateUI(data) {
            const md = data.market_data || {};
            const sr = data.support_resistance || {};
            const tech = data.technical_indicators || {};
            const onchain = data.onchain_metrics || {};
            const deriv = data.derivatives_data || {};
            const liq = data.liquidity || {};
            const lth = data.lth_metrics || {};
            const hodl = data.hodl || {};
            const fg = data.fear_greed || {};
            const analysis = data.analysis || {};

            // Market Data
            document.getElementById('price').textContent = formatCurrency(md.price);
            document.getElementById('change24h').innerHTML = formatPercent(md.price_change_24h);
            document.getElementById('change7d').innerHTML = formatPercent(md.price_change_7d);
            document.getElementById('marketCap').textContent = formatCurrency(md.market_cap);
            document.getElementById('volume').textContent = formatCurrency(md.volume_24h);

            // Score Display
            const score = analysis.total_score || 0;
            document.getElementById('scoreValue').textContent = Math.round(score);
            document.getElementById('scoreCircle').style.background = getScoreColor(score);
            
            const actionBadge = document.getElementById('actionBadge');
            actionBadge.textContent = analysis.action || 'ANALYZING...';
            actionBadge.style.background = getActionColor(analysis.action);
            
            document.getElementById('riskLevel').textContent = 'Risk Level: ' + (analysis.risk_level || '-');

            // Support/Resistance
            if (sr.nearest_resistance) {
                document.getElementById('resistance').innerHTML = 
                    formatCurrency(sr.nearest_resistance) + ' ' + 
                    formatPercent(sr.resistance_distance_pct);
            }
            if (sr.nearest_support) {
                document.getElementById('support').innerHTML = 
                    formatCurrency(sr.nearest_support) + ' ' + 
                    formatPercent(-sr.support_distance_pct);
            }
            if (sr.range_position_pct) {
                const pos = sr.range_position_pct;
                document.getElementById('rangePosition').textContent = Math.round(pos) + '%';
                const progressBar = document.querySelector('#srProgress .progress-fill');
                progressBar.style.width = pos + '%';
                progressBar.textContent = Math.round(pos) + '%';
            }

            // HODL Momentum
            if (hodl.score) {
                document.getElementById('hodlScore').textContent = Math.round(hodl.score) + '/100';
                document.getElementById('hodlLevel').textContent = hodl.level;
                document.getElementById('hodlInterpretation').textContent = hodl.interpretation;
                
                // Show consecutive warning
                const consecutiveWarning = document.getElementById('hodlConsecutiveWarning');
                if (hodl.consecutive_warning) {
                    consecutiveWarning.style.display = 'block';
                } else {
                    consecutiveWarning.style.display = 'none';
                }
                
                // Show 7-day average (if available in history)
                // Note: This would require additional API endpoint to fetch history
                // For now, hide if not available
                document.getElementById('hodlAvgContainer').style.display = 'none';
            }

            // Fear & Greed
            if (fg.current_value) {
                document.getElementById('fearGreed').textContent = fg.current_value;
                document.getElementById('fgClass').textContent = fg.classification;
                const fgBar = document.querySelector('#fgProgress .progress-fill');
                fgBar.style.width = fg.current_value + '%';
                fgBar.textContent = fg.current_value;
                
                if (fg.current_value < 25) fgBar.style.background = '#ef4444';
                else if (fg.current_value < 45) fgBar.style.background = '#f97316';
                else if (fg.current_value < 55) fgBar.style.background = '#f59e0b';
                else if (fg.current_value < 75) fgBar.style.background = '#84cc16';
                else fgBar.style.background = '#22c55e';
            }

            // LTH
            if (lth.lth_behavior) {
                document.getElementById('lthBehavior').textContent = lth.lth_behavior;
                document.getElementById('lthStrength').textContent = lth.signal_strength;
                document.getElementById('lthSupply').textContent = 
                    Math.round(lth.estimated_lth_supply_pct) + '%';
                
                // Show confirmation badge
                const confirmationBadge = document.getElementById('lthConfirmation');
                if (lth.signal_strength === 'CONFIRMED' || lth.signal_strength === 'VERY_STRONG') {
                    confirmationBadge.style.display = 'block';
                    if (lth.signal_strength === 'VERY_STRONG') {
                        confirmationBadge.textContent = '💪 VERY STRONG SIGNAL';
                        confirmationBadge.style.background = 'linear-gradient(135deg, #22c55e 0%, #16a34a 100%)';
                    } else {
                        confirmationBadge.textContent = '✅ TREND CONFIRMED';
                    }
                } else {
                    confirmationBadge.style.display = 'none';
                }
                
                // Hide trend for now (needs history data)
                document.getElementById('lthTrendContainer').style.display = 'none';
            }

            // Technical Indicators
            if (tech.rsi) {
                document.getElementById('rsi').innerHTML = 
                    formatNumber(tech.rsi, 1) + ' - ' + tech.rsi_signal;
                const rsiBar = document.querySelector('#rsiProgress .progress-fill');
                rsiBar.style.width = tech.rsi + '%';
                rsiBar.textContent = Math.round(tech.rsi);
                
                if (tech.rsi < 30) rsiBar.style.background = '#22c55e';
                else if (tech.rsi > 70) rsiBar.style.background = '#ef4444';
                else rsiBar.style.background = 'linear-gradient(90deg, #1e3a8a 0%, #3b82f6 100%)';
            }

            if (tech.macd) {
                document.getElementById('macd').textContent = formatNumber(tech.macd.macd, 2);
                document.getElementById('macdSignal').textContent = tech.macd_signal;
            }

            // Moving Averages
            const ma = tech.moving_averages || {};
            if (ma.ma7) {
                document.getElementById('ma7').innerHTML = 
                    formatCurrency(ma.ma7) + ' ' + formatPercent(ma.price_vs_ma7);
                document.getElementById('ma25').innerHTML = 
                    formatCurrency(ma.ma25) + ' ' + formatPercent(ma.price_vs_ma25);
                
                if (ma.ma50) {
                    document.getElementById('ma50').innerHTML = 
                        formatCurrency(ma.ma50) + ' ' + formatPercent(ma.price_vs_ma50);
                }
                if (ma.ma200) {
                    document.getElementById('ma200').innerHTML = 
                        formatCurrency(ma.ma200) + ' ' + formatPercent(ma.price_vs_ma200);
                }

                let maStatusText = '';
                if (ma.golden_cross) maStatusText = '✨ GOLDEN CROSS';
                else if (ma.death_cross) maStatusText = '💀 DEATH CROSS';
                else if (ma.above_ma200) maStatusText = '🟢 Above MA200 (Bull market)';
                else maStatusText = '🔴 Below MA200 (Bear market)';
                document.getElementById('maStatus').textContent = maStatusText;
            }

            // Liquidity
            if (liq.source) {
                document.getElementById('liqSource').textContent = liq.source;
                document.getElementById('bidAsk').textContent = formatNumber(liq.bid_ask_ratio, 2);
                document.getElementById('imbalance').textContent = liq.imbalance;
                document.getElementById('spread').textContent = formatNumber(liq.spread_pct, 4) + '%';
            }

            // On-chain
            if (onchain.flow_direction) {
                document.getElementById('exchangeFlow').textContent = onchain.flow_direction;
                document.getElementById('activeAddr').textContent = 
                    formatNumber(onchain.active_addresses, 0);
                document.getElementById('mvrv').textContent = 
                    onchain.mvrv_ratio ? formatNumber(onchain.mvrv_ratio, 2) : 'N/A';
            }

            // Derivatives
            if (deriv.exchange) {
                document.getElementById('derivExchange').textContent = deriv.exchange;
                document.getElementById('funding').textContent = 
                    deriv.funding_rate ? formatNumber(deriv.funding_rate, 4) + '%' : '-';
                document.getElementById('lsRatio').textContent = 
                    deriv.long_short_ratio ? formatNumber(deriv.long_short_ratio, 2) : '-';
                document.getElementById('openInterest').textContent = 
                    deriv.open_interest_coin ? formatNumber(deriv.open_interest_coin, 0) + ' ' + data.symbol : '-';
            }

            // Leverage Estimation
            if (data.leverage_estimate) {
                const leverage = data.leverage_estimate;
                const leverageCard = document.getElementById('leverageCard');
                leverageCard.style.display = 'block';
                
                // Update score
                const score = leverage.leverage_score || 0;
                document.getElementById('leverageScore').textContent = Math.round(score) + '/100';
                
                // Update progress bar with color coding
                const leverageBar = document.querySelector('#leverageProgress .progress-fill');
                leverageBar.style.width = score + '%';
                leverageBar.textContent = Math.round(score);
                
                // Color code based on risk level
                if (score >= 85) {
                    leverageBar.style.background = '#ef4444'; // Red - Extreme
                } else if (score >= 70) {
                    leverageBar.style.background = '#f97316'; // Orange - High
                } else if (score >= 50) {
                    leverageBar.style.background = '#f59e0b'; // Yellow - Elevated
                } else if (score >= 30) {
                    leverageBar.style.background = '#84cc16'; // Light green - Moderate
                } else {
                    leverageBar.style.background = '#22c55e'; // Green - Low
                }
                
                // Update level and interpretation
                document.getElementById('leverageLevel').textContent = leverage.risk_level || '-';
                document.getElementById('leverageInterpretation').textContent = leverage.interpretation || '-';
                
                // Update details
                if (leverage.oi_to_mcap) {
                    document.getElementById('leverageOI').innerHTML = 
                        formatNumber(leverage.oi_to_mcap * 100, 2) + '% <span style="color: #999;">(' + 
                        (leverage.oi_level || '-') + ')</span>';
                }
                
                document.getElementById('leverageFunding').textContent = leverage.funding_level || '-';
            } else {
                // Hide card if no leverage data
                document.getElementById('leverageCard').style.display = 'none';
            }

            // Score Breakdown
            const scoreComponents = analysis.score_components || {};
            let breakdownHTML = '';
            for (const [component, score] of Object.entries(scoreComponents)) {
                const color = score > 0 ? '#22c55e' : score < 0 ? '#ef4444' : '#f59e0b';
                const width = Math.abs(score) * 5;
                breakdownHTML += `
                    <div class="metric">
                        <span class="metric-label">${component.toUpperCase()}</span>
                        <span class="metric-value" style="color: ${color}">${score > 0 ? '+' : ''}${formatNumber(score, 1)}</span>
                    </div>
                    <div class="progress-bar" style="margin-bottom: 10px;">
                        <div class="progress-fill" style="width: ${Math.min(width, 100)}%; background: ${color};">
                            ${score > 0 ? '+' : ''}${formatNumber(score, 1)}
                        </div>
                    </div>
                `;
            }
            document.getElementById('scoreBreakdown').innerHTML = breakdownHTML || '<p>No breakdown available</p>';

            // Signals
            const signals = analysis.signals || [];
            const signalsList = document.getElementById('signalsList');
            if (signals.length > 0) {
                signalsList.innerHTML = signals.map(s => `<li>${s}</li>`).join('');
            } else {
                signalsList.innerHTML = '<li>No signals detected</li>';
            }

            // Divergence Signals
            const divergenceSignals = signals.filter(s => 
                s.includes('DIVERGENCE') || s.toLowerCase().includes('divergence')
            );

            const divergenceCard = document.getElementById('divergenceCard');
            const divergenceList = document.getElementById('divergenceList');

            if (divergenceSignals.length > 0) {
                divergenceCard.style.display = 'block';
                divergenceList.innerHTML = divergenceSignals.map(s => {
                    // Color code based on type
                    let bgColor = 'rgba(255,255,255,0.2)';
                    if (s.includes('BEARISH_DIVERGENCE') || s.includes('BEARISH')) {
                        bgColor = 'rgba(239, 68, 68, 0.3)'; // Red for bearish
                    } else if (s.includes('BULLISH_DIVERGENCE') || s.includes('BULLISH')) {
                        bgColor = 'rgba(34, 197, 94, 0.3)'; // Green for bullish
                    }
                    return `<li style="background: ${bgColor}; border-left: 4px solid white;">${s}</li>`;
                }).join('');
            } else {
                divergenceCard.style.display = 'none';
            }

            // Suggestions
            const suggestions = data.suggestions || [];
            const suggestionsList = document.getElementById('suggestionsList');
            if (suggestions.length > 0) {
                suggestionsList.innerHTML = suggestions.map(s => 
                    `<div class="suggestion-item">${s}</div>`
                ).join('');
            } else {
                suggestionsList.innerHTML = '<div class="suggestion-item">No suggestions available</div>';
            }

            // ✅ Expected Returns 
            const expectedReturns = data.expected_returns;
            const returnsTab = document.getElementById('returnsTab');
            const returnsBadge = document.getElementById('returnsBadge');

            // 先確保 badge 可見（移除任何 display:none）
            if (returnsBadge) {
                returnsBadge.style.display = 'inline-block';
            }

            if (expectedReturns) {
                if (returnsBadge) {
                    returnsBadge.style.background = '#22c55e';
                    returnsBadge.textContent = 'READY';
                    returnsBadge.style.animation = 'pulse 2s infinite';
                }
                
                if (returnsTab) {
                    returnsTab.style.opacity = '1';
                    returnsTab.style.pointerEvents = 'auto';
                    returnsTab.style.cursor = 'pointer';
                }
                
                // Update probability
                const prob = expectedReturns.upside_probability || 0;
                document.getElementById('upsideProbability').textContent = prob.toFixed(1) + '%';
                
                // Update EV
                const ev = expectedReturns.expected_value || 0;
                const evElement = document.getElementById('expectedValue');
                evElement.textContent = (ev > 0 ? '+' : '') + ev.toFixed(2) + '%';
                evElement.style.color = ev > 1.5 ? '#22c55e' : ev > 0 ? '#84cc16' : '#ef4444';
                
                // Update returns/loss
                document.getElementById('expectedReturn').textContent = 
                    '+' + formatNumber(expectedReturns.expected_return_10d, 2) + '%';
                document.getElementById('expectedLoss').textContent = 
                    '-' + formatNumber(expectedReturns.expected_loss_10d, 2) + '%';
                
                // Update RR ratio
                const rr = expectedReturns.risk_reward_ratio || 0;
                const rrElement = document.getElementById('riskReward');
                rrElement.textContent = rr.toFixed(2) + ':1';
                rrElement.style.color = rr > 2 ? '#22c55e' : rr > 1.5 ? '#84cc16' : '#f59e0b';
                
                // Update confidence
                document.getElementById('confidenceLevel').textContent = expectedReturns.confidence_level || '-';
                
                // Update recommendation
                const recommendation = expectedReturns.recommendation || '-';
                const recElement = document.getElementById('returnsRecommendation');
                recElement.textContent = recommendation;
                
                if (recommendation.includes('EXCELLENT')) {
                    recElement.style.background = 'rgba(34, 197, 94, 0.3)';
                } else if (recommendation.includes('GOOD')) {
                    recElement.style.background = 'rgba(132, 204, 22, 0.3)';
                } else if (recommendation.includes('ACCEPTABLE')) {
                    recElement.style.background = 'rgba(245, 158, 11, 0.3)';
                } else {
                    recElement.style.background = 'rgba(239, 68, 68, 0.3)';
                }
                
                // Update probability factors
                const factors = expectedReturns.probability_factors || [];
                const factorsContainer = document.getElementById('probabilityFactors');
                
                if (factors.length > 0) {
                    const positive = factors.filter(f => f[1] > 0);
                    const negative = factors.filter(f => f[1] < 0);
                    
                    let html = '';
                    
                    if (positive.length > 0) {
                        html += '<h4 style="color: #22c55e; margin-top: 10px;">🟢 Bullish Factors:</h4>';
                        html += '<ul style="list-style: none; padding-left: 0;">';
                        positive.sort((a, b) => b[1] - a[1]).forEach(([name, value]) => {
                            html += `<li style="padding: 8px; margin: 5px 0; background: #f0fdf4; border-left: 4px solid #22c55e; border-radius: 5px;">
                                <strong>${name}:</strong> +${value}%
                            </li>`;
                        });
                        html += '</ul>';
                    }
                    
                    if (negative.length > 0) {
                        html += '<h4 style="color: #ef4444; margin-top: 15px;">🔴 Bearish Factors:</h4>';
                        html += '<ul style="list-style: none; padding-left: 0;">';
                        negative.sort((a, b) => a[1] - b[1]).forEach(([name, value]) => {
                            html += `<li style="padding: 8px; margin: 5px 0; background: #fef2f2; border-left: 4px solid #ef4444; border-radius: 5px;">
                                <strong>${name}:</strong> ${value}%
                            </li>`;
                        });
                        html += '</ul>';
                    }
                    
                    html += `<div style="margin-top: 20px; padding: 15px; background: #f8f9fa; border-radius: 8px;">
                        <strong>Base Probability:</strong> ${expectedReturns.base_probability}%<br>
                        <strong>Total Adjustment:</strong> ${expectedReturns.total_adjustment > 0 ? '+' : ''}${expectedReturns.total_adjustment}%<br>
                        <strong>Final Probability:</strong> ${expectedReturns.upside_probability.toFixed(1)}%
                    </div>`;
                    
                    factorsContainer.innerHTML = html;
                } else {
                    factorsContainer.innerHTML = '<p style="color: #999;">No significant factors detected</p>';
                }
                
            } else {
                if (returnsBadge) {
                    returnsBadge.style.background = '#999';
                    returnsBadge.textContent = 'N/A';
                    returnsBadge.style.animation = 'none';
                }
                
                if (returnsTab) {
                    returnsTab.style.opacity = '0.6';
                    returnsTab.style.pointerEvents = 'auto';  
                    returnsTab.style.cursor = 'pointer';
                }
                
                // 顯示 "Not Available" 訊息
                document.getElementById('upsideProbability').textContent = 'N/A';
                document.getElementById('expectedValue').textContent = 'N/A';
                document.getElementById('expectedReturn').textContent = '-';
                document.getElementById('expectedLoss').textContent = '-';
                document.getElementById('riskReward').textContent = '-';
                document.getElementById('confidenceLevel').textContent = '-';
                
                document.getElementById('returnsRecommendation').innerHTML = 
                    '⚠️ Expected Returns analysis only available for <strong>BUY</strong> signals<br><small style="opacity: 0.8;">Current signal does not qualify for expected returns calculation.</small>';
                document.getElementById('returnsRecommendation').style.background = 'rgba(245, 158, 11, 0.2)';
                
                document.getElementById('probabilityFactors').innerHTML = 
                    '<p style="color: #999; text-align: center; padding: 40px;">📊 Analyze a cryptocurrency with a <strong>BUY</strong> signal to view expected returns analysis.</p>';
            }
        }

        async function fetchAndDisplayHistory(symbol) {
            try {
                const response = await fetch('/api/history', {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({ symbol: symbol })
                });
                
                const data = await response.json();
                
                if (data.has_data && data.history.hodl_scores) {
                    const scores = data.history.hodl_scores.filter(s => s !== null);
                    if (scores.length >= 7) {
                        const avg = scores.slice(-7).reduce((a, b) => a + b, 0) / Math.min(7, scores.length);
                        document.getElementById('hodlAvg').textContent = Math.round(avg) + '/100';
                        document.getElementById('hodlAvgContainer').style.display = 'flex';
                    }
                }
                
                if (data.has_data && data.history.lth_supply) {
                    const supply = data.history.lth_supply.filter(s => s !== null);
                    if (supply.length >= 3) {
                        const change = supply[supply.length - 1] - supply[supply.length - 3];
                        if (Math.abs(change) > 3) {
                            const emoji = change > 0 ? '📈' : '📉';
                            const color = change > 0 ? '#22c55e' : '#ef4444';
                            document.getElementById('lthTrend').innerHTML = 
                                `<span style="color: ${color}">${emoji} ${change > 0 ? '+' : ''}${change.toFixed(1)}%</span>`;
                            document.getElementById('lthTrendContainer').style.display = 'flex';
                        }
                    }
                }
            } catch (error) {
                console.log('History fetch failed:', error);
            }
        }

        // Live price monitoring with display
        let livePriceInterval = null;
        let currentSymbol = null;
        let lastPrice = null;
        let supportLevel = null;
        let resistanceLevel = null;
        let alertShown = {support: false, resistance: false};

        function startLivePriceMonitoring(symbol) {
            currentSymbol = symbol;
            alertShown = {support: false, resistance: false};
            priceUpdateFailures = 0;  // Reset failure counter
            
            if (livePriceInterval) {
                clearInterval(livePriceInterval);
            }

            // Show live price container
            document.getElementById('livePriceContainer').style.display = 'flex';

            // Update immediately
            updateLivePrice();

            // Update every 30 seconds 
            // More responsive for trading decisions
            livePriceInterval = setInterval(() => {
                updateLivePrice();
            }, 30000);  // 30 seconds
        }

        function stopLivePriceMonitoring() {
            if (livePriceInterval) {
                clearInterval(livePriceInterval);
                livePriceInterval = null;
            }
            // Hide live price container
            document.getElementById('livePriceContainer').style.display = 'none';
        }

        let priceUpdateFailures = 0;  // Track consecutive failures
        const MAX_FAILURES = 3;        // Max failures before stopping

        async function updateLivePrice() {
            if (!currentSymbol) return;

            try {
                const response = await fetch('/api/live_price', {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({ symbol: currentSymbol }),
                    signal: AbortSignal.timeout(30000)  // 30 second timeout
                });

                if (!response.ok) {
                    throw new Error(`HTTP ${response.status}: ${response.statusText}`);
                }

                const data = await response.json();
                
                if (!data.price) {
                    throw new Error('Price data missing in response');
                }

                // Reset failure counter on success
                priceUpdateFailures = 0;
                
                const newPrice = data.price;
                const change24h = data.change_24h || 0;
                
                // Update live price display in the controls
                const livePriceElement = document.getElementById('livePrice');
                const livePriceChangeElement = document.getElementById('livePriceChange');
                
                // Animate price changes with color
                if (lastPrice) {
                    if (newPrice > lastPrice) {
                        livePriceElement.style.color = '#22c55e';
                        livePriceElement.style.transition = 'color 0.3s ease';
                    } else if (newPrice < lastPrice) {
                        livePriceElement.style.color = '#ef4444';
                        livePriceElement.style.transition = 'color 0.3s ease';
                    }
                    // Reset color after animation
                    setTimeout(() => {
                        livePriceElement.style.color = '';
                    }, 2000);
                }
                
                livePriceElement.textContent = formatCurrency(newPrice);
                
                // Update 24h change indicator
                const changeColor = change24h > 0 ? '#22c55e' : change24h < 0 ? '#ef4444' : '#666';
                const changeSymbol = change24h > 0 ? '▲' : change24h < 0 ? '▼' : '•';
                livePriceChangeElement.innerHTML = `<span style="color: ${changeColor}">${changeSymbol} ${Math.abs(change24h).toFixed(2)}%</span>`;
                
                // Also update the main price display
                const priceElement = document.getElementById('price');
                if (lastPrice) {
                    if (newPrice > lastPrice) {
                        priceElement.style.color = '#22c55e';
                    } else if (newPrice < lastPrice) {
                        priceElement.style.color = '#ef4444';
                    }
                    setTimeout(() => {
                        priceElement.style.color = '';
                    }, 2000);
                }
                
                priceElement.textContent = formatCurrency(newPrice);
                lastPrice = newPrice;

                // Check for support/resistance alerts
                checkPriceAlerts(newPrice);
                
            } catch (error) {
                console.error('Live price update error:', error);
                priceUpdateFailures++;
                
                // Show error state to user
                const livePriceElement = document.getElementById('livePrice');
                const statusText = document.getElementById('statusText');
                
                if (priceUpdateFailures >= MAX_FAILURES) {
                    // Stop monitoring after max failures
                    livePriceElement.textContent = 'Offline';
                    livePriceElement.style.color = '#999';
                    statusText.textContent = `Live price monitoring stopped (connection lost)`;
                    statusText.style.color = '#ef4444';
                    
                    stopLivePriceMonitoring();
                    
                    // Show reconnect button
                    showReconnectOption();
                } else {
                    // Temporary error - retry with exponential backoff
                    livePriceElement.textContent = 'Updating...';
                    livePriceElement.style.color = '#f59e0b';
                    statusText.textContent = `Price update failed (retry ${priceUpdateFailures}/${MAX_FAILURES})`;
                    statusText.style.color = '#f59e0b';
                    
                    // Retry after delay (3s, 6s, 9s)
                    const retryDelay = 3000 * priceUpdateFailures;
                    setTimeout(() => {
                        updateLivePrice();
                    }, retryDelay);
                }
            }
        }

        // Show reconnect option when monitoring stops
        function showReconnectOption() {
            const controlsDiv = document.querySelector('.controls .input-group');
            
            // Check if button already exists
            if (document.getElementById('reconnectBtn')) return;
            
            const reconnectBtn = document.createElement('button');
            reconnectBtn.id = 'reconnectBtn';
            reconnectBtn.textContent = '🔄 Reconnect Live Price';
            reconnectBtn.style.background = 'linear-gradient(135deg, #f59e0b 0%, #d97706 100%)';
            reconnectBtn.onclick = () => {
                priceUpdateFailures = 0;
                reconnectBtn.remove();
                startLivePriceMonitoring(currentSymbol);
                document.getElementById('statusText').textContent = 'Reconnecting...';
                document.getElementById('statusText').style.color = '#666';
            };
            
            controlsDiv.appendChild(reconnectBtn);
        }

        let lastAlertTime = {support: 0, resistance: 0};  // Add to global scope
        const ALERT_COOLDOWN = 5 * 60 * 1000;  // 5 minutes in milliseconds

        function checkPriceAlerts(currentPrice) {
            if (!supportLevel || !resistanceLevel) return;

            const supportThreshold = 0.02; // 2%
            const resistanceThreshold = 0.02; // 2%
            const now = Date.now();

            // Check support level
            const supportDist = Math.abs((currentPrice - supportLevel) / supportLevel);
            if (supportDist <= supportThreshold) {
                // Only alert if cooldown period has passed
                if (!lastAlertTime.support || now - lastAlertTime.support > ALERT_COOLDOWN) {
                    showPriceAlert('support', currentPrice, supportLevel);
                    lastAlertTime.support = now;
                }
            }

            // Check resistance level
            const resistanceDist = Math.abs((currentPrice - resistanceLevel) / resistanceLevel);
            if (resistanceDist <= resistanceThreshold) {
                // Only alert if cooldown period has passed
                if (!lastAlertTime.resistance || now - lastAlertTime.resistance > ALERT_COOLDOWN) {
                    showPriceAlert('resistance', currentPrice, resistanceLevel);
                    lastAlertTime.resistance = now;
                }
            }
        }

        function showPriceAlert(type, currentPrice, level) {
            // Remove existing alerts
            const existingAlerts = document.querySelectorAll('.price-alert');
            existingAlerts.forEach(alert => alert.remove());

            const alert = document.createElement('div');
            alert.className = `price-alert ${type}`;
            
            const emoji = type === 'support' ? '🟢' : '🔴';
            const title = type === 'support' ? 'SUPPORT LEVEL REACHED' : 'RESISTANCE LEVEL REACHED';
            const message = type === 'support' 
                ? 'Price is near support! Potential bounce opportunity.'
                : 'Price is near resistance! Watch for rejection or breakout.';

            alert.innerHTML = `
                <button class="close-btn" onclick="this.parentElement.remove()">×</button>
                <h4>${emoji} ${title}</h4>
                <p style="margin: 10px 0;">
                    <strong>Current Price:</strong> ${formatCurrency(currentPrice)}<br>
                    <strong>${type === 'support' ? 'Support' : 'Resistance'}:</strong> ${formatCurrency(level)}<br>
                    <strong>Distance:</strong> ${Math.abs(((currentPrice - level) / level * 100)).toFixed(2)}%
                </p>
                <p style="margin-top: 10px; color: #666; font-size: 0.9em;">
                    ${message}
                </p>
            `;

            document.body.appendChild(alert);

            // Auto-remove after 10 seconds
            setTimeout(() => {
                alert.remove();
            }, 10000);
        }

        // Analysis with better error handling
        async function analyzeSymbol() {
            const symbol = document.getElementById('symbolSelect').value;
            const analyzeBtn = document.getElementById('analyzeBtn');
            const statusText = document.getElementById('statusText');
            
            // Stop live monitoring during analysis
            stopLivePriceMonitoring();
            
            analyzeBtn.disabled = true;
            statusText.textContent = 'Analyzing...';
            statusText.style.color = '#666';
            document.getElementById('loadingSymbol').textContent = symbol;
            document.getElementById('loading').style.display = 'block';
            document.getElementById('results').style.display = 'none';

            try {
                // Set a timeout for the entire analysis (5 minutes max)
                const controller = new AbortController();
                const timeoutId = setTimeout(() => controller.abort(), 300000); // 5 minutes

                const response = await fetch('/api/analyze', {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json',
                    },
                    body: JSON.stringify({ symbol: symbol }),
                    signal: controller.signal
                });

                clearTimeout(timeoutId);

                if (!response.ok) {
                    const errorData = await response.json();
                    throw new Error(errorData.error || `HTTP ${response.status}`);
                }

                const data = await response.json();

                if (data.error) {
                    throw new Error(data.error);
                }
                
                // Success - update UI
                document.getElementById('loading').style.display = 'none';
                document.getElementById('results').style.display = 'block';
                updateUI(data);
                fetchAndDisplayHistory(symbol);
                
                // Store support/resistance levels for alerts
                if (data.support_resistance) {
                    supportLevel = data.support_resistance.nearest_support;
                    resistanceLevel = data.support_resistance.nearest_resistance;
                }
                
                // Start live price monitoring
                startLivePriceMonitoring(symbol);
                
                statusText.textContent = `✅ Analysis complete! (Updated: ${new Date().toLocaleTimeString()})`;
                statusText.style.color = '#22c55e';
                
            } catch (error) {
                console.error('Analysis error:', error);
                
                // Hide loading, show error message
                document.getElementById('loading').style.display = 'none';
                
                // Create error display
                const errorDiv = document.createElement('div');
                errorDiv.className = 'error-message';
                errorDiv.style.margin = '20px 0';
                
                if (error.name === 'AbortError') {
                    errorDiv.innerHTML = `
                        <h3>⏱️ Analysis Timeout</h3>
                        <p>The analysis took too long and was cancelled. This usually happens due to:</p>
                        <ul>
                            <li>API rate limiting (too many requests)</li>
                            <li>Slow network connection</li>
                            <li>Server overload</li>
                        </ul>
                        <p><strong>Suggestion:</strong> Wait 2-3 minutes and try again.</p>
                    `;
                } else {
                    errorDiv.innerHTML = `
                        <h3>❌ Analysis Error</h3>
                        <p><strong>Error:</strong> ${error.message}</p>
                        <p>This could be due to:</p>
                        <ul>
                            <li>Network connectivity issues</li>
                            <li>API service unavailable</li>
                            <li>Invalid cryptocurrency symbol</li>
                            <li>Rate limiting (try again in a few minutes)</li>
                        </ul>
                        <p><strong>Suggestion:</strong> Check your connection and try again.</p>
                    `;
                }
                
                // Insert error message
                const container = document.querySelector('.container');
                const existingError = container.querySelector('.error-message');
                if (existingError) {
                    existingError.remove();
                }
                container.insertBefore(errorDiv, document.getElementById('results'));
                
                statusText.textContent = '❌ Analysis failed - see error details above';
                statusText.style.color = '#ef4444';
                
            } finally {
                analyzeBtn.disabled = false;
            }
        }

        // Auto-load message on page load
        window.addEventListener('load', () => {
            setTimeout(() => {
                document.getElementById('statusText').textContent = 'Ready! Click "Analyze Now" to start.';
            }, 500);
        });

        // Clean up on page unload
        window.addEventListener('beforeunload', () => {
            stopLivePriceMonitoring();
        });
    </script>
</body>
</html>
"""

def convert_to_serializable(obj):
    """Convert non-serializable objects to JSON-compatible format"""
    import numpy as np
    
    if isinstance(obj, datetime):
        return obj.isoformat()
    elif isinstance(obj, (np.integer, np.floating)):
        return float(obj)
    elif isinstance(obj, np.ndarray):
        return obj.tolist()
    elif isinstance(obj, (np.bool_, bool)):
        return bool(obj)
    elif isinstance(obj, dict):
        return {k: convert_to_serializable(v) for k, v in obj.items()}
    elif isinstance(obj, (list, tuple)):
        return [convert_to_serializable(item) for item in obj]
    elif hasattr(obj, '__dict__'):
        return convert_to_serializable(obj.__dict__)
    else:
        return obj

def make_json_serializable(data):
    """Recursively convert all data to JSON-serializable format"""
    if isinstance(data, dict):
        return {k: make_json_serializable(v) for k, v in data.items()}
    elif isinstance(data, (list, tuple)):
        return [make_json_serializable(item) for item in data]
    else:
        return convert_to_serializable(data)

@app.route('/')
def index():
    """Serve the main dashboard"""
    return render_template_string(HTML_TEMPLATE)

@app.route('/api/analyze', methods=['POST'])
@rate_limit('analyze')
def analyze():
    """API endpoint for crypto analysis with validation"""
    global tracker
    
    try:
        data = request.get_json()
        
        # Validate JSON data
        if not data:
            return jsonify({'error': 'Invalid request: JSON body required'}), 400
        
        symbol = data.get('symbol', 'BTC')
        
        # Validate symbol
        is_valid, result = validate_symbol(symbol)
        if not is_valid:
            return jsonify({'error': result}), 400
        
        symbol = result  # Use validated/normalized symbol
        
        print(f"\n{'='*80}")
        print(f"🔍 Analyzing {symbol}...")
        print(f"   Client IP: {request.remote_addr}")
        print(f"{'='*80}\n")
        
        # Initialize tracker if needed
        if tracker is None:
            tracker = ComprehensiveCryptoRiskTracker(symbols=[symbol])
        
        # Perform analysis
        result = tracker.analyze_comprehensive_risk(symbol)
        
        # Check if analysis returned valid data
        if not result or not result.get('market_data'):
            return jsonify({
                'error': 'Analysis failed',
                'message': 'Unable to fetch data for this cryptocurrency. Try again later.'
            }), 503
        
        # Generate suggestions
        suggestions = tracker.generate_trading_suggestions(result)
        result['suggestions'] = suggestions
        
        # Calculate leverage if derivatives data available
        if result.get('derivatives_data') and result.get('market_data'):
            leverage = tracker.estimate_market_leverage(
                result['derivatives_data'], 
                result['market_data']
            )
            result['leverage_estimate'] = leverage
        else:
            result['leverage_estimate'] = None

        # Convert all data to JSON-serializable format
        result = make_json_serializable(result)
        
        print(f"\n✅ Analysis complete for {symbol}!")
        print(f"   Score: {result['analysis']['total_score']:.1f}/100")
        print(f"   Action: {result['analysis']['action']}")
        print(f"{'='*80}\n")
        
        return jsonify(result)
        
    except Exception as e:
        print(f"\n❌ Error analyzing: {str(e)}\n")
        import traceback
        traceback.print_exc()
        
        # Return user-friendly error message
        return jsonify({
            'error': 'Internal server error',
            'message': 'An unexpected error occurred during analysis. Please try again later.',
            'details': str(e) if app.debug else None
        }), 500

@app.route('/api/status')
def status():
    """Check if the service is running"""
    return jsonify({
        'status': 'online',
        'timestamp': datetime.now().isoformat(),
        'tracker_initialized': tracker is not None
    })

@app.route('/api/live_price', methods=['POST'])
@rate_limit('live_price')
def live_price():
    """Get live price for a symbol (lightweight endpoint)"""
    try:
        data = request.get_json()
        
        # Validate JSON data
        if not data:
            return jsonify({'error': 'Invalid request: JSON body required'}), 400
        
        symbol = data.get('symbol', 'BTC')
        
        # Validate symbol
        is_valid, result = validate_symbol(symbol)
        if not is_valid:
            return jsonify({'error': result}), 400
        
        symbol = result  # Use validated/normalized symbol
        
        # Use CoinGecko for quick price fetch
        coingecko_ids = {
            'BTC': 'bitcoin',
            'ETH': 'ethereum'
        }
        
        coin_id = coingecko_ids.get(symbol, symbol.lower())
        url = f"https://api.coingecko.com/api/v3/simple/price?ids={coin_id}&vs_currencies=usd&include_24hr_change=true&include_24hr_vol=true&include_market_cap=true"
        
        response = requests.get(url, timeout=60)
        
        if response.status_code == 200:
            api_data = response.json()
            if coin_id in api_data:
                return jsonify({
                    'symbol': symbol,
                    'price': api_data[coin_id]['usd'],
                    'change_24h': api_data[coin_id].get('usd_24h_change', 0),
                    'volume_24h': api_data[coin_id].get('usd_24h_vol', 0),
                    'market_cap': api_data[coin_id].get('usd_market_cap', 0),
                    'timestamp': datetime.now().isoformat()
                })
        
        # If CoinGecko fails, return error
        return jsonify({
            'error': 'Price not available',
            'message': f'Unable to fetch price for {symbol} from CoinGecko'
        }), 503
        
    except requests.exceptions.Timeout:
        return jsonify({
            'error': 'Request timeout',
            'message': 'CoinGecko API did not respond in time'
        }), 504
        
    except Exception as e:
        return jsonify({
            'error': 'Internal server error',
            'message': str(e) if app.debug else 'An unexpected error occurred'
        }), 500

def open_browser():
    """Open browser after a short delay"""
    import time
    time.sleep(1.5)
    webbrowser.open('http://localhost:8000')

@app.route('/api/history', methods=['POST'])
def get_history():
    """Get historical data for a symbol"""
    global tracker
    
    try:
        data = request.get_json()
        symbol = data.get('symbol', 'BTC')
        
        if tracker and hasattr(tracker, 'history'):
            history = tracker.history.get(symbol, {})
            return jsonify({
                'symbol': symbol,
                'history': make_json_serializable(history),
                'has_data': len(history.get('timestamps', [])) > 0
            })
        
        return jsonify({
            'symbol': symbol,
            'history': {},
            'has_data': False
        })
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500
    
if __name__ == '__main__':
    import socket
    PORT = int(os.environ.get('PORT', 8000))  # Render sets PORT env variable
    DEBUG = os.environ.get('DEBUG', 'False').lower() == 'true'

    # Detect if running in cloud or locally
    is_cloud = os.environ.get('RENDER') or os.environ.get('RAILWAY_ENVIRONMENT')
    
    if is_cloud:
        print("""
        ╔═══════════════════════════════════════════════════════════════════════════╗
        ║   CRYPTO RISK SCANNER - CLOUD DEPLOYMENT                                  ║
        ║                                                                           ║
        ║   🌐 Starting Flask Server on Cloud...                                    ║
        ║   🔗 Access via your Render URL                                           ║
        ║   📱 Works on any device with internet connection                         ║
        ║                                                                           ║
        ╚═══════════════════════════════════════════════════════════════════════════╝
        """)
    else:
        # Local deployment - get IP address
        def get_local_ip():
            try:
                s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
                s.connect(("8.8.8.8", 80))
                ip = s.getsockname()[0]
                s.close()
                return ip
            except:
                return "localhost"
        
        local_ip = get_local_ip()
        
        print(f"""
        ╔═══════════════════════════════════════════════════════════════════════════╗
        ║   CRYPTO RISK ASSESSMENT WEB APPLICATION                                  ║
        ║                                                                           ║
        ║   🖥️  Local Access:  http://localhost:{PORT}                              
        ║   📱 Network Access: http://{local_ip}:{PORT}                              
        ║                                                                           ║
        ╚═══════════════════════════════════════════════════════════════════════════╝
        """)
        
        # Open browser in a separate thread (only locally)
        threading.Thread(target=open_browser, daemon=True).start()
    
    # Start Flask app
    # Cloud: Render will set host and port automatically
    # Local: Listen on all interfaces
    app.run(
        host='0.0.0.0',
        port=PORT,
        debug=DEBUG
    )
