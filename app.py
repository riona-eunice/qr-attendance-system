import sqlite3
import uuid
import io
import csv
import re
import base64
from datetime import date, datetime

import qrcode
from flask import Flask, render_template, request, redirect, url_for, flash, jsonify, Response

app = Flask(__name__)
app.secret_key = "dev-secret-key-change-this"

DB_NAME = "attendance.db"
EMAIL_PATTERN = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")

# ---------- COLLEGE / DEPARTMENT BRANDING ----------
# Edit these two lines to rebrand the whole app for your institution.
COLLEGE_NAME = "Panimalar Engineering College"
DEPARTMENT_NAME = "Department of Artificial Intelligence and Machine Learning"


# ---------- DATABASE SETUP ----------

def get_db():
    conn = sqlite3.connect(DB_NAME)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db():
    conn = get_db()
    conn.execute("""
        CREATE TABLE IF NOT EXISTS faculty (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            designation TEXT NOT NULL,
            email TEXT NOT NULL,
            is_hod INTEGER NOT NULL DEFAULT 0,
            created_at TEXT NOT NULL
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS students (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            roll_no TEXT NOT NULL UNIQUE,
            register_no TEXT NOT NULL UNIQUE,
            email TEXT NOT NULL,
            token TEXT NOT NULL UNIQUE,
            created_at TEXT NOT NULL
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS courses (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            code TEXT NOT NULL UNIQUE,
            faculty_id INTEGER NOT NULL,
            created_at TEXT NOT NULL,
            FOREIGN KEY (faculty_id) REFERENCES faculty (id)
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS sessions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            course_id INTEGER NOT NULL,
            session_date TEXT NOT NULL,
            conducted_by_id INTEGER NOT NULL,
            created_at TEXT NOT NULL,
            FOREIGN KEY (course_id) REFERENCES courses (id),
            FOREIGN KEY (conducted_by_id) REFERENCES faculty (id)
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS attendance (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id INTEGER NOT NULL,
            student_id INTEGER NOT NULL,
            marked_at TEXT NOT NULL,
            FOREIGN KEY (session_id) REFERENCES sessions (id),
            FOREIGN KEY (student_id) REFERENCES students (id),
            UNIQUE (session_id, student_id)
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS od_requests (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            student_id INTEGER NOT NULL,
            od_date TEXT NOT NULL,
            reason TEXT NOT NULL,
            approved_by_id INTEGER NOT NULL,
            created_at TEXT NOT NULL,
            FOREIGN KEY (student_id) REFERENCES students (id),
            FOREIGN KEY (approved_by_id) REFERENCES faculty (id),
            UNIQUE (student_id, od_date)
        )
    """)
    conn.commit()
    conn.close()


def get_hod():
    conn = get_db()
    hod = conn.execute("SELECT * FROM faculty WHERE is_hod = 1").fetchone()
    conn.close()
    return hod


@app.context_processor
def inject_branding():
    """Makes college name / department / HOD available to every template automatically."""
    return {
        "COLLEGE_NAME": COLLEGE_NAME,
        "DEPARTMENT_NAME": DEPARTMENT_NAME,
        "current_hod": get_hod(),
    }


# ---------- HOME ----------

@app.route("/")
def home():
    conn = get_db()
    courses = conn.execute(
        """SELECT courses.*, faculty.name AS faculty_name
           FROM courses JOIN faculty ON courses.faculty_id = faculty.id
           ORDER BY courses.id DESC"""
    ).fetchall()
    student_count = conn.execute("SELECT COUNT(*) AS c FROM students").fetchone()["c"]
    faculty_count = conn.execute("SELECT COUNT(*) AS c FROM faculty").fetchone()["c"]
    conn.close()
    return render_template("home.html", courses=courses, student_count=student_count, faculty_count=faculty_count)


# ---------- FACULTY ----------

@app.route("/faculty", methods=["GET", "POST"])
def faculty():
    conn = get_db()
    if request.method == "POST":
        name = request.form["name"].strip()
        designation = request.form["designation"].strip()
        email = request.form["email"].strip()
        is_hod = 1 if request.form.get("is_hod") == "on" else 0

        if not (name and designation and email):
            flash("All fields are required.")
            conn.close()
            return redirect(url_for("faculty"))

        if not EMAIL_PATTERN.match(email):
            flash("Please enter a valid email address.")
            conn.close()
            return redirect(url_for("faculty"))

        # Only one HOD at a time -- unset any previous HOD if this one is marked as HOD
        if is_hod:
            conn.execute("UPDATE faculty SET is_hod = 0")

        conn.execute(
            "INSERT INTO faculty (name, designation, email, is_hod, created_at) VALUES (?, ?, ?, ?, ?)",
            (name, designation, email, is_hod, datetime.now().isoformat(timespec="seconds")),
        )
        conn.commit()
        conn.close()
        return redirect(url_for("faculty"))

    all_faculty = conn.execute("SELECT * FROM faculty ORDER BY is_hod DESC, name").fetchall()
    conn.close()
    return render_template("faculty.html", faculty_list=all_faculty)


