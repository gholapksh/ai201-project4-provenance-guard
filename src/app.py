import os, uuid, sqlite3
from datetime import datetime
from flask import Flask, request, jsonify
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from signals_stylometry import calculate_stylometrics

app = Flask(__name__)
limiter = Limiter(key_func=get_remote_address, app=app, default_limits=[], storage_uri="memory://")
DB_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "provenance_guard.db")

def init_db():
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute("""CREATE TABLE IF NOT EXISTS audit_logs (content_id TEXT PRIMARY KEY, creator_id TEXT NOT NULL, timestamp TEXT NOT NULL, text_preview TEXT NOT NULL, llm_score REAL, structural_score REAL, combined_confidence REAL NOT NULL, attribution TEXT NOT NULL, status TEXT NOT NULL, appeal_reasoning TEXT)""")
init_db()

@app.route("/submit", methods=["POST"])
def submit_content():
    data = request.get_json() or {}
    text, creator_id = data.get("text", "").strip(), data.get("creator_id", "").strip()
    if not text or not creator_id: return jsonify({"error": "Missing fields"}), 400
    content_id, timestamp = str(uuid.uuid4()), datetime.utcnow().isoformat() + "Z"
    structural_score = calculate_stylometrics(text)["structural_score"]
    combined_confidence = round((0.70 * 0.6) + (structural_score * 0.4), 2)
    attribution = "likely_human" if combined_confidence >= 0.75 else "uncertain"
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute("INSERT INTO audit_logs VALUES (?, ?, ?, ?, 0.70, ?, ?, ?, \"classified\", NULL)", (content_id, creator_id, timestamp, text[:60]+"...", structural_score, combined_confidence, attribution))
    return jsonify({"content_id": content_id, "attribution": attribution, "confidence": combined_confidence, "transparency_label": "Placeholder", "status": "classified"}), 200

if __name__ == "__main__":
    app.run(port=5000, debug=True)
