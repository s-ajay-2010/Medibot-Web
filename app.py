import os
import sqlite3
from flask import Flask, request, jsonify, send_from_directory
from werkzeug.utils import secure_filename
from dotenv import load_dotenv

load_dotenv()


GEMINI_KEY = os.getenv("GEMINI_API_KEY")
UPLOAD_FOLDER = os.path.join(os.getcwd(), "uploads")
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
DB_PATH = os.path.join(os.getcwd(), "medibot.db")


USE_GEMINI = bool(GEMINI_KEY)
if USE_GEMINI:
    try:
        from google import generativeai as genai
    except Exception:
        import google.generativeai as genai

    genai.configure(api_key=GEMINI_KEY)


try:
    from PIL import Image
    import cv2
    import numpy as np
    HAS_IMG = True
except Exception:
    HAS_IMG = False


app = Flask(__name__, static_folder="static", template_folder="templates")
app.config["UPLOAD_FOLDER"] = UPLOAD_FOLDER


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


def safe_prefix():
    return (
        "You are Medibot, an educational health assistant. "
        "Do not diagnose. Provide simple explanations only. "
        "Recommend real doctors when needed.\n\n"
    )


def gemini_generate(prompt):
    try:
        model = genai.GenerativeModel("gemini-2.5-flash-lite")
        resp = model.generate_content(prompt)
        return resp.text
    except Exception as e:
        print("Gemini error:", e)
        return None

def generate_text(user_input):
    prompt = safe_prefix() + user_input
    if USE_GEMINI:
        out = gemini_generate(prompt)
        if out:
            return out
        return "AI error. Try again."
    return "AI not configured. Add GEMINI_API_KEY in your .env"


def image_describe(path):
    if not HAS_IMG:
        return "Image libraries not installed."
    img = cv2.imread(path)
    if img is None:
        return "Unable to read image."
    h, w = img.shape[:2]
    avg = img.mean(axis=(0,1)).astype(int).tolist()
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    edges = cv2.Canny(gray, 50, 150)
    cont, _ = cv2.findContours(edges, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    return (
        f"Educational image description: resolution {w}x{h}, "
        f"contours detected {len(cont)}, average color {avg}. "
        "Not a diagnosis."
    )

def safe_image_prompt():
    return (
        "You are Medibot, an educational health assistant. "
        "You can describe what is visually present in the image in SIMPLE, non-expert terms. "
        "You MUST NOT diagnose any disease, condition, or medical problem. "
        "Only describe visible patterns like redness, swelling, marks, shapes, shadows, objects, etc. "
        "If something looks unusual, say it *may appear unusual*, not that it *is* a disease. "
        "Always end by telling the user to consult a doctor for proper medical interpretation.\n\n"
    )

@app.route("/")
def index():
    return send_from_directory("templates", "index.html")

@app.route("/static/<path:path>")
def static_files(path):
    return send_from_directory("static", path)

@app.route("/api/chat", methods=["POST"])
def api_chat():
    msg = request.json.get("message","").strip()
    if not msg:
        return jsonify({"error": "empty"}), 400
    return jsonify({"reply": generate_text(msg)})

@app.route("/api/summarize", methods=["POST"])
def api_summarize():
    text = request.json.get("text","").strip()
    if not text:
        return jsonify({"error":"empty"}), 400
    prompt = (
        "Summarize the following for a non-expert in 4 bullet points plus a plain short summary:\n\n"
        + text
    )
    return jsonify({"summary": generate_text(prompt)})

@app.route("/api/upload_image", methods=["POST"])
def api_upload_image():
    if "image" not in request.files:
        return jsonify({"error": "no file"}), 400

    f = request.files["image"]
    name = secure_filename(f.filename)
    path = os.path.join(app.config["UPLOAD_FOLDER"], name)
    f.save(path)

    # 1. Local OpenCV analysis
    local_desc = image_describe(path)

    # 2. Gemini Vision analysis (if enabled)
    gem_desc = None
    if USE_GEMINI:
        try:
            gem_desc = gemini_generate(
                safe_prefix()
                + "Explain this image in simple educational terms. No diagnosis."
            )
        except Exception as e:
            gem_desc = f"Gemini error: {e}"

    return jsonify({
        "local_description": local_desc,
        "gemini_description": gem_desc
    })



@app.route("/api/analyze_local", methods=["POST"])
def api_analyze_local():
    path = request.json.get("path")
    if not path or not os.path.exists(path):
        return jsonify({"error":"path missing"}), 400
    return jsonify({"description": image_describe(path)})

@app.route("/api/reminder", methods=["POST"])
def api_add_reminder_route():
    data = request.json
    name = data.get("name")
    time = data.get("time")
    if not name or not time:
        return jsonify({"error":"missing fields"}), 400
    add_reminder(name, time)
    return jsonify({"ok": True, "reminders": list_reminders()})

@app.route("/api/reminders", methods=["GET"])
def api_list_reminders_route():
    return jsonify({"reminders": list_reminders()})

@app.route("/api/notes", methods=["POST"])
def api_add_note_route():
    content = request.json.get("content","").strip()
    if not content:
        return jsonify({"error":"empty"}), 400
    add_note(content)
    return jsonify({"ok": True, "notes": list_notes()})

@app.route("/api/notes", methods=["GET"])
def api_list_notes_route():
    return jsonify({"notes": list_notes()})

@app.route("/api/water", methods=["POST"])
def api_set_water_route():
    data = request.json
    date = data.get("date")
    count = int(data.get("count",0))
    if not date:
        return jsonify({"error":"missing date"}), 400
    set_water_count(date, count)
    return jsonify({"ok": True, "count": count})

@app.route("/api/water", methods=["GET"])
def api_get_water_route():
    date = request.args.get("date")
    if not date:
        return jsonify({"error":"missing date"}), 400
    cur = get_water_count(date)
    return jsonify({"count": cur["count"] if cur else 0})

@app.route("/api/daily_summary", methods=["GET"])
def api_daily_summary():
    notes = list_notes(10)
    reminders = list_reminders()

    prompt = "Create a friendly daily summary:\n\nNotes:\n"
    for n in notes:
        prompt += "- " + n["content"] + "\n"
    prompt += "\nReminders:\n"
    for r in reminders:
        prompt += "- " + r["name"] + " at " + r["time"] + "\n"
    prompt += "\nAdd one actionable health tip."

    return jsonify({
        "summary": generate_text(prompt),
        "notes": notes,
        "reminders": reminders
    })

@app.route("/.well-known/assetlinks.json")
def assetlinks():
    return send_from_directory(".","assetlinks.json",mimetype="application/json")


if __name__ == "__main__":
    init_db()
    port = int(os.getenv("PORT", 5000))
    print("Medibot running on port", port)
    app.run(host="0.0.0.0", port=port)
