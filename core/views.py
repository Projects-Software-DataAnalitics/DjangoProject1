import csv
import io

from django.contrib.auth.models import User
from django.http import JsonResponse, HttpResponseForbidden
from django.shortcuts import get_object_or_404, render, redirect
from django.views.decorators.csrf import csrf_exempt
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
        for row in reader:
            username = row[username_source].strip()
            course_name = row[course_source].strip()
            midterm = float(row[midterm_source])
            assignment = float(row[assignment_source])
            final = float(row[final_source])

            if not username or not course_name:
                return JsonResponse({'error': 'Username and course name required'}, status=400)

            student, _ = Student.objects.get_or_create(
                username=username,
                defaults={'student_id': f'{username}_id'}
            )

            Grade.objects.update_or_create(
                student=student,
                course_name=course_name,
                defaults={'midterm': midterm, 'assignment': assignment, 'final': final}
            )
    except (KeyError, ValueError):
        return JsonResponse({'error': 'Invalid data in CSV'}, status=400)

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
    grades = Grade.objects.filter(student=student)
    return render(request, 'student.html', {'student': student, 'grades': grades})

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
