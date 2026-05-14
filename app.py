import os
import time
from flask import Flask, request, jsonify, render_template, send_from_directory, Response, stream_with_context
from quant_logic import QuantLogic
from flask_cors import CORS
import pandas as pd
from datetime import datetime
from google import genai
import threading
import pytz
import json
import re
import io
import base64
import matplotlib.pyplot as plt
import matplotlib
matplotlib.use('Agg')

app = Flask(__name__)
CORS(app)

# Global progress state
progress_state = {"status": "idle", "progress": 0, "logs": [], "error": None}

@app.route('/progress', methods=['GET'])
def get_progress():
    global progress_state
    return jsonify(progress_state)

def update_progress(pct, msg, error_enc=None):
    global progress_state
    if error_enc:
        progress_state["error"] = error_enc
    if pct is not None:
        progress_state["progress"] = pct
    if msg:
        now_str = datetime.now().strftime('%H:%M:%S')
        progress_state["logs"].append(f"[{now_str}] {msg}")

logic_mgr = QuantLogic()
def save_results_to_html(result, query, buy_logic, sell_logic):
    try:
        now = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"Report_{now}.html"
        dir_name = os.path.join(os.path.dirname(os.path.abspath(__file__)), "Memories")
        os.makedirs(dir_name, exist_ok=True)
        filepath = os.path.join(dir_name, filename)

        stats = result.get('detailed_stats', {})
        ai_report = result.get('ai_report', "보고서 생성 실패")
        trades = result.get('trade_history', [])
        returns = result.get('returns_data', [])

        # 그래프 생성 및 별도 이미지 저장
        graph_filename = f"Graph_{now}.png"
        graph_filepath = os.path.join(dir_name, graph_filename)
        graph_base64 = ""
        
        try:
            plt.figure(figsize=(10, 6))
            dates = [r['Date'].split(' ')[0] for r in returns]
            strat = [r['Strategy'] for r in returns]
            bnh = [r['BnH'] for r in returns]
            kospi = [r.get('KOSPI', 0) for r in returns]
            
            plt.plot(dates, strat, label='Strategy', color='red', linewidth=2)
            plt.plot(dates, bnh, label='B&H', color='blue', linestyle='--', linewidth=1)
            plt.plot(dates, kospi, label='KOSPI', color='green', linestyle=':', linewidth=1)
            
            plt.title('Performance Comparison')
            plt.xlabel('Date')
            plt.ylabel('Return (%)')
            plt.legend()
            plt.grid(True, alpha=0.3)
            
            # X축 레이블 겹침 방지 (최대 10개만 표시)
            n = max(1, len(dates) // 10)
            plt.xticks(dates[::n], rotation=45)
            plt.tight_layout()
            
            # 1. 머신 로컬 파일로 저장
            plt.savefig(graph_filepath)
            
            # 2. HTML 내장용 Base64 생성 (인터넷/외부 환경 호환성)
            buf = io.BytesIO()
            plt.savefig(buf, format='png')
            buf.seek(0)
            graph_base64 = base64.b64encode(buf.read()).decode('utf-8')
            plt.close()
        except Exception as ge:
            print("그래프 이미지 생성 실패:", ge)
            graph_base64 = None

        html_content = f"""
        <!DOCTYPE html>
        <html lang="ko">
        <head>
            <meta charset="UTF-8">
            <title>백테스트 결과 보고서</title>
            <style>
                body {{ font-family: 'Malgun Gothic', sans-serif; line-height: 1.6; color: #333; max-width: 1000px; margin: 0 auto; padding: 20px; background-color: #f4f7f6; }}
                .container {{ background: white; padding: 30px; border-radius: 12px; box-shadow: 0 4px 15px rgba(0,0,0,0.1); }}
                h1 {{ color: #2c3e50; border-bottom: 2px solid #3498db; padding-bottom: 10px; }}
                .tabs {{ display: flex; border-bottom: 2px solid #ddd; margin-bottom: 20px; }}
                .tab-btn {{ padding: 10px 20px; border: none; background: none; cursor: pointer; font-size: 16px; font-weight: bold; color: #7f8c8d; border-bottom: 3px solid transparent; }}
                .tab-btn.active {{ color: #3498db; border-bottom-color: #3498db; }}
                .tab-content {{ display: none; }}
                .tab-content.active {{ display: block; }}
                table {{ width: 100%; border-collapse: collapse; margin-top: 15px; }}
                th, td {{ padding: 12px; border: 1px solid #ddd; text-align: left; }}
                th {{ background-color: #f8f9fa; color: #2c3e50; }}
                .stats-grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(150px, 1fr)); gap: 15px; margin-bottom: 25px; }}
                .stat-card {{ background: #ecf0f1; padding: 15px; border-radius: 8px; text-align: center; }}
                .stat-label {{ font-size: 12px; color: #7f8c8d; display: block; }}
                .stat-value {{ font-size: 18px; font-weight: bold; color: #2980b9; }}
                .report-box {{ background: #fdf9f3; border-left: 5px solid #f39c12; padding: 20px; border-radius: 4px; font-style: italic; white-space: pre-wrap; }}
                .m-buy {{ color: #e74c3c; font-weight: bold; }}
                .m-sell {{ color: #3498db; font-weight: bold; }}
                .graph-img {{ width: 100%; border: 1px solid #ddd; border-radius: 8px; margin: 20px 0; }}
            </style>
        </head>
        <body>
            <div class="container">
                <h1>📈 퀀트 시뮬레이션 결과 보고서</h1>
                <p><strong>수집 조건:</strong> {query} | <strong>매수:</strong> {buy_logic} | <strong>매도:</strong> {sell_logic}</p>

                <div class="tabs">
                    <button class="tab-btn active" onclick="showTab('summary')">종합 요약</button>
                    <button class="tab-btn" onclick="showTab('trades')">상세 매매 기록</button>
                    <button class="tab-btn" onclick="showTab('raw_data')">수익률 추이</button>
                </div>

                <div id="summary" class="tab-content active">
                    <div class="stats-grid">
                        <div class="stat-card"><span class="stat-label">누적 수익률</span><span class="stat-value">{stats.get('Total Return', '0%')}</span></div>
                        <div class="stat-card"><span class="stat-label">B&H 수익률</span><span class="stat-value">{stats.get('BnH Return', '0%')}</span></div>
                        <div class="stat-card"><span class="stat-label">KOSPI 수익률</span><span class="stat-value">{stats.get('KOSPI Return', '0%')}</span></div>
                        <div class="stat-card"><span class="stat-label">CAGR</span><span class="stat-value">{stats.get('CAGR', '0%')}</span></div>
                        <div class="stat-card"><span class="stat-label">MDD</span><span class="stat-value">{stats.get('MDD', '0%')}</span></div>
                        <div class="stat-card"><span class="stat-label">샤프 지수</span><span class="stat-value">{stats.get('Sharpe', '0')}</span></div>
                    </div>
                    
                    {f'<h3>📊 성과 그래프</h3><img src="data:image/png;base64,{graph_base64}" class="graph-img">' if graph_base64 else ''}

                    <h3>🤖 AI 투자 전략 분석</h3>
                    <div class="report-box">{ai_report}</div>
                </div>

                <div id="trades" class="tab-content">
                    <h3>📃 매매 히스토리</h3>
                    <table>
                        <thead>
                            <tr><th>날짜</th><th>구분</th><th>종목명</th><th>가격</th><th>수량</th><th>수익률</th></tr>
                        </thead>
                        <tbody>
                            {"".join([f"<tr><td>{t['date']}</td><td class='{'m-buy' if '매수' in t['type'] or '매입' in t['type'] else 'm-sell'}'>{t['type']}</td><td>{t['name']}</td><td>{t['price']:,}원</td><td>{t['qty']}</td><td>{t.get('return', '-')}</td></tr>" for t in trades])}
                        </tbody>
                    </table>
                </div>

                <div id="raw_data" class="tab-content">
                    <h3>📊 일별 누적 수익률 (%)</h3>
                    <table>
                        <thead>
                            <tr><th>날짜</th><th>전략</th><th>B&H</th><th>KOSPI</th></tr>
                        </thead>
                        <tbody>
                            {"".join([f"<tr><td>{r['Date']}</td><td>{r['Strategy']:.2f}%</td><td>{r['BnH']:.2f}%</td><td>{r.get('KOSPI', 0):.2f}%</td></tr>" for r in returns])}
                        </tbody>
                    </table>
                </div>
            </div>

            <script>
                function showTab(tabId) {{
                    document.querySelectorAll('.tab-content').forEach(c => c.classList.remove('active'));
                    document.querySelectorAll('.tab-btn').forEach(b => b.classList.remove('active'));
                    document.getElementById(tabId).classList.add('active');
                    event.currentTarget.classList.add('active');
                }}
            </script>
        </body>
        </html>
        """
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(html_content)
            
        try:
            if trades:
                trades_df = pd.DataFrame(trades)
                csv_filename = f"Report_{now}.csv"
                csv_filepath = os.path.join(dir_name, csv_filename)
                trades_df.to_csv(csv_filepath, index=False, encoding='utf-8-sig')
        except Exception as ce:
            print("CSV 저장 실패:", ce)
            
        return filename
    except Exception as e:
        print("HTML 저장 실패:", e)
        return None

@app.route('/', methods=['GET'])
def index():
    return render_template('index.html')

@app.route('/status', methods=['GET'])
def server_status():
    return jsonify({
        "status": "success",
        "message": "KRX Quant Simulator Backend is running",
        "version": "1.3.0-local-ai"
    }), 200

@app.route('/manual', methods=['GET'])
def download_manual():
    dir_name = os.path.dirname(os.path.abspath(__file__))
    return send_from_directory(dir_name, '사용설명서.pdf', as_attachment=False)

@app.route('/filter', methods=['POST'])
def filter_companies():
    data = request.json
    if not data or 'query' not in data:
        return jsonify({"error": "Missing 'query' parameter"}), 400
    
    query = data['query']
    filtered_list = logic_mgr.run_financial_filter(query)
    
    return jsonify({
        "status": "success",
        "count": len(filtered_list),
        "filtered_companies": filtered_list
    }), 200

@app.route('/backtest', methods=['POST'])
def run_backtest():
    data = request.json
    if not data:
        return jsonify({"error": "Missing request body"}), 400
    
    target_companies = data.get('target_companies', [])
    query = data.get('query', '전체')
    buy_logic = data.get('buy_logic', '')
    sell_logic = data.get('sell_logic', '')
    period_months = data.get('period_months', 12)
    mc_period_str = data.get('mc_period_str', '안함')
    portfolio_strategy = data.get('portfolio_strategy', 'equal_weight')
    use_tax_fee = data.get('use_tax_fee', False)
    gemini_key = data.get('gemini_key', '')
    dart_key = data.get('dart_key', '')
    
    global progress_state
    progress_state = {"status": "running", "progress": 0, "logs": [], "error": None}
    
    if not target_companies or not buy_logic or not sell_logic:
        err = "Missing required logic or target companies"
        update_progress(None, err, err)
        return jsonify({"error": err}), 400
        
    try:
        update_progress(5, "백테스트 시뮬레이션 요청 수신...")
        result = logic_mgr.run_backtest_logic(
            target_companies, 
            buy_logic, 
            sell_logic, 
            period_months, 
            mc_period_str,
            portfolio_strategy=portfolio_strategy,
            use_tax_fee=use_tax_fee,
            dart_key=dart_key,
            progress_callback=update_progress
        )
        if "error" in result:
            update_progress(None, result["error"], result["error"])
            return jsonify({"status": "error", "message": result["error"]}), 400
            
        update_progress(90, "AI 분석 보고서 생성 중...")
        
        report = ""
        try:
            stats = result.get('detailed_stats', {})
            signals = result.get('recent_signals', {'buy':[], 'sell':[]})
            
            buy_sig_str = ", ".join([s['name'] for s in signals['buy']]) or "없음"
            sell_sig_str = ", ".join([s['name'] for s in signals['sell']]) or "없음"
            
            mc_info = result.get('mc_results')
            mc_text = ""
            if mc_info and mc_info.get('dates') and len(mc_info.get('dates')) > 0:
                mc_text = f"몬테카를로 분석: 미래 예측 중앙값 최종 자산 {mc_info.get('median')[-1]:,.0f}원"

            prompt = f"""
            당신은 전문 퀀트 투자 분석가입니다. 아래 백테스트 지표를 분석하고, 특히 코스피(KOSPI) 및 Buy&Hold(B&H) 전략과 비교하여 3~4문장의 한국어 성과 분석 보고서를 작성하세요.
            전략 수익률이 코스피보다 현저히 낮다면 '무의미한 전략'임을 강조해야 합니다.
            
            [백테스트 지표]
            - 전략 수익률: {stats.get('Total Return', '-')}
            - B&H 수익률: {stats.get('BnH Return', '-')}
            - KOSPI 수익률: {stats.get('KOSPI Return', '-')}
            - CAGR: {stats.get('CAGR', '-')}
            - MDD: {stats.get('MDD', '-')}
            - 샤프 지수: {stats.get('Sharpe', '-')}
            - 승률: {stats.get('Win Rate', '-')}
            - 최근 매수 신호: {buy_sig_str}
            - 최근 매도 신호: {sell_sig_str}
            {mc_text}
            """
            
            if gemini_key:
                client = genai.Client(api_key=gemini_key)
                response = client.models.generate_content(
                    model='gemini-2.5-flash',
                    contents=[prompt]
                )
                report = re.sub(r'\*\*', '', response.text).strip()
                result['ai_report'] = report
            else:
                result['ai_report'] = "Gemini API Key가 제공되지 않았습니다."
                
        except Exception as e:
            print("AI 보고서 생성 실패:", e)
            result['ai_report'] = "AI 보고서를 생성하지 못했습니다."

        update_progress(95, "백테스트 결과 HTML 리포트 저장 중...")
        filename = save_results_to_html(result, query, buy_logic, sell_logic)
        result['report_file'] = filename
            
        update_progress(100, "시뮬레이션 완료!")
        progress_state["status"] = "done"
            
        return jsonify({
            "status": "success",
            "data": result
        }), 200
    except Exception as e:
        msg = f"내부 오류 발생: {str(e)}"
        update_progress(None, msg, msg)
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route('/generate', methods=['POST'])
def generate_logic_with_gemini():
    data = request.json
    if not data or 'prompt' not in data or 'type' not in data:
        return jsonify({"error": "Missing prompt or type"}), 400
        
    user_prompt = data['prompt']
    target_type = data['type'] 
    gemini_key = data.get('gemini_key', '')
    
    if not gemini_key:
        return jsonify({"error": "Gemini API Key is missing"}), 400
        
    # Read logic.csv to teach API the rules
    logic_csv_path = os.path.join(os.path.dirname(__file__), 'logic.csv')
    logic_rules = ""
    if os.path.exists(logic_csv_path):
        with open(logic_csv_path, 'r', encoding='utf-8') as f:
            logic_rules = f.read()

    tag = "재무 필터링" if target_type == "filter" else "매도" if target_type == "sell" else "매수"
    
    sys_prompt = f"""당신은 사용자 입력을 분석해 KRX Quant Simulator 시뮬레이터 수식으로 가장 정확하게 변환해주는 퀀트 전문가입니다.
자연어 설명을 덧붙이지 말고, 오직 완성된 단일 '수식 문자열' 하나만 반환하세요.

[시뮬레이터 동작 규칙(logic.csv 학습)]
{logic_rules}

[추가 규칙]
1. 부등호 사용 시 '>=' 대신 '>', '<=' 대신 '<' 를 사용하세요. (예: PER <= 10 -> PER < 10)
2. 출력 형식에는 Markdown, 인용 부호, 또는 불필요한 설명이 없어야 합니다. 오직 변환된 공식 문자열만 응답하세요.

[사용자 입력 ({tag} 조건)]
{user_prompt}
"""

    try:
        from google import genai
        client = genai.Client(api_key=gemini_key)
        
        def generate_stream():
            try:
                # Streaming directly from gemini
                response = client.models.generate_content_stream(
                    model='gemini-2.5-flash',
                    contents=[sys_prompt]
                )
                for chunk in response:
                    if chunk.text:
                        # Clean backticks if model ignored instruction
                        cleaned = chunk.text.replace('`', '').replace('python', '').replace('csv', '').strip()
                        if cleaned:
                            yield cleaned + " " # append trailing space for continuous feel
            except Exception as e:
                yield f"Error: {str(e)}"

        return Response(stream_with_context(generate_stream()), mimetype='text/plain')
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route('/fast_backtest_parse', methods=['POST'])
def fast_backtest_parse():
    data = request.json
    text = data.get('text', '')
    
    gemini_key = data.get('gemini_key', '')
    
    if not text:
        return jsonify({"status": "error", "message": "입력 텍스트가 없습니다."}), 400
    if not gemini_key:
        return jsonify({"status": "error", "message": "Gemini API Key가 없습니다."}), 400

    try:
        client = genai.Client(api_key=gemini_key)
        sys_prompt = """당신은 사용자 입력을 분석해 백테스팅 조건을 추출하는 퀀트 전략 전문가입니다.
        
        [규칙]
        1. 모든 로직은 반드시 시뮬레이터 전용 수식 형식으로 작성하세요. 자연어로 설명하지 마세요.
        2. 부등호 사용 시 반드시 '>=' 대신 '>', '<=' 대신 '<'를 사용하세요. (시스템 강제 사항)
        3. PER, PBR, ROE, 부채비율 등 재무 지표는 'financial_logic'에만 넣으세요.
        4. 이동평균선, RSI, MACD, 골든크로스 등 기술적 지표는 'buy_logic'/'sell_logic'에 넣으세요.
        5. 'financial_logic' 기본값은 '전체', 'sell_logic' 기본값은 'Buy&Hold'입니다.
        
        [Few-shot 예시 (데이터셋 기반)]
        Q: 5일 이동평균선이 20일 이동평균선보다 크고, RSI가 70보다 작은 종목
        A: {"buy_logic": "5일 이동평균선 > 20일 이동평균선 AND RSI < 70"}
        
        Q: MACD가 0보다 크거나 골든크로스가 발생한 종목
        A: {"buy_logic": "MACD > 0 OR 골든크로스 == True"}
        
        Q: 거래대금이 100억 이상이면서 (기관 순매수가 0보다 크거나 외국인 순매수가 0보다 큰) 종목
        A: {"buy_logic": "거래대금 > 100 AND (기관 순매수 > 0 OR 외국인 순매수 > 0)"}
        
        Q: ROE가 15%를 초과하고, 동시에 부채비율이 100% 미만인 종목
        A: {"financial_logic": "ROE > 15 AND 부채비율 < 100"}
        
        Q: PER이 20보다 작거나 PBR이 1보다 작은 종목 중에서, ROA가 5%를 넘는 기업
        A: {"financial_logic": "(PER < 20 OR PBR < 1) AND ROA > 5"}
        
        Q: 매출액증가율이 10% 이상이거나 영업이익증가율이 15% 이상인 종목들 중에서, (EPS증가율과 BPS증가율 모두 5% 이상) 또는 (재고자산회전율이 3을 초과하고 총자산회전율이 1을 초과하는) 기업
        A: {"financial_logic": "(매출액증가율 > 10 OR 영업이익증가율 > 15) AND ((EPS증가율 > 5 AND BPS증가율 > 5) OR (재고자산회전율 > 3 AND 총자산회전율 > 1))"}
        
        Q: 적삼병이거나 망치형 캔들이 나타나고 동시에 5일 이동평균선이 20일 이동평균선보다 큰 종목
        A: {"buy_logic": "적삼병 == True OR (망치형 == True AND 5일 이동평균선 > 20일 이동평균선)"}
        
        Q: EV/EBITDA가 5보다 작고 PBR이 0.7보다 작은 종목 중에서, FCF가 양수이거나 EBITDA가 양수인 기업
        A: {"financial_logic": "(EV/EBITDA < 5 AND PBR < 0.7) AND (FCF > 0 OR EBITDA > 0)"}
        
        Q: 5일 이동평균선이 20일 이동평균선 위에 있으며, (골든크로스가 발생했거나 (RSI가 50 이상이고 스토캐스틱 K가 스토캐스틱 D보다 높은)) 종목
        A: {"buy_logic": "5일 이동평균선 > 20일 이동평균선 AND (골든크로스 == True OR (RSI > 50 AND 스토캐스틱 K > 스토캐스틱 D))"}
        
        Q: 총자산회전율이 0.8을 넘고 EPS증가율이 0보다 큰 종목
        A: {"financial_logic": "총자산회전율 > 0.8 AND EPS증가율 > 0"}

        반드시 아래 JSON 형식으로만 답변하세요.
        {
            "financial_logic": "...",
            "buy_logic": "...",
            "sell_logic": "...",
            "period_months": 36,
            "mc_period": "안함"
        }
        """
        
        from google.genai import types
        response = client.models.generate_content(
            model='gemini-2.5-flash',
            contents=[sys_prompt + "\n사용자 입력: " + text],
            config=types.GenerateContentConfig(
                response_mime_type='application/json',
            )
        )
        
        # Robust parsing
        res_text = response.text.strip()
        try:
            parsed = json.loads(res_text)
        except:
            import re
            match = re.search(r'\{.*\}', res_text, re.DOTALL)
            if match:
                parsed = json.loads(match.group(0))
            else:
                raise ValueError("JSON matching failed")

        return jsonify({"status": "success", "data": parsed}), 200
    except Exception as e:
        print(f"Fast Backtest Parse Error: {e}")
        return jsonify({"status": "error", "message": f"AI 분석 중 오류가 발생했습니다: {str(e)}"}), 500

@app.route('/memories/delete', methods=['POST'])
def delete_memories():
    data = request.json
    if not data:
        return jsonify({"error": "Missing request body"}), 400
        
    dir_name = os.path.join(os.path.dirname(os.path.abspath(__file__)), "Memories")
    
    if not os.path.exists(dir_name):
        return jsonify({"status": "success"})
        
    delete_all = data.get('delete_all', False)
    filenames = data.get('filenames', [])
    
    deleted_count = 0
    try:
        for f in os.listdir(dir_name):
            if f == "stock_cache.db":
                continue
            path = os.path.join(dir_name, f)
            if not os.path.isfile(path):
                continue
            if delete_all or f in filenames:
                os.remove(path)
                deleted_count += 1
        return jsonify({"status": "success", "deleted": deleted_count}), 200
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route('/memories', methods=['GET'])
def list_memories():
    dir_name = os.path.join(os.path.dirname(os.path.abspath(__file__)), "Memories")
    files_data = []
    
    if os.path.exists(dir_name):
        for f in os.listdir(dir_name):
            if f == "stock_cache.db":
                continue
            if not f.lower().endswith('.html'):
                continue
            if f.lower().endswith('.png'): # 추가 안전장치
                continue
            path = os.path.join(dir_name, f)
            if os.path.isfile(path):
                stat = os.stat(path)
                size_kb = stat.st_size / 1024
                size_str = f"{size_kb:.1f} KB" if size_kb < 1024 else f"{(size_kb/1024):.1f} MB"
                kst = pytz.timezone('Asia/Seoul')
                mod_time = datetime.fromtimestamp(stat.st_mtime, kst).strftime("%Y-%m-%d %H:%M")
                
                files_data.append({
                    "name": f,
                    "size": size_str,
                    "modified": mod_time,
                    "timestamp": stat.st_mtime
                })
        files_data.sort(key=lambda x: x['timestamp'], reverse=True)
        
    return jsonify({"status": "success", "files": files_data})

@app.route('/download/<path:filename>', methods=['GET'])
def download_memory(filename):
    dir_name = os.path.join(os.path.dirname(os.path.abspath(__file__)), "Memories")
    return send_from_directory(dir_name, filename, as_attachment=True)

import socket
def get_available_port(start_port=7861, end_port=7898):
    for port in range(start_port, end_port + 1):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            try:
                s.bind(('0.0.0.0', port))
                return port
            except OSError:
                continue
    return start_port

fin_progress_state = {"status": "idle", "progress": 0, "logs": [], "error": None}

@app.route('/update_financials/progress', methods=['GET'])
def get_fin_progress():
    global fin_progress_state
    return jsonify(fin_progress_state)

def update_fin_progress(pct, msg, error_enc=None):
    global fin_progress_state
    if error_enc:
        fin_progress_state["error"] = error_enc
        fin_progress_state["status"] = "error"
    if pct is not None:
        fin_progress_state["progress"] = pct
    if msg:
        now_str = datetime.now().strftime('%H:%M:%S')
        fin_progress_state["logs"].append(f"[{now_str}] {msg}")

@app.route('/update_financials', methods=['POST'])
def run_update_financials():
    data = request.json
    dart_key = data.get('dart_api_key', '')
    if not dart_key:
        return jsonify({"status": "error", "message": "DART API 키가 제공되지 않았습니다."}), 400
        
    global fin_progress_state
    fin_progress_state = {"status": "updating", "progress": 0, "logs": [], "error": None}
    
    def background_update():
        try:
            logic_mgr.update_financial_data(dart_key, update_fin_progress)
            fin_progress_state["status"] = "done"
            update_fin_progress(100, "재무제표 업데이트 성공적으로 완료")
        except Exception as e:
            update_fin_progress(None, f"업데이트 실패: {str(e)}", str(e))

    import threading
    th = threading.Thread(target=background_update)
    th.daemon = True
    th.start()
    
    return jsonify({"status": "updating"}), 200

if __name__ == '__main__':
    port_env = os.environ.get("APP_PORT") or os.environ.get("GRADIO_SERVER_PORT") or os.environ.get("PORT")
    port = int(port_env) if port_env else get_available_port()
    print(f"[KRX Quant Simulator] Starting on port {port}...")
    app.run(host='0.0.0.0', port=port, debug=False)
