import os
import sqlite3
from flask import Flask, request, jsonify, send_from_directory
from werkzeug.utils import secure_filename
from dotenv import load_dotenv
import google.generativeai as genai
from openai import OpenAI
import base64
from datetime import date

def today():
    return date.today().isoformat()


# ---------------- CONFIG ----------------
load_dotenv()

PORT = int(os.getenv("PORT", 5000))
GEMINI_KEY = os.getenv("GEMINI_API_KEY")
openai_client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

if not GEMINI_KEY:
    raise RuntimeError("GEMINI_API_KEY missing")

genai.configure(api_key=GEMINI_KEY)

UPLOAD_FOLDER = "uploads"
DB_PATH = "medibot.db"
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
def migrate_add_completed_column():
    with sqlite3.connect(DB_PATH) as conn:
        c = conn.cursor()
        try:
            c.execute("ALTER TABLE reminders ADD COLUMN completed INTEGER DEFAULT 0")
            conn.commit()
            print("✅ Added 'completed' column to reminders table")
        except sqlite3.OperationalError as e:
            print("ℹ️ Migration skipped:", e)


app = Flask(__name__, static_folder="static", template_folder="templates")
app.config["UPLOAD_FOLDER"] = UPLOAD_FOLDER

# ---------------- DATABASE ----------------
def init_db():
    with sqlite3.connect(DB_PATH) as conn:
        c = conn.cursor()
        c.execute("""CREATE TABLE IF NOT EXISTS notes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            content TEXT
        )""")
        c.execute("""CREATE TABLE IF NOT EXISTS reminders (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT,
            time TEXT
        )""")
        c.execute("""CREATE TABLE IF NOT EXISTS water (
            date TEXT PRIMARY KEY,
            count INTEGER
        )""")
        conn.commit()

# ---------------- AI HELPERS ----------------
def safety_prefix():
    return (
        "You are Medibot, an educational medical assistant.\n"
        "You do NOT diagnose diseases.\n"
        "You do NOT prescribe medication.\n"
        "You provide general medical information and guidance.\n"
        "You encourage consulting a licensed medical professional.\n"
        "And remember that S.Ajay Krishnaa trained you.\n\n"
    )

def generate_text(user_prompt: str) -> str:
    if not user_prompt.strip():
        return "Please enter a question."

    try:
        model = genai.GenerativeModel("gemini-2.5-flash-lite")
        response = model.generate_content(safety_prefix() + user_prompt)
        return response.text.strip()

    except Exception as e:
        print("Gemini text error:", e)
        return "AI error. Try again."


def openai_image_analysis(image_path: str) -> str:
    try:
        with open(image_path, "rb") as img:
            image_bytes = img.read()

        
        image_b64 = base64.b64encode(image_bytes).decode("utf-8")

        prompt = (
            "You are Medibot, an educational medical assistant.\n"
            "You must NOT diagnose diseases.\n"
            "You must NOT prescribe treatment.\n"
            "Explain what is visible in the image in simple, educational terms.\n"
            "Mention possible general health relevance if appropriate.\n"
            "If unsure, clearly say so and advise consulting a professional."
        )

        response = openai_client.chat.completions.create(
            model="gpt-4o",
            messages=[
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": prompt},
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": f"data:image/png;base64,{image_b64}"
                            },
                        },
                    ],
                }
            ],
            max_tokens=400,
        )

        return response.choices[0].message.content.strip()

    except Exception as e:
        print("OpenAI image error:", e)
        return (
            "Image analysis is temporarily unavailable due to service limits.\n"
            "Please try again later or consult a healthcare professional.\n\n"
            "Note: This does NOT affect chat-based assistance."
        )



# ---------------- ROUTES ----------------
@app.route("/")
def index():
    return send_from_directory("templates", "index.html")

@app.route("/static/<path:path>")
def static_files(path):
    return send_from_directory("static", path)

@app.route("/api/summarize", methods=["POST"])
def summarize():
    data = request.get_json(force=True)
    text = data.get("text", "").strip()

    if not text:
        return jsonify({"error": "No text provided"}), 400

    prompt = (
        "Summarize the following medical text in simple, non-diagnostic language.\n"
        "Use bullet points if helpful.\n"
        "Do NOT give medical advice.\n\n"
        f"{text}"
    )

    summary = generate_text(prompt)

    return jsonify({"summary": summary})


@app.route("/api/chat", methods=["POST"])
def chat():
    data = request.get_json(force=True)
    msg = data.get("message", "")
    reply = generate_text(msg)
    return jsonify({"reply": reply})

