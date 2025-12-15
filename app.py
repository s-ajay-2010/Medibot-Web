import os
import sqlite3
import base64
from datetime import date
from flask import Flask, request, jsonify, send_from_directory
from werkzeug.utils import secure_filename
from dotenv import load_dotenv
import google.generativeai as genai
from openai import OpenAI

# ---------------- CONFIG ----------------
load_dotenv()

PORT = int(os.getenv("PORT", 5000))
GEMINI_KEY = os.getenv("GEMINI_API_KEY")
OPENAI_KEY = os.getenv("OPENAI_API_KEY")

genai.configure(api_key=GEMINI_KEY)
openai_client = OpenAI(api_key=OPENAI_KEY)

DB_PATH = "medibot.db"
UPLOAD_FOLDER = "uploads"
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

app = Flask(__name__, static_folder="static", template_folder="templates")
app.config["UPLOAD_FOLDER"] = UPLOAD_FOLDER

# ---------------- HELPERS ----------------
def today():
    return date.today().isoformat()

def get_user_id():
    return request.remote_addr  # simple per-user partition

# ---------------- DATABASE ----------------
def init_db():
    with sqlite3.connect(DB_PATH) as conn:
        c = conn.cursor()

        c.execute("""
        CREATE TABLE IF NOT EXISTS reminders (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT,
            time TEXT,
            completed INTEGER DEFAULT 0,
            user_id TEXT
        )
        """)

        c.execute("""
        CREATE TABLE IF NOT EXISTS water (
            date TEXT,
            count INTEGER,
            user_id TEXT,
            PRIMARY KEY (date, user_id)
        )
        """)

        conn.commit()

# ---------------- AI ----------------
def safety_prefix():
    return (
        "You are Medibot, an educational medical assistant.\n"
        "Do NOT diagnose.\n"
        "Do NOT prescribe.\n"
        "Educational guidance only.\n\n"
    )

def generate_text(prompt):
    try:
        model = genai.GenerativeModel("gemini-2.5-flash-lite")
        r = model.generate_content(safety_prefix() + prompt)
        return r.text.strip()
    except:
        return "AI error. Try again."

def analyze_image(path):
    try:
        with open(path, "rb") as f:
            b64 = base64.b64encode(f.read()).decode()

        response = openai_client.chat.completions.create(
            model="gpt-4o",
            messages=[{
                "role": "user",
                "content": [
                    {"type": "text", "text": safety_prefix() + "Explain this image medically (educational)."},
                    {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{b64}"}}
                ]
            }],
            max_tokens=300
        )
        return response.choices[0].message.content.strip()
    except:
        return ("Image analysis is temporarily unavailable due to service limits.\n"
                "Please try again later or consult a healthcare professional.\n\n"
                "Note: This does NOT affect chat-based assistance."
                )

# ---------------- ROUTES ----------------
@app.route("/")
def index():
    return send_from_directory("templates", "index.html")

@app.route("/api/chat", methods=["POST"])
def chat():
    msg = request.json.get("message", "")
    return jsonify({"reply": generate_text(msg)})

@app.route("/api/summarize", methods=["POST"])
def summarize():
    text = request.json.get("text", "")
    return jsonify({"summary": generate_text("Summarize:\n" + text)})

@app.route("/api/upload_image", methods=["POST"])
def upload_image():
    f = request.files.get("image")
    path = os.path.join(UPLOAD_FOLDER, secure_filename(f.filename))
    f.save(path)
    return jsonify({"medical_assistance": analyze_image(path)})

# ---------------- REMINDERS ----------------
@app.route("/api/reminder", methods=["POST"])
def add_reminder():
    user = get_user_id()
    name = request.json["name"]
    time = request.json["time"]

    with sqlite3.connect(DB_PATH) as conn:
        conn.execute(
            "INSERT INTO reminders (name, time, completed, user_id) VALUES (?, ?, 0, ?)",
            (name, time, user)
        )
        conn.commit()

    return jsonify({"ok": True})

@app.route("/api/reminders", methods=["GET"])
def get_reminders():
    user = get_user_id()
    with sqlite3.connect(DB_PATH) as conn:
        rows = conn.execute(
            "SELECT id, name, time, completed FROM reminders WHERE user_id=? ORDER BY time",
            (user,)
        ).fetchall()

    return jsonify({
        "reminders": [
            {"id": r[0], "name": r[1], "time": r[2], "completed": bool(r[3])}
            for r in rows
        ]
    })

@app.route("/api/reminder/<int:rid>/complete", methods=["POST"])
def complete_reminder(rid):
    user = get_user_id()
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute(
            "UPDATE reminders SET completed=1 WHERE id=? AND user_id=?",
            (rid, user)
        )
        conn.commit()
    return jsonify({"ok": True})

@app.route("/api/reminders/completed", methods=["DELETE"])
def delete_completed():
    user = get_user_id()
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute(
            "DELETE FROM reminders WHERE completed=1 AND user_id=?",
            (user,)
        )
        conn.commit()
    return jsonify({"ok": True})

# ---------------- WATER ----------------
@app.route("/api/water", methods=["GET"])
def get_water():
    user = get_user_id()
    d = today()
    with sqlite3.connect(DB_PATH) as conn:
        row = conn.execute(
            "SELECT count FROM water WHERE date=? AND user_id=?",
            (d, user)
        ).fetchone()

    return jsonify({"count": row[0] if row else 0})

@app.route("/api/water", methods=["POST"])
def add_water():
    user = get_user_id()
    d = today()
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute("""
            INSERT INTO water (date, count, user_id)
            VALUES (?, 1, ?)
            ON CONFLICT(date, user_id)
            DO UPDATE SET count = count + 1
        """, (d, user))
        conn.commit()

        row = conn.execute(
            "SELECT count FROM water WHERE date=? AND user_id=?",
            (d, user)
        ).fetchone()

    return jsonify({"count": row[0]})

# ---------------- DAILY SUMMARY ----------------
@app.route("/api/daily_summary", methods=["GET"])
def daily_summary():
    user = get_user_id()
    with sqlite3.connect(DB_PATH) as conn:
        reminders = conn.execute(
            "SELECT name, time FROM reminders WHERE user_id=? AND completed=0",
            (user,)
        ).fetchall()

    reminder_text = "\n".join(f"- {t}: {n}" for n, t in reminders) or "No reminders today."
    summary = generate_text("Create a daily health summary:\n" + reminder_text)
    return jsonify({"summary": summary})

# ---------------- START ----------------
if __name__ == "__main__":
    init_db()
    app.run(host="0.0.0.0", port=PORT)
