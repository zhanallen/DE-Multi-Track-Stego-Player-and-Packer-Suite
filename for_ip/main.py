import os
import sys
import asyncio
import ipaddress
from typing import Dict, Optional
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse
from pydantic import BaseModel

# Add current folder to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from i18n_security import SmartClientContextMiddleware, ClientContext

app = FastAPI(title="Smart i18n & IP Context Security Simulator")

# Configure environment variables
os.environ["TRUSTED_PROXIES"] = "10.0.0.0/8,127.0.0.1/32,172.16.0.0/12,192.168.0.0/16"
os.environ["DEFAULT_LOCALE"] = "en"

SUPPORTED_LOCALES = ["zh", "en", "fr", "es", "ar"]

# Add middleware to the server for standard requests
app.add_middleware(
    SmartClientContextMiddleware,
    supported_locales=SUPPORTED_LOCALES
)

# Simulator Input model
class SimulationRequest(BaseModel):
    peer_ip: str
    headers: Dict[str, str]
    cookies: Dict[str, str]

@app.post("/api/simulate")
async def simulate_context(data: SimulationRequest):
    # Construct a simulated middleware instance
    middleware = SmartClientContextMiddleware(
        app=None,
        supported_locales=SUPPORTED_LOCALES
    )
    
    # Format headers
    raw_headers = []
    for k, v in data.headers.items():
        if v:
            raw_headers.append((k.lower().encode("latin-1"), v.encode("latin-1")))
            
    if data.cookies:
        cookie_parts = []
        for k, v in data.cookies.items():
            if v:
                cookie_parts.append(f"{k}={v}")
        if cookie_parts:
            raw_headers.append((b"cookie", "; ".join(cookie_parts).encode("latin-1")))

    # Construct request scope
    scope = {
        "type": "http",
        "client": (data.peer_ip, 12345),
        "headers": raw_headers,
        "path": "/test",
        "method": "GET",
        "query_string": b"",
    }
    sim_req = Request(scope)
    
    # We call the middleware's internal dispatch logic safely
    async def dummy_call_next(request: Request):
        return JSONResponse({"status": "ok"})
        
    await middleware.dispatch(sim_req, dummy_call_next)
    
    ctx: ClientContext = sim_req.state.client_context
    return ctx.model_dump()

@app.get("/api/my-context")
async def get_my_context(request: Request):
    """Returns the actual context resolved from the user's browser."""
    ctx: ClientContext = request.state.client_context
    return ctx.model_dump()