# ---------- STUDENTS (ID CARD REGISTRATION) ----------

@app.route("/students", methods=["GET", "POST"])
def students():
    conn = get_db()
    if request.method == "POST":
        name = request.form["name"].strip()
        roll_no = request.form["roll_no"].strip()
        register_no = request.form["register_no"].strip()
        email = request.form["email"].strip()

        if not (name and roll_no and register_no and email):
            flash("All fields are required.")
            conn.close()
            return redirect(url_for("students"))

        if not EMAIL_PATTERN.match(email):
            flash("Please enter a valid email address.")
            conn.close()
            return redirect(url_for("students"))

        token = uuid.uuid4().hex  # this becomes the content of the student's QR ID card
        try:
            conn.execute(
                "INSERT INTO students (name, roll_no, register_no, email, token, created_at) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (name, roll_no, register_no, email, token, datetime.now().isoformat(timespec="seconds")),
            )
            conn.commit()
        except sqlite3.IntegrityError:
            flash("A student with that roll number or register number already exists.")
            conn.close()
            return redirect(url_for("students"))

        student_id = conn.execute("SELECT id FROM students WHERE token = ?", (token,)).fetchone()["id"]
        conn.close()
        return redirect(url_for("student_card", student_id=student_id))

    all_students = conn.execute("SELECT * FROM students ORDER BY id DESC").fetchall()
    conn.close()
    return render_template("students.html", students=all_students)


@app.route("/students/<int:student_id>/card")
def student_card(student_id):
    conn = get_db()
    student = conn.execute("SELECT * FROM students WHERE id = ?", (student_id,)).fetchone()
    conn.close()

    if student is None:
        flash("Student not found.")
        return redirect(url_for("students"))

    img = qrcode.make(student["token"])
    buffer = io.BytesIO()
    img.save(buffer, format="PNG")
    qr_base64 = base64.b64encode(buffer.getvalue()).decode("utf-8")

    return render_template("student_card.html", student=student, qr_base64=qr_base64)


# ---------- COURSES ----------

@app.route("/courses", methods=["GET", "POST"])
def courses():
    conn = get_db()
    all_faculty = conn.execute("SELECT * FROM faculty ORDER BY name").fetchall()

    if request.method == "POST":
        if not all_faculty:
            flash("Add at least one faculty member before creating a course.")
            conn.close()
            return redirect(url_for("faculty"))

        name = request.form["name"].strip()
        code = request.form["code"].strip()
        faculty_id = request.form["faculty_id"]

        if not (name and code and faculty_id):
            flash("All fields are required.")
        else:
            try:
                conn.execute(
                    "INSERT INTO courses (name, code, faculty_id, created_at) VALUES (?, ?, ?, ?)",
                    (name, code, faculty_id, datetime.now().isoformat(timespec="seconds")),
                )
                conn.commit()
            except sqlite3.IntegrityError:
                flash("A course with that code already exists.")
        conn.close()
        return redirect(url_for("home"))

    conn.close()
    return render_template("courses.html", faculty_list=all_faculty)


@app.route("/courses/<int:course_id>")
def course_detail(course_id):
    conn = get_db()
    course = conn.execute(
        """SELECT courses.*, faculty.name AS faculty_name
           FROM courses JOIN faculty ON courses.faculty_id = faculty.id
           WHERE courses.id = ?""",
        (course_id,),
    ).fetchone()
    sessions = conn.execute(
        """SELECT sessions.*, faculty.name AS conducted_by_name
           FROM sessions JOIN faculty ON sessions.conducted_by_id = faculty.id
           WHERE sessions.course_id = ? ORDER BY sessions.id DESC""",
        (course_id,),
    ).fetchall()
    all_faculty = conn.execute("SELECT * FROM faculty ORDER BY name").fetchall()
    conn.close()

    if course is None:
        flash("Course not found.")
        return redirect(url_for("home"))

    return render_template(
        "course_detail.html", course=course, sessions=sessions, faculty_list=all_faculty
    )


