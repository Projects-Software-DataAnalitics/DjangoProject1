import csv
import io
import json

from django.conf import settings
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, render
from django.views.decorators.csrf import csrf_exempt

from .models import Grade, Student


def normalize_course_name(course_name):
    """Normalize course name to standard format"""
    if not course_name:
        return course_name
    
    course_name = course_name.strip()
    
    # Common course name mappings to standardize
    course_mappings = {
        'algorithm': 'Algorithms',
        'algortihm': 'Algorithms',  # Fix typo
        'algortihms': 'Algorithms',
        'web programming': 'Web Programming',
        'webprogramming': 'Web Programming',
        'computer architecture': 'Computer Architecture',
        'computerarchitecture': 'Computer Architecture',
    }
    
    # Check if course name matches any mapping (case-insensitive)
    course_lower = course_name.lower()
    if course_lower in course_mappings:
        return course_mappings[course_lower]
    
    # If not in mappings, capitalize properly (title case)
    # But preserve common abbreviations
    words = course_name.split()
    normalized_words = []
    for word in words:
        if word.lower() in ['web', 'api', 'ai', 'ml']:
            normalized_words.append(word.upper())
        else:
            normalized_words.append(word.capitalize())
    
    return ' '.join(normalized_words)


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

            # Normalize course name to standard format
            course_name = normalize_course_name(course_name)

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
    # Create student if doesn't exist (from JSON login)
    student, created = Student.objects.get_or_create(
        username=username,
        defaults={'student_id': f'{username}_id'}
    )
    grades = Grade.objects.filter(student=student)
    return render(request, 'student.html', {'student': student, 'grades': grades})


@csrf_exempt
def get_student_grades_api(request, username):
    """API endpoint to get student grades as JSON"""
    # Create student if doesn't exist (from JSON login)
    student, created = Student.objects.get_or_create(
        username=username,
        defaults={'student_id': f'{username}_id'}
    )
    grades = Grade.objects.filter(student=student)
    grades_data = [
        {
            'course_name': grade.course_name,
            'midterm': grade.midterm,
            'assignment': grade.assignment,
            'final': grade.final,
        }
        for grade in grades
    ]
    return JsonResponse({'status': 'ok', 'grades': grades_data})


@csrf_exempt
def get_course_students(request, course_name):
    """Get students enrolled in a specific course"""
    try:
        students_json_path = settings.BASE_DIR / 'static' / 'json' / 'students.json'
        with open(students_json_path, 'r', encoding='utf-8') as f:
            all_students = json.load(f)
        
        # Normalize course name for case-insensitive comparison
        course_name_normalized = course_name.strip()
        
        # Filter students by course (case-insensitive)
        course_students = []
        for student in all_students:
            student_courses = student.get('courses', [])
            # Check if course matches (case-insensitive)
            for student_course in student_courses:
                if student_course.strip().lower() == course_name_normalized.lower():
                    course_students.append({
                        'username': student['username'],
                        'firstName': student['firstName'],
                        'lastName': student['lastName'],
                        'student_id': student.get('student_id', f"{student['username']}_id")
                    })
                    break  # Only add student once
        
        return JsonResponse({'status': 'ok', 'students': course_students})
    except Exception as e:
        return JsonResponse({'status': 'error', 'message': str(e)}, status=500)