@app.get("/", response_class=HTMLResponse)
async def serve_dashboard():
    html_content = """<!DOCTYPE html>
<html lang="zh-Hant">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>🌍 Smart i18n & IP Context Security Hub</title>
    <link href="https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&family=Outfit:wght@400;500;600;700;800&family=Fira+Code:wght@400;500&display=swap" rel="stylesheet">
    <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.0/css/all.min.css">
    <script src="https://cdn.jsdelivr.net/npm/mermaid@10/dist/mermaid.min.js"></script>
    <script>
        mermaid.initialize({
            startOnLoad: true,
            theme: 'dark',
            themeVariables: {
                background: '#0b0f19',
                primaryColor: '#8b5cf6',
                primaryTextColor: '#f3f4f6',
                lineColor: '#3b82f6',
                secondaryColor: '#00f2fe'
            }
        });
    </script>
    <style>
        :root {
            --bg-dark: #050811;
            --card-bg: rgba(13, 20, 38, 0.55);
            --card-border: rgba(255, 255, 255, 0.05);
            --text-primary: #f8fafc;
            --text-secondary: #94a3b8;
            --text-muted: #64748b;
            
            /* Accents */
            --teal: #00f2fe;
            --blue: #3b82f6;
            --emerald: #10b981;
            --gold: #f59e0b;
            --rose: #f43f5e;
            --purple: #8b5cf6;
            
            /* Gradients */
            --gradient-teal: linear-gradient(135deg, #00f2fe 0%, #4facfe 100%);
            --gradient-purple: linear-gradient(135deg, #8b5cf6 0%, #d946ef 100%);
            --gradient-rose: linear-gradient(135deg, #f43f5e 0%, #f97316 100%);
            --gradient-card: linear-gradient(135deg, rgba(17, 24, 43, 0.8) 0%, rgba(8, 12, 24, 0.95) 100%);
        }

        * {
            box-sizing: border-box;
            margin: 0;
            padding: 0;
        }

        body {
            font-family: 'Inter', sans-serif;
            background-color: var(--bg-dark);
            color: var(--text-primary);
            min-height: 100vh;
            display: flex;
            flex-direction: column;
            overflow-x: hidden;
            background-image: 
                radial-gradient(at 0% 0%, rgba(59, 130, 246, 0.12) 0px, transparent 50%),
                radial-gradient(at 100% 100%, rgba(139, 92, 246, 0.12) 0px, transparent 50%),
                radial-gradient(at 50% 50%, rgba(0, 242, 254, 0.04) 0px, transparent 60%);
        }

        h1, h2, h3, h4 {
            font-family: 'Outfit', sans-serif;
            font-weight: 600;
        }

        /* Layout */
        header {
            padding: 20px 40px;
            background: rgba(5, 8, 17, 0.8);
            backdrop-filter: blur(16px);
            border-bottom: 1px solid var(--card-border);
            display: flex;
            justify-content: space-between;
            align-items: center;
            position: sticky;
            top: 0;
            z-index: 100;
        }

        .logo-container {
            display: flex;
            align-items: center;
            gap: 12px;
        }

        .logo-icon {
            font-size: 28px;
            background: var(--gradient-teal);
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
            filter: drop-shadow(0 2px 8px rgba(0, 242, 254, 0.3));
        }

        .logo-text {
            font-size: 20px;
            letter-spacing: -0.5px;
        }

        /* Tabs Menu */
        .tab-navigation {
            display: flex;
            gap: 6px;
            background: rgba(15, 23, 42, 0.6);
            border: 1px solid rgba(255, 255, 255, 0.05);
            padding: 5px;
            border-radius: 12px;
            backdrop-filter: blur(8px);
        }

        .tab-btn {
            background: transparent;
            border: none;
            color: var(--text-secondary);
            padding: 8px 18px;
            font-size: 13px;
            font-weight: 600;
            border-radius: 8px;
            cursor: pointer;
            transition: all 0.25s cubic-bezier(0.4, 0, 0.2, 1);
            display: flex;
            align-items: center;
            gap: 8px;
        }

        .tab-btn:hover {
            color: var(--text-primary);
            background: rgba(255, 255, 255, 0.04);
        }

        .tab-btn.active {
            color: #fff;
            background: var(--purple);
            box-shadow: 0 4px 12px rgba(139, 92, 246, 0.35);
        }

        .badge-live {
            background: rgba(16, 185, 129, 0.12);
            border: 1px solid rgba(16, 185, 129, 0.3);
            color: var(--emerald);
            padding: 5px 12px;
            border-radius: 99px;
            font-size: 12px;
            font-weight: 600;
            display: flex;
            align-items: center;
            gap: 6px;
        }

        .badge-live span {
            width: 8px;
            height: 8px;
            background-color: var(--emerald);
            border-radius: 50%;
            display: inline-block;
            animation: pulse 1.8s infinite;
        }

        @keyframes pulse {
            0% { transform: scale(0.95); box-shadow: 0 0 0 0 rgba(16, 185, 129, 0.7); }
            70% { transform: scale(1); box-shadow: 0 0 0 6px rgba(16, 185, 129, 0); }
            100% { transform: scale(0.95); box-shadow: 0 0 0 0 rgba(16, 185, 129, 0); }
        }

        main {
            flex: 1;
            padding: 32px 40px;
            max-width: 1600px;
            width: 100%;
            margin: 0 auto;
            position: relative;
        }

        /* Tab Content Panel Styling */
        .tab-contents-container {
            position: relative;
            width: 100%;
        }

        .tab-content {
            position: absolute;
            left: 0;
            top: 0;
            width: 100%;
            visibility: hidden;
            opacity: 0;
            pointer-events: none;
            transform: translateY(12px);
            transition: opacity 0.35s ease, transform 0.35s ease, visibility 0.35s ease;
        }

        .tab-content.active {
            position: relative;
            visibility: visible;
            opacity: 1;
            pointer-events: auto;
            transform: translateY(0);
        }

        /* Glassmorphism Card style */
        .glass-card {
            background: var(--gradient-card);
            border: 1px solid var(--card-border);
            border-radius: 20px;
            padding: 28px;
            backdrop-filter: blur(20px);
            box-shadow: 0 10px 30px rgba(0, 0, 0, 0.3);
            transition: transform 0.3s ease, border-color 0.3s ease, box-shadow 0.3s ease;
        }

        .glass-card:hover {
            border-color: rgba(255, 255, 255, 0.12);
            box-shadow: 0 15px 35px rgba(0, 0, 0, 0.4);
        }

        .card-title {
            font-size: 17px;
            margin-bottom: 24px;
            display: flex;
            align-items: center;
            gap: 10px;
            border-bottom: 1px solid rgba(255, 255, 255, 0.05);
            padding-bottom: 12px;
        }

        /* Form Inputs */
        .form-group {
            margin-bottom: 20px;
        }

        .form-group label {
            display: block;
            font-size: 13px;
            font-weight: 500;
            color: var(--text-secondary);
            margin-bottom: 8px;
        }

        .input-wrapper {
            position: relative;
        }

        .input-wrapper i {
            position: absolute;
            left: 14px;
            top: 50%;
            transform: translateY(-50%);
            color: rgba(255, 255, 255, 0.3);
            font-size: 14px;
            pointer-events: none;
        }

        input[type="text"], select {
            width: 100%;
            background: rgba(15, 23, 42, 0.6);
            border: 1px solid rgba(255, 255, 255, 0.1);
            border-radius: 10px;
            padding: 12px 14px 12px 40px;
            color: var(--text-primary);
            font-family: inherit;
            font-size: 14px;
            transition: all 0.3s ease;
        }

        input[type="text"]:focus, select:focus {
            outline: none;
            border-color: var(--teal);
            box-shadow: 0 0 12px rgba(0, 242, 254, 0.25);
            background: rgba(15, 23, 42, 0.8);
        }

        /* Buttons & Presets */
        .preset-section {
            margin-bottom: 24px;
        }

        .preset-grid {
            display: grid;
            grid-template-columns: repeat(2, 1fr);
            gap: 10px;
            margin-top: 10px;
        }

        .preset-btn {
            background: rgba(255, 255, 255, 0.02);
            border: 1px solid rgba(255, 255, 255, 0.06);
            border-radius: 8px;
            color: var(--text-secondary);
            padding: 8px 12px;
            font-size: 12px;
            font-weight: 500;
            cursor: pointer;
            text-align: left;
            transition: all 0.2s ease;
            white-space: nowrap;
            overflow: hidden;
            text-overflow: ellipsis;
        }

        .preset-btn:hover {
            background: rgba(255, 255, 255, 0.07);
            color: var(--text-primary);
            border-color: rgba(255, 255, 255, 0.15);
        }

        .preset-btn.active {
            background: rgba(139, 92, 246, 0.12);
            color: #c084fc;
            border-color: rgba(139, 92, 246, 0.4);
            box-shadow: 0 0 8px rgba(139, 92, 246, 0.2);
        }

        .btn-primary {
            width: 100%;
            background: var(--gradient-teal);
            border: none;
            border-radius: 12px;
            color: #0b0f19;
            padding: 14px;
            font-size: 15px;
            font-weight: 700;
            cursor: pointer;
            transition: all 0.3s ease;
            display: flex;
            align-items: center;
            justify-content: center;
            gap: 8px;
            box-shadow: 0 4px 15px rgba(0, 242, 254, 0.25);
        }

        .btn-primary:hover {
            transform: translateY(-2px);
            box-shadow: 0 6px 20px rgba(0, 242, 254, 0.4);
            filter: brightness(1.1);
        }

        .btn-primary:active {
            transform: translateY(1px);
        }

        .btn-secondary {
            width: 100%;
            background: rgba(255, 255, 255, 0.04);
            border: 1px solid rgba(255, 255, 255, 0.08);
            border-radius: 12px;
            color: var(--text-primary);
            padding: 12px;
            font-size: 14px;
            font-weight: 600;
            cursor: pointer;
            transition: all 0.2s ease;
            display: flex;
            align-items: center;
            justify-content: center;
            gap: 8px;
            margin-top: 12px;
        }

        .btn-secondary:hover {
            background: rgba(255, 255, 255, 0.08);
            border-color: rgba(255, 255, 255, 0.18);
        }

        /* Results Display Workspace */
        .simulator-layout {
            display: grid;
            grid-template-columns: 440px 1fr;
            gap: 32px;
        }

        @media (max-width: 1200px) {
            .simulator-layout {
                grid-template-columns: 1fr;
            }
        }

        .results-workspace {
            display: grid;
            grid-template-rows: auto 1fr;
            gap: 32px;
        }

        .overview-row {
            display: grid;
            grid-template-columns: repeat(3, 1fr);
            gap: 20px;
        }

        @media (max-width: 768px) {
            .overview-row {
                grid-template-columns: 1fr;
            }
        }

        .info-card {
            background: rgba(255, 255, 255, 0.015);
            border: 1px solid rgba(255, 255, 255, 0.04);
            border-radius: 16px;
            padding: 20px;
            display: flex;
            flex-direction: column;
            gap: 10px;
            position: relative;
            overflow: hidden;
        }

        .info-card::before {
            content: '';
            position: absolute;
            top: 0;
            left: 0;
            width: 4px;
            height: 100%;
        }

        .info-card.ip-card::before { background: var(--gradient-teal); }
        .info-card.locale-card::before { background: var(--gradient-purple); }
        .info-card.geo-card::before { background: var(--gradient-rose); }

        .info-label {
            font-size: 11px;
            text-transform: uppercase;
            letter-spacing: 0.5px;
            color: var(--text-secondary);
            font-weight: 600;
            line-height: 1.4;
        }

        .info-value {
            font-size: 22px;
            font-weight: 700;
            font-family: 'Outfit', sans-serif;
            display: flex;
            align-items: center;
            gap: 8px;
        }

        .info-subtext {
            font-size: 12px;
            color: var(--text-secondary);
            display: flex;
            align-items: center;
            gap: 4px;
        }

        /* Details Grid */
        .details-grid {
            display: grid;
            grid-template-columns: 1fr 1fr;
            gap: 24px;
        }

        @media (max-width: 992px) {
            .details-grid {
                grid-template-columns: 1fr;
            }
        }

        /* Visual Decision Tree Node list */
        .decision-tree {
            display: flex;
            flex-direction: column;
            gap: 12px;
        }

        .tree-node {
            background: rgba(255, 255, 255, 0.01);
            border: 1px solid rgba(255, 255, 255, 0.03);
            border-radius: 12px;
            padding: 14px 18px;
            display: flex;
            align-items: center;
            justify-content: space-between;
            transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
            position: relative;
        }

        .tree-node::before {
            content: '';
            position: absolute;
            left: 0;
            top: 0;
            width: 3px;
            height: 100%;
            background: transparent;
            transition: all 0.3s ease;
        }

        .tree-node.active {
            background: rgba(139, 92, 246, 0.06);
            border-color: rgba(139, 92, 246, 0.25);
            transform: translateX(4px);
            box-shadow: 0 4px 15px rgba(0, 0, 0, 0.15);
        }

        .tree-node.active::before {
            background: var(--purple);
        }

        .node-left {
            display: flex;
            align-items: center;
            gap: 12px;
            flex: 1;
            padding-right: 12px;
        }

        .node-index {
            background: rgba(255, 255, 255, 0.04);
            border-radius: 50%;
            width: 24px;
            height: 24px;
            display: flex;
            align-items: center;
            justify-content: center;
            font-size: 11px;
            font-weight: 700;
            color: var(--text-secondary);
        }

        .tree-node.active .node-index {
            background: var(--purple);
            color: #fff;
        }

        .node-info h4 {
            font-size: 13px;
            font-weight: 600;
        }

        .node-info p {
            font-size: 11px;
            color: var(--text-secondary);
            margin-top: 2px;
            line-height: 1.4;
        }

        .node-status {
            font-size: 11px;
            font-weight: 600;
            padding: 4px 8px;
            border-radius: 6px;
            background: rgba(255, 255, 255, 0.04);
            color: var(--text-secondary);
            white-space: nowrap;
        }

        .tree-node.active .node-status {
            background: rgba(139, 92, 246, 0.2);
            color: #c084fc;
        }

        /* JSON Output Panel */
        .json-panel {
            display: flex;
            flex-direction: column;
            height: 100%;
        }

        .json-header {
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 12px;
            font-size: 11px;
            color: var(--text-secondary);
            text-transform: uppercase;
            letter-spacing: 1px;
        }

        .code-container {
            flex: 1;
            background: #04060d;
            border: 1px solid rgba(255, 255, 255, 0.04);
            border-radius: 12px;
            padding: 20px;
            overflow: auto;
            font-family: 'Fira Code', monospace;
            font-size: 13px;
            line-height: 1.5;
            color: #38bdf8;
            max-height: 480px;
            box-shadow: inset 0 2px 8px rgba(0, 0, 0, 0.5);
        }

        .code-container pre {
            white-space: pre-wrap;
            word-break: break-all;
        }

        .keyword { color: #f43f5e; }
        .string { color: #10b981; }
        .number { color: #f59e0b; }
        .boolean { color: #8b5cf6; }
        .null { color: #6b7280; }

        /* General Badge tags */
        .tag {
            display: inline-flex;
            align-items: center;
            padding: 2px 8px;
            border-radius: 4px;
            font-size: 11px;
            font-weight: 600;
            text-transform: uppercase;
        }

        .tag-teal { background: rgba(0, 242, 254, 0.08); color: var(--teal); border: 1px solid rgba(0, 242, 254, 0.15); }
        .tag-rose { background: rgba(244, 63, 94, 0.08); color: var(--rose); border: 1px solid rgba(244, 63, 94, 0.15); }
        .tag-purple { background: rgba(139, 92, 246, 0.08); color: #c084fc; border: 1px solid rgba(139, 92, 246, 0.15); }
        .tag-emerald { background: rgba(16, 185, 129, 0.08); color: var(--emerald); border: 1px solid rgba(16, 185, 129, 0.15); }
        .tag-gold { background: rgba(245, 158, 11, 0.08); color: var(--gold); border: 1px solid rgba(245, 158, 11, 0.15); }

        /* Dictionary tab styling */
        .dictionary-layout {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(360px, 1fr));
            gap: 24px;
        }

        .dict-card {
            display: flex;
            flex-direction: column;
            gap: 16px;
        }

        .dict-item {
            background: rgba(15, 23, 42, 0.4);
            border: 1px solid rgba(255, 255, 255, 0.03);
            border-radius: 10px;
            padding: 14px;
            display: flex;
            flex-direction: column;
            gap: 6px;
            transition: all 0.25s ease;
        }

        .dict-item:hover {
            background: rgba(15, 23, 42, 0.65);
            border-color: rgba(255, 255, 255, 0.08);
            transform: translateY(-2px);
        }

        .dict-field {
            font-family: 'Fira Code', monospace;
            font-size: 13.5px;
            color: var(--teal);
            font-weight: 600;
        }

        .dict-explanation {
            font-size: 12.5px;
            color: var(--text-secondary);
            line-height: 1.5;
        }

        footer {
            padding: 24px;
            text-align: center;
            border-top: 1px solid var(--card-border);
            font-size: 12px;
            color: var(--text-secondary);
            margin-top: auto;
            background: rgba(5, 8, 17, 0.9);
        }

        footer a {
            color: var(--teal);
            text-decoration: none;
        }
        
        footer a:hover {
            text-decoration: underline;
        }
    </style>
</head>
<body>
    <header>
        <div class="logo-container">
            <i class="fa-solid fa-shield-halved logo-icon"></i>
            <div>
                <h1 class="logo-text">i18n & IP Context Security</h1>
                <p style="font-size: 11px; color: var(--text-secondary);">FastAPI Zero-Trust Middleware Hub</p>
            </div>
        </div>
        
        <!-- Tabbed Menu navigation -->
        <nav class="tab-navigation">
            <button class="tab-btn active" onclick="switchTab('tab-simulator')">
                <i class="fa-solid fa-square-poll-horizontal"></i> 即時模擬分析
            </button>
            <button class="tab-btn" onclick="switchTab('tab-flowchart')">
                <i class="fa-solid fa-diagram-project"></i> 決策樹流程圖
            </button>
            <button class="tab-btn" onclick="switchTab('tab-dictionary')">
                <i class="fa-solid fa-book-bookmark"></i> 安全欄位字典
            </button>
        </nav>
        
        <div class="badge-live">
            <span></span>模擬器已啟動 (Uvicorn Live)
        </div>
    </header>

    <main>
        <div class="tab-contents-container">
            
            <!-- Tab 1: Live Simulator -->
            <div id="tab-simulator" class="tab-content active">
                <div class="simulator-layout">
                    <!-- Simulation Input Form -->
                    <div class="glass-card" style="height: fit-content;">
                        <h3 class="card-title"><i class="fa-solid fa-sliders"></i> 模擬環境設定</h3>
                        
                        <div class="preset-section">
                            <label style="font-size: 12px; font-weight: 600; color: var(--text-secondary);">選擇場景預設樣版：</label>
                            <div class="preset-grid">
                                <button class="preset-btn active" onclick="loadPreset('cf-fr')">🇫🇷 Cloudflare 法國用戶</button>
                                <button class="preset-btn" onclick="loadPreset('spoof-direct')">🚨 TC-01 IP偽造攻擊</button>
                                <button class="preset-btn" onclick="loadPreset('deep-spoof')">🛡️ TC-02 深度偽造防禦</button>
                                <button class="preset-btn" onclick="loadPreset('cookie-override')">🍪 Cookie 強制切換</button>
                                <button class="preset-btn" onclick="loadPreset('sqli-attack')">💉 TC-04 SQL 注入嘗試</button>
                                <button class="preset-btn" onclick="loadPreset('tw-mobile')">🇹🇼 台灣中華電信直連</button>
                            </div>
                            <button class="preset-btn" onclick="detectMyPublicIP(event)" style="width: 100%; margin-top: 10px; background: rgba(0, 242, 254, 0.06); color: var(--teal); border-color: rgba(0, 242, 254, 0.2); font-weight: 600; height: 38px; text-align: center; display: flex; align-items: center; justify-content: center; gap: 8px;">
                                <i class="fa-solid fa-crosshairs"></i> 🔍 自動偵測並模擬我手機的真實 IP
                            </button>
                        </div>

                        <form id="simulator-form" onsubmit="runSimulation(event)">
                            <!-- Peer IP -->
                            <div class="form-group">
                                <label for="peer_ip">TCP Peer IP (Socket 連線直接來源 IP，代表直接與伺服器連線的用戶或代理 IP)</label>
                                <div class="input-wrapper">
                                    <i class="fa-solid fa-ethernet"></i>
                                    <input type="text" id="peer_ip" value="103.21.244.5" required>
                                </div>
                            </div>

                            <!-- CF-Connecting-IP -->
                            <div class="form-group">
                                <label for="cf_connecting_ip">CF-Connecting-IP Header (由 Cloudflare 邊緣節點注入的用戶真實 IP，無法被用戶偽造)</label>
                                <div class="input-wrapper">
                                    <i class="fa-solid fa-cloud"></i>
                                    <input type="text" id="cf_connecting_ip" value="198.51.100.22">
                                </div>
                            </div>

                            <!-- X-Forwarded-For -->
                            <div class="form-group">
                                <label for="x_forwarded_for">X-Forwarded-For Header (反向代理鏈路 IP 列表，格式為 Client, Proxy1, Proxy2...)</label>
                                <div class="input-wrapper">
                                    <i class="fa-solid fa-network-wired"></i>
                                    <input type="text" id="x_forwarded_for" value="198.51.100.22">
                                </div>
                            </div>

                            <!-- CF-IPCountry -->
                            <div class="form-group">
                                <label for="cf_ipcountry">CF-IPCountry Header (由 Cloudflare 邊緣偵測並注入的 ISO 雙字元國家代碼，如 TW、US)</label>
                                <div class="input-wrapper">
                                    <i class="fa-solid fa-globe"></i>
                                    <input type="text" id="cf_ipcountry" value="FR">
                                </div>
                            </div>

                            <!-- Accept-Language -->
                            <div class="form-group">
                                <label for="accept_language">Accept-Language Header (瀏覽器設定的語系偏好與權重，如 zh-TW,zh;q=0.9)</label>
                                <div class="input-wrapper">
                                    <i class="fa-solid fa-language"></i>
                                    <input type="text" id="accept_language" value="fr-FR,fr;q=0.9,en;q=0.8">
                                </div>
                            </div>

                            <!-- Cookie locale -->
                            <div class="form-group">
                                <label for="cookie_locale">Cookie: locale (用戶手動在網頁切換並保存的語系代碼，代表用戶的主動意圖)</label>
                                <div class="input-wrapper">
                                    <i class="fa-solid fa-cookie"></i>
                                    <input type="text" id="cookie_locale" value="">
                                </div>
                            </div>

                            <!-- X-Client-Timezone -->
                            <div class="form-group">
                                <label for="client_timezone">X-Client-Timezone Header (由前端 JavaScript 從用戶手機或瀏覽器裝置中自動偵測的真實時區，如 Asia/Taipei)</label>
                                <div class="input-wrapper">
                                    <i class="fa-solid fa-clock"></i>
                                    <input type="text" id="client_timezone" value="">
                                </div>
                            </div>

                            <button type="submit" class="btn-primary">
                                <i class="fa-solid fa-bolt"></i> 開始模擬解析
                            </button>
                        </form>

                        <button onclick="useActualBrowser()" class="btn-secondary">
                            <i class="fa-solid fa-computer"></i> 使用我真實的瀏覽器 Context
                        </button>
                    </div>

                    <!-- Output Visualizations -->
                    <div class="results-workspace">
                        <!-- Summary Row -->
                        <div class="overview-row">
                            <!-- IP Card -->
                            <div class="info-card ip-card">
                                <span class="info-label">安全解析 IP (client.ip) <br/>(防禦偽造攻擊後的真實來源客戶端 IP)</span>
                                <div class="info-value" id="res-ip">-</div>
                                <div class="info-subtext" id="res-proxy-badge">
                                    <span class="tag tag-teal">確認直連</span>
                                </div>
                            </div>

                            <!-- Locale Card -->
                            <div class="info-card locale-card">
                                <span class="info-label">確定語系 (i18n.detected_locale) <br/>(系統最終決策之最適國際化語系代碼)</span>
                                <div class="info-value" id="res-locale">-</div>
                                <div class="info-subtext" id="res-locale-badge">
                                    <i class="fa-solid fa-circle-nodes"></i> Decision Source
                                </div>
                            </div>

                            <!-- Geo Card -->
                            <div class="info-card geo-card">
                                <span class="info-label">地理定位 (geo.country_code) <br/>(客戶端 IP 所屬國家代碼與對應時區)</span>
                                <div class="info-value" id="res-geo">-</div>
                                <div class="info-subtext" id="res-timezone">
                                    <i class="fa-solid fa-clock"></i> Timezone
                                </div>
                            </div>
                        </div>

                        <!-- Details & JSON -->
                        <div class="details-grid">
                            <!-- Decision Tree visualizer -->
                            <div class="glass-card">
                                <h3 class="card-title"><i class="fa-solid fa-diagram-project"></i> 語系決策路徑分析</h3>
                                <div class="decision-tree">
                                    <!-- Node 1 -->
                                    <div class="tree-node" id="node-cookie">
                                        <div class="node-left">
                                            <div class="node-index">1</div>
                                            <div class="node-info">
                                                <h4>Cookie 白名單驗證 (EXPLICIT_COOKIE)</h4>
                                                <p>(優先檢查使用者手動於網頁設定並保存之語系 Cookie，代表主動意圖)</p>
                                            </div>
                                        </div>
                                        <div class="node-status">未匹配</div>
                                    </div>

                                    <!-- Node 2a -->
                                    <div class="tree-node" id="node-header-precise">
                                        <div class="node-left">
                                            <div class="node-index">2a</div>
                                            <div class="node-info">
                                                <h4>瀏覽器 Header 精確匹配 (ACCEPT_LANGUAGE_HEADER)</h4>
                                                <p>(檢查瀏覽器內建 Accept-Language 是否與支援列表精確吻合，如 zh 對應 zh)</p>
                                            </div>
                                        </div>
                                        <div class="node-status">未匹配</div>
                                    </div>

                                    <!-- Node 2b -->
                                    <div class="tree-node" id="node-header-fuzzy">
                                        <div class="node-left">
                                            <div class="node-index">2b</div>
                                            <div class="node-info">
                                                <h4>瀏覽器 Header 模糊降級 (ACCEPT_LANGUAGE_HEADER)</h4>
                                                <p>(將 Accept-Language 區域代碼進行主標籤模糊化切分，如 zh-TW 降級匹配至 zh)</p>
                                            </div>
                                        </div>
                                        <div class="node-status">未匹配</div>
                                    </div>

                                    <!-- Node 3 -->
                                    <div class="tree-node" id="node-cf-geo">
                                        <div class="node-left">
                                            <div class="node-index">3</div>
                                            <div class="node-info">
                                                <h4>Cloudflare 邊緣 GeoIP (CF_EDGE_GEOIP)</h4>
                                                <p>(讀取 Cloudflare 邊緣節點基於地理位置判定並注入之國家代碼，對照預設語系對照表)</p>
                                            </div>
                                        </div>
                                        <div class="node-status">未匹配</div>
                                    </div>

                                    <!-- Node 4 -->
                                    <div class="tree-node" id="node-local-geo">
                                        <div class="node-left">
                                            <div class="node-index">4</div>
                                            <div class="node-info">
                                                <h4>離線 DB-IP 本機資料庫 (LOCAL_DB_GEOIP)</h4>
                                                <p>(藉由本機離線 mmdb 資料庫查詢真實 Client IP 所屬國家，對照該國家預設之常用語系)</p>
                                            </div>
                                        </div>
                                        <div class="node-status">未匹配</div>
                                    </div>

                                    <!-- Node 5 -->
                                    <div class="tree-node" id="node-default">
                                        <div class="node-left">
                                            <div class="node-index">5</div>
                                            <div class="node-info">
                                                <h4>系統預設 Fallback (SYSTEM_DEFAULT)</h4>
                                                <p>(若以上路徑皆未能成功匹配，則強制降級採用系統定義之預設語系 en)</p>
                                            </div>
                                        </div>
                                        <div class="node-status">未匹配</div>
                                    </div>
                                </div>
                            </div>

                            <!-- Code View -->
                            <div class="json-panel">
                                <div class="json-header">
                                    <span><i class="fa-solid fa-code"></i> resolved_context payload (經過防偽造解析後的 Pydantic 資料載荷)</span>
                                    <span style="font-size: 11px;">Pydantic JSON</span>
                                </div>
                                <div class="code-container">
                                    <pre id="json-output">// 執行模擬後，此處將輸出解析後的 ClientContext JSON 資料</pre>
                                </div>
                            </div>
                        </div>
                    </div>
                </div>
            </div>

            <!-- Tab 2: Decision Flowchart -->
            <div id="tab-flowchart" class="tab-content">
                <div class="glass-card" style="width: 100%;">
                    <h3 class="card-title"><i class="fa-solid fa-route"></i> 語系決策樹分析流程圖</h3>
                    <div style="background: rgba(11, 15, 25, 0.4); border-radius: 12px; padding: 32px; overflow-x: auto; display: flex; justify-content: center; border: 1px solid rgba(255, 255, 255, 0.05);">
                        <pre class="mermaid" style="background: transparent; border: none; margin: 0; width: 100%; display: flex; justify-content: center;">
graph TD
    Start(["用戶發送請求"]) --> P1{"1. Cookie 'locale'<br/>是否有效且在白名單?"}
    P1 -- 是 --> S1["EXPLICIT_COOKIE<br/>信心指數: 1.0"]
    
    P1 -- 否 --> P2{"2. Accept-Language Header<br/>是否存在?"}
    P2 -- 是 --> P2a{"2a. 精確匹配<br/>是否在支援列表?"}
    P2a -- 是 --> S2a["ACCEPT_LANGUAGE_HEADER (Precise)<br/>信心指數: 0.85"]
    P2a -- 否 --> P2b{"2b. 模糊降級/主語系<br/>是否在支援列表?"}
    P2b -- 是 --> S2b["ACCEPT_LANGUAGE_HEADER (Fuzzy)<br/>信心指數: 0.65"]
    
    P2 -- 否 --> P3{"3. CF-IPCountry Header<br/>是否存在且在對照表中?"}
    P2b -- 否 --> P3
    
    P3 -- 是 --> P3a{"對照語系<br/>是否在支援列表?"}
    P3a -- 是 --> S3["CF_EDGE_GEOIP<br/>信心指數: 0.7"]
    
    P3 -- 否 --> P4{"4. 本機 DB-IP 庫查詢<br/>是否有國家代碼且在對照表中?"}
    P3a -- 否 --> P4
    
    P4 -- 是 --> P4a{"對照語系<br/>是否在支援列表?"}
    P4a -- 是 --> S4["LOCAL_DB_GEOIP<br/>信心指數: 0.7"]
    
    P4 -- 否 --> P5["5. 系統預設<br/>信心指數: 0.1"]
    P4a -- 否 --> P5
    
    S1 --> End(["寫入 request.state.client_context"])
    S2a --> End
    S2b --> End
    S3 --> End
    S4 --> End
    P5 --> S5["語系 = DEFAULT_LOCALE"] --> End
                        </pre>
                    </div>
                </div>
            </div>

            <!-- Tab 3: Security Fields Dictionary -->
            <div id="tab-dictionary" class="tab-content">
                <div class="dictionary-layout">
                    <!-- ClientInfo Card -->
                    <div class="glass-card dict-card">
                        <h3 class="card-title" style="color: var(--teal); border-color: rgba(0, 242, 254, 0.15);"><i class="fa-solid fa-user-shield"></i> ClientInfo (客戶端來源查驗安全資料)</h3>
                        
                        <div class="dict-item">
                            <span class="dict-field">client.ip</span>
                            <span class="dict-explanation">(代表經過防禦 XFF 或 Cloudflare IP 偽造篡改查驗後的「最終真實客戶端來源 IP 位址」，供安全性存取控制與防護決策使用)</span>
                        </div>
                        
                        <div class="dict-item">
                            <span class="dict-field">client.is_proxy_detected</span>
                            <span class="dict-explanation">(布林值，代表該請求鏈路中是否曾經過「受信任的反向代理伺服器」（如 Cloudflare 節點或自建內部 Ingress/Nginx）)</span>
                        </div>
                        
                        <div class="dict-item">
                            <span class="dict-field">client.proxy_type</span>
                            <span class="dict-explanation">(字串或空值，指示偵測到的代理伺服器類型：'Cloudflare'（快速通道）、'Generic'（自建 Nginx/ALB 反向代理鏈路）或 None（代表直接連線）)</span>
                        </div>
                    </div>

                    <!-- I18nInfo Card -->
                    <div class="glass-card dict-card">
                        <h3 class="card-title" style="color: var(--purple); border-color: rgba(139, 92, 246, 0.15);"><i class="fa-solid fa-language"></i> I18nInfo (國際化多語系決策屬性)</h3>
                        
                        <div class="dict-item">
                            <span class="dict-field">i18n.detected_locale</span>
                            <span class="dict-explanation">(代表系統判定最合適請求適用的「國際化 BCP-47 語系代碼」，例如 'zh' 或 'en'，業務端可直接讀取此字串載入語言翻譯資源檔)</span>
                        </div>
                        
                        <div class="dict-item">
                            <span class="dict-field">i18n.decision_source</span>
                            <span class="dict-explanation">(代表系統決定該語系的「信賴來源途徑」：EXPLICIT_COOKIE、ACCEPT_LANGUAGE_HEADER、CF_EDGE_GEOIP、LOCAL_DB_GEOIP 或 SYSTEM_DEFAULT，用於日誌追蹤)</span>
                        </div>
                        
                        <div class="dict-item">
                            <span class="dict-field">i18n.confidence_score</span>
                            <span class="dict-explanation">(浮點數值，代表語系判定結果的「信賴度評分」，介於 0.1 至 1.0 之間。若評分小於 0.7，建議在前端彈出切換語言的詢問框)</span>
                        </div>
                    </div>

                    <!-- GeoInfo Card -->
                    <div class="glass-card dict-card">
                        <h3 class="card-title" style="color: var(--rose); border-color: rgba(244, 63, 94, 0.15);"><i class="fa-solid fa-map-location-dot"></i> GeoInfo (地理定位與時區安全資料)</h3>
                        
                        <div class="dict-item">
                            <span class="dict-field">geo.country_code</span>
                            <span class="dict-explanation">(代表解析出的「ISO 雙字元國家代碼」，例如 'TW'、'FR'、'US'，可用於地區內容授權控制或粗粒度市場行銷投放判定)</span>
                        </div>
                        
                        <div class="dict-item">
                            <span class="dict-field">geo.timezone</span>
                            <span class="dict-explanation">(代表客戶端標準的「時區地區名稱」，例如 'Asia/Taipei'。優先由前端傳送的 X-Client-Timezone Header 注入，若無則透過 IP 位址地理定位模糊預估)</span>
                        </div>
                    </div>
                </div>
            </div>

        </div>
    </main>

    <footer>
        <p>🔒 <strong>Zero-Trust Boundary Validation</strong> | IP Geolocation by <a href="https://db-ip.com" target="_blank">DB-IP</a> (CC BY 4.0)</p>
    </footer>

    <script>
        const PRESETS = {
            'cf-fr': {
                peer_ip: '103.21.244.5', // Cloudflare Edge Node
                cf_connecting_ip: '198.51.100.22', // Real client in France
                x_forwarded_for: '198.51.100.22',
                cf_ipcountry: 'FR',
                accept_language: 'fr-FR,fr;q=0.9,en;q=0.8',
                cookie_locale: ''
            },
            'spoof-direct': {
                peer_ip: '203.0.113.45', // Real malicious client
                cf_connecting_ip: '',
                x_forwarded_for: '8.8.8.8', // Spoofed Google DNS
                cf_ipcountry: '',
                accept_language: 'zh-TW,zh;q=0.9',
                cookie_locale: ''
            },
            'deep-spoof': {
                peer_ip: '10.0.0.1', // Trusted Ingress proxy
                cf_connecting_ip: '',
                x_forwarded_for: '1.1.1.1, 103.21.244.1, 203.0.113.45', // Truncates at 203.0.113.45
                cf_ipcountry: '',
                accept_language: 'en-US,en;q=0.9',
                cookie_locale: ''
            },
            'cookie-override': {
                peer_ip: '203.0.113.45',
                cf_connecting_ip: '',
                x_forwarded_for: '',
                cf_ipcountry: '',
                accept_language: 'en-US,en;q=0.9',
                cookie_locale: 'zh' // Whitelisted cookie overrides header
            },
            'sqli-attack': {
                peer_ip: '203.0.113.45',
                cf_connecting_ip: '',
                x_forwarded_for: '',
                cf_ipcountry: '',
                accept_language: "'; DROP TABLE users;-- , zh;q=0.9", // SQLi safely discarded
                cookie_locale: 'xx-invalid'
            },
            'tw-mobile': {
                peer_ip: '168.95.1.1', // Taiwan mobile user direct connect
                cf_connecting_ip: '',
                x_forwarded_for: '',
                cf_ipcountry: '',
                accept_language: 'zh-TW,zh;q=0.9',
                cookie_locale: ''
            }
        };

        function switchTab(tabId) {
            // Remove active class from all tabs
            document.querySelectorAll('.tab-btn').forEach(btn => btn.classList.remove('active'));
            // Hide all tab content
            document.querySelectorAll('.tab-content').forEach(content => content.classList.remove('active'));
            
            // Set active classes
            const activeBtn = Array.from(document.querySelectorAll('.tab-btn')).find(btn => btn.getAttribute('onclick').includes(tabId));
            if (activeBtn) activeBtn.classList.add('active');
            
            const activeContent = document.getElementById(tabId);
            if (activeContent) activeContent.classList.add('active');
        }

        async function detectMyPublicIP(event) {
            const btn = event.currentTarget;
            const originalText = btn.innerHTML;
            btn.innerHTML = `<i class="fa-solid fa-spinner fa-spin"></i> 正在獲取真實外網 IP...`;
            btn.disabled = true;
            
            try {
                const ipRes = await fetch('https://api.ipify.org?format=json');
                if (!ipRes.ok) throw new Error('API request failed');
                const ipData = await ipRes.json();
                const publicIP = ipData.ip;
                
                // Populate inputs
                document.getElementById('peer_ip').value = publicIP;
                document.getElementById('cf_connecting_ip').value = '';
                document.getElementById('x_forwarded_for').value = '';
                document.getElementById('cf_ipcountry').value = '';
                document.getElementById('accept_language').value = navigator.language || 'zh-TW,zh;q=0.9';
                document.getElementById('cookie_locale').value = '';
                document.getElementById('client_timezone').value = Intl.DateTimeFormat().resolvedOptions().timeZone;
                
                // Set active classes
                document.querySelectorAll('.preset-btn').forEach(b => b.classList.remove('active'));
                btn.classList.add('active');
                
                // Run simulation
                await runSimulation();
            } catch (err) {
                alert('自動偵測公網 IP 失敗，請手動複製輸入。錯誤: ' + err.message);
            } finally {
                btn.innerHTML = originalText;
                btn.disabled = false;
            }
        }

        function loadPreset(key) {
            document.querySelectorAll('.preset-btn').forEach(btn => btn.classList.remove('active'));
            event.target.classList.add('active');
            
            const preset = PRESETS[key];
            if (preset) {
                document.getElementById('peer_ip').value = preset.peer_ip;
                document.getElementById('cf_connecting_ip').value = preset.cf_connecting_ip;
                document.getElementById('x_forwarded_for').value = preset.x_forwarded_for;
                document.getElementById('cf_ipcountry').value = preset.cf_ipcountry;
                document.getElementById('accept_language').value = preset.accept_language;
                document.getElementById('cookie_locale').value = preset.cookie_locale;
                document.getElementById('client_timezone').value = preset.client_timezone || Intl.DateTimeFormat().resolvedOptions().timeZone;
            }
        }

        async function runSimulation(e) {
            if (e) e.preventDefault();
            
            const data = {
                peer_ip: document.getElementById('peer_ip').value.trim(),
                headers: {
                    'CF-Connecting-IP': document.getElementById('cf_connecting_ip').value.trim(),
                    'X-Forwarded-For': document.getElementById('x_forwarded_for').value.trim(),
                    'CF-IPCountry': document.getElementById('cf_ipcountry').value.trim(),
                    'Accept-Language': document.getElementById('accept_language').value.trim(),
                    'X-Client-Timezone': document.getElementById('client_timezone').value.trim(),
                },
                cookies: {
                    'locale': document.getElementById('cookie_locale').value.trim()
                }
            };

            try {
                const response = await fetch('/api/simulate', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify(data)
                });
                
                const result = await response.json();
                updateVisuals(result);
            } catch (err) {
                alert('模擬執行出錯: ' + err);
            }
        }

        async function useActualBrowser() {
            try {
                const tz = Intl.DateTimeFormat().resolvedOptions().timeZone;
                const response = await fetch('/api/my-context', {
                    headers: {
                        'X-Client-Timezone': tz
                    }
                });
                const result = await response.json();
                
                // Populate inputs with current actual values
                document.getElementById('peer_ip').value = '127.0.0.1'; // Local socket host
                document.getElementById('cf_connecting_ip').value = '';
                document.getElementById('x_forwarded_for').value = '';
                document.getElementById('cf_ipcountry').value = '';
                document.getElementById('accept_language').value = navigator.language;
                document.getElementById('cookie_locale').value = '';
                document.getElementById('client_timezone').value = tz;
                
                updateVisuals(result);
            } catch (err) {
                alert('獲取真實 Context 失敗: ' + err);
            }
        }

        function updateVisuals(data) {
            // 1. Update Cards
            document.getElementById('res-ip').innerText = data.client.ip;
            
            // Proxy badge
            const proxyBadge = document.getElementById('res-proxy-badge');
            if (data.client.is_proxy_detected) {
                proxyBadge.innerHTML = `<span class="tag tag-rose"><i class="fa-solid fa-triangle-exclamation"></i> 偵測到代理 (${data.client.proxy_type})</span>`;
            } else {
                proxyBadge.innerHTML = `<span class="tag tag-emerald"><i class="fa-solid fa-check"></i> 安全直連</span>`;
            }
            
            // Locale card
            document.getElementById('res-locale').innerHTML = `<i class="fa-solid fa-language" style="color: var(--purple);"></i> ${data.i18n.detected_locale.toUpperCase()}`;
            document.getElementById('res-locale-badge').innerHTML = `<span class="tag tag-purple">依據: ${data.i18n.decision_source} (信心度: ${data.i18n.confidence_score})</span>`;
            
            // Geo card
            const country = data.geo.country_code || '未知';
            const flagMap = { 'TW': '🇹🇼', 'CN': '🇨🇳', 'FR': '🇫🇷', 'ES': '🇪🇸', 'AR': '🇸🇦', 'US': '🇺🇸', 'GB': '🇬🇧' };
            const flag = flagMap[country] || '🏳️';
            document.getElementById('res-geo').innerText = `${flag} ${country}`;
            document.getElementById('res-timezone').innerText = data.geo.timezone || '無時區資料';

            // 2. Highlight Decision Tree Nodes
            document.querySelectorAll('.tree-node').forEach(node => {
                node.classList.remove('active');
                node.querySelector('.node-status').innerText = '未匹配';
            });

            const source = data.i18n.decision_source;
            const score = data.i18n.confidence_score;
            let activeNodeId = '';

            if (source === 'EXPLICIT_COOKIE') {
                activeNodeId = 'node-cookie';
            } else if (source === 'ACCEPT_LANGUAGE_HEADER') {
                if (score === 0.85) {
                    activeNodeId = 'node-header-precise';
                } else {
                    activeNodeId = 'node-header-fuzzy';
                }
            } else if (source === 'CF_EDGE_GEOIP') {
                activeNodeId = 'node-cf-geo';
            } else if (source === 'LOCAL_DB_GEOIP') {
                activeNodeId = 'node-local-geo';
            } else if (source === 'SYSTEM_DEFAULT') {
                activeNodeId = 'node-default';
            }

            if (activeNodeId) {
                const activeNode = document.getElementById(activeNodeId);
                activeNode.classList.add('active');
                activeNode.querySelector('.node-status').innerText = '命中匹配';
            }

            // 3. Update Raw JSON Payload with Syntax Highlight
            const outputPre = document.getElementById('json-output');
            const jsonString = JSON.stringify(data, null, 2);
            outputPre.innerHTML = syntaxHighlight(jsonString);
        }

        function syntaxHighlight(json) {
            json = json.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
            return json.replace(/("(\\u[a-zA-Z0-9]{4}|\\[^u]|[^\\"])*"(\s*:)?|\b(true|false|null)\b|-?\d+(?:\.\d*)?(?:[eE][+-]?\d+)?)/g, function (match) {
                let cls = 'number';
                if (/^"/.test(match)) {
                    if (/:$/.test(match)) {
                        cls = 'keyword';
                    } else {
                        cls = 'string';
                    }
                } else if (/true|false/.test(match)) {
                    cls = 'boolean';
                } else if (/null/.test(match)) {
                    cls = 'null';
                }
                return '<span class="' + cls + '">' + match + '</span>';
            });
        }

        // Trigger simulation on load
        window.onload = () => {
            document.getElementById('client_timezone').value = Intl.DateTimeFormat().resolvedOptions().timeZone;
            runSimulation();
        };
    </script>
</body>
</html>
"""
    return HTMLResponse(content=html_content)

if __name__ == "__main__":
    import uvicorn
    import socket
    
    def get_local_ip():
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            s.connect(('10.255.255.255', 1))
            IP = s.getsockname()[0]
        except Exception:
            IP = '127.0.0.1'
        finally:
            s.close()
        return IP

    local_ip = get_local_ip()
    print("\n" + "="*60)
    print("i18n & IP Context Security Simulator")
    print(f"Local access:  http://127.0.0.1:8000")
    print(f"Mobile access: http://{local_ip}:8000 (Please make sure both devices are on the same Wi-Fi)")
    print("="*60 + "\n")
    
    uvicorn.run(app, host="0.0.0.0", port=8000)