@app.route("/courses/<int:course_id>/start_session", methods=["POST"])
def start_session(course_id):
    conducted_by_id = request.form.get("conducted_by_id")
    conn = get_db()
    course = conn.execute("SELECT * FROM courses WHERE id = ?", (course_id,)).fetchone()
    if not conducted_by_id:
        conducted_by_id = course["faculty_id"]  # default to the assigned faculty in-charge

    today = date.today().isoformat()
    conn.execute(
        "INSERT INTO sessions (course_id, session_date, conducted_by_id, created_at) VALUES (?, ?, ?, ?)",
        (course_id, today, conducted_by_id, datetime.now().isoformat(timespec="seconds")),
    )
    conn.commit()
    session_id = conn.execute("SELECT last_insert_rowid() AS id").fetchone()["id"]
    conn.close()
    return redirect(url_for("scan", session_id=session_id))


# ---------- LIVE CAMERA SCANNING ----------

@app.route("/session/<int:session_id>/scan")
def scan(session_id):
    conn = get_db()
    session = conn.execute(
        """SELECT sessions.*, courses.name AS course_name, courses.code AS course_code,
                  faculty.name AS conducted_by_name
           FROM sessions
           JOIN courses ON sessions.course_id = courses.id
           JOIN faculty ON sessions.conducted_by_id = faculty.id
           WHERE sessions.id = ?""",
        (session_id,),
    ).fetchone()
    conn.close()

    if session is None:
        flash("Session not found.")
        return redirect(url_for("home"))

    return render_template("scan.html", session=session)


@app.route("/api/mark", methods=["POST"])
def api_mark():
    """Called by JavaScript on the scan page every time the camera reads a QR code."""
    data = request.get_json(force=True)
    session_id = data.get("session_id")
    token = (data.get("token") or "").strip()

    conn = get_db()
    student = conn.execute("SELECT * FROM students WHERE token = ?", (token,)).fetchone()

    if student is None:
        conn.close()
        return jsonify({"status": "unknown", "message": "This ID card is not registered."})

    try:
        conn.execute(
            "INSERT INTO attendance (session_id, student_id, marked_at) VALUES (?, ?, ?)",
            (session_id, student["id"], datetime.now().isoformat(timespec="seconds")),
        )
        conn.commit()
        result = {"status": "marked", "name": student["name"], "roll_no": student["roll_no"]}
    except sqlite3.IntegrityError:
        result = {"status": "duplicate", "name": student["name"], "roll_no": student["roll_no"]}
    conn.close()
    return jsonify(result)


# ---------- DASHBOARD & CSV EXPORT ----------

@app.route("/session/<int:session_id>/dashboard")
def dashboard(session_id):
    conn = get_db()
    session = conn.execute(
        """SELECT sessions.*, courses.name AS course_name, courses.code AS course_code,
                  faculty.name AS conducted_by_name
           FROM sessions
           JOIN courses ON sessions.course_id = courses.id
           JOIN faculty ON sessions.conducted_by_id = faculty.id
           WHERE sessions.id = ?""",
        (session_id,),
    ).fetchone()

    if session is None:
        conn.close()
        flash("Session not found.")
        return redirect(url_for("home"))

    records = conn.execute(
        """SELECT students.name, students.roll_no, students.register_no, students.email, attendance.marked_at
           FROM attendance JOIN students ON attendance.student_id = students.id
           WHERE attendance.session_id = ?
           ORDER BY attendance.marked_at""",
        (session_id,),
    ).fetchall()

    # Students who have an approved OD for this session's date, and were NOT scanned present
    scanned_rolls = {r["roll_no"] for r in records}
    od_today = conn.execute(
        """SELECT students.name, students.roll_no, students.register_no, students.email,
                  od_requests.reason, faculty.name AS approved_by_name
           FROM od_requests
           JOIN students ON od_requests.student_id = students.id
           JOIN faculty ON od_requests.approved_by_id = faculty.id
           WHERE od_requests.od_date = ?""",
        (session["session_date"],),
    ).fetchall()
    od_today = [r for r in od_today if r["roll_no"] not in scanned_rolls]
    conn.close()

    return render_template("dashboard.html", session=session, records=records, od_today=od_today)


