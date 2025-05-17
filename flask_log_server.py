from flask import Flask, render_template_string, Response, request, redirect, url_for
import threading
import time
import json
from threading import Lock
import logging

log = logging.getLogger('werkzeug')
log.setLevel(logging.ERROR)
app = Flask(__name__)
LOGS = {}  
WALLET_STATUS = {}  
STOP_FLAGS = {}  
GLOBAL_LOOP_INTERVAL = None
LOOP_INTERVALS = {}  
GLOBAL_LOOP_EVENT = threading.Event()
GLOBAL_CONFIG = {"loop_interval": 60}
config_lock = Lock()

TEMPLATE = """
<!DOCTYPE html>
<html>
<head>
    <title>Pharos Wallet Manager</title>
    <style>
        body { font-family: monospace; background: #23272e; color: #c0caf5; margin: 0; padding: 20px; }
        pre { background: #181926; padding: 1em; border-radius: 8px; max-height: 70vh; overflow-y: scroll; white-space: pre-wrap; word-break: break-word;}
        a { color: #5ad4e6; text-decoration: none; }
        a:hover { text-decoration: underline; }
        .log-entry { margin-bottom: 2px; }
        .wallet-list { display: flex; flex-wrap: wrap; gap: 10px; margin-bottom: 20px; }
        .wallet-item { padding: 8px 12px; border-radius: 6px; background: #2a2f3a; display: flex; flex-direction: column; min-width: 220px;}
        .wallet-address { font-weight: bold; margin-bottom: 4px; }
        .status-running { color: #9ece6a; }
        .status-idle { color: #7aa2f7; }
        .status-looping { color: #e0af68; }
        .status-global_looping { color: #7dcfff; }
        .status-stopped { color: #f7768e; }
        .controls { display: flex; flex-direction: column; gap: 6px; margin-top: 8px; }
        .button { padding: 4px 8px; border-radius: 4px; border: none; color: white; cursor: pointer; font-size: 12px; text-align: center;}
        .start-btn { background: #9ece6a; }
        .loop-btn { background: #e0af68; }
        .stop-btn { background: #f7768e; }
        .task-selector { margin-right: 8px; padding: 3px; border-radius: 4px; border: 1px solid #888; background: #1a1b26; color: #c0caf5; }
        .global-controls { margin: 10px 0 20px 0; padding: 15px; background: #2a2f3a; border-radius: 8px; display: flex; gap: 12px; align-items: center; flex-wrap: wrap;}
        .global-task-selector { padding: 6px; border-radius: 4px; border: 1px solid #888; background: #1a1b26; color: #c0caf5; min-width: 200px;}
        .global-btn { padding: 6px 12px; border-radius: 4px; border: none; color: white; cursor: pointer; font-weight: bold;}
        .global-start { background: #9ece6a; }
        .global-stop { background: #f7768e; }
        .loop-field { width: 56px; border-radius: 4px; border: 1px solid #888; padding: 2px 4px; background: #181926; color: #c0caf5;}
        .interval-label { font-size: 11px; color: #b4b4b4; margin-left: 3px;}
        @media (max-width: 900px) {
            .wallet-list { flex-direction: column; }
            .wallet-item { min-width: 90vw; }
        }
    </style>
</head>
<body>
    <h2>Pharos Wallet Manager</h2>

    <div class="global-controls" style="flex-direction:column;">
        <form id="global-task-form" action="/start_all" method="post" style="display: flex; align-items: center; gap: 10px;">
            <select name="task" class="global-task-selector">
                <option value="check_in">Perform check-in</option>
                <option value="claim_faucet">Claim tokens from faucet</option>
                <option value="send_txs">Send 10 transactions</option>
                <option value="perform_swaps">Perform 10 swaps</option>
                <option value="add_liquidity">Perform 10 liquidity adds (staking)</option>
                <option value="all">Do everything (sequentially)</option>
            </select>
            <button type="submit" class="global-btn global-start">Start All Wallets</button>
        </form>

        <form id="global-loop-form" action="/start_all_loop" method="post" style="display: flex; align-items: center; gap: 10px; margin-top:5px;">
            <select name="loop_task" class="global-task-selector">
                <option value="check_in">Check-in (loop)</option>
                <option value="claim_faucet">Claim faucet (loop)</option>
                <option value="send_txs">Send txs (loop)</option>
                <option value="perform_swaps">Swaps (loop)</option>
                <option value="add_liquidity">Liquidity (loop)</option>
                <option value="all">All (loop)</option>
            </select>
            <input type="number" name="interval" min="1" max="2880" value="{{ global_interval or 60 }}" class="loop-field" style="width: 55px;">
            <span class="interval-label">min</span>
            <button type="submit" class="global-btn loop-btn" style="background:#e0af68;">Start All Loop</button>
        </form>
        <div style="display:flex; gap:10px; margin-top:7px;">
            <form action="/stop_all" method="post" style="display:inline;">
                <button type="submit" class="global-btn global-stop">Stop All Tasks</button>
            </form>
            <form action="/stop_all_loop" method="post" style="display:inline;">
                <button type="submit" class="global-btn global-stop">Stop All Loop</button>
            </form>
        </div>
    </div>

    <div class="wallet-list">
    {% for addr in addresses %}
        <div class="wallet-item">
            <div class="wallet-address">
                <a href="/log/{{addr}}" {% if addr == address %}style="font-weight:bold"{% endif %}>{{addr[:8]}}...{{addr[-6:]}}</a>
            </div>
            {% if addr in statuses %}
                <div class="status status-{{statuses[addr]['status']}}" data-addr="{{addr}}">
                    Status: {{statuses[addr]['status']|capitalize}}
                    {% if statuses[addr]['task'] %}
                        ({{statuses[addr]['task']}})
                    {% endif %}
                </div>
            {% else %}
                <div class="status status-idle" data-addr="{{addr}}">Status: Idle</div>
            {% endif %}

            <div class="controls">
                <form action="/start/{{addr}}" method="post" style="margin:0; display:inline;">
                    <select name="task" class="task-selector">
                        <option value="check_in">Check-in</option>
                        <option value="claim_faucet">Claim faucet</option>
                        <option value="send_txs">Send txs</option>
                        <option value="perform_swaps">Swaps</option>
                        <option value="add_liquidity">Liquidity</option>
                        <option value="all">All</option>
                    </select>
                    <button type="submit" class="button start-btn">Start</button>
                </form>
                <form action="/start_loop/{{addr}}" method="post" style="margin:0; display:inline;">
                    <select name="loop_task" class="task-selector">
                        <option value="check_in">Check-in (loop)</option>
                        <option value="claim_faucet">Claim faucet (loop)</option>
                        <option value="send_txs">Send txs (loop)</option>
                        <option value="perform_swaps">Swaps (loop)</option>
                        <option value="add_liquidity">Liquidity (loop)</option>
                        <option value="all">All (loop)</option>
                    </select>
                    <input type="number" name="interval" class="loop-field"
                        min="1" max="2880" value="{{ intervals.get(addr, 60) }}" style="width:56px;">
                    <span class="interval-label">min</span>
                    <button type="submit" class="button loop-btn" style="background:#e0af68;">Start Loop</button>
                </form>
                <form action="/stop/{{addr}}" method="post" style="margin:0; display:inline;">
                    <button type="submit" class="button stop-btn">Stop</button>
                </form>
            </div>
        </div>
    {% endfor %}
    </div>

    {% if address %}
    <h3>Live logs for: {{address}}</h3>
    <pre id="logbox"></pre>
    <script>
        let logbox = document.getElementById('logbox');
        let es = new EventSource("/stream/{{address}}");
        es.onmessage = function(e) {
            try {
                const data = JSON.parse(e.data);
                if (data.type === 'initial') {
                    logbox.innerHTML = data.logs.map(log =>
                        `<div class="log-entry">${log}</div>`
                    ).join('');
                } else if (data.type === 'update') {
                    const newEntry = document.createElement('div');
                    newEntry.className = 'log-entry';
                    newEntry.textContent = data.log;
                    logbox.appendChild(newEntry);
                }
                logbox.scrollTop = logbox.scrollHeight;
            } catch (err) {
                console.error("Error parsing message:", err);
            }
        };
        es.onerror = function() {
            const errorMsg = document.createElement('div');
            errorMsg.className = 'log-entry';
            errorMsg.style.color = '#ff5555';
            errorMsg.textContent = "[SSE disconnected, reload page]";
            logbox.appendChild(errorMsg);
        };
    </script>
    {% endif %}

    <script>
        // Общий автообновлятор статусов
        function updateAllStatuses() {
            document.querySelectorAll('.status[data-addr]').forEach(elem => {
                const addr = elem.getAttribute('data-addr');
                fetch(`/status/${addr}`)
                    .then(res => res.json())
                    .then(data => {
                        const s = data.status;
                        const t = data.task;
                        let text = `Status: ${s.charAt(0).toUpperCase() + s.slice(1)}`;
                        if (t) text += ` (${t})`;
                        elem.className = `status status-${s}`;
                        elem.textContent = text;
                    })
                    .catch(err => console.warn(`Status fetch error for ${addr}:`, err));
            });
        }
        setInterval(updateAllStatuses, 5000);
    </script>
</body>
</html>
"""

