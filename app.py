# app.py
import os
import sqlite3
from flask import Flask, request, jsonify, send_from_directory
from werkzeug.utils import secure_filename
from dotenv import load_dotenv

load_dotenv()

# Config
GEMINI_KEY = os.getenv("GEMINI_API_KEY")
UPLOAD_FOLDER = os.path.join(os.getcwd(), "uploads")
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
DB_PATH = os.path.join(os.getcwd(), "medibot.db")

# Optional Gemini
USE_GEMINI = bool(GEMINI_KEY)
if USE_GEMINI:
    try:
        from google import generativeai as genai
    except Exception:
        import google.generativeai as genai
    genai.configure(api_key=GEMINI_KEY)

# image libs (optional: used for basic descriptive output)
try:
    from PIL import Image
    import cv2
    import numpy as np
    HAS_IMG = True
except Exception:
    HAS_IMG = False

app = Flask(__name__, static_folder="static", template_folder="templates")
app.config["UPLOAD_FOLDER"] = UPLOAD_FOLDER

# DB helpers
def init_db():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("""
    CREATE TABLE IF NOT EXISTS reminders (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      name TEXT,
      time TEXT
    )""")
    c.execute("""
    CREATE TABLE IF NOT EXISTS notes (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      content TEXT,
      created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )""")
    c.execute("""
    CREATE TABLE IF NOT EXISTS water (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      date TEXT,
      count INTEGER
    )""")
    conn.commit()
    conn.close()

def add_reminder(name, time):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("INSERT INTO reminders (name, time) VALUES (?, ?)", (name, time))
    conn.commit()
    conn.close()

def list_reminders():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT id, name, time FROM reminders ORDER BY id DESC")
    rows = c.fetchall()
    conn.close()
    return [{"id": r[0], "name": r[1], "time": r[2]} for r in rows]

def add_note(content):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("INSERT INTO notes (content) VALUES (?)", (content,))
    conn.commit()
    conn.close()

def list_notes(limit=20):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT id, content, created_at FROM notes ORDER BY created_at DESC LIMIT ?", (limit,))
    rows = c.fetchall()
    conn.close()
    return [{"id": r[0], "content": r[1], "created_at": r[2]} for r in rows]

def get_water_count(date_str):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT id, count FROM water WHERE date = ?", (date_str,))
    row = c.fetchone()
    conn.close()
    if row:
        return {"id": row[0], "count": row[1]}
    return None

def set_water_count(date_str, count):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    existing = get_water_count(date_str)
    if existing:
        c.execute("UPDATE water SET count = ? WHERE id = ?", (count, existing["id"]))
    else:
        c.execute("INSERT INTO water (date, count) VALUES (?, ?)", (date_str, count))
    conn.commit()
    conn.close()

# AI wrappers
def safe_prefix():
    return ("You are Medibot, a friendly educational health assistant. "
            "Always avoid providing medical diagnoses or emergency instructions. "
            "When unsure, advise consulting a licensed clinician.\n\n")

def gemini_generate(prompt, max_output_tokens=512):
    if not USE_GEMINI:
        raise RuntimeError("Gemini not configured")
    try:
        resp = genai.responses.create(
            model="gemini-2.0-flash",
            input=prompt,
            max_output_tokens=max_output_tokens
        )
        # new SDK returns output_text
        if hasattr(resp, "output_text"):
            return resp.output_text
        # fallback: check resp.output
        out = ""
        for item in getattr(resp, "output", []) :
            if isinstance(item, dict):
                for c in item.get("content", []):
                    if c.get("type") == "output_text":
                        out += c.get("text","")
        if out:
            return out
        return str(resp)
    except Exception as e:
        print("Gemini error:", e)
        return None

def generate_text(prompt):
    p = safe_prefix() + prompt
    if USE_GEMINI:
        out = gemini_generate(p)
        if out:
            return out
        return "AI error. Try again."
    return "AI not configured. Set GEMINI_API_KEY."

