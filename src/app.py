import os, uuid, sqlite3
from datetime import datetime
from flask import Flask, request, jsonify
from dotenv import load_dotenv
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from signals_stylometry import calculate_stylometrics
from signals_llm import calculate_llm_signal

load_dotenv()
app = Flask(__name__)
limiter = Limiter(key_func=get_remote_address, app=app, default_limits=[], storage_uri="memory://")
DB_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "provenance_guard.db")

LLM_WEIGHT = 0.6
STYLOMETRY_WEIGHT = 0.4

LABEL_HUMAN_THRESHOLD = 0.65
LABEL_AI_THRESHOLD = 0.30

LABELS = {
    "likely_human": "This work appears to be human-written, based on a high-confidence analysis of writing style and content.",
    "uncertain": "We were unable to confidently determine whether this work is human-written or AI-generated. Treat the attribution as inconclusive.",
    "likely_ai": "This work appears to be AI-generated, based on a high-confidence analysis of writing style and content.",
}


def init_db():
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute("""CREATE TABLE IF NOT EXISTS audit_logs (
            content_id TEXT PRIMARY KEY,
            creator_id TEXT NOT NULL,
            timestamp TEXT NOT NULL,
            text_preview TEXT NOT NULL,
            llm_score REAL,
            structural_score REAL,
            combined_confidence REAL NOT NULL,
            attribution TEXT NOT NULL,
            status TEXT NOT NULL,
            appeal_reasoning TEXT
        )""")
init_db()


def classify(combined_confidence: float) -> str:
    if combined_confidence >= LABEL_HUMAN_THRESHOLD:
        return "likely_human"
    if combined_confidence < LABEL_AI_THRESHOLD:
        return "likely_ai"
    return "uncertain"


@app.route("/submit", methods=["POST"])
@limiter.limit("10 per minute;100 per day")
def submit_content():
    data = request.get_json() or {}
    text, creator_id = data.get("text", "").strip(), data.get("creator_id", "").strip()
    if not text or not creator_id:
        return jsonify({"error": "Missing fields"}), 400

    content_id, timestamp = str(uuid.uuid4()), datetime.utcnow().isoformat() + "Z"

    structural_score = calculate_stylometrics(text)["structural_score"]
    llm_result = calculate_llm_signal(text)
    llm_score = llm_result["llm_score"]

    combined_confidence = round((LLM_WEIGHT * llm_score) + (STYLOMETRY_WEIGHT * structural_score), 2)
    attribution = classify(combined_confidence)
    label_text = LABELS[attribution]

    with sqlite3.connect(DB_PATH) as conn:
        conn.execute(
            "INSERT INTO audit_logs VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, NULL)",
            (
                content_id, creator_id, timestamp, text[:60] + "...",
                llm_score, structural_score, combined_confidence,
                attribution, "classified",
            ),
        )

    return jsonify({
        "content_id": content_id,
        "attribution": attribution,
        "confidence": combined_confidence,
        "llm_score": llm_score,
        "structural_score": structural_score,
        "transparency_label": label_text,
        "status": "classified",
    }), 200


@app.route("/appeal", methods=["POST"])
def appeal_content():
    data = request.get_json() or {}
    content_id = data.get("content_id", "").strip()
    creator_reasoning = data.get("creator_reasoning", "").strip()
    if not content_id or not creator_reasoning:
        return jsonify({"error": "Missing fields"}), 400

    with sqlite3.connect(DB_PATH) as conn:
        cur = conn.execute("SELECT content_id FROM audit_logs WHERE content_id = ?", (content_id,))
        if cur.fetchone() is None:
            return jsonify({"error": "Record not found"}), 404
        conn.execute(
            "UPDATE audit_logs SET status = ?, appeal_reasoning = ? WHERE content_id = ?",
            ("under_review", creator_reasoning, content_id),
        )

    return jsonify({"content_id": content_id, "status": "under_review", "message": "Appeal received."}), 200


@app.route("/log", methods=["GET"])
def get_log():
    with sqlite3.connect(DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute("SELECT * FROM audit_logs ORDER BY timestamp DESC LIMIT 50").fetchall()
    return jsonify({"entries": [dict(r) for r in rows]}), 200


if __name__ == "__main__":
    app.run(port=5000, debug=True)