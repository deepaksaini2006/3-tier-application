"""Admission form backend for Sobhasaria Group of Institutions (Flask + MySQL)."""
import os
import re
import secrets
import time
from datetime import date, datetime, timezone

from flask import Flask, g, jsonify, request
from flask_cors import CORS
import pymysql
import pymysql.cursors

try:  # optional: load backend/.env if python-dotenv is installed
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass
from pymysql.err import IntegrityError

DB_CONFIG = {
    "host": os.environ.get("MYSQL_HOST", "127.0.0.1"),
    "port": int(os.environ.get("MYSQL_PORT", "3306")),
    "user": os.environ.get("MYSQL_USER", "root"),
    "password": os.environ.get("MYSQL_PASSWORD", ""),
    "database": os.environ.get("MYSQL_DATABASE", "sobhasaria_admissions"),
    "charset": "utf8mb4",
    "cursorclass": pymysql.cursors.DictCursor,
    "autocommit": False,
}
ADMIN_TOKEN = os.environ.get("ADMIN_TOKEN", "")  # set this to enable the admin list endpoint

app = Flask(__name__)
CORS(app, origins=os.environ.get("CORS_ORIGINS", "*").split(","))  # e.g. CORS_ORIGINS=https://your-domain.com

PROGRAMS = {
    "B.Tech": ["Computer Science & Engineering", "Electronics & Communication",
               "Mechanical Engineering", "Civil Engineering", "Electrical Engineering"],
    "BCA": ["General"],
    "BBA": ["General"],
    "M.Tech": ["Computer Science", "Structural Engineering", "Thermal Engineering"],
    "MBA": ["Marketing", "Finance", "Human Resources"],
    "Diploma in Engineering": ["Computer Engineering", "Mechanical Engineering", "Civil Engineering"],
}
QUALIFICATIONS = {"Class 10", "Class 12 (PCM)", "Class 12 (other stream)", "Diploma", "Bachelor's degree"}
EMAIL_RE = re.compile(r"^[^\s@]+@[^\s@]+\.[^\s@]+$")
PHONE_RE = re.compile(r"^[6-9]\d{9}$")


# ---------- database ----------
def get_db():
    if "db" not in g:
        g.db = pymysql.connect(**DB_CONFIG)
    return g.db


@app.teardown_appcontext
def close_db(_exc):
    db = g.pop("db", None)
    if db is not None:
        db.close()


def init_db():
    """Create the table if it does not exist. The database itself must exist (see schema.sql)."""
    conn = None
    for attempt in range(15):  # MySQL in Docker can take a few seconds to accept connections
        try:
            conn = pymysql.connect(**DB_CONFIG)
            break
        except pymysql.err.OperationalError:
            if attempt == 14:
                raise
            time.sleep(2)
    try:
        with conn.cursor() as cur:
            cur.execute(
                """CREATE TABLE IF NOT EXISTS applications (
                    id INT AUTO_INCREMENT PRIMARY KEY,
                    reference VARCHAR(20) NOT NULL UNIQUE,
                    name VARCHAR(120) NOT NULL,
                    dob DATE NOT NULL,
                    email VARCHAR(190) NOT NULL,
                    phone CHAR(10) NOT NULL,
                    course VARCHAR(60) NOT NULL,
                    branch VARCHAR(80) NOT NULL,
                    qualification VARCHAR(40) NOT NULL,
                    marks DECIMAL(5,2) NOT NULL,
                    city VARCHAR(120) NOT NULL,
                    message TEXT,
                    created_at DATETIME NOT NULL,
                    INDEX idx_email (email),
                    INDEX idx_course (course)
                ) CHARACTER SET utf8mb4"""
            )
        conn.commit()
    finally:
        conn.close()


# ---------- validation ----------
def validate(data):
    errors = {}
    name = (data.get("name") or "").strip()
    if len(name) < 3:
        errors["name"] = "Enter your full name."

    try:
        dob = date.fromisoformat(data.get("dob") or "")
        age = (date.today() - dob).days / 365.25
        if not 15 <= age <= 60:
            errors["dob"] = "Enter a valid date of birth."
    except ValueError:
        errors["dob"] = "Select your date of birth."

    if not EMAIL_RE.match(data.get("email") or ""):
        errors["email"] = "Enter a valid email address."
    if not PHONE_RE.match(data.get("phone") or ""):
        errors["phone"] = "Enter a 10-digit mobile number starting with 6, 7, 8 or 9."

    course, branch = data.get("course"), data.get("branch")
    if course not in PROGRAMS:
        errors["course"] = "Select a valid program."
    elif branch not in PROGRAMS[course]:
        errors["branch"] = "Select a valid branch for this program."

    if data.get("qual") not in QUALIFICATIONS:
        errors["qual"] = "Select your last qualification."

    try:
        marks = float(data.get("marks"))
        if not 0 <= marks <= 100:
            raise ValueError
    except (TypeError, ValueError):
        errors["marks"] = "Enter a percentage between 0 and 100."

    if len((data.get("city") or "").strip()) < 2:
        errors["city"] = "Enter your city and state."
    if not data.get("agree"):
        errors["agree"] = "Please confirm to submit."
    return errors


# ---------- routes ----------
@app.get("/api/health")
def health():
    return jsonify(status="ok")


@app.post("/api/apply")
def apply():
    data = request.get_json(silent=True) or request.form.to_dict()
    errors = validate(data)
    if errors:
        return jsonify(ok=False, errors=errors), 400

    db = get_db()
    # reference collisions are very unlikely, but retry on the UNIQUE constraint
    for _ in range(5):
        reference = "SGI26-" + secrets.token_hex(3).upper()
        try:
            with db.cursor() as cur:
                cur.execute(
                    """INSERT INTO applications
                       (reference, name, dob, email, phone, course, branch, qualification,
                        marks, city, message, created_at)
                       VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
                    (reference, data["name"].strip(), data["dob"], data["email"].strip().lower(),
                     data["phone"], data["course"], data["branch"], data["qual"],
                     float(data["marks"]), data["city"].strip(), (data.get("msg") or "").strip(),
                     datetime.now(timezone.utc).replace(tzinfo=None)),
                )
            db.commit()
            break
        except IntegrityError:
            db.rollback()
            continue
    else:
        return jsonify(ok=False, error="Could not save the application. Try again."), 500

    return jsonify(ok=True, reference=reference), 201


@app.get("/api/applications")
def list_applications():
    """Admin only: send header  Authorization: Bearer <ADMIN_TOKEN>."""
    auth = request.headers.get("Authorization", "")
    if not ADMIN_TOKEN or not secrets.compare_digest(auth, f"Bearer {ADMIN_TOKEN}"):
        return jsonify(ok=False, error="Unauthorized"), 401
    with get_db().cursor() as cur:
        cur.execute("SELECT * FROM applications ORDER BY id DESC")
        rows = cur.fetchall()
    for r in rows:  # make dates/decimals JSON friendly
        r["dob"] = r["dob"].isoformat()
        r["created_at"] = r["created_at"].isoformat()
        r["marks"] = float(r["marks"])
    return jsonify(ok=True, applications=rows)


init_db()

if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5000, debug=os.environ.get("FLASK_DEBUG") == "1")
