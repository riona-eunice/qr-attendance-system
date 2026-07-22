"""
Automated tests for the department-level QR ID-card attendance system.

Run with:
    python -m unittest test_app.py

These use a temporary throwaway database, so running them never touches
your real attendance.db or any real student/faculty data.
"""

import os
import tempfile
import unittest

import app as attendance_app


class AttendanceAppTests(unittest.TestCase):
    def setUp(self):
        self.db_fd, self.db_path = tempfile.mkstemp()
        attendance_app.DB_NAME = self.db_path
        attendance_app.init_db()
        self.client = attendance_app.app.test_client()

    def tearDown(self):
        os.close(self.db_fd)
        os.unlink(self.db_path)

    # ---------- helpers ----------

    def register_faculty(self, name="Dr. Test Faculty", designation="Assistant Professor",
                          email="faculty@example.com", is_hod=False):
        data = {"name": name, "designation": designation, "email": email}
        if is_hod:
            data["is_hod"] = "on"
        self.client.post("/faculty", data=data)
        conn = attendance_app.get_db()
        f = conn.execute("SELECT * FROM faculty WHERE email = ?", (email,)).fetchone()
        conn.close()
        return f

    def register_student(self, name="Test Student", roll_no="R1", register_no="REG1", email="test@example.com"):
        response = self.client.post(
            "/students",
            data={"name": name, "roll_no": roll_no, "register_no": register_no, "email": email},
            follow_redirects=True,
        )
        conn = attendance_app.get_db()
        s = conn.execute("SELECT * FROM students WHERE roll_no = ?", (roll_no,)).fetchone()
        conn.close()
        return response, s

    def create_course_and_session(self, faculty_id, name="Test Course", code="TC101"):
        self.client.post("/courses", data={"name": name, "code": code, "faculty_id": faculty_id})
        conn = attendance_app.get_db()
        course = conn.execute("SELECT * FROM courses WHERE code = ?", (code,)).fetchone()
        conn.close()

        self.client.post(f"/courses/{course['id']}/start_session", data={"conducted_by_id": faculty_id})
        conn = attendance_app.get_db()
        session = conn.execute(
            "SELECT * FROM sessions WHERE course_id = ?", (course["id"],)
        ).fetchone()
        conn.close()
        return course, session

    # ---------- tests ----------

    def test_home_page_loads(self):
        response = self.client.get("/")
        self.assertEqual(response.status_code, 200)

    def test_register_faculty_and_hod(self):
        f = self.register_faculty(is_hod=True)
        self.assertIsNotNone(f)
        self.assertEqual(f["is_hod"], 1)

    def test_only_one_hod_at_a_time(self):
        self.register_faculty(name="Dr. A", email="a@example.com", is_hod=True)
        self.register_faculty(name="Dr. B", email="b@example.com", is_hod=True)
        conn = attendance_app.get_db()
        hods = conn.execute("SELECT * FROM faculty WHERE is_hod = 1").fetchall()
        conn.close()
        self.assertEqual(len(hods), 1)
        self.assertEqual(hods[0]["name"], "Dr. B")

    def test_register_student(self):
        response, student = self.register_student()
        self.assertEqual(response.status_code, 200)
        self.assertIsNotNone(student)

    def test_duplicate_roll_number_rejected(self):
        self.register_student(roll_no="DUP1", register_no="REGA")
        response, _ = self.register_student(roll_no="DUP1", register_no="REGB")
        self.assertIn(b"already exists", response.data)

    def test_create_course_requires_faculty(self):
        f = self.register_faculty()
        course, session = self.create_course_and_session(f["id"])
        self.assertIsNotNone(course)
        self.assertIsNotNone(session)
        self.assertEqual(session["conducted_by_id"], f["id"])

    def test_mark_attendance_and_prevent_duplicate_scan(self):
        f = self.register_faculty()
        _, student = self.register_student(roll_no="R99", register_no="REG99")
        _, session = self.create_course_and_session(f["id"], name="Course X", code="CX")

        response = self.client.post(
            "/api/mark", json={"session_id": session["id"], "token": student["token"]}
        )
        self.assertEqual(response.get_json()["status"], "marked")

        response = self.client.post(
            "/api/mark", json={"session_id": session["id"], "token": student["token"]}
        )
        self.assertEqual(response.get_json()["status"], "duplicate")

    def test_unknown_qr_code_is_rejected(self):
        f = self.register_faculty()
        _, session = self.create_course_and_session(f["id"], name="Course Y", code="CY")
        response = self.client.post(
            "/api/mark", json={"session_id": session["id"], "token": "does-not-exist"}
        )
        self.assertEqual(response.get_json()["status"], "unknown")

    def test_od_grant_counts_as_attended_in_report(self):
        f = self.register_faculty()
        _, student = self.register_student(roll_no="R50", register_no="REG50")
        course, session = self.create_course_and_session(f["id"], name="Course Z", code="CZ")

        # Grant an OD for this student on the session's date, WITHOUT scanning them in
        self.client.post("/od", data={
            "student_id": student["id"],
            "od_date": session["session_date"],
            "reason": "College symposium",
            "approved_by_id": f["id"],
        })

        response = self.client.get(f"/courses/{course['id']}/report")
        self.assertEqual(response.status_code, 200)
        # The student should show 100% attendance because the OD counts as attended
        self.assertIn(b"100.0%", response.data)

    def test_od_duplicate_for_same_date_rejected(self):
        f = self.register_faculty()
        _, student = self.register_student(roll_no="R51", register_no="REG51")
        self.client.post("/od", data={
            "student_id": student["id"], "od_date": "2026-01-01",
            "reason": "Sports meet", "approved_by_id": f["id"],
        })
        response = self.client.post("/od", data={
            "student_id": student["id"], "od_date": "2026-01-01",
            "reason": "Duplicate attempt", "approved_by_id": f["id"],
        }, follow_redirects=True)
        self.assertIn(b"already has an OD", response.data)


if __name__ == "__main__":
    unittest.main()
