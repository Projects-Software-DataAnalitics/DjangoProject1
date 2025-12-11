import csv
import io
import json
import os

from django.contrib.auth.models import User
from django.http import JsonResponse, HttpResponseForbidden
from django.shortcuts import get_object_or_404, render, redirect
from django.views.decorators.csrf import csrf_exempt
from django.conf import settings
from .models import Grade, Student, Course, ProgramOutcome


def faculty_head_required(view_func):
    def wrapper(request, *args, **kwargs):
        user = request.user
        if not user.is_authenticated:
            return view_func(request, *args, **kwargs)

        role = getattr(user, "role", None)
        if role is None and hasattr(user, "profile"):
            role = getattr(user.profile, "role", None)

        if role != "faculty_head":
            return HttpResponseForbidden("You are not allowed here")

        return view_func(request, *args, **kwargs)

    return wrapper

@csrf_exempt
def upload_grades(request):
    if request.method != 'POST':
        return JsonResponse({'error': 'Only POST allowed'}, status=405)

    csv_file = request.FILES.get('csv_file')
    if not csv_file:
        return JsonResponse({'error': 'CSV file required'}, status=400)

    try:
        text_file = io.TextIOWrapper(csv_file.file, encoding='utf-8')
        reader = csv.DictReader(text_file)
    except Exception:
        return JsonResponse({'error': 'Invalid CSV file'}, status=400)

    def normalize(name):
        if not name:
            return ''
        return name.strip().lower().lstrip('\ufeff')

    normalized_fields = {normalize(col): col for col in (reader.fieldnames or [])}
    required_columns = {'student_username', 'course_name', 'midterm', 'assignment', 'final'}
    if not reader.fieldnames or not required_columns.issubset(normalized_fields.keys()):
        return JsonResponse(
            {'error': 'CSV must include headers: student_username, course_name, midterm, assignment, final'},
            status=400
        )

    username_source = normalized_fields['student_username']
    course_source = normalized_fields['course_name']
    midterm_source = normalized_fields['midterm']
    assignment_source = normalized_fields['assignment']
    final_source = normalized_fields['final']

    try:
        def parse_score(raw_value, label):
            value = (raw_value or '').strip()
            if value == '':
                raise ValueError(f'{label} must not be empty')
            return float(value)

        for row in reader:
            username = (row[username_source] or '').strip()
            course_name = (row[course_source] or '').strip()
            midterm = parse_score(row[midterm_source], 'midterm')
            assignment = parse_score(row[assignment_source], 'assignment')
            final = parse_score(row[final_source], 'final')

            if not username or not course_name:
                return JsonResponse({'error': 'Username and course_name are required'}, status=400)

            student = Student.objects.filter(username=username).first()
            if not student:
                return JsonResponse({'error': f'Student not found: {username}'}, status=400)

            course = Course.objects.filter(name=course_name).first()
            if not course:
                return JsonResponse({'error': f'Course not found: {course_name}'}, status=400)

            Grade.objects.update_or_create(
                student=student,
                course=course,
                defaults={'midterm': midterm, 'assignment': assignment, 'final': final}
            )
    except (KeyError, ValueError) as exc:
        return JsonResponse({'error': f'CSV hatası: {exc}'}, status=400)

    return JsonResponse({'status': 'ok'})


def index(request):
    return render(request, 'index.html')


def student_login(request):
    return render(request, 'student_login.html')


def instructor_login(request):
    return render(request, 'instructor_login.html')


def faculty_head_login(request):
    return render(request, 'faculty_head_login.html')


def student_dashboard(request):
    return render(request, 'student.html', {'grades': None})


def instructor_dashboard(request):
    return render(request, 'instructor.html')


@faculty_head_required
def faculty_head_dashboard(request):
    return render(request, 'faculty_head.html')


def student_grades(request, username):
    student = get_object_or_404(Student, username=username)
    grades_qs = Grade.objects.filter(student=student).select_related('course')

    courses_with_grades = []
    students_json_path = os.path.join(settings.BASE_DIR, 'static', 'json', 'students.json')
    try:
        with open(students_json_path, encoding='utf-8') as f:
            students_data = json.load(f)
    except (OSError, json.JSONDecodeError):
        students_data = []

    user_courses = []
    for entry in students_data:
        if entry.get('username') == username:
            user_courses = entry.get('courses', []) or []
            break

    for course_name in user_courses:
        grade_obj = next((g for g in grades_qs if g.course.name == course_name), None)
        courses_with_grades.append({
            'course_name': course_name,
            'midterm': grade_obj.midterm if grade_obj else None,
            'assignment': grade_obj.assignment if grade_obj else None,
            'final': grade_obj.final if grade_obj else None,
        })

    return render(
        request,
        'student.html',
        {
            'student': student,
            'grades': grades_qs,
            'courses_with_grades': courses_with_grades,
        }
    )

@faculty_head_required
def all_courses(request):
    return render(request, 'faculty/all_courses.html')

@faculty_head_required
def my_courses(request):
    return render(request, 'faculty/my_courses.html')

@faculty_head_required
def program_outcomes(request):
    outcomes_qs = ProgramOutcome.objects.select_related('created_by').order_by('-created_at')
    outcomes_data = []
    for o in outcomes_qs:
        creator_name = o.created_by.get_full_name() or o.created_by.username
        outcomes_data.append(
            {
                'text': o.text,
                'course': o.course_name or '',
                'created_by': creator_name,
                'created_at': o.created_at.strftime('%Y-%m-%d %H:%M'),
            }
        )
    return render(
        request,
        'faculty/program_outcomes.html',
        {
            'outcomes_data': outcomes_data,
        }
    )

@faculty_head_required
def create_program_outcome(request):
    if request.method == 'POST':
        text = (request.POST.get('text') or '').strip()
        course_name = (request.POST.get('course_name') or '').strip()
        creator = request.user if request.user.is_authenticated else None
        if creator is None:
            username = (request.POST.get('creator_username') or '').strip()
            first_name = (request.POST.get('creator_first_name') or '').strip()
            last_name = (request.POST.get('creator_last_name') or '').strip()

            if username:
                creator, created = User.objects.get_or_create(
                    username=username,
                    defaults={'first_name': first_name, 'last_name': last_name}
                )
                if created:
                    creator.set_unusable_password()
                    creator.save()

        if not creator:
            return HttpResponseForbidden("Login required to create program outcomes.")

        if not text or not course_name:
            return render(
                request,
                'faculty/create_outcome.html',
                {
                    'error': 'Outcome text and course are required.',
                    'course_name': course_name,
                }
            )

        ProgramOutcome.objects.create(text=text, course_name=course_name, created_by=creator)
        return redirect('program_outcomes')

    return render(request, 'faculty/create_outcome.html', {'course_name': request.GET.get('course', '')})

@faculty_head_required
def give_grade(request, course_id):
    course = get_object_or_404(Course, id=course_id)
    return render(request, 'faculty/give_grade.html', {'course': course})