@app.route("/session/<int:session_id>/export.csv")
def export_csv(session_id):
    conn = get_db()
    session = conn.execute(
        """SELECT sessions.*, courses.name AS course_name, faculty.name AS conducted_by_name
           FROM sessions
           JOIN courses ON sessions.course_id = courses.id
           JOIN faculty ON sessions.conducted_by_id = faculty.id
           WHERE sessions.id = ?""",
        (session_id,),
    ).fetchone()
    records = conn.execute(
        """SELECT students.name, students.roll_no, students.register_no, students.email, attendance.marked_at
           FROM attendance JOIN students ON attendance.student_id = students.id
           WHERE attendance.session_id = ?
           ORDER BY attendance.marked_at""",
        (session_id,),
    ).fetchall()
    conn.close()

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["Name", "Roll No", "Register No", "Email", "Marked At", "Conducted By"])
    for r in records:
        writer.writerow(
            [r["name"], r["roll_no"], r["register_no"], r["email"], r["marked_at"], session["conducted_by_name"]]
        )

    safe_course = session["course_name"].replace(" ", "_")
    filename = f"attendance_{safe_course}_{session['session_date']}.csv"
    return Response(
        output.getvalue(),
        mimetype="text/csv",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )


# ---------- OD (ON-DUTY) MANAGEMENT ----------

@app.route("/od", methods=["GET", "POST"])
def od():
    conn = get_db()
    all_students = conn.execute("SELECT * FROM students ORDER BY name").fetchall()
    all_faculty = conn.execute("SELECT * FROM faculty ORDER BY name").fetchall()

    if request.method == "POST":
        student_id = request.form.get("student_id")
        od_date = request.form.get("od_date")
        reason = request.form.get("reason", "").strip()
        approved_by_id = request.form.get("approved_by_id")

        if not (student_id and od_date and reason and approved_by_id):
            flash("All fields are required to grant an OD.")
        else:
            try:
                conn.execute(
                    "INSERT INTO od_requests (student_id, od_date, reason, approved_by_id, created_at) "
                    "VALUES (?, ?, ?, ?, ?)",
                    (student_id, od_date, reason, approved_by_id, datetime.now().isoformat(timespec="seconds")),
                )
                conn.commit()
                flash("OD granted successfully.")
            except sqlite3.IntegrityError:
                flash("This student already has an OD recorded for that date.")

    od_list = conn.execute(
        """SELECT od_requests.*, students.name AS student_name, students.roll_no,
                  faculty.name AS approved_by_name
           FROM od_requests
           JOIN students ON od_requests.student_id = students.id
           JOIN faculty ON od_requests.approved_by_id = faculty.id
           ORDER BY od_requests.od_date DESC"""
    ).fetchall()
    conn.close()

    return render_template("od.html", students=all_students, faculty_list=all_faculty, od_list=od_list)


# ---------- COURSE-WIDE ATTENDANCE REPORT ----------

@app.route("/courses/<int:course_id>/report")
def report(course_id):
    conn = get_db()
    course = conn.execute(
        """SELECT courses.*, faculty.name AS faculty_name
           FROM courses JOIN faculty ON courses.faculty_id = faculty.id
           WHERE courses.id = ?""",
        (course_id,),
    ).fetchone()
    sessions = conn.execute(
        "SELECT * FROM sessions WHERE course_id = ? ORDER BY session_date", (course_id,)
    ).fetchall()
    all_students = conn.execute("SELECT * FROM students ORDER BY name").fetchall()

    marked = conn.execute(
        """SELECT session_id, student_id FROM attendance
           WHERE session_id IN (SELECT id FROM sessions WHERE course_id = ?)""",
        (course_id,),
    ).fetchall()
    od_rows = conn.execute("SELECT student_id, od_date FROM od_requests").fetchall()
    conn.close()

    if course is None:
        flash("Course not found.")
        return redirect(url_for("home"))

    marked_set = {(m["session_id"], m["student_id"]) for m in marked}
    od_set = {(o["student_id"], o["od_date"]) for o in od_rows}
    total_sessions = len(sessions)

    rows = []
    for s in all_students:
        attended = 0
        statuses = {}
        for sess in sessions:
            if (sess["id"], s["id"]) in marked_set:
                statuses[sess["id"]] = "P"
                attended += 1
            elif (s["id"], sess["session_date"]) in od_set:
                statuses[sess["id"]] = "OD"
                attended += 1  # OD counts toward attendance percentage
            else:
                statuses[sess["id"]] = "A"
        percentage = round((attended / total_sessions) * 100, 1) if total_sessions else 0.0
        rows.append({"student": s, "statuses": statuses, "percentage": percentage})

    return render_template("report.html", course=course, sessions=sessions, rows=rows)


if __name__ == "__main__":
    init_db()
    app.run(host="0.0.0.0", port=5000, debug=True)
