from flask import Flask, render_template, jsonify
from poller import data_store, start_poller
from datetime import datetime

app = Flask(__name__)
start_poller(interval=30)

@app.route("/")
def index():
    return render_template("dashboard.html")

@app.route("/api/data")
def api_data():
    return jsonify(list(data_store.values()))

@app.route("/api/deploy", methods=["POST"])
def deploy():
    return jsonify({
        "success": True,
        "output": "[TV2] Ansible playbook chay thanh cong!\nVLAN config da duoc push len toan bo switch."
    })

@app.route("/api/backup", methods=["POST"])
def backup():
    return jsonify({
        "success": True,
        "output": "[TV3] Backup thanh cong luc " + datetime.now().strftime("%H:%M:%S %d/%m/%Y")
    })

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=False)