@app.route("/")
def index():
    return render_template_string(
    TEMPLATE,
    addresses=LOGS.keys(),
    statuses=WALLET_STATUS,
    intervals=LOOP_INTERVALS,
    global_interval=GLOBAL_LOOP_INTERVAL
)

@app.route("/log/<address>")
def show_log(address):
    return render_template_string(
        TEMPLATE,
        addresses=LOGS.keys(),
        address=address,
        statuses=WALLET_STATUS,
        intervals=LOOP_INTERVALS,
        global_interval=GLOBAL_LOOP_INTERVAL
    )


@app.route('/stream/<address>')
def stream(address):
    def event_stream():
        if address in LOGS:
            initial_data = {
                'type': 'initial',
                'logs': LOGS[address]
            }
            yield f"data: {json.dumps(initial_data)}\n\n"
        last_index = len(LOGS.get(address, []))
        while True:
            if address in LOGS:
                current_logs = LOGS[address]
                if len(current_logs) > last_index:
                    for i in range(last_index, len(current_logs)):
                        update_data = {
                            'type': 'update',
                            'log': current_logs[i]
                        }
                        yield f"data: {json.dumps(update_data)}\n\n"
                    last_index = len(current_logs)
            time.sleep(0.2)
    return Response(event_stream(), mimetype="text/event-stream")

