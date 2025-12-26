#!/usr/bin/env python3
import os
import sys
import django

# Setup Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'DjangoProject2.settings')
django.setup()

from django.contrib.auth.models import User
from core.models import Student, Course, UserProfile, Faculty
import json

# Load JSON files
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
students_path = os.path.join(BASE_DIR, 'static', 'json', 'students.json')
instructors_path = os.path.join(BASE_DIR, 'static', 'json', 'instructors.json')

print("=" * 60)
print("Checking PostgreSQL Database Status")
print("=" * 60)

# Check students
print("\n--- Students in Database ---")
db_students = Student.objects.all()
print(f"Total students in DB: {db_students.count()}")
for s in db_students:
    courses = [c.name for c in s.courses.all()]
    print(f"  - {s.username} ({s.student_id}): {s.department}, Year {s.year}, Courses: {courses}")

# Check students in JSON
print("\n--- Students in JSON ---")
with open(students_path, encoding='utf-8') as f:
    students_data = json.load(f)
print(f"Total students in JSON: {len(students_data)}")
for s in students_data:
    print(f"  - {s['username']} ({s.get('student_id', 'N/A')}): {s.get('department', 'N/A')}, Year {s.get('year', 'N/A')}, Courses: {s.get('courses', [])}")

# Check instructors
print("\n--- Instructors in Database ---")
db_instructors = UserProfile.objects.filter(role='instructor')
print(f"Total instructors in DB: {db_instructors.count()}")
for p in db_instructors:
    courses = [c.name for c in p.courses.all()]
    print(f"  - {p.user.username}: {p.department}, Courses: {courses}")

# Check instructors in JSON
print("\n--- Instructors in JSON ---")
with open(instructors_path, encoding='utf-8') as f:
    instructors_data = json.load(f)
print(f"Total instructors in JSON: {len(instructors_data)}")
for i in instructors_data:
    print(f"  - {i['username']}: {i.get('department', 'N/A')}, Courses: {i.get('courses', [])}")

# Check courses
print("\n--- Courses in Database ---")
db_courses = Course.objects.all()
print(f"Total courses in DB: {db_courses.count()}")
for c in db_courses:
    print(f"  - {c.name}: {c.department}, Instructor: {c.instructor.username if c.instructor else 'N/A'}")

# Get all course names from JSON files
all_json_courses = set()
for s in students_data:
    all_json_courses.update(s.get('courses', []))
for i in instructors_data:
    all_json_courses.update(i.get('courses', []))

print(f"\n--- Courses in JSON files ---")
print(f"Total unique courses in JSON: {len(all_json_courses)}")
for course in sorted(all_json_courses):
    print(f"  - {course}")

print("\n" + "=" * 60)
print("Run 'python3 manage.py sync_from_json' to sync data")
print("=" * 60)