@csrf_exempt
def save_manual_grades(request):
    """Save manually entered grades"""
    if request.method != 'POST':
        return JsonResponse({'error': 'Only POST allowed'}, status=405)
    
    try:
        data = json.loads(request.body)
        course_name = data.get('course_name')
        grades_list = data.get('grades', [])
        
        if not course_name:
            return JsonResponse({'error': 'Course name required'}, status=400)
        
        if not grades_list:
            return JsonResponse({'error': 'Grades list required'}, status=400)
        
        saved_count = 0
        for grade_data in grades_list:
            username = grade_data.get('student_username')
            midterm = grade_data.get('midterm')
            assignment = grade_data.get('assignment')
            final = grade_data.get('final')
            
            if not username:
                continue
            
            # Validate grades are numbers
            try:
                midterm = float(midterm) if midterm else 0.0
                assignment = float(assignment) if assignment else 0.0
                final = float(final) if final else 0.0
            except (ValueError, TypeError):
                continue
            
            # Get or create student
            student, _ = Student.objects.get_or_create(
                username=username,
                defaults={'student_id': f'{username}_id'}
            )
            
            # Normalize course name
            course_name = normalize_course_name(course_name)
            
            # Update or create grade
            Grade.objects.update_or_create(
                student=student,
                course_name=course_name,
                defaults={
                    'midterm': midterm,
                    'assignment': assignment,
                    'final': final
                }
            )
            saved_count += 1
        
        return JsonResponse({
            'status': 'ok',
            'message': f'Successfully saved {saved_count} grades',
            'saved_count': saved_count
        })
    except json.JSONDecodeError:
        return JsonResponse({'error': 'Invalid JSON'}, status=400)
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)


@csrf_exempt
def get_instructor_grades(request, course_name):
    """Get grades given by instructor for a specific course"""
    try:
        grades = Grade.objects.filter(course_name=course_name)
        grades_data = [
            {
                'student_username': grade.student.username,
                'student_id': grade.student.student_id,
                'midterm': grade.midterm,
                'assignment': grade.assignment,
                'final': grade.final,
            }
            for grade in grades
        ]
        return JsonResponse({'status': 'ok', 'grades': grades_data})
    except Exception as e:
        return JsonResponse({'status': 'error', 'message': str(e)}, status=500)


@csrf_exempt
def get_all_students_courses(request):
    """Get all students with their enrolled courses"""
    try:
        students_json_path = settings.BASE_DIR / 'static' / 'json' / 'students.json'
        with open(students_json_path, 'r', encoding='utf-8') as f:
            all_students = json.load(f)
        
        students_data = [
            {
                'username': student['username'],
                'firstName': student['firstName'],
                'lastName': student['lastName'],
                'student_id': student.get('student_id', f"{student['username']}_id"),
                'department': student.get('department', ''),
                'class': student.get('class', ''),
                'courses': student.get('courses', [])
            }
            for student in all_students
        ]
        
        return JsonResponse({'status': 'ok', 'students': students_data})
    except Exception as e:
        return JsonResponse({'status': 'error', 'message': str(e)}, status=500)


@csrf_exempt
def get_course_enrollment(request):
    """Get all courses with their enrolled students"""
    try:
        students_json_path = settings.BASE_DIR / 'static' / 'json' / 'students.json'
        with open(students_json_path, 'r', encoding='utf-8') as f:
            all_students = json.load(f)
        
        # Create a dictionary to group students by course
        course_enrollment = {}
        
        for student in all_students:
            courses = student.get('courses', [])
            for course in courses:
                # Normalize course name
                normalized_course = normalize_course_name(course)
                
                # Use normalized course name as key (case-insensitive grouping)
                course_key = normalized_course
                for existing_course in course_enrollment.keys():
                    if existing_course.lower() == normalized_course.lower():
                        course_key = existing_course
                        break
                
                if course_key not in course_enrollment:
                    course_enrollment[course_key] = []
                
                course_enrollment[course_key].append({
                    'username': student['username'],
                    'firstName': student['firstName'],
                    'lastName': student['lastName'],
                    'student_id': student.get('student_id', f"{student['username']}_id"),
                    'department': student.get('department', ''),
                    'class': student.get('class', '')
                })
        
        # Convert to list format
        enrollment_data = [
            {
                'course_name': course,
                'student_count': len(students),
                'students': students
            }
            for course, students in course_enrollment.items()
        ]
        
        return JsonResponse({'status': 'ok', 'enrollment': enrollment_data})
    except Exception as e:
        return JsonResponse({'status': 'error', 'message': str(e)}, status=500)