@app.route("/start/<address>", methods=["POST"])
def start_task(address):
    task = request.form.get("task", "all")
    WALLET_STATUS[address] = {"status": "running", "task": task}
    STOP_FLAGS[address] = False
    return redirect(url_for("show_log", address=address))

@app.route("/stop/<address>", methods=["POST"])
def stop_task(address):
    if address in WALLET_STATUS:
        WALLET_STATUS[address]["status"] = "stopped"
    STOP_FLAGS[address] = True
    return redirect(url_for("show_log", address=address))

@app.route("/start_all", methods=["POST"])
def start_all():
    task = request.form.get("task", "all")
    for address in LOGS.keys():
        WALLET_STATUS[address] = {"status": "running", "task": task}
        STOP_FLAGS[address] = False
    return redirect(url_for("index"))
    
@app.route("/start_all_loop", methods=["POST"])
def start_all_loop():
    interval = int(request.form.get("interval", 60))
    with config_lock:
        GLOBAL_CONFIG["loop_interval"] = interval
    task = request.form.get("loop_task", "all")
    print(f"START_ALL_LOOP POST: interval={interval}, task={task}")
    global GLOBAL_LOOP_INTERVAL, GLOBAL_LOOP_EVENT
    GLOBAL_LOOP_INTERVAL = interval
    print(f"[FLASK] GLOBAL_LOOP_INTERVAL set to {GLOBAL_LOOP_INTERVAL}")
    GLOBAL_LOOP_EVENT.set()
    for address in LOGS.keys():
        WALLET_STATUS[address] = {"status": "global_looping", "task": task}
        STOP_FLAGS[address] = False
        if address in LOOP_INTERVALS:
            LOOP_INTERVALS.pop(address)
    return redirect(url_for("index"))


@app.route("/stop_all", methods=["POST"])
def stop_all():
    for address in LOGS.keys():
        WALLET_STATUS[address] = {"status": "idle", "task": None}
        STOP_FLAGS[address] = True
    return redirect(url_for("index"))

    
@app.route("/stop_all_loop", methods=["POST"])
def stop_all_loop():
    global GLOBAL_LOOP_EVENT
    GLOBAL_LOOP_EVENT.clear()
    for address in LOGS.keys():
        WALLET_STATUS[address] = {"status": "stopped", "task": None}
        STOP_FLAGS[address] = True
    return redirect(url_for("index"))

@app.route("/start_loop/<address>", methods=["POST"])
def start_loop(address):
    interval = int(request.form.get("interval", 60))
    loop_task = request.form.get("loop_task", "all")
    LOOP_INTERVALS[address] = interval
    WALLET_STATUS[address] = {"status": "looping", "task": loop_task}
    STOP_FLAGS[address] = False
    return redirect(url_for("show_log", address=address))

    
@app.route("/status/<address>")
def status(address):
    status_data = WALLET_STATUS.get(address, {"status": "idle", "task": None})
    status_value = status_data.get("status", "idle")
    task_value = status_data.get("task", None)
    return {
        "status": status_value,
        "task": task_value
    }

def run_flask():
    app.run(host="127.0.0.1", port=8080, debug=False, use_reloader=False)

def should_stop(address):
    """Check if task for this address should be stopped"""
    return STOP_FLAGS.get(address, False)

def set_wallet_status(address, status, task=None):
    """Update wallet status"""
    if status == "idle":
        WALLET_STATUS[address] = {"status": "idle", "task": None}
    else:
        if address in WALLET_STATUS:
            WALLET_STATUS[address]["status"] = status
            if task:
                WALLET_STATUS[address]["task"] = task
        else:
            WALLET_STATUS[address] = {"status": status, "task": task}

def log_wallet(address, msg):
    """Log message for wallet address"""
    print(f"[{address[:8]}] {msg}")
    timestamp = time.strftime("%H:%M:%S", time.localtime())
    formatted_msg = f"[{timestamp}] {msg}"
    LOGS.setdefault(address, []).append(formatted_msg)
    if len(LOGS[address]) > 1000:
        LOGS[address] = LOGS[address][-1000:]