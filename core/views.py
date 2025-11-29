import csv
import io

from django.http import JsonResponse
from django.shortcuts import get_object_or_404, render
from django.views.decorators.csrf import csrf_exempt

from .models import Grade, Student


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


def faculty_head_dashboard(request):
    return render(request, 'faculty_head.html')


def student_grades(request, username):
    student = get_object_or_404(Student, username=username)
    grades = Grade.objects.filter(student=student)
    return render(request, 'student.html', {'student': student, 'grades': grades})