# Image analysis (lightweight, educational)
def image_describe(path):
    if not HAS_IMG:
        return "Image libs not installed on server."
    img = cv2.imread(path)
    if img is None:
        return "Could not read image."
    h, w = img.shape[:2]
    avg_color = img.mean(axis=(0,1)).astype(int).tolist()
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    edges = cv2.Canny(gray, 50, 150)
    contours, _ = cv2.findContours(edges, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    n = len(contours)
    desc = f"Educational image description: resolution {w}x{h}. Detected ~{n} edge contours. Average BGR color {avg_color}.\nNote: This is not a medical diagnosis."
    return desc

# Routes
@app.route("/")
def index():
    return send_from_directory("templates", "index.html")

@app.route("/static/<path:path>")
def static_files(path):
    return send_from_directory("static", path)

@app.route("/api/chat", methods=["POST"])
def api_chat():
    data = request.json or {}
    msg = data.get("message","").strip()
    if not msg:
        return jsonify({"error":"empty"}), 400
    out = generate_text(msg)
    return jsonify({"reply": out})

@app.route("/api/summarize", methods=["POST"])
def api_summarize():
    data = request.json or {}
    text = data.get("text","").strip()
    if not text:
        return jsonify({"error":"empty"}), 400
    prompt = "Summarize for a non-expert in 4 bullet points and a short plain summary:\n\n" + text
    out = generate_text(prompt)
    return jsonify({"summary": out})

@app.route("/api/upload_image", methods=["POST"])
def api_upload_image():
    if "image" not in request.files:
        return jsonify({"error":"no file"}), 400
    f = request.files["image"]
    name = secure_filename(f.filename)
    target = os.path.join(app.config["UPLOAD_FOLDER"], name)
    f.save(target)
    desc = image_describe(target)
    return jsonify({"description": desc, "file": target})

@app.route("/api/analyze_local", methods=["POST"])
def api_analyze_local():
    data = request.json or {}
    path = data.get("path")
    if not path or not os.path.exists(path):
        return jsonify({"error":"path missing or not found"}), 400
    desc = image_describe(path)
    return jsonify({"description": desc})

# reminders / notes / water API (simple)
@app.route("/api/reminder", methods=["POST"])
def api_add_reminder():
    data = request.json or {}
    name = data.get("name")
    time = data.get("time")
    if not name or not time:
        return jsonify({"error":"missing fields"}), 400
    add_reminder(name, time)
    return jsonify({"ok": True, "reminders": list_reminders()})

@app.route("/api/reminders", methods=["GET"])
def api_list_reminders():
    return jsonify({"reminders": list_reminders()})

@app.route("/api/notes", methods=["POST"])
def api_add_note():
    data = request.json or {}
    content = data.get("content","").strip()
    if not content:
        return jsonify({"error":"empty"}), 400
    add_note(content)
    return jsonify({"ok": True, "notes": list_notes()})

@app.route("/api/notes", methods=["GET"])
def api_list_notes():
    return jsonify({"notes": list_notes()})

@app.route("/api/water", methods=["POST"])
def api_set_water():
    data = request.json or {}
    date = data.get("date")
    count = int(data.get("count", 0))
    if not date:
        return jsonify({"error":"missing date"}), 400
    set_water_count(date, count)
    return jsonify({"ok": True, "count": count})

@app.route("/api/water", methods=["GET"])
def api_get_water():
    date = request.args.get("date")
    if not date:
        return jsonify({"error":"missing date"}), 400
    cur = get_water_count(date)
    return jsonify({"count": cur["count"] if cur else 0})

@app.route("/api/daily_summary", methods=["GET"])
def api_daily_summary():
    notes = list_notes(limit=10)
    reminders = list_reminders()
    prompt = "Create a short daily summary (3-6 sentences) from these notes and reminders. Notes:\n"
    for n in notes:
        prompt += "- " + n["content"] + "\n"
    prompt += "\nReminders:\n"
    for r in reminders:
        prompt += "- " + r["name"] + " at " + r["time"] + "\n"
    prompt += "\nWrite a friendly daily summary and list one actionable tip."
    out = generate_text(prompt)
    return jsonify({"summary": out, "notes": notes, "reminders": reminders})

if __name__ == "__main__":
    init_db()
    port = int(os.getenv("PORT", 5000))
    print("Medibot starting on port", port)
    app.run(host="0.0.0.0", port=port)
