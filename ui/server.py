import sys
import os
from pathlib import Path
from flask import Flask, jsonify, send_file

sys.path.insert(0, str(Path(__file__).parent.parent))
import config
from state.schema import read_state, read_passes

app = Flask(__name__)

@app.route("/")
def index():
    return send_file(str(Path(__file__).parent / "dashboard.html"))

@app.route("/api/state")
def api_state():
    state = read_state()
    return jsonify(state)

@app.route("/api/passes")
def api_passes():
    passes = read_passes()
    return jsonify(passes)

@app.route("/api/image")
def api_image():
    state = read_state()
    filepath = state.get("latest_image", {}).get("filepath")
    if filepath and Path(filepath).exists():
        mime = "image/jpeg" if filepath.endswith(".jpg") else "image/png"
        return send_file(filepath, mimetype=mime)
    if config.LATEST_IMAGE.exists():
        return send_file(str(config.LATEST_IMAGE), mimetype="image/png")
    return "", 404

def run_server():
    print(f"[UI] Dashboard at http://{config.UI_HOST}:{config.UI_PORT}")
    app.run(host=config.UI_HOST, port=config.UI_PORT, debug=False)

if __name__ == "__main__":
    run_server()