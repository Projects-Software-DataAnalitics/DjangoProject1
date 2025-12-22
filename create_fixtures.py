import json
import os
import sys
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'DjangoProject2.settings')
django.setup()

from django.contrib.auth.models import User
from core.models import Student, Course, UserProfile, Faculty

with open('static/json/students.json', encoding='utf-8') as f:
    students_data = json.load(f)

with open('static/json/instructors.json', encoding='utf-8') as f:
    instructors_data = json.load(f)

with open('static/json/faculty_heads.json', encoding='utf-8') as f:
    faculty_heads_data = json.load(f)

fixtures = []
pk_counter = 1
user_pk_counter = 1
course_pk_counter = 1

faculty, _ = Faculty.objects.get_or_create(
    name='Engineering',
    defaults={'slug': 'engineering'}
)

for student in students_data:
    user_data = {
        'model': 'auth.user',
        'pk': user_pk_counter,
        'fields': {
            'username': student['username'],
            'first_name': student['firstName'],
            'last_name': student['lastName'],
            'password': 'pbkdf2_sha256$600000$dummy$dummy=',
            'is_active': True,
        }
    }
    fixtures.append(user_data)
    
    year_value = student.get('year')
    if isinstance(year_value, str):
        year_value = int(year_value) if year_value.isdigit() else None
    
    student_data = {
        'model': 'core.student',
        'pk': pk_counter,
        'fields': {
            'username': student['username'],
            'student_id': student.get('student_id', student['username']),
            'first_name': student['firstName'],
            'last_name': student['lastName'],
            'department': student['department'],
            'year': year_value,
            'user': user_pk_counter,
        }
    }
    fixtures.append(student_data)
    
    user_pk_counter += 1
    pk_counter += 1

all_courses = {}
for instructor in instructors_data:
    user_data = {
        'model': 'auth.user',
        'pk': user_pk_counter,
        'fields': {
            'username': instructor['username'],
            'first_name': instructor['firstName'],
            'last_name': instructor['lastName'],
            'password': 'pbkdf2_sha256$600000$dummy$dummy=',
            'is_active': True,
        }
    }
    fixtures.append(user_data)
    
    profile_pk = pk_counter
    profile_data = {
        'model': 'core.userprofile',
        'pk': profile_pk,
        'fields': {
            'user': user_pk_counter,
            'role': 'instructor',
            'department': instructor['department'],
            'faculty': faculty.id,
        }
    }
    fixtures.append(profile_data)
    
    for course_name in instructor.get('courses', []):
        if course_name not in all_courses:
            all_courses[course_name] = []
        all_courses[course_name].append(profile_pk)
    
    user_pk_counter += 1
    pk_counter += 1

for faculty_head in faculty_heads_data:
    user_data = {
        'model': 'auth.user',
        'pk': user_pk_counter,
        'fields': {
            'username': faculty_head['username'],
            'first_name': faculty_head['firstName'],
            'last_name': faculty_head['lastName'],
            'password': 'pbkdf2_sha256$600000$dummy$dummy=',
            'is_active': True,
        }
    }
    fixtures.append(user_data)
    
    profile_pk = pk_counter
    profile_data = {
        'model': 'core.userprofile',
        'pk': profile_pk,
        'fields': {
            'user': user_pk_counter,
            'role': 'faculty_head',
            'department': faculty_head['department'],
            'faculty': faculty.id,
        }
    }
    fixtures.append(profile_data)
    
    for course_name in faculty_head.get('courses', []):
        if course_name not in all_courses:
            all_courses[course_name] = []
        all_courses[course_name].append(profile_pk)
    
    user_pk_counter += 1
    pk_counter += 1

default_instructor_user_pk = None
for item in fixtures:
    if item['model'] == 'auth.user' and item['pk'] == 1:
        for inst in instructors_data:
            if inst['username'] == item['fields']['username']:
                default_instructor_user_pk = item['pk']
                break
        if default_instructor_user_pk:
            break

if not default_instructor_user_pk and instructors_data:
    for item in fixtures:
        if item['model'] == 'auth.user':
            for inst in instructors_data:
                if inst['username'] == item['fields']['username']:
                    default_instructor_user_pk = item['pk']
                    break
            if default_instructor_user_pk:
                break

if not default_instructor_user_pk:
    default_instructor_user_pk = 1

for course_name in sorted(all_courses.keys()):
    department = instructors_data[0]['department'] if instructors_data else (
        faculty_heads_data[0]['department'] if faculty_heads_data else ''
    )
    
    course_data = {
        'model': 'core.course',
        'pk': course_pk_counter,
        'fields': {
            'name': course_name,
            'code': '',
            'department': department,
            'instructor': default_instructor_user_pk,
        }
    }
    fixtures.append(course_data)
    
    for profile_pk in all_courses[course_name]:
        for item in fixtures:
            if item['model'] == 'core.userprofile' and item['pk'] == profile_pk:
                if 'courses' not in item['fields']:
                    item['fields']['courses'] = []
                item['fields']['courses'].append(course_pk_counter)
                break
    
    course_pk_counter += 1

os.makedirs('fixtures', exist_ok=True)
with open('fixtures/initial_data.json', 'w', encoding='utf-8') as f:
    json.dump(fixtures, f, indent=2, ensure_ascii=False)

print(f"Created fixtures/initial_data.json with {len(fixtures)} items")