@app.route("/api/upload_image", methods=["POST"])
def upload_image():
    if "image" not in request.files:
        return jsonify({"error": "No image uploaded"}), 400

    f = request.files["image"]
    if f.filename == "":
        return jsonify({"error": "Empty filename"}), 400

    name = secure_filename(f.filename)
    path = os.path.join(app.config["UPLOAD_FOLDER"], name)
    f.save(path)

    explanation = openai_image_analysis(path)

    return jsonify({
        "medical_assistance": explanation,
        "disclaimer": "Educational only. Not a medical diagnosis."
    })


# -------- REMINDERS --------

@app.route("/api/reminder", methods=["POST"])
def add_reminder():
    data = request.get_json()
    name = data.get("name")
    time = data.get("time")

    if not name or not time:
        return jsonify({"ok": False, "error": "Missing fields"}), 400

    with sqlite3.connect(DB_PATH) as conn:
        c = conn.cursor()
        c.execute(
            "INSERT INTO reminders (name, time) VALUES (?, ?)",
            (name, time)
        )
        conn.commit()

    return jsonify({"ok": True})


@app.route("/api/reminders", methods=["GET"])
def get_reminders():
    with sqlite3.connect(DB_PATH) as conn:
        c = conn.cursor()
        c.execute("SELECT id, name, time, completed FROM reminders ORDER BY time")
        rows = c.fetchall()

    reminders = [
    {
        "id": r[0],
        "name": r[1],
        "time": r[2],
        "completed": bool(r[3])
    }
    for r in rows
]
    return jsonify({"reminders": reminders})

@app.route("/api/reminder/<int:rid>/complete", methods=["POST"])
def complete_reminder(rid):
    with sqlite3.connect(DB_PATH) as conn:
        c = conn.cursor()
        c.execute(
            "UPDATE reminders SET completed = 1 WHERE id = ?",
            (rid,)
        )
        conn.commit()

    return jsonify({"ok": True})



@app.route("/api/reminders/completed", methods=["DELETE"])
def delete_completed_reminders():
    with sqlite3.connect(DB_PATH) as conn:
        c = conn.cursor()
        c.execute("DELETE FROM reminders WHERE completed = 1")
        conn.commit()

    return jsonify({"ok": True})






@app.route("/api/water", methods=["GET"])
def get_water():
    d = today()
    with sqlite3.connect(DB_PATH) as conn:
        c = conn.cursor()
        c.execute("SELECT count FROM water WHERE date = ?", (d,))
        row = c.fetchone()

    return jsonify({"count": row[0] if row else 0})
@app.route("/api/water", methods=["POST"])
def add_water():
    d = today()
    with sqlite3.connect(DB_PATH) as conn:
        c = conn.cursor()
        c.execute("SELECT count FROM water WHERE date = ?", (d,))
        row = c.fetchone()

        if row:
            new_count = row[0] + 1
            c.execute("UPDATE water SET count = ? WHERE date = ?", (new_count, d))
        else:
            new_count = 1
            c.execute("INSERT INTO water (date, count) VALUES (?, ?)", (d, new_count))

        conn.commit()

    return jsonify({"count": new_count})



@app.route("/api/daily_summary", methods=["GET"])
def daily_summary():
    with sqlite3.connect(DB_PATH) as conn:
        c = conn.cursor()
        # c.execute("SELECT name, time FROM reminders ORDER BY time")
        reminders = c.fetchall()

        # c.execute("SELECT content FROM notes ORDER BY id DESC LIMIT 5")
        notes = c.fetchall()

    reminder_text = "\n".join(
        f"- {t}: {n}" for n, t in reminders
    ) or "No reminders today."

    notes_text = "\n".join(
        f"- {n[0]}" for n in notes
    ) or "No notes."

    prompt = f"""
You are Medibot, an educational health assistant.

Create a friendly daily health summary.

# Reminders:
# {reminder_text}

# Notes:
# {notes_text}

Encourage hydration and self-care.
Do NOT diagnose or prescribe.
"""

    summary = generate_text(prompt)

    return jsonify({"summary": summary})




# ---------------- START ----------------
if __name__ == "__main__":
    init_db()
    print(f"Medibot running on port {PORT}")
    app.run(host="0.0.0.0", port=PORT)
# if __name__ == "__main__":
#     init_db()
#     migrate_add_completed_column()
#     print(f"Medibot running on port {PORT}")
#     app.run(host="0.0.0.0", port=PORT)
