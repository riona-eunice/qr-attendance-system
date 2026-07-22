# 📋 Panimalar Engineering College — AI & ML Department Attendance System

A full department-level attendance management system built for the **Department of Artificial
Intelligence and Machine Learning, Panimalar Engineering College**. Replaces manual roll-call with
live camera QR scanning of student ID cards, tracks which faculty conducted each class, and
handles official On-Duty (OD) exemptions — all with anti-proxy safeguards built in.

Built with **Python (Flask)**, **SQLite**, and **html5-qrcode** for real-time browser-based camera scanning.

---

## ✨ Features

- 🏫 **College & department branding** on every page, with the current HOD shown automatically
- 🧑‍🏫 **Faculty management** — register faculty with designation, email, and HOD status (only one HOD at a time, enforced automatically)
- 🎓 **Student registration** — name, roll number, register number, email, each with a permanent QR ID card
- 📚 **Course management** — every course has a named **Faculty In-Charge**
- 📷 **Live camera scanning** — hold an ID card up to a webcam/phone camera, attendance is marked instantly, and the system records **which faculty conducted that specific session** (supports substitute faculty)
- 📝 **OD (On-Duty) management** — faculty can pre-approve a student's official absence (symposium, sports, etc.); this is the *only* way to be marked present without a live scan
- 🚫 **Anti-proxy design**:
  - Attendance can only be marked by a physical camera scan of a real ID card during a live session — no manual typing, no shared codes
  - The database itself blocks a student being scanned twice in one session (`UNIQUE` constraint)
  - OD can only be granted by a registered faculty member, never by a student
- 📊 **Live dashboard** — see who's present (scanned) and who's on OD today, with auto-refresh
- ⬇️ **CSV export** — every session's attendance sheet, including which faculty conducted it
- 📈 **Attendance reports** — a full per-student, per-session grid showing ✅ Present / 🟡 OD / ❌ Absent and an attendance percentage
- ✅ **10 automated tests** covering registration, duplicate prevention, HOD uniqueness, and OD logic

---

## 🧰 Tech Stack

| Layer | Technology |
|---|---|
| Backend | Python 3, Flask |
| Database | SQLite |
| QR generation | `qrcode` (Python) |
| QR scanning | `html5-qrcode` (JavaScript, browser camera API) |
| Frontend | Server-rendered HTML/CSS + vanilla JS |
| Testing | Python `unittest` |

---

## 🗂 Project Structure

```
qr-attendance-v3/
├── app.py                      # All routes, database logic, and branding config
├── test_app.py                  # 10 automated tests
├── requirements.txt              # Pinned Python dependencies
├── LICENSE                       # MIT License
├── .gitignore
├── README.md
└── templates/
    ├── base.html                  # Shared layout, college/department header, nav
    ├── home.html                   # Lists all courses with faculty in-charge
    ├── faculty.html                 # Register + list faculty, HOD flag
    ├── students.html                # Register + list students
    ├── student_card.html            # A student's printable QR ID card
    ├── courses.html                  # Add a course (choose faculty in-charge)
    ├── course_detail.html            # Session history + "start session" (choose conducting faculty)
    ├── scan.html                      # Live camera scanning page
    ├── dashboard.html                  # Live attendance + OD-today list + CSV export
    └── report.html                     # Present/OD/Absent grid + attendance %
```

---

## 🗃 Database Schema

```sql
faculty(id, name, designation, email, is_hod, created_at)
students(id, name, roll_no, register_no, email, token, created_at)
courses(id, name, code, faculty_id, created_at)                      -- faculty_id = in-charge
sessions(id, course_id, session_date, conducted_by_id, created_at)   -- one row per class held
attendance(id, session_id, student_id, marked_at)                    -- one row per scanned check-in
od_requests(id, student_id, od_date, reason, approved_by_id, created_at)
```

**Design notes:**
- `students.token` is a random, permanent unique string encoded in the student's QR ID card — it never changes, so one card works for every class, forever.
- `UNIQUE(session_id, student_id)` on `attendance` means the database itself guarantees no student can be marked present twice in one session.
- `UNIQUE(student_id, od_date)` on `od_requests` prevents duplicate OD entries for the same day.
- `sessions.conducted_by_id` is separate from `courses.faculty_id` so a substitute faculty member taking a class is still accurately recorded.

---

## 🚀 Getting Started

### 1. Prerequisites
Python 3.9 or later.

### 2. Clone and set up

```bash
git clone https://github.com/your-username/panimalar-aiml-attendance.git
cd panimalar-aiml-attendance

python -m venv venv
venv\Scripts\activate        # Windows
# source venv/bin/activate   # Mac/Linux

pip install -r requirements.txt
```

### 3. Run it

```bash
python app.py
```

Open **http://localhost:5000**.

> **Camera note:** browsers only allow camera access on `localhost` or over HTTPS. For a demo, run
> the scanner in your laptop's own browser at `localhost` and hold ID cards up to your webcam. For
> scanning from a separate device over your network, use [ngrok](https://ngrok.com) for an HTTPS
> tunnel, or deploy to a host with automatic HTTPS (Render, Railway, PythonAnywhere).

### 4. Run the tests

```bash
python -m unittest test_app.py -v
```

All 10 tests should pass, using a temporary throwaway database.

---

## 🧑‍🏫 Usage Walkthrough

1. **Faculty** → register your department's faculty, mark the HOD
2. **Add Course** → create a course, assign a Faculty In-Charge
3. **Students** → register each student → open their **ID Card** and print/screenshot the QR code
4. Open the course → **Start Today's Session** (choose which faculty is conducting, defaults to the in-charge)
5. Allow camera access → hold up each student's ID card → green confirmation appears instantly
6. **OD Management** → any faculty member can pre-approve a student's official absence for a specific date
7. **Dashboard** → live list of who's present + who's on OD today, with CSV export
8. **Report** (from the course page) → full-term Present/OD/Absent grid with attendance %

---

## 🔒 How Proxy Attendance Is Prevented

This was a core design goal, not an afterthought:

1. **No manual entry** — the only way to be marked present is a live camera reading a real ID
   card's QR code during an active session.
2. **No shared/reusable session code** — unlike a single QR code that could be photographed and
   passed around, each student's ID is personal and the scan happens on the faculty's device.
3. **OD is faculty-gated** — the only legitimate way to be marked present without scanning is an
   OD explicitly granted by a registered faculty member, tied to their name, and visible in every
   report. A student cannot self-grant or fake this.
4. **Full audit trail** — every attendance record stores exactly who conducted the session, and
   every OD stores exactly who approved it, and when.

---

## 🔭 Possible Future Extensions

*(Not required — the project is fully functional as-is.)*

- Faculty login system so each faculty only manages their own courses
- Student photo on the ID card for visual verification during scanning
- Automatic session expiry after the class period ends
- Bulk student import via CSV upload
- Automated low-attendance email alerts to students and HOD
- Attendance trend charts (e.g. with Chart.js)

---

## 📄 License

Licensed under the [MIT License](LICENSE).

---

## 🙋 Author

Built by Riona Eunice J, Department of Artificial Intelligence and Machine Learning,
Panimalar Engineering College.
