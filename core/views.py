import csv
import io
import json
import os

from django.contrib.auth.models import User
from django.contrib.auth import authenticate, login as auth_login, logout, get_user_model
from django.http import JsonResponse, HttpResponseForbidden
from django.shortcuts import get_object_or_404, render, redirect
from django.views.decorators.csrf import csrf_exempt
from django.conf import settings
from django.db import transaction
from django.db.models import Q
from django.core.cache import cache
from .models import Grade, Student, Course, ProgramOutcome, Assessment, UserProfile

User = get_user_model()


def get_instructors_map():
    cache_key = 'instructors_map_db'
    cached_map = cache.get(cache_key)
    if cached_map is not None:
        return cached_map
    
    instructors = User.objects.filter(profile__role='instructor').select_related('profile')
    instructors_map = {}
    for user in instructors:
        full_name = (user.first_name + ' ' + user.last_name).strip()
        if full_name:
            instructors_map[user.username] = full_name
        else:
            instructors_map[user.username] = user.username
    
    # Cache'e kaydet (1 saat)
    cache.set(cache_key, instructors_map, 3600)
    return instructors_map


def get_faculty_heads_map():
    """Faculty heads veritabanından username -> full_name mapping'i döndür (cache'li)"""
    cache_key = 'faculty_heads_map_db'
    cached_map = cache.get(cache_key)
    if cached_map is not None:
        return cached_map
    
    faculty_heads = User.objects.filter(profile__role='faculty_head').select_related('profile')
    faculty_heads_map = {}
    for user in faculty_heads:
        full_name = (user.first_name + ' ' + user.last_name).strip()
        if full_name:
            faculty_heads_map[user.username] = full_name
        else:
            faculty_heads_map[user.username] = user.username
    
    # Cache'e kaydet (1 saat)
    cache.set(cache_key, faculty_heads_map, 3600)
    return faculty_heads_map


def get_faculty_head_data(username):
    """Belirli bir faculty head'in veritabanı verisini döndür (cache'li)"""
    cache_key = f'faculty_head_data_{username}'
    cached_data = cache.get(cache_key)
    if cached_data is not None:
        return cached_data
    
    try:
        user = User.objects.select_related('profile', 'profile__faculty').get(
            username=username, 
            profile__role='faculty_head'
        )
        profile = user.profile
        
        # Courses bilgisini al
        courses = [course.name for course in profile.courses.all()]
        
        data = {
            'username': user.username,
            'firstName': user.first_name,
            'lastName': user.last_name,
            'department': profile.department or '',
            'faculty': profile.faculty.name if profile.faculty else '',
            'courses': courses,
        }
        
        # Cache'e kaydet (1 saat)
        cache.set(cache_key, data, 3600)
        return data
    except User.DoesNotExist:
        return {}


def get_students_data():
    """Students veritabanı verisini döndür (cache'li)"""
    cache_key = 'students_data_db'
    cached_data = cache.get(cache_key)
    if cached_data is not None:
        return cached_data
    
    students = Student.objects.select_related('user').prefetch_related('courses')
    students_list = []
    for student in students:
        courses = [course.name for course in student.courses.all()]
        students_list.append({
            'username': student.username,
            'firstName': student.first_name or (student.user.first_name if student.user else ''),
            'lastName': student.last_name or (student.user.last_name if student.user else ''),
            'department': student.department or '',
            'year': student.year,
            'courses': courses,
        })
    
    # Cache'e kaydet (1 saat)
    cache.set(cache_key, students_list, 3600)
    return students_list


def get_instructor_data(username):
    """Belirli bir instructor'ın veritabanı verisini döndür (cache'li)"""
    cache_key = f'instructor_data_{username}'
    cached_data = cache.get(cache_key)
    if cached_data is not None:
        return cached_data
    
    try:
        user = User.objects.select_related('profile', 'profile__faculty').prefetch_related('profile__courses').get(
            username=username,
            profile__role='instructor'
        )
        profile = user.profile
        
        # Courses bilgisini al (hem Course modelinden hem de UserProfile'dan)
        courses_from_profile = [course.name for course in profile.courses.all()]
        courses_from_instructor = [course.name for course in user.instructor_courses.all()]
        all_courses = list(set(courses_from_profile + courses_from_instructor))
        
        data = {
            'username': user.username,
            'firstName': user.first_name,
            'lastName': user.last_name,
            'department': profile.department or '',
            'faculty': profile.faculty.name if profile.faculty else '',
            'courses': all_courses,
        }
        
        # Cache'e kaydet (1 saat)
        cache.set(cache_key, data, 3600)
        return data
    except User.DoesNotExist:
        return {}


def faculty_head_required(view_func):
    def wrapper(request, *args, **kwargs):
        if not request.user.is_authenticated:
            from django.shortcuts import redirect
            return redirect('faculty-head-login')
        
        user = request.user
        
        role = getattr(user, "role", None)
        if role is None:
            profile = getattr(user, "profile", None)
            if profile:
                role = getattr(profile, "role", None)

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
        with transaction.atomic():
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
    if request.method == 'POST':
        username = request.POST.get('username', '').strip()
        password = request.POST.get('password', '').strip()
        
        user = authenticate(request, username=username, password=password)
        if user:
            try:
                student = Student.objects.get(user=user)
                auth_login(request, user)
                return JsonResponse({'status': 'success', 'username': username})
            except Student.DoesNotExist:
                return JsonResponse({'status': 'error', 'message': 'User is not a student'}, status=403)
        else:
            return JsonResponse({'status': 'error', 'message': 'Invalid username or password'}, status=401)
    
    return render(request, 'student_login.html')


@csrf_exempt
def instructor_login(request):
    if request.method == 'POST':
        try:
            username = request.POST.get('username', '').strip()
            password = request.POST.get('password', '').strip()
            
            if not username or not password:
                return JsonResponse({'status': 'error', 'message': 'Username and password are required'}, status=400)
            
            user = authenticate(request, username=username, password=password)
            
            if user:
                try:
                    profile = user.profile
                    if profile.role == 'instructor':
                        auth_login(request, user)
                        return JsonResponse({'status': 'success', 'username': username})
                    else:
                        return JsonResponse({'status': 'error', 'message': 'User is not an instructor'}, status=403)
                except AttributeError:
                    return JsonResponse({'status': 'error', 'message': 'User profile not found'}, status=403)
            else:
                try:
                    User.objects.get(username=username)
                    return JsonResponse({'status': 'error', 'message': 'Invalid password'}, status=401)
                except User.DoesNotExist:
                    return JsonResponse({'status': 'error', 'message': 'Invalid username or password'}, status=401)
        except Exception as e:
            import logging
            import traceback
            logger = logging.getLogger(__name__)
            logger.error(f'Instructor login error: {str(e)}\n{traceback.format_exc()}')
            return JsonResponse({'status': 'error', 'message': 'An error occurred during login. Please try again.'}, status=500)
    
    return render(request, 'instructor_login.html')


@csrf_exempt
def faculty_head_login(request):
    if request.method == 'POST':
        username = request.POST.get('username', '').strip()
        password = request.POST.get('password', '').strip()
        
        user = authenticate(request, username=username, password=password)
        if user:
            try:
                profile = user.profile
                if profile.role == 'faculty_head':
                    auth_login(request, user)
                    return redirect('faculty-head')
                else:
                    return render(request, 'faculty_head_login.html', {
                        'error': 'User is not a faculty head.'
                    })
            except AttributeError:
                return render(request, 'faculty_head_login.html', {
                    'error': 'User profile not found.'
                })
        else:
            return render(request, 'faculty_head_login.html', {
                'error': 'Invalid username or password.'
            })
    
    
    return render(request, 'faculty_head_login.html')


def student_dashboard(request):
    if not request.user.is_authenticated:
        return redirect('student-login')
    
    from datetime import datetime
    from .models import Announcement
    from django.db.models import Q
    
    try:
        student = Student.objects.get(user=request.user)
        student_info = {
            'username': student.username,
            'name': f"{student.first_name} {student.last_name}".strip() or student.username,
            'student_id': student.student_id,
        }
        
        current_month = datetime.now().month
        current_year = datetime.now().year
        
        if current_month >= 9:
            academic_term = f"{current_year}-{current_year + 1} Fall"
        elif current_month >= 2:
            academic_term = f"{current_year - 1}-{current_year} Spring"
        else:
            academic_term = f"{current_year - 1}-{current_year} Fall"
        
        year_display = f"{student.year}. Year" if student.year else "-"
        department_display = student.department or "-"
        
        advisor_name = "Prof. Dr. Ahmet Bulut"
        
        courses = student.courses.all().select_related('instructor')
        courses_list = []
        for course in courses:
            courses_list.append({
                'name': course.name,
                'code': course.code,
                'credits': course.credits,
            })
        
    except Student.DoesNotExist:
        student_info = {
            'username': request.user.username,
            'name': request.user.get_full_name() or request.user.username,
            'student_id': '-',
        }
        academic_term = "-"
        year_display = "-"
        department_display = "-"
        advisor_name = "-"
        courses_list = []
    
    latest_announcements = Announcement.objects.filter(
        Q(receiver=request.user) | Q(receiver__isnull=True)
    ).select_related('sender').order_by('-created_at')[:5]
    
    announcements_list = []
    for ann in latest_announcements:
        sender_name = ann.sender.get_full_name() or ann.sender.username
        announcements_list.append({
            'id': ann.id,
            'subject': ann.subject,
            'sender': sender_name,
            'created_at': ann.created_at.strftime('%Y-%m-%d %H:%M'),
        })
    
    return render(request, 'student.html', {
        'student_info': student_info,
        'latest_announcements': announcements_list,
        'academic_term': academic_term,
        'year_display': year_display,
        'department_display': department_display,
        'advisor_name': advisor_name,
        'courses_list': courses_list,
    })


def instructor_required(view_func):
    """Decorator to check if user is authenticated and is an instructor"""
    def wrapper(request, *args, **kwargs):
        if not request.user.is_authenticated:
            from django.shortcuts import redirect
            return redirect('instructor-login')
        
        try:
            profile = request.user.profile
            if profile.role != 'instructor':
                from django.http import HttpResponseForbidden
                return HttpResponseForbidden("You are not allowed here")
        except AttributeError:
            from django.http import HttpResponseForbidden
            return HttpResponseForbidden("User profile not found")
        
        request.instructor_user = request.user
        return view_func(request, *args, **kwargs)
    return wrapper


@instructor_required
def instructor_dashboard(request):
    from datetime import datetime
    from .models import Announcement
    from django.db.models import Q
    
    instructor_user = request.instructor_user
    profile = getattr(instructor_user, 'profile', None)
    
    instructor_info = {
        'username': instructor_user.username,
        'name': f"{instructor_user.first_name} {instructor_user.last_name}".strip() or instructor_user.username,
        'faculty': profile.faculty.name if profile and profile.faculty else '-',
        'department': profile.department if profile else '-',
    }
    
    current_month = datetime.now().month
    current_year = datetime.now().year
    
    if current_month >= 9:
        academic_term = f"{current_year}-{current_year + 1} Fall"
    elif current_month >= 2:
        academic_term = f"{current_year - 1}-{current_year} Spring"
    else:
        academic_term = f"{current_year - 1}-{current_year} Fall"
    
    courses_list = []
    total_students_set = set()
    chart_data = {'labels': [], 'data': []}
    
    if profile:
        courses = profile.courses.all().select_related('instructor').prefetch_related('students')
        for course in courses:
            students = course.students.all()
            student_count = students.count()
            
            for student in students:
                total_students_set.add(student.id)
            
            courses_list.append({
                'id': course.id,
                'name': course.name,
                'code': course.code,
                'credits': course.credits,
                'student_count': student_count,
            })
            
            chart_data['labels'].append(course.name)
            chart_data['data'].append(student_count)
    
    total_courses = len(courses_list)
    total_students = len(total_students_set)
    
    latest_announcements = Announcement.objects.filter(
        Q(sender=instructor_user) | Q(receiver=instructor_user) | Q(receiver__isnull=True)
    ).select_related('sender', 'receiver').order_by('-created_at')[:5]
    
    announcements_list = []
    for ann in latest_announcements:
        sender_name = ann.sender.get_full_name() or ann.sender.username
        announcements_list.append({
            'id': ann.id,
            'subject': ann.subject,
            'sender': sender_name,
            'created_at': ann.created_at.strftime('%Y-%m-%d %H:%M'),
        })
    
    chart_data_json = json.dumps(chart_data)
    
    return render(request, 'instructor_main.html', {
        'instructor_info': instructor_info,
        'academic_term': academic_term,
        'courses_list': courses_list,
        'total_courses': total_courses,
        'total_students': total_students,
        'chart_data': chart_data,
        'chart_data_json': chart_data_json,
        'latest_announcements': announcements_list,
    })

@instructor_required
def instructor_profile(request):
    instructor_user = request.instructor_user
    profile = getattr(instructor_user, 'profile', None)
    
    courses = []
    if profile:
        courses = [course.name for course in profile.courses.all()]
    
    profile_data = {
        'name': f"{instructor_user.first_name} {instructor_user.last_name}".strip() or instructor_user.username,
        'username': instructor_user.username,
        'faculty': profile.faculty.name if profile and profile.faculty else '-',
        'department': profile.department if profile else '-',
        'courses': courses,
    }
    
    return render(request, 'instructor.html', {
        'show_welcome': False,
        'page': 'profile',
        'profile': profile_data
    })

@instructor_required
@instructor_required
def instructor_my_courses(request):
    instructor_user = request.instructor_user
    profile = getattr(instructor_user, 'profile', None)
    
    courses_data = []
    if profile:
        courses = profile.courses.all().select_related('instructor').prefetch_related('students')
        for course in courses:
            instructor_name = f"{course.instructor.first_name} {course.instructor.last_name}".strip() or course.instructor.username
            
            # Get students enrolled in this course
            students = course.students.all().order_by('first_name', 'last_name', 'username')
            students_list = []
            for student in students:
                full_name = f"{student.first_name} {student.last_name}".strip() if student.first_name or student.last_name else ''
                if not full_name and student.user:
                    full_name = f"{student.user.first_name} {student.user.last_name}".strip()
                name = full_name if full_name else student.username
                students_list.append({
                    'name': name,
                    'student_id': student.student_id or '-',
                    'year': student.year or '-',
                })
            
            courses_data.append({
                'id': course.id,
                'name': course.name,
                'code': course.code,
                'instructor': instructor_name,
                'department': course.department,
                'credits': course.credits,
                'students': students_list,
                'students_json': json.dumps(students_list),
            })
    
    # Prepare JSON data for template
    courses_json = json.dumps([{
        'id': course['id'],
        'name': course['name'],
        'students': course['students']
    } for course in courses_data])
    
    return render(request, 'instructor.html', {
        'show_welcome': False,
        'page': 'my_courses',
        'courses': courses_data,
        'courses_json': courses_json
    })

@instructor_required
def instructor_grades(request):
    instructor_user = request.instructor_user
    profile = getattr(instructor_user, 'profile', None)
    
    courses = []
    if profile:
        courses = [course.name for course in profile.courses.all()]
    
    return render(request, 'instructor.html', {
        'show_welcome': False,
        'page': 'grades',
        'instructor_courses': courses
    })

@instructor_required
def instructor_course_grades(request, course_name):
    from .models import Assessment
    
    instructor_user = request.instructor_user
    profile = getattr(instructor_user, 'profile', None)
    try:
        course = Course.objects.get(name=course_name)
    except Course.DoesNotExist:
        return redirect('instructor_grades')
    
    if profile and course not in profile.courses.all():
        return HttpResponseForbidden("You don't have access to this course")
    
    # Assessment'ı al veya oluştur (default değerlerle)
    assessment, created = Assessment.objects.get_or_create(
        course=course,
        defaults={
            'midterm': 2,
            'final': 1,
            'proje': 0,
            'homework': 0,
            'absence': 0,
            'quiz': 0,
            'assessment_count': 3,
            'midterm_percentage': 60,
            'final_percentage': 40,
            'proje_percentage': 0,
            'homework_percentage': 0,
            'absence_percentage': 0,
            'quiz_percentage': 0
        }
    )
    
    # Get students enrolled in this course
    students = course.students.all().order_by('first_name', 'last_name', 'username')
    students_list = [{'id': student.id, 'student_id': student.student_id, 'name': f"{student.first_name} {student.last_name}".strip() or student.username} for student in students]
    
    # Get uploaded file info for each assessment (from first student as sample)
    uploaded_files_info = {}
    sample_grade = Grade.objects.filter(course=course).first()
    if sample_grade and sample_grade.assessment_scores:
        assessment_types = ['midterm', 'final', 'proje', 'homework', 'absence', 'quiz']
        for assessment_type in assessment_types:
            count = getattr(assessment, assessment_type, 0)
            for i in range(1, count + 1):
                key = f'{assessment_type}_{i}'
                file_name, uploaded_at = sample_grade.get_uploaded_file_info(key)
                if file_name:
                    uploaded_files_info[key] = {
                        'file_name': file_name,
                        'uploaded_at': uploaded_at
                    }
    
    # Prepare grades data for the grades list table
    grades_data = []
    assessment_columns = []  # List of assessment column names (e.g., ["Midterm 1", "Midterm 2", "Final"])
    
    # Build assessment columns based on assessment counts
    assessment_type_labels = {
        'midterm': 'Midterm',
        'final': 'Final',
        'proje': 'Proje',
        'homework': 'Homework',
        'absence': 'Absence',
        'quiz': 'Quiz'
    }
    
    for assessment_type in ['midterm', 'final', 'proje', 'homework', 'absence', 'quiz']:
        count = getattr(assessment, assessment_type, 0)
        label = assessment_type_labels[assessment_type]
        for i in range(1, count + 1):
            assessment_columns.append({
                'key': f'{assessment_type}_{i}',
                'label': f'{label} {i}',
                'type': assessment_type
            })
    
    # Get grades for all students
    for student in students:
        grade_obj = Grade.objects.filter(student=student, course=course).first()
        student_data = {
            'student_id': student.student_id,
            'full_name': f"{student.first_name} {student.last_name}".strip() or student.username,
            'grades': {}
        }
        
        if grade_obj:
            # Get individual scores for each assessment column
            for col in assessment_columns:
                score = grade_obj.get_individual_score(col['key'])
                if score is not None:
                    student_data['grades'][col['key']] = score
                else:
                    # If individual score doesn't exist, check if average is available
                    # But for table display, we show individual scores only
                    student_data['grades'][col['key']] = None
        
        grades_data.append(student_data)
    
    # Get last changes timestamp (from any grade in this course)
    last_changes_at = None
    any_grade = Grade.objects.filter(course=course).exclude(last_changes_at__isnull=True).order_by('-last_changes_at').first()
    if any_grade and any_grade.last_changes_at:
        last_changes_at = any_grade.last_changes_at.isoformat()
    
    return render(request, 'instructor/course_grades.html', {
        'course': course,
        'assessment': assessment,
        'students_json': json.dumps(students_list),
        'uploaded_files_info': json.dumps(uploaded_files_info),
        'grades_data': json.dumps(grades_data),
        'assessment_columns': json.dumps(assessment_columns),
        'last_changes_at': last_changes_at,
    })

@instructor_required
@csrf_exempt
def upload_assessment_grades(request, course_name, assessment_type, assessment_index):
    """
    Upload grades for a specific assessment file (e.g., midterm_1, midterm_2)
    CSV format: student_id, score (single column for scores)
    Only calculates average when ALL files for that assessment type are uploaded
    """
    if request.method != 'POST':
        return JsonResponse({'error': 'Only POST allowed'}, status=405)
    
    # Valid assessment types
    valid_types = ['midterm', 'final', 'proje', 'homework', 'absence', 'quiz']
    if assessment_type not in valid_types:
        return JsonResponse({'error': f'Invalid assessment type. Must be one of: {", ".join(valid_types)}'}, status=400)
    
    try:
        assessment_index = int(assessment_index)
        if assessment_index < 1:
            return JsonResponse({'error': 'Assessment index must be >= 1'}, status=400)
    except ValueError:
        return JsonResponse({'error': 'Invalid assessment index'}, status=400)
    
    instructor_user = request.instructor_user
    profile = getattr(instructor_user, 'profile', None)
    
    try:
        course = Course.objects.get(name=course_name)
    except Course.DoesNotExist:
        return JsonResponse({'error': 'Course not found'}, status=404)
    
    if profile and course not in profile.courses.all():
        return JsonResponse({'error': 'Access denied'}, status=403)
    
    # Get assessment for this course
    try:
        assessment = Assessment.objects.get(course=course)
    except Assessment.DoesNotExist:
        return JsonResponse({'error': 'Assessment not found for this course. Please configure assessment first.'}, status=404)
    
    # Get the count for this assessment type
    assessment_count = getattr(assessment, assessment_type, 0)
    if assessment_count == 0:
        return JsonResponse({'error': f'No {assessment_type} assessments configured for this course'}, status=400)
    
    if assessment_index > assessment_count:
        return JsonResponse({'error': f'Assessment index {assessment_index} exceeds configured count of {assessment_count}'}, status=400)
    
    csv_file = request.FILES.get('csv_file')
    if not csv_file:
        return JsonResponse({'error': 'CSV file required'}, status=400)
    
    # Read CSV file into memory for validation
    try:
        csv_file.file.seek(0)  # Reset file pointer
        text_file = io.TextIOWrapper(csv_file.file, encoding='utf-8')
        csv_content = text_file.read()
        csv_file.file.seek(0)  # Reset again for processing
        text_file = io.TextIOWrapper(csv_file.file, encoding='utf-8')
        reader = csv.DictReader(text_file)
    except Exception as e:
        return JsonResponse({'error': f'Invalid CSV file: {str(e)}'}, status=400)
    
    def normalize(name):
        if not name:
            return ''
        return name.strip().lower().lstrip('\ufeff')
    
    # Expected columns: student_id, score
    normalized_fields = {normalize(col): col for col in (reader.fieldnames or [])}
    
    # Check for student_id
    if 'student_id' not in normalized_fields:
        return JsonResponse({'error': 'CSV must include "student_id" column'}, status=400)
    
    # Check for score column (can be named 'score' or assessment_type_index)
    score_column = None
    possible_score_names = ['score', f'{assessment_type}_{assessment_index}', f'{assessment_type}{assessment_index}']
    for name in possible_score_names:
        if normalize(name) in normalized_fields:
            score_column = normalized_fields[normalize(name)]
            break
    
    if not score_column:
        return JsonResponse({'error': f'CSV must include a score column (named: score, {assessment_type}_{assessment_index}, or {assessment_type}{assessment_index})'}, status=400)
    
    student_id_source = normalized_fields['student_id']
    assessment_key = f'{assessment_type}_{assessment_index}'
    
    # First pass: Validate all scores (0-100 range) before processing
    validation_errors = []
    csv_file.file.seek(0)  # Reset file pointer
    text_file = io.TextIOWrapper(csv_file.file, encoding='utf-8')
    validation_reader = csv.DictReader(text_file)
    normalized_fields_validation = {normalize(col): col for col in (validation_reader.fieldnames or [])}
    score_column_validation = None
    for name in possible_score_names:
        if normalize(name) in normalized_fields_validation:
            score_column_validation = normalized_fields_validation[normalize(name)]
            break
    
    for row_num, row in enumerate(validation_reader, start=2):
        score_value = (row.get(score_column_validation, '') or '').strip()
        if score_value != '':  # Only validate non-empty values (empty is allowed)
            try:
                score = float(score_value)
                if score < 0:
                    validation_errors.append(f'Row {row_num}: Grade cannot be below 0 (value: {score_value})')
                elif score > 100:
                    validation_errors.append(f'Row {row_num}: Grade cannot be over 100 (value: {score_value})')
            except ValueError:
                validation_errors.append(f'Row {row_num}: Invalid number format (value: {score_value})')
    
    # If there are validation errors, return early without processing
    if validation_errors:
        return JsonResponse({
            'error': "Grades can't be below 0 and over 100. Please check your grades.",
            'details': validation_errors[:20]  # Show first 20 errors
        }, status=400)
    
    # Second pass: Process valid scores
    csv_file.file.seek(0)  # Reset file pointer again
    text_file = io.TextIOWrapper(csv_file.file, encoding='utf-8')
    reader = csv.DictReader(text_file)
    normalized_fields = {normalize(col): col for col in (reader.fieldnames or [])}
    student_id_source = normalized_fields['student_id']
    score_column = None
    for name in possible_score_names:
        if normalize(name) in normalized_fields:
            score_column = normalized_fields[normalize(name)]
            break
    
    try:
        with transaction.atomic():
            def parse_score(raw_value, label):
                value = (raw_value or '').strip()
                if value == '':
                    return None  # Allow empty values
                try:
                    # Convert to float
                    score = float(value)
                    # Validate range: 0 <= score <= 100 (already validated in first pass, but double-check)
                    if score < 0:
                        raise ValueError(f'{label} cannot be below 0')
                    if score > 100:
                        raise ValueError(f'{label} cannot be over 100')
                    # If it's a whole number (like 95), ensure it's stored as 95.0
                    # If it has decimals (like 95.5), keep it as is
                    # float() already handles this, but we ensure consistency
                    return score
                except ValueError as e:
                    # Re-raise with original message if it's our validation error
                    if 'cannot be' in str(e):
                        raise e
                    raise ValueError(f'{label} must be a valid number')
            
            updated_count = 0
            errors = []
            from django.utils import timezone
            
            for row_num, row in enumerate(reader, start=2):  # Start at 2 (header is row 1)
                try:
                    student_id_str = (row[student_id_source] or '').strip()
                    if not student_id_str:
                        errors.append(f'Row {row_num}: student_id is required')
                        continue
                    
                    # Get student by student_id (not by id)
                    try:
                        student = Student.objects.get(student_id=student_id_str)
                    except Student.DoesNotExist:
                        errors.append(f'Row {row_num}: Student with student_id {student_id_str} not found')
                        continue
                    except Student.MultipleObjectsReturned:
                        errors.append(f'Row {row_num}: Multiple students found with student_id {student_id_str}')
                        continue
                    
                    # Check if student is enrolled in this course
                    if course not in student.courses.all():
                        errors.append(f'Row {row_num}: Student {student_id_str} is not enrolled in course {course_name}')
                        continue
                    
                    # Get or create grade record
                    grade, created = Grade.objects.get_or_create(
                        student=student,
                        course=course
                    )
                    
                    # Parse score
                    score = parse_score(row[score_column], 'score')
                    
                    # Store individual score with file name
                    if score is not None:
                        grade.set_individual_score(assessment_key, score, file_name=csv_file.name)
                    else:
                        # Remove if score is None
                        grade.remove_individual_score(assessment_key)
                    
                    # Check if all files for this assessment type are uploaded
                    all_scores = []
                    for i in range(1, assessment_count + 1):
                        key = f'{assessment_type}_{i}'
                        individual_score = grade.get_individual_score(key)
                        if individual_score is not None:
                            all_scores.append(individual_score)
                    
                    # Only set average if ALL files are uploaded
                    if len(all_scores) == assessment_count and assessment_count > 0:
                        average_score = sum(all_scores) / len(all_scores)
                        setattr(grade, assessment_type, average_score)
                    else:
                        # Not all files uploaded yet, don't set average
                        setattr(grade, assessment_type, None)
                    
                    grade.save()
                    updated_count += 1
                        
                except Exception as e:
                    errors.append(f'Row {row_num}: {str(e)}')
            
            if errors and updated_count == 0:
                return JsonResponse({
                    'error': 'Failed to process CSV',
                    'details': errors[:10]  # Show first 10 errors
                }, status=400)
            
            # Count how many files are uploaded for this assessment type (check first student as sample)
            files_uploaded = 0
            file_info = None
            if updated_count > 0:
                sample_grade = Grade.objects.filter(course=course).first()
                if sample_grade and sample_grade.assessment_scores:
                    files_uploaded = len([k for k in sample_grade.assessment_scores.keys() if k.startswith(f'{assessment_type}_')])
                    # Get file info for this specific assessment file
                    file_name, uploaded_at = sample_grade.get_uploaded_file_info(assessment_key)
                    if file_name:
                        file_info = {
                            'file_name': file_name,
                            'uploaded_at': uploaded_at
                        }
            
            response_data = {
                'status': 'ok',
                'updated_count': updated_count,
                'assessment_type': assessment_type,
                'assessment_index': assessment_index,
                'files_uploaded': files_uploaded,
                'total_required': assessment_count,
                'file_info': file_info
            }
            if errors:
                response_data['warnings'] = errors[:10]
            
            return JsonResponse(response_data)
            
    except Exception as e:
        return JsonResponse({'error': f'CSV processing error: {str(e)}'}, status=400)

@instructor_required
@csrf_exempt
def delete_assessment_file(request, course_name, assessment_type, assessment_index):
    """Delete a specific assessment file (e.g., midterm_1)"""
    if request.method != 'POST':
        return JsonResponse({'error': 'Only POST allowed'}, status=405)
    
    valid_types = ['midterm', 'final', 'proje', 'homework', 'absence', 'quiz']
    if assessment_type not in valid_types:
        return JsonResponse({'error': f'Invalid assessment type'}, status=400)
    
    try:
        assessment_index = int(assessment_index)
        if assessment_index < 1:
            return JsonResponse({'error': 'Assessment index must be >= 1'}, status=400)
    except ValueError:
        return JsonResponse({'error': 'Invalid assessment index'}, status=400)
    
    instructor_user = request.instructor_user
    profile = getattr(instructor_user, 'profile', None)
    
    try:
        course = Course.objects.get(name=course_name)
    except Course.DoesNotExist:
        return JsonResponse({'error': 'Course not found'}, status=404)
    
    if profile and course not in profile.courses.all():
        return JsonResponse({'error': 'Access denied'}, status=403)
    
    try:
        assessment = Assessment.objects.get(course=course)
    except Assessment.DoesNotExist:
        return JsonResponse({'error': 'Assessment not found'}, status=404)
    
    assessment_count = getattr(assessment, assessment_type, 0)
    if assessment_index > assessment_count:
        return JsonResponse({'error': 'Invalid assessment index'}, status=400)
    
    assessment_key = f'{assessment_type}_{assessment_index}'
    
    try:
        with transaction.atomic():
            # Get all students enrolled in this course
            students = course.students.all()
            updated_count = 0
            
            for student in students:
                try:
                    grade = Grade.objects.get(student=student, course=course)
                    # Remove individual score
                    grade.remove_individual_score(assessment_key)
                    
                    # Recalculate average if needed
                    all_scores = []
                    for i in range(1, assessment_count + 1):
                        key = f'{assessment_type}_{i}'
                        individual_score = grade.get_individual_score(key)
                        if individual_score is not None:
                            all_scores.append(individual_score)
                    
                    # Only set average if ALL remaining files are uploaded
                    if len(all_scores) == assessment_count and assessment_count > 0:
                        average_score = sum(all_scores) / len(all_scores)
                        setattr(grade, assessment_type, average_score)
                    else:
                        # Not all files uploaded, clear average
                        setattr(grade, assessment_type, None)
                    
                    grade.save()
                    updated_count += 1
                except Grade.DoesNotExist:
                    continue
            
            return JsonResponse({
                'status': 'ok',
                'updated_count': updated_count,
                'assessment_type': assessment_type,
                'assessment_index': assessment_index
            })
            
    except Exception as e:
        return JsonResponse({'error': f'Delete error: {str(e)}'}, status=400)

@instructor_required
@csrf_exempt
def update_individual_grade(request, course_name):
    """Update individual grade score from table cell edit"""
    if request.method != 'POST':
        return JsonResponse({'error': 'Only POST allowed'}, status=405)
    
    instructor_user = request.instructor_user
    profile = getattr(instructor_user, 'profile', None)
    
    try:
        course = Course.objects.get(name=course_name)
    except Course.DoesNotExist:
        return JsonResponse({'error': 'Course not found'}, status=404)
    
    if profile and course not in profile.courses.all():
        return JsonResponse({'error': 'Access denied'}, status=403)
    
    try:
        data = json.loads(request.body)
        student_id = data.get('student_id')
        assessment_key = data.get('assessment_key')  # e.g., "midterm_1"
        score = data.get('score')
        
        if not student_id:
            return JsonResponse({'error': 'student_id is required'}, status=400)
        if not assessment_key:
            return JsonResponse({'error': 'assessment_key is required'}, status=400)
        
        # Get student
        try:
            student = Student.objects.get(student_id=student_id)
        except Student.DoesNotExist:
            return JsonResponse({'error': 'Student not found'}, status=404)
        
        # Check if student is enrolled
        if course not in student.courses.all():
            return JsonResponse({'error': 'Student is not enrolled in this course'}, status=400)
        
        # Get or create grade
        grade, created = Grade.objects.get_or_create(
            student=student,
            course=course
        )
        
        # Parse score
        if score is None or score == '':
            # Remove score
            grade.remove_individual_score(assessment_key)
            score_value = None
        else:
            try:
                score_value = float(score)
                if score_value < 0:
                    return JsonResponse({'error': 'Score cannot be less than 0'}, status=400)
                if score_value > 100:
                    return JsonResponse({'error': 'Score cannot be greater than 100'}, status=400)
                # Set individual score (without file_name since it's manual edit)
                # Keep existing file_name if exists
                existing_file_name = ''
                if grade.assessment_scores and assessment_key in grade.assessment_scores:
                    existing_file_name = grade.assessment_scores[assessment_key].get('file_name', '')
                grade.set_individual_score(assessment_key, score_value, file_name=existing_file_name)
            except ValueError:
                return JsonResponse({'error': 'Score must be a valid number'}, status=400)
        
        # Recalculate average for this assessment type if needed
        assessment_type = assessment_key.split('_')[0]
        try:
            assessment = Assessment.objects.get(course=course)
            assessment_count = getattr(assessment, assessment_type, 0)
            
            if assessment_count > 0:
                all_scores = []
                for i in range(1, assessment_count + 1):
                    key = f'{assessment_type}_{i}'
                    individual_score = grade.get_individual_score(key)
                    if individual_score is not None:
                        all_scores.append(individual_score)
                
                # Only set average if ALL files are uploaded
                if len(all_scores) == assessment_count:
                    average_score = sum(all_scores) / len(all_scores)
                    setattr(grade, assessment_type, average_score)
                else:
                    # Not all files uploaded, clear average
                    setattr(grade, assessment_type, None)
        except Assessment.DoesNotExist:
            pass
        
        # Update last_changes_at
        from django.utils import timezone
        grade.last_changes_at = timezone.now()
        grade.save()
        
        return JsonResponse({
            'status': 'ok',
            'score': score_value,
            'assessment_key': assessment_key,
            'last_changes_at': grade.last_changes_at.isoformat() if grade.last_changes_at else None
        })
        
    except Exception as e:
        return JsonResponse({'error': f'Update error: {str(e)}'}, status=400)

@instructor_required
@csrf_exempt
def update_assessment(request, course_name):
    if request.method != 'POST':
        return JsonResponse({'error': 'Method not allowed'}, status=405)
    
    instructor_user = request.instructor_user
    profile = getattr(instructor_user, 'profile', None)
    
    try:
        course = Course.objects.get(name=course_name)
    except Course.DoesNotExist:
        return JsonResponse({'error': 'Course not found'}, status=404)
    
    if profile and course not in profile.courses.all():
        return JsonResponse({'error': 'Access denied'}, status=403)
    
    try:
        data = json.loads(request.body)
        midterm = data.get('midterm')
        final = data.get('final')
        proje = data.get('proje')
        homework = data.get('homework')
        absence = data.get('absence')
        quiz = data.get('quiz')
        
        # Validation: Integer kontrolü ve 10'dan küçük olması
        values = {
            'midterm': midterm,
            'final': final,
            'proje': proje,
            'homework': homework,
            'absence': absence,
            'quiz': quiz
        }
        
        for key, value in values.items():
            if value is None:
                return JsonResponse({'error': f'{key} is required'}, status=400)
            try:
                int_value = int(value)
            except (ValueError, TypeError):
                return JsonResponse({'error': f'{key} must be an integer'}, status=400)
            if int_value >= 10:
                return JsonResponse({'error': f'{key} must be less than 10'}, status=400)
            if int_value < 0:
                return JsonResponse({'error': f'{key} cannot be negative'}, status=400)
            values[key] = int_value
        
        # Assessment'ı güncelle veya oluştur
        assessment, created = Assessment.objects.get_or_create(
            course=course,
            defaults={
                'midterm': values['midterm'],
                'final': values['final'],
                'proje': values['proje'],
                'homework': values['homework'],
                'absence': values['absence'],
                'quiz': values['quiz'],
            }
        )
        
        if not created:
            assessment.midterm = values['midterm']
            assessment.final = values['final']
            assessment.proje = values['proje']
            assessment.homework = values['homework']
            assessment.absence = values['absence']
            assessment.quiz = values['quiz']
            # save() metodu assessment_count'u otomatik hesaplayacak
            assessment.save()
        
        return JsonResponse({
            'status': 'ok',
            'assessment_count': assessment.assessment_count
        })
        
    except (json.JSONDecodeError, KeyError, ValueError) as e:
        return JsonResponse({'error': f'Invalid data: {str(e)}'}, status=400)

@instructor_required
@csrf_exempt
def update_assessment_percentages(request, course_name):
    if request.method != 'POST':
        return JsonResponse({'error': 'Method not allowed'}, status=405)
    
    instructor_user = request.instructor_user
    profile = getattr(instructor_user, 'profile', None)
    
    try:
        course = Course.objects.get(name=course_name)
    except Course.DoesNotExist:
        return JsonResponse({'error': 'Course not found'}, status=404)
    
    if profile and course not in profile.courses.all():
        return JsonResponse({'error': 'Access denied'}, status=403)
    
    try:
        data = json.loads(request.body)
        midterm_percentage = data.get('midterm_percentage')
        final_percentage = data.get('final_percentage')
        proje_percentage = data.get('proje_percentage')
        homework_percentage = data.get('homework_percentage')
        absence_percentage = data.get('absence_percentage')
        quiz_percentage = data.get('quiz_percentage')
        
        # Validation: Integer kontrolü
        values = {
            'midterm_percentage': midterm_percentage,
            'final_percentage': final_percentage,
            'proje_percentage': proje_percentage,
            'homework_percentage': homework_percentage,
            'absence_percentage': absence_percentage,
            'quiz_percentage': quiz_percentage
        }
        
        for key, value in values.items():
            if value is None:
                return JsonResponse({'error': f'{key} is required'}, status=400)
            try:
                int_value = int(value)
            except (ValueError, TypeError):
                return JsonResponse({'error': f'{key} must be an integer'}, status=400)
            if int_value < 0:
                return JsonResponse({'error': f'{key} cannot be negative'}, status=400)
            if int_value > 100:
                return JsonResponse({'error': f'{key} cannot be greater than 100'}, status=400)
            values[key] = int_value
        
        # Toplam 100 kontrolü
        total = sum(values.values())
        if total != 100:
            return JsonResponse({'error': f'Total percentage must be exactly 100. Current total: {total}'}, status=400)
        
        # Assessment'ı güncelle veya oluştur
        assessment, created = Assessment.objects.get_or_create(
            course=course,
            defaults={
                'midterm_percentage': values['midterm_percentage'],
                'final_percentage': values['final_percentage'],
                'proje_percentage': values['proje_percentage'],
                'homework_percentage': values['homework_percentage'],
                'absence_percentage': values['absence_percentage'],
                'quiz_percentage': values['quiz_percentage'],
            }
        )
        
        if not created:
            assessment.midterm_percentage = values['midterm_percentage']
            assessment.final_percentage = values['final_percentage']
            assessment.proje_percentage = values['proje_percentage']
            assessment.homework_percentage = values['homework_percentage']
            assessment.absence_percentage = values['absence_percentage']
            assessment.quiz_percentage = values['quiz_percentage']
            assessment.save()
        
        return JsonResponse({
            'status': 'ok'
        })
        
    except (json.JSONDecodeError, KeyError, ValueError) as e:
        return JsonResponse({'error': f'Invalid data: {str(e)}'}, status=400)


@instructor_required
def instructor_announcements(request):
    from .models import Announcement, UserProfile
    instructor_user = request.instructor_user
    
    instructors = User.objects.filter(profile__role='instructor').select_related('profile')
    faculty_heads = User.objects.filter(profile__role='faculty_head').select_related('profile')
    
    instructors_map = get_instructors_map()
    faculty_heads_map = get_faculty_heads_map()
    
    if request.method == 'POST':
        message = (request.POST.get('message') or '').strip()
        subject = (request.POST.get('subject') or '').strip()
        receivers_str = (request.POST.get('receivers') or '').strip()
        
        if message:
            if not subject:
                subject = 'No Topic'
            
            # Parse receivers (comma-separated)
            receivers_list = [r.strip() for r in receivers_str.split(',') if r.strip()]
            
            with transaction.atomic():
                for receiver_username in receivers_list:
                    # Check if it's a course selection (format: course_CourseName)
                    if receiver_username.startswith('course_'):
                        course_name = receiver_username.replace('course_', '', 1)
                        try:
                            course = Course.objects.get(name=course_name)
                            # Verify instructor has access to this course
                            profile = getattr(instructor_user, 'profile', None)
                            if profile and course in profile.courses.all():
                                # Get all students enrolled in this course
                                students = Student.objects.filter(courses=course).select_related('user')
                                # Add course marker to subject for grouping (will be removed when displaying)
                                course_marker = f"__COURSE:{course_name}__"
                                marked_subject = course_marker + subject if not subject.startswith(course_marker) else subject
                                for student in students:
                                    student_user = student.user
                                    if student_user:
                                        Announcement.objects.create(
                                            sender=instructor_user,
                                            receiver=student_user,
                                            subject=marked_subject,
                                            message=message,
                                            sender_role='instructor',
                                            receiver_role='student'
                                        )
                        except Course.DoesNotExist:
                            pass
                    else:
                        # Regular user receiver
                        try:
                            receiver = User.objects.get(username=receiver_username)
                            profile = getattr(receiver, 'profile', None)
                            receiver_role = None
                            if profile:
                                receiver_role = profile.role
                            
                            Announcement.objects.create(
                                sender=instructor_user,
                                receiver=receiver,
                                subject=subject,
                                message=message,
                                sender_role='instructor',
                                receiver_role=receiver_role
                            )
                        except User.DoesNotExist:
                            pass
            
            return redirect('instructor_announcements')
    
    # ORM ile announcements'ları çek - select_related ile JOIN optimizasyonu
    announcements = Announcement.objects.filter(
        Q(sender=instructor_user) | Q(receiver=instructor_user)
    ).select_related('sender', 'receiver').order_by('-created_at')
    
    all_announcements = []
    for ann in announcements:
        all_announcements.append({
            'id': ann.id,
            'subject': ann.subject,
            'message': ann.message,
            'sender_id': ann.sender.id,
            'receiver_id': ann.receiver.id if ann.receiver else None,
            'sender_username': ann.sender.username,
            'sender_first_name': ann.sender.first_name,
            'sender_last_name': ann.sender.last_name,
            'receiver_username': ann.receiver.username if ann.receiver else None,
            'receiver_first_name': ann.receiver.first_name if ann.receiver else '',
            'receiver_last_name': ann.receiver.last_name if ann.receiver else '',
            'sender_role': ann.sender_role,
            'receiver_role': ann.receiver_role,
            'created_at': ann.created_at,
        })
    
    # Group announcements sent to course students
    from collections import defaultdict
    from datetime import timedelta
    
    # First, process all announcements and group them
    announcements_data = []
    processed_ids = set()
    
    for ann in all_announcements:
        if ann['id'] in processed_ids:
            continue
            
        sender_full_name = f"{ann['sender_first_name']} {ann['sender_last_name']}".strip() if ann['sender_first_name'] or ann['sender_last_name'] else ''
        sender_name = instructors_map.get(ann['sender_username']) or faculty_heads_map.get(ann['sender_username']) or sender_full_name or ann['sender_username']
        
        is_sent = ann['sender_id'] == instructor_user.id
        
        # Check if this is part of a course broadcast
        if is_sent:
            # Find all announcements with same subject, message, sender, and sent within 10 seconds
            created_at_str = ann['created_at']
            if isinstance(created_at_str, str):
                from datetime import datetime
                try:
                    created_at_dt = datetime.strptime(created_at_str, '%Y-%m-%d %H:%M:%S.%f')
                except:
                    try:
                        created_at_dt = datetime.strptime(created_at_str, '%Y-%m-%d %H:%M:%S')
                    except:
                        created_at_dt = datetime.now()
            else:
                created_at_dt = created_at_str if hasattr(created_at_str, 'timestamp') else None
                if not created_at_dt:
                    from datetime import datetime
                    created_at_dt = datetime.now()
            
            course_name_from_marker = None
            clean_subject = ann['subject']
            if ann['subject'].startswith('__COURSE:'):
                marker_end = ann['subject'].find('__', 9)  
                if marker_end > 0:
                    course_name_from_marker = ann['subject'][9:marker_end]
                    clean_subject = ann['subject'][marker_end + 2:]
            
            matching_anns = []
            for other_ann in all_announcements:
                if (other_ann['id'] in processed_ids or 
                    other_ann['sender_id'] != ann['sender_id'] or
                    other_ann['message'] != ann['message']):
                    continue
                
                other_subject = other_ann['subject']
                other_course_name = None
                if other_subject.startswith('__COURSE:'):
                    marker_end = other_subject.find('__', 9)
                    if marker_end > 0:
                        other_course_name = other_subject[9:marker_end]
                        other_subject = other_subject[marker_end + 2:]
                
                if other_subject != clean_subject:
                    continue
                
                if course_name_from_marker and other_course_name:
                    if course_name_from_marker != other_course_name:
                        continue
                elif course_name_from_marker or other_course_name:
                    continue
                
                other_created_at_str = other_ann['created_at']
                if isinstance(other_created_at_str, str):
                    try:
                        other_created_at_dt = datetime.strptime(other_created_at_str, '%Y-%m-%d %H:%M:%S.%f')
                    except:
                        try:
                            other_created_at_dt = datetime.strptime(other_created_at_str, '%Y-%m-%d %H:%M:%S')
                        except:
                            continue
                else:
                    other_created_at_dt = other_created_at_str if hasattr(other_created_at_str, 'timestamp') else None
                    if not other_created_at_dt:
                        continue
                
                time_diff = abs((created_at_dt - other_created_at_dt).total_seconds())
                if time_diff <= 10:
                    matching_anns.append(other_ann)
            
            if course_name_from_marker and len(matching_anns) > 1:
                created_at_formatted = created_at_dt.strftime('%Y-%m-%d %H:%M') if hasattr(created_at_dt, 'strftime') else str(created_at_dt)
                announcements_data.append({
                    'id': ann['id'],
                    'subject': clean_subject,
                    'message': ann['message'],
                    'sender': sender_name,
                    'sender_username': ann['sender_username'],
                    'receiver': f'All students in {course_name_from_marker}',
                    'receiver_username': None,
                    'is_sent': True,
                    'created_at': created_at_formatted,
                })
                for ma in matching_anns:
                    processed_ids.add(ma['id'])
                continue
        
        if ann['id'] not in processed_ids:
            receiver_name = "Everyone"
            receiver_username = None
            if ann['receiver_id']:
                receiver_full_name = f"{ann['receiver_first_name']} {ann['receiver_last_name']}".strip() if ann['receiver_first_name'] or ann['receiver_last_name'] else ''
                receiver_name = instructors_map.get(ann['receiver_username']) or faculty_heads_map.get(ann['receiver_username']) or receiver_full_name or ann['receiver_username']
                receiver_username = ann['receiver_username']
            
            created_at_str = ann['created_at']
            if isinstance(created_at_str, str):
                from datetime import datetime
                try:
                    created_at_dt = datetime.strptime(created_at_str, '%Y-%m-%d %H:%M:%S.%f')
                except:
                    try:
                        created_at_dt = datetime.strptime(created_at_str, '%Y-%m-%d %H:%M:%S')
                    except:
                        created_at_dt = datetime.now()
                created_at_formatted = created_at_dt.strftime('%Y-%m-%d %H:%M')
            else:
                created_at_formatted = created_at_str.strftime('%Y-%m-%d %H:%M') if hasattr(created_at_str, 'strftime') else str(created_at_str)
            
            display_subject = ann['subject']
            if display_subject.startswith('__COURSE:'):
                marker_end = display_subject.find('__', 9)
                if marker_end > 0:
                    display_subject = display_subject[marker_end + 2:]
            
            announcements_data.append({
                'id': ann['id'],
                'subject': display_subject,
                'message': ann['message'],
                'sender': sender_name,
                'sender_username': ann['sender_username'],
                'receiver': receiver_name,
                'receiver_username': receiver_username,
                'is_sent': is_sent,
                'created_at': created_at_formatted,
            })
            processed_ids.add(ann['id'])
    
    recipients = []
    
    profile = getattr(instructor_user, 'profile', None)
    instructor_courses = []
    
    if profile:
        instructor_courses = list(profile.courses.all())
        courses_list = []
        for course in instructor_courses:
            courses_list.append({
                'username': f'course_{course.name}',
                'name': f'All students in {course.name}',
                'role': 'course'
            })
        courses_list.sort(key=lambda x: x['name'])
        recipients.extend(courses_list)
    
    professors_list = []
    for inst in instructors:
        if inst.username != instructor_user.username:
            name = instructors_map.get(inst.username) or inst.get_full_name() or inst.username
            professors_list.append({
                'username': inst.username, 
                'name': name, 
                'role': 'instructor'
            })
    
    for fh in faculty_heads:
        name = faculty_heads_map.get(fh.username) or fh.get_full_name() or fh.username
        professors_list.append({
            'username': fh.username, 
            'name': name, 
            'role': 'faculty_head'
        })
    
    professors_list.sort(key=lambda x: x['name'])
    
    if professors_list:
        professors_list[0]['show_professors_heading'] = True
    
    recipients.extend(professors_list)
    
    if instructor_courses:
        students = Student.objects.filter(
            courses__in=instructor_courses
        ).distinct().select_related('user')
        
        students_list = []
        for student in students:
            full_name = f"{student.first_name} {student.last_name}".strip() if student.first_name or student.last_name else ''
            if not full_name and student.user:
                full_name = f"{student.user.first_name} {student.user.last_name}".strip()
            name = full_name if full_name else student.username
            students_list.append({
                'username': student.user.username if student.user else student.username,
                'name': name,
                'role': 'student'
            })
        
        students_list.sort(key=lambda x: x['name'])
        recipients.extend(students_list)
    
    sent_messages = [ann for ann in announcements_data if ann['is_sent']]
    received_messages = [ann for ann in announcements_data if not ann['is_sent']]
    
    announcements_json = json.dumps({str(ann['id']): {
        'subject': ann['subject'],
        'message': ann['message'],
        'sender': ann['sender'],
        'receiver': ann['receiver'],
        'created_at': ann['created_at'],
        'is_sent': ann['is_sent']
    } for ann in announcements_data})
    
    return render(request, 'instructor/instructor_announcements.html', {
        'all_announcements': announcements_data,
        'announcements_json': announcements_json,
        'sent_messages': sent_messages,
        'received_messages': received_messages,
        'recipients': recipients,
    })


@csrf_exempt
def set_instructor_session(request):
    """Set instructor username in session (only for authenticated instructors)"""
    if not request.user.is_authenticated:
        return JsonResponse({'status': 'error', 'message': 'Not authenticated'}, status=401)
    
    # User'ın instructor olduğunu kontrol et
    try:
        if request.user.profile.role != 'instructor':
            return JsonResponse({'status': 'error', 'message': 'Not an instructor'}, status=403)
    except AttributeError:
        return JsonResponse({'status': 'error', 'message': 'Profile not found'}, status=403)
    
    if request.method == 'POST':
        # Sadece authenticated user'ın kendi username'ini set edebilir
        request.session['instructor_username'] = request.user.username
        return JsonResponse({'status': 'ok'})
    return JsonResponse({'status': 'error'}, status=400)


@faculty_head_required
def faculty_head_dashboard(request):
    from datetime import datetime
    from .models import Announcement
    from django.db.models import Q
    
    faculty_head_user = request.user
    profile = getattr(faculty_head_user, 'profile', None)
    faculty_head_data = get_faculty_head_data(faculty_head_user.username)
    faculty_head_department = faculty_head_data.get('department')
    
    faculty_head_info = {
        'username': faculty_head_user.username,
        'name': f"{faculty_head_user.first_name} {faculty_head_user.last_name}".strip() or faculty_head_user.username,
        'faculty': profile.faculty.name if profile and profile.faculty else '-',
        'department': profile.department if profile else '-',
    }
    
    current_month = datetime.now().month
    current_year = datetime.now().year
    
    if current_month >= 9:
        academic_term = f"{current_year}-{current_year + 1} Fall"
    elif current_month >= 2:
        academic_term = f"{current_year - 1}-{current_year} Spring"
    else:
        academic_term = f"{current_year - 1}-{current_year} Fall"
    
    courses_list = []
    total_students_set = set()
    total_instructors_set = set()
    chart_data = {'labels': [], 'data': []}
    
    if faculty_head_department:
        courses = Course.objects.filter(department=faculty_head_department).select_related('instructor').prefetch_related('students')
        for course in courses:
            students = course.students.all()
            student_count = students.count()
            
            for student in students:
                total_students_set.add(student.id)
            
            if course.instructor:
                total_instructors_set.add(course.instructor.id)
            
            instructor_name = f"{course.instructor.first_name} {course.instructor.last_name}".strip() if course.instructor else 'Unknown'
            if not instructor_name or instructor_name == ' ':
                instructor_name = course.instructor.username if course.instructor else 'Unknown'
            
            courses_list.append({
                'id': course.id,
                'name': course.name,
                'code': course.code,
                'credits': course.credits,
                'instructor': instructor_name,
                'student_count': student_count,
            })
            
            chart_data['labels'].append(course.name)
            chart_data['data'].append(student_count)
    
    total_courses = len(courses_list)
    total_students = len(total_students_set)
    total_instructors = len(total_instructors_set)
    
    latest_announcements = Announcement.objects.filter(
        Q(sender=faculty_head_user) | Q(receiver=faculty_head_user) | Q(receiver__isnull=True)
    ).select_related('sender', 'receiver').order_by('-created_at')[:5]
    
    announcements_list = []
    for ann in latest_announcements:
        sender_name = ann.sender.get_full_name() or ann.sender.username
        announcements_list.append({
            'id': ann.id,
            'subject': ann.subject,
            'sender': sender_name,
            'created_at': ann.created_at.strftime('%Y-%m-%d %H:%M'),
        })
    
    chart_data_json = json.dumps(chart_data)
    
    return render(request, 'faculty_head_main.html', {
        'faculty_head_info': faculty_head_info,
        'academic_term': academic_term,
        'courses_list': courses_list,
        'total_courses': total_courses,
        'total_students': total_students,
        'total_instructors': total_instructors,
        'chart_data': chart_data,
        'chart_data_json': chart_data_json,
        'latest_announcements': announcements_list,
    })

@faculty_head_required
def faculty_head_profile(request):
    profile = getattr(request.user, 'profile', None)
    faculty = profile.faculty if profile else None
    
    courses = []
    if profile:
        courses = [course.name for course in profile.courses.all()]
    
    profile_data = {
        'name': f"{request.user.first_name} {request.user.last_name}".strip() or request.user.username,
        'username': request.user.username,
        'department': profile.department if profile else '-',
        'faculty': faculty.name if faculty else '-',
        'courses': courses,
    }
    
    return render(request, 'faculty_head.html', {
        'show_welcome': False,
        'page': 'profile',
        'profile': profile_data
    })

@faculty_head_required
def all_courses(request):
    faculty_head_data = get_faculty_head_data(request.user.username)
    faculty_head_department = faculty_head_data.get('department')
    
    if request.method == 'POST':
        action = request.POST.get('action')
        
        if action == 'add_course':
            course_name = request.POST.get('course_name', '').strip()
            instructor_username = request.POST.get('instructor_username', '').strip()
            credits_str = request.POST.get('credits', '').strip()
            
            if course_name:
                credits = None
                if credits_str:
                    try:
                        credits = int(credits_str)
                    except ValueError:
                        pass
                
                instructor_user = None
                if instructor_username:
                    try:
                        instructor_user = User.objects.get(username=instructor_username)
                    except User.DoesNotExist:
                        pass
                
                if not instructor_user:
                    default_instructor = UserProfile.objects.filter(role='instructor').first()
                    instructor_user = default_instructor.user if default_instructor else User.objects.first()
                
                course, created = Course.objects.get_or_create(
                    name=course_name,
                    defaults={
                        'code': '',
                        'department': faculty_head_department or '',
                        'instructor': instructor_user,
                        'credits': credits,
                    }
                )
                
                if not created:
                    course.instructor = instructor_user
                    if credits is not None:
                        course.credits = credits
                    course.save()
        
        elif action == 'update_course':
            course_id = request.POST.get('course_id')
            course_name = request.POST.get('course_name', '').strip()
            instructor_username = request.POST.get('instructor_username', '').strip()
            credits_str = request.POST.get('credits', '').strip()
            
            try:
                course = Course.objects.get(id=course_id)
                
                if course_name:
                    course.name = course_name
                
                if instructor_username:
                    try:
                        instructor_user = User.objects.get(username=instructor_username)
                        course.instructor = instructor_user
                    except User.DoesNotExist:
                        pass
                
                if credits_str:
                    try:
                        credits = int(credits_str)
                        course.credits = credits
                    except ValueError:
                        pass
                else:
                    course.credits = None
                
                course.save()
            except Course.DoesNotExist:
                pass
        
        return redirect('all_courses')
    
    faculty_courses_with_instructors = []
    course_instructor_map = {}
    
    # Instructors'ları veritabanından çek
    instructors = User.objects.filter(profile__role='instructor').select_related('profile').prefetch_related('profile__courses', 'instructor_courses')
    for user in instructors:
        profile = user.profile
        inst_department = profile.department
        if faculty_head_department:
            if inst_department != faculty_head_department:
                continue
        
        # Courses bilgisini al (hem UserProfile'dan hem de Course modelinden)
        courses_from_profile = [course.name for course in profile.courses.all()]
        courses_from_instructor = [course.name for course in user.instructor_courses.all()]
        inst_courses = list(set(courses_from_profile + courses_from_instructor))
        
        full_name = (user.first_name + ' ' + user.last_name).strip()
        instructor_name = full_name if full_name else user.username
        
        for course_name in inst_courses:
            if course_name not in course_instructor_map:
                course_instructor_map[course_name] = []
            course_instructor_map[course_name].append(instructor_name)
    
    # Faculty heads'leri veritabanından çek
    faculty_heads = User.objects.filter(profile__role='faculty_head').select_related('profile').prefetch_related('profile__courses')
    for user in faculty_heads:
        profile = user.profile
        fh_department = profile.department
        if faculty_head_department and fh_department != faculty_head_department:
            continue
        
        fh_courses = [course.name for course in profile.courses.all()]
        full_name = (user.first_name + ' ' + user.last_name).strip()
        faculty_head_name = full_name if full_name else user.username
        
        for course_name in fh_courses:
            if course_name not in course_instructor_map:
                course_instructor_map[course_name] = []
            course_instructor_map[course_name].append(faculty_head_name)
    
    all_course_names = set(course_instructor_map.keys())
    if faculty_head_department:
        all_courses_in_dept = Course.objects.filter(department=faculty_head_department).values_list('name', flat=True).distinct()
        all_course_names.update(all_courses_in_dept)
    
    for course_name in sorted(all_course_names):
        instructors = course_instructor_map.get(course_name, [])
        
        course = Course.objects.filter(name=course_name).first()
        if course and course.instructor:
            instructor_full_name = (course.instructor.first_name + ' ' + course.instructor.last_name).strip()
            instructor_name = instructor_full_name if instructor_full_name else course.instructor.username
            if instructor_name not in instructors:
                instructors.append(instructor_name)
        
        instructor_display = ', '.join(instructors) if instructors else 'Unknown'
        
        first_learning_outcome = None
        if course:
            learning_outcomes = ProgramOutcome.objects.filter(course_name=course_name).order_by('-created_at')
            first_learning_outcome = learning_outcomes.first()
        
        faculty_courses_with_instructors.append({
            'course': course_name,
            'instructor': instructor_display,
            'course_id': course.id if course else None,
            'credits': course.credits if course else None,
            'first_lo_id': first_learning_outcome.id if first_learning_outcome else None,
        })
    
    available_instructors_list = []
    available_instructors_qs = User.objects.filter(profile__role='instructor').select_related('profile')
    for user in available_instructors_qs:
        profile = user.profile
        inst_department = profile.department
        if faculty_head_department:
            if inst_department != faculty_head_department:
                continue
        
        full_name = (user.first_name + ' ' + user.last_name).strip()
        instructor_name = full_name if full_name else user.username
        available_instructors_list.append({
            'username': user.username,
            'name': instructor_name,
        })
    
    import json as json_module
    context = {
        'faculty_head': faculty_head_data,
        'faculty_courses': faculty_courses_with_instructors,
        'faculty_courses_json': json_module.dumps(faculty_courses_with_instructors),
        'available_instructors': available_instructors_list,
        'available_instructors_json': json_module.dumps(available_instructors_list),
    }
    return render(request, 'faculty/all_courses.html', context)

@faculty_head_required
def my_courses(request):
    profile = getattr(request.user, 'profile', None)
    
    # Get faculty head's department
    faculty_head_data = get_faculty_head_data(request.user.username)
    faculty_head_department = faculty_head_data.get('department')
    
    courses_data = []
    if profile:
        courses = profile.courses.all().select_related('instructor')
        for course in courses:
            # Filter by department - only show courses from faculty head's department
            if faculty_head_department and course.department != faculty_head_department:
                continue
            
            instructor_name = f"{course.instructor.first_name} {course.instructor.last_name}".strip() or course.instructor.username
            
            first_learning_outcome = None
            learning_outcomes = ProgramOutcome.objects.filter(course_name=course.name).order_by('-created_at')
            first_learning_outcome = learning_outcomes.first()
            
            courses_data.append({
                'id': course.id,
                'name': course.name,
                'code': course.code,
                'instructor': instructor_name,
                'department': course.department,
                'credits': course.credits,
                'first_lo_id': first_learning_outcome.id if first_learning_outcome else None,
            })
    
    context = {
        'courses': courses_data,
    }
    return render(request, 'faculty/my_courses.html', context)

@faculty_head_required
def program_outcomes(request):
    from .models import Faculty
    
    profile = getattr(request.user, 'profile', None)
    faculty = profile.faculty if profile else None
    
    faculty_head_data = get_faculty_head_data(request.user.username)
    faculty_head_department = faculty_head_data.get('department')
    faculty_name_from_json = faculty_head_data.get('faculty')
    
    if not faculty and faculty_name_from_json:
        with transaction.atomic():
            faculty_slug = faculty_name_from_json.lower().replace(' ', '-')
            try:
                faculty = Faculty.objects.get(slug=faculty_slug)
            except Faculty.DoesNotExist:
                faculty, _ = Faculty.objects.get_or_create(
                    slug=faculty_slug,
                    defaults={'name': faculty_name_from_json}
                )
            if profile:
                profile.faculty = faculty
                profile.save()
    
    if request.method == 'POST':
        text = (request.POST.get('text') or '').strip()
        creator = request.user if request.user.is_authenticated else None
        
        faculty_heads_map = get_faculty_heads_map()
        instructors_map = get_instructors_map()
        
        if not creator:
            outcomes_qs = ProgramOutcome.objects.filter(faculty=faculty, course_name='').select_related('created_by').prefetch_related('learning_outcomes__created_by').order_by('-created_at')
            outcomes_data = []
            for o in outcomes_qs:
                creator_username = o.created_by.username
                creator_name = faculty_heads_map.get(creator_username) or o.created_by.get_full_name() or creator_username
                
                linked_learning_outcomes = []
                seen_course_instructor = set()
                for lo in o.learning_outcomes.all():
                    lo_creator_username = lo.created_by.username
                    lo_creator_name = instructors_map.get(lo_creator_username) or lo.created_by.get_full_name() or lo_creator_username
                    course_instructor_key = (lo.course_name, lo_creator_name)
                    if course_instructor_key not in seen_course_instructor:
                        seen_course_instructor.add(course_instructor_key)
                        linked_learning_outcomes.append({
                            'text': lo.text,
                            'course': lo.course_name,
                            'instructor': lo_creator_name,
                        })
                
                outcomes_data.append({
                    'id': o.id,
                    'text': o.text,
                    'created_by': creator_name,
                    'created_at': o.created_at.strftime('%Y-%m-%d %H:%M'),
                    'linked_learning_outcomes': linked_learning_outcomes,
                })
            return render(request, 'faculty/program_outcomes.html', {
                'error': 'Login required to create program outcomes.',
                'outcomes_data': outcomes_data,
                'faculty_head_department': faculty_head_department,
            })
        
        if not text:
            outcomes_qs = ProgramOutcome.objects.filter(faculty=faculty, course_name='').select_related('created_by').prefetch_related('learning_outcomes__created_by').order_by('-created_at')
            outcomes_data = []
            for o in outcomes_qs:
                creator_username = o.created_by.username
                creator_name = faculty_heads_map.get(creator_username) or o.created_by.get_full_name() or creator_username
                
                linked_learning_outcomes = []
                seen_course_instructor = set()
                for lo in o.learning_outcomes.all():
                    lo_creator_username = lo.created_by.username
                    lo_creator_name = instructors_map.get(lo_creator_username) or lo.created_by.get_full_name() or lo_creator_username
                    course_instructor_key = (lo.course_name, lo_creator_name)
                    if course_instructor_key not in seen_course_instructor:
                        seen_course_instructor.add(course_instructor_key)
                        linked_learning_outcomes.append({
                            'text': lo.text,
                            'course': lo.course_name,
                            'instructor': lo_creator_name,
                        })
                
                outcomes_data.append({
                    'id': o.id,
                    'text': o.text,
                    'created_by': creator_name,
                    'created_at': o.created_at.strftime('%Y-%m-%d %H:%M'),
                    'linked_learning_outcomes': linked_learning_outcomes,
                })
            return render(request, 'faculty/program_outcomes.html', {
                'error': 'Outcome text is required.',
                'outcomes_data': outcomes_data,
                'faculty_head_department': faculty_head_department,
            })
        
        with transaction.atomic():
            ProgramOutcome.objects.create(text=text, course_name='', faculty=faculty, created_by=creator)
        return redirect('program_outcomes')
    
    faculty_heads_map = get_faculty_heads_map()
    instructors_map = get_instructors_map()
    
    outcomes_qs = ProgramOutcome.objects.filter(faculty=faculty, course_name='').select_related('created_by').prefetch_related('learning_outcomes__created_by').order_by('-created_at')
    outcomes_data = []
    for o in outcomes_qs:
        creator_username = o.created_by.username
        creator_name = faculty_heads_map.get(creator_username) or o.created_by.get_full_name() or creator_username
        
        linked_learning_outcomes = []
        seen_course_instructor = set()
        for lo in o.learning_outcomes.all():
            lo_creator_username = lo.created_by.username
            lo_creator_name = instructors_map.get(lo_creator_username) or lo.created_by.get_full_name() or lo_creator_username
            course_instructor_key = (lo.course_name, lo_creator_name)
            if course_instructor_key not in seen_course_instructor:
                seen_course_instructor.add(course_instructor_key)
                linked_learning_outcomes.append({
                    'text': lo.text,
                    'course': lo.course_name,
                    'instructor': lo_creator_name,
                })
        
        outcomes_data.append({
            'id': o.id,
            'text': o.text,
            'created_by': creator_name,
            'created_at': o.created_at.strftime('%Y-%m-%d %H:%M'),
            'linked_learning_outcomes': linked_learning_outcomes,
        })
    
    return render(request, 'faculty/program_outcomes.html', {
        'outcomes_data': outcomes_data,
        'faculty_head_department': faculty_head_department,
    })


@faculty_head_required
def program_outcome_detail(request, outcome_id):
    """Show detail page for a program outcome with linked learning outcomes"""
    from .models import Faculty
    
    profile = getattr(request.user, 'profile', None)
    faculty = profile.faculty if profile else None
    
    faculty_head_data = get_faculty_head_data(request.user.username)
    faculty_name_from_json = faculty_head_data.get('faculty')
    
    if not faculty and faculty_name_from_json:
        try:
            faculty = Faculty.objects.get(slug=faculty_name_from_json.lower())
        except Faculty.DoesNotExist:
            faculty, _ = Faculty.objects.get_or_create(
                slug=faculty_name_from_json.lower(),
                defaults={'name': faculty_name_from_json}
            )
    
    outcome = get_object_or_404(ProgramOutcome, id=outcome_id, faculty=faculty, course_name='')
    
    related_learning_outcomes = outcome.learning_outcomes.all().order_by('-created_at')
    
    instructors_map = get_instructors_map()
    
    learning_outcomes_data = []
    for lo in related_learning_outcomes:
        lo_creator_username = lo.created_by.username
        lo_creator_name = instructors_map.get(lo_creator_username) or lo.created_by.get_full_name() or lo_creator_username
        learning_outcomes_data.append({
            'id': lo.id,
            'text': lo.text,
            'course': lo.course_name,
            'instructor': lo_creator_name,
            'created_at': lo.created_at.strftime('%Y-%m-%d %H:%M'),
        })
    
    return render(
        request,
        'faculty/program_outcome_detail.html',
        {
            'outcome': outcome,
            'learning_outcomes': learning_outcomes_data,
        }
    )


@faculty_head_required
def update_program_outcome(request, outcome_id):
    profile = getattr(request.user, 'profile', None)
    faculty = profile.faculty if profile else None
    
    outcome = get_object_or_404(ProgramOutcome, id=outcome_id, faculty=faculty, created_by=request.user)
    
    if request.method == 'POST':
        text = (request.POST.get('text') or '').strip()
        if text:
            with transaction.atomic():
                outcome.text = text
                outcome.save()
        return redirect('program_outcomes')
    
    return JsonResponse({'text': outcome.text})


@faculty_head_required
def delete_program_outcome(request, outcome_id):
    profile = getattr(request.user, 'profile', None)
    faculty = profile.faculty if profile else None
    
    outcome = get_object_or_404(ProgramOutcome, id=outcome_id, faculty=faculty, created_by=request.user)
    with transaction.atomic():
        outcome.delete()
    
    return redirect('program_outcomes')


@faculty_head_required
def create_program_outcome(request):
    profile = getattr(request.user, 'profile', None)
    faculty = profile.faculty if profile else None
    if not faculty:
        return render(request, 'faculty/create_outcome.html', {
            'error': 'No faculty assigned to your profile.',
        })
    
    faculty_head_data = get_faculty_head_data(request.user.username)
    faculty_head_department = faculty_head_data.get('department')
    
    if request.method == 'POST':
        text = (request.POST.get('text') or '').strip()
        course_name = (request.POST.get('course_name') or '').strip()
        creator = request.user if request.user.is_authenticated else None
        
        if not creator:
            return HttpResponseForbidden("Login required to create program outcomes.")
        
        if not text:
            return render(
                request,
                'faculty/create_outcome.html',
                {
                    'error': 'Outcome text is required.',
                    'faculty_name': faculty.name,
                    'faculty_head_department': faculty_head_department,
                }
            )
        
        with transaction.atomic():
            ProgramOutcome.objects.create(text=text, course_name=course_name, faculty=faculty, created_by=creator)
        return redirect('program_outcomes')
    
    return render(request, 'faculty/create_outcome.html', {
        'faculty_name': faculty.name,
        'faculty_head_department': faculty_head_department,
    })

@faculty_head_required
def faculty_head_learning_outcomes(request):
    """Show learning outcomes for faculty head's own courses"""
    profile = getattr(request.user, 'profile', None)
    courses = []
    if profile:
        courses = profile.courses.all()
    
    course_names = [course.name for course in courses]
    
    outcomes_qs = ProgramOutcome.objects.filter(
        course_name__in=course_names
    ).select_related('created_by').order_by('-created_at')
    
    outcomes_data = []
    for o in outcomes_qs:
        creator_name = o.created_by.get_full_name() or o.created_by.username
        outcomes_data.append({
            'text': o.text,
            'course': o.course_name or '',
            'created_by': creator_name,
            'created_at': o.created_at.strftime('%Y-%m-%d %H:%M'),
        })
    
    return render(
        request,
        'faculty/learning_outcomes.html',
        {
            'outcomes_data': outcomes_data,
            'faculty_head_courses': course_names,
        }
    )

@faculty_head_required
def faculty_head_course_learning_outcomes(request, course_name):
    """Show and create learning outcomes for a specific course (for faculty head)"""
    course_name_slug = course_name
    course_name = course_name.replace('-', ' ')
    
    profile = getattr(request.user, 'profile', None)
    if profile:
        faculty_head_courses = profile.courses.all()
        course = None
        for c in faculty_head_courses:
            if c.name.lower() == course_name.lower():
                course = c
                break
        if not course:
            course = Course.objects.filter(name__iexact=course_name).first()
            if course and profile:
                with transaction.atomic():
                    profile.courses.add(course)
        if not course:
            return HttpResponseForbidden("You don't have access to this course.")
        course_id = course.id
        course_name = course.name
    else:
        course = Course.objects.filter(name__iexact=course_name).first()
        if not course:
            return HttpResponseForbidden("You don't have access to this course.")
        course_id = course.id
        course_name = course.name
    
    from .models import Faculty
    faculty = None
    if profile:
        faculty = profile.faculty
    
    program_outcomes = []
    if faculty:
        program_outcomes_qs = ProgramOutcome.objects.filter(
            faculty=faculty,
            course_name=''
        ).select_related('created_by').order_by('created_at')
        for po in program_outcomes_qs:
            program_outcomes.append({
                'id': po.id,
                'text': po.text,
            })
    
    if request.method == 'POST':
        text = (request.POST.get('text') or '').strip()
        if text:
            with transaction.atomic():
                learning_outcome = ProgramOutcome.objects.create(
                    text=text,
                    course_name=course_name,
                    created_by=request.user
                )
                selected_program_outcome_ids = request.POST.getlist('program_outcomes')
                if selected_program_outcome_ids:
                    program_outcomes_to_link = ProgramOutcome.objects.filter(
                        id__in=selected_program_outcome_ids,
                        faculty=faculty,
                        course_name=''
                    )
                    learning_outcome.related_program_outcomes.set(program_outcomes_to_link)
        course_name_slug = course_name.replace(' ', '-')
        return redirect('faculty_head_course_learning_outcomes', course_name=course_name_slug)
    
    outcomes_qs = ProgramOutcome.objects.filter(
        course_name=course_name
    ).select_related('created_by').prefetch_related('related_program_outcomes').order_by('-created_at')
    
    instructors_map = get_instructors_map()
    
    faculty_heads_map = get_faculty_heads_map()
    
    outcomes_data = []
    for o in outcomes_qs:
        creator_username = o.created_by.username
        creator_name = faculty_heads_map.get(creator_username) or instructors_map.get(creator_username) or o.created_by.get_full_name() or creator_username
        related_program_outcomes = o.related_program_outcomes.all()
        outcomes_data.append({
            'id': o.id,
            'text': o.text,
            'course': o.course_name or '',
            'created_by': creator_name,
            'created_at': o.created_at.strftime('%Y-%m-%d %H:%M'),
            'related_program_outcomes': [{'id': po.id, 'text': po.text} for po in related_program_outcomes],
        })
    
    if not course_id:
        return HttpResponseForbidden("You don't have access to this course.")
    
    return render(
        request,
        'faculty/course_learning_outcomes.html',
        {
            'course_name': course_name,
            'course_id': course_id,
            'outcomes_data': outcomes_data,
            'program_outcomes': program_outcomes,
        }
    )

@faculty_head_required
def faculty_head_learning_outcome_detail(request, course_id, outcome_id):
    """Show detail page for a learning outcome with linked program outcomes (for faculty head)"""
    profile = getattr(request.user, 'profile', None)
    course = get_object_or_404(Course, id=course_id)
    if profile:
        if course not in profile.courses.all():
            profile.courses.add(course)
    
    outcome = get_object_or_404(ProgramOutcome, id=outcome_id, course_name=course.name)
    
    from .models import Faculty
    faculty = None
    if profile:
        faculty = profile.faculty
    
    related_program_outcomes = outcome.related_program_outcomes.all().order_by('id')
    
    from .models import LearningOutcomeProgramOutcome
    program_outcomes_data = []
    for po in related_program_outcomes:
        try:
            lo_po = LearningOutcomeProgramOutcome.objects.get(learning_outcome=outcome, program_outcome=po)
            percentage = lo_po.percentage
        except LearningOutcomeProgramOutcome.DoesNotExist:
            percentage = 0
        program_outcomes_data.append({
            'id': po.id,
            'text': po.text,
            'percentage': percentage,
        })
    
    available_program_outcomes = []
    if faculty:
        available_program_outcomes_qs = ProgramOutcome.objects.filter(
            faculty=faculty,
            course_name=''
        ).exclude(id__in=[po.id for po in related_program_outcomes]).select_related('created_by').order_by('created_at')
        for po in available_program_outcomes_qs:
            available_program_outcomes.append({
                'id': po.id,
                'text': po.text,
            })
    
    course_name_slug = outcome.course_name.replace(' ', '-')
    
    referer = request.META.get('HTTP_REFERER', '')
    from_all_courses = 'all-courses' in referer
    
    return render(
        request,
        'faculty/learning_outcome_detail.html',
        {
            'outcome': outcome,
            'course': course,
            'program_outcomes': program_outcomes_data,
            'available_program_outcomes': available_program_outcomes,
            'course_name_slug': course_name_slug,
            'from_all_courses': from_all_courses,
        }
    )

@faculty_head_required
def faculty_head_learning_outcome_graph(request, course_id, outcome_id):
    """Show graph view for learning outcome (for faculty head)"""
    profile = getattr(request.user, 'profile', None)
    if profile:
        course = profile.courses.filter(id=course_id).first()
        if not course:
            return HttpResponseForbidden("You don't have access to this course.")
    else:
        course = get_object_or_404(Course, id=course_id)
    
    outcome = get_object_or_404(ProgramOutcome, id=outcome_id, course_name=course.name)
    
    related_program_outcomes = outcome.related_program_outcomes.all().order_by('id')
    
    from .models import LearningOutcomeProgramOutcome
    program_outcomes_data = []
    for po in related_program_outcomes:
        try:
            lo_po = LearningOutcomeProgramOutcome.objects.get(learning_outcome=outcome, program_outcome=po)
            percentage = lo_po.percentage
        except LearningOutcomeProgramOutcome.DoesNotExist:
            percentage = 0
        program_outcomes_data.append({
            'id': po.id,
            'text': po.text,
            'percentage': percentage,
        })
    
    course_name_slug = outcome.course_name.replace(' ', '-')
    
    return render(
        request,
        'faculty/learning_outcome_graph.html',
        {
            'outcome': outcome,
            'course': course,
            'program_outcomes': program_outcomes_data,
            'course_name_slug': course_name_slug,
        }
    )


@faculty_head_required
def faculty_head_update_learning_outcome(request, outcome_id):
    """Update a learning outcome (for faculty head)"""
    outcome = get_object_or_404(ProgramOutcome, id=outcome_id)
    
    if request.method == 'POST':
        text = (request.POST.get('text') or '').strip()
        if text:
            with transaction.atomic():
                outcome.text = text
                outcome.save()
        profile = getattr(request.user, 'profile', None)
        if profile:
            course = None
            for c in profile.courses.all():
                if c.name.lower() == outcome.course_name.lower():
                    course = c
                    break
            if not course:
                course = Course.objects.filter(name__iexact=outcome.course_name).first()
                if course and profile:
                    with transaction.atomic():
                        profile.courses.add(course)
            course_id = course.id if course else None
            if course_id:
                return redirect('faculty_head_learning_outcome_detail', course_id=course_id, outcome_id=outcome_id)
        course_name_slug = outcome.course_name.replace(' ', '-')
        return redirect('faculty_head_course_learning_outcomes', course_name=course_name_slug)
    
    return JsonResponse({'text': outcome.text})

@faculty_head_required
def faculty_head_delete_learning_outcome(request, outcome_id):
    """Delete a learning outcome (for faculty head)"""
    profile = getattr(request.user, 'profile', None)
    outcome = get_object_or_404(ProgramOutcome, id=outcome_id, course_name__isnull=False)
    
    course_name = outcome.course_name
    course_name_slug = course_name.replace(' ', '-')
    
    with transaction.atomic():
        outcome.delete()
    
    referer = request.META.get('HTTP_REFERER', '')
    if 'all-courses' in referer:
        return redirect('all_courses')
    
    return redirect('faculty_head_course_learning_outcomes', course_name=course_name_slug)

@faculty_head_required
def faculty_head_unlink_program_outcome(request, outcome_id, program_outcome_id):
    """Unlink a program outcome from a learning outcome (for faculty head)"""
    outcome = get_object_or_404(ProgramOutcome, id=outcome_id)
    program_outcome = get_object_or_404(ProgramOutcome, id=program_outcome_id)
    
    with transaction.atomic():
        outcome.related_program_outcomes.remove(program_outcome)
    
    profile = getattr(request.user, 'profile', None)
    if profile:
        course = None
        for c in profile.courses.all():
            if c.name.lower() == outcome.course_name.lower():
                course = c
                break
        if not course:
            course = Course.objects.filter(name__iexact=outcome.course_name).first()
            if course and profile:
                with transaction.atomic():
                    profile.courses.add(course)
        course_id = course.id if course else None
        if course_id:
            return redirect('faculty_head_learning_outcome_detail', course_id=course_id, outcome_id=outcome_id)
    course_name_slug = outcome.course_name.replace(' ', '-')
    return redirect('faculty_head_course_learning_outcomes', course_name=course_name_slug)

@faculty_head_required
def faculty_head_link_program_outcomes(request, outcome_id):
    """Link program outcomes to a learning outcome (for faculty head)"""
    outcome = get_object_or_404(ProgramOutcome, id=outcome_id)
    
    if request.method == 'POST':
        selected_program_outcome_ids = request.POST.getlist('program_outcomes')
        if selected_program_outcome_ids:
            profile = getattr(request.user, 'profile', None)
            faculty = None
            if profile:
                faculty = profile.faculty
            
            if faculty:
                with transaction.atomic():
                    program_outcomes_to_link = ProgramOutcome.objects.filter(
                        id__in=selected_program_outcome_ids,
                        faculty=faculty,
                        course_name=''
                    )
                    outcome.related_program_outcomes.add(*program_outcomes_to_link)
    
    profile = getattr(request.user, 'profile', None)
    if profile:
        course = None
        for c in profile.courses.all():
            if c.name.lower() == outcome.course_name.lower():
                course = c
                break
        if not course:
            course = Course.objects.filter(name__iexact=outcome.course_name).first()
            if course and profile:
                profile.courses.add(course)
        course_id = course.id if course else None
        if course_id:
            return redirect('faculty_head_learning_outcome_detail', course_id=course_id, outcome_id=outcome_id)
    course_name_slug = outcome.course_name.replace(' ', '-')
    return redirect('faculty_head_course_learning_outcomes', course_name=course_name_slug)

@faculty_head_required
def give_grade(request, course_id):
    course = get_object_or_404(Course, id=course_id)
    return render(request, 'faculty/give_grade.html', {'course': course})

@faculty_head_required
def faculty_head_grades(request):
    profile = getattr(request.user, 'profile', None)
    
    # Get faculty head's department
    faculty_head_data = get_faculty_head_data(request.user.username)
    faculty_head_department = faculty_head_data.get('department')
    
    courses = []
    if profile:
        # Get courses from profile, filtered by department
        all_courses = profile.courses.all()
        for course in all_courses:
            if faculty_head_department and course.department != faculty_head_department:
                continue
            courses.append(course.name)
    
    context = {
        'faculty_head_courses': courses,
        'faculty_head': json.dumps(faculty_head_data),
        'user': request.user,
    }
    return render(request, 'faculty/faculty_head_grades.html', context)

@faculty_head_required
def faculty_head_course_grades(request, course_name):
    from django.utils import timezone
    from datetime import datetime
    
    profile = getattr(request.user, 'profile', None)
    faculty_head_data = get_faculty_head_data(request.user.username)
    faculty_head_department = faculty_head_data.get('department')
    
    try:
        course = Course.objects.get(name=course_name)
    except Course.DoesNotExist:
        return redirect('faculty-head-grades')
    
    # Check if faculty head has access to this course
    if profile and course not in profile.courses.all():
        return HttpResponseForbidden("You don't have access to this course")
    
    # Check department match
    if faculty_head_department and course.department != faculty_head_department:
        return HttpResponseForbidden("You don't have access to this course")
    
    # Course'a kayıtlı öğrencileri al
    students = Student.objects.filter(courses=course).order_by('username')
    students_with_grades = []
    for student in students:
        grade_obj = Grade.objects.filter(student=student, course=course).first()
        grades_dict = {}
        is_finalized = False
        
        if grade_obj:
            # Yeni JSONField'dan notları al
            if grade_obj.grades:
                grades_dict = grade_obj.grades
            # Eski alanlardan notları al (geriye dönük uyumluluk)
            elif grade_obj.midterm is not None or grade_obj.assignment is not None or grade_obj.final is not None:
                if grade_obj.midterm is not None:
                    grades_dict['Midterm'] = grade_obj.midterm
                if grade_obj.assignment is not None:
                    grades_dict['Assignment'] = grade_obj.assignment
                if grade_obj.final is not None:
                    grades_dict['Final'] = grade_obj.final
            
            is_finalized = grade_obj.is_finalized
        
        students_with_grades.append({
            'student': student,
            'grades': grades_dict,
            'is_finalized': is_finalized
        })
    
    # Uploaded file bilgisini al (course'daki herhangi bir grade'den)
    uploaded_file = None
    grade_with_file = Grade.objects.filter(course=course).exclude(uploaded_file_name='').first()
    if grade_with_file and grade_with_file.uploaded_file_name:
        uploaded_file = {
            'name': grade_with_file.uploaded_file_name,
            'uploaded_at': grade_with_file.uploaded_at
        }
    
    is_finalized = all(item['is_finalized'] for item in students_with_grades if item['grades'])
    students_with_grades_json = json.dumps([
        {
            'id': item['student'].id,
            'username': item['student'].username,
            'first_name': item['student'].first_name or '',
            'last_name': item['student'].last_name or '',
            'grades': item['grades'],
            'is_finalized': item['is_finalized']
        }
        for item in students_with_grades
    ])
    
    return render(request, 'faculty/faculty_head_course_grades.html', {
        'course': course,
        'students': students,
        'students_with_grades': students_with_grades,
        'students_with_grades_json': students_with_grades_json,
        'uploaded_file': uploaded_file,
        'is_finalized': is_finalized
    })

@faculty_head_required
@csrf_exempt
def faculty_head_delete_uploaded_csv(request, course_name):
    if request.method != 'POST':
        return JsonResponse({'error': 'Method not allowed'}, status=405)
    
    profile = getattr(request.user, 'profile', None)
    faculty_head_data = get_faculty_head_data(request.user.username)
    faculty_head_department = faculty_head_data.get('department')
    
    try:
        course = Course.objects.get(name=course_name)
    except Course.DoesNotExist:
        return JsonResponse({'error': 'Course not found'}, status=404)
    
    if profile and course not in profile.courses.all():
        return JsonResponse({'error': 'Access denied'}, status=403)
    
    if faculty_head_department and course.department != faculty_head_department:
        return JsonResponse({'error': 'Access denied'}, status=403)
    
    # Course'daki tüm grade'lerden uploaded file bilgisini temizle
    Grade.objects.filter(course=course).update(
        uploaded_file_name='',
        uploaded_at=None
    )
    
    return JsonResponse({'status': 'ok'})

@faculty_head_required
@csrf_exempt
def faculty_head_update_manual_grades(request, course_name):
    if request.method != 'POST':
        return JsonResponse({'error': 'Method not allowed'}, status=405)
    
    profile = getattr(request.user, 'profile', None)
    faculty_head_data = get_faculty_head_data(request.user.username)
    faculty_head_department = faculty_head_data.get('department')
    
    try:
        course = Course.objects.get(name=course_name)
    except Course.DoesNotExist:
        return JsonResponse({'error': 'Course not found'}, status=404)
    
    if profile and course not in profile.courses.all():
        return JsonResponse({'error': 'Access denied'}, status=403)
    
    if faculty_head_department and course.department != faculty_head_department:
        return JsonResponse({'error': 'Access denied'}, status=403)
    
    # Grade'ler finalized mi kontrol et
    finalized_grades = Grade.objects.filter(course=course, is_finalized=True).exists()
    if finalized_grades:
        return JsonResponse({'error': 'Grades are finalized and cannot be updated'}, status=400)
    
    try:
        data = json.loads(request.body)
        students_data = data.get('students', [])
        
        with transaction.atomic():
            for student_data in students_data:
                student_id = student_data.get('student_id')
                grades_list = student_data.get('grades', [])
                
                try:
                    student = Student.objects.get(id=student_id)
                except Student.DoesNotExist:
                    continue
                
                # Grades dict'ini oluştur
                grades_dict = {}
                for grade_item in grades_list:
                    grade_name = grade_item.get('name', '').strip()
                    grade_score = grade_item.get('score')
                    if grade_name and grade_score is not None:
                        try:
                            grades_dict[grade_name] = float(grade_score)
                        except (ValueError, TypeError):
                            continue
                
                # Grade objesini güncelle veya oluştur
                Grade.objects.update_or_create(
                    student=student,
                    course=course,
                    defaults={'grades': grades_dict}
                )
        
        return JsonResponse({'status': 'ok'})
    except (json.JSONDecodeError, KeyError, ValueError) as e:
        return JsonResponse({'error': f'Invalid data: {str(e)}'}, status=400)

@faculty_head_required
@csrf_exempt
def faculty_head_finalize_grades(request, course_name):
    if request.method != 'POST':
        return JsonResponse({'error': 'Method not allowed'}, status=405)
    
    from django.utils import timezone
    
    profile = getattr(request.user, 'profile', None)
    faculty_head_data = get_faculty_head_data(request.user.username)
    faculty_head_department = faculty_head_data.get('department')
    
    try:
        course = Course.objects.get(name=course_name)
    except Course.DoesNotExist:
        return JsonResponse({'error': 'Course not found'}, status=404)
    
    if profile and course not in profile.courses.all():
        return JsonResponse({'error': 'Access denied'}, status=403)
    
    if faculty_head_department and course.department != faculty_head_department:
        return JsonResponse({'error': 'Access denied'}, status=403)
    
    # Course'daki tüm grade'leri finalized yap
    with transaction.atomic():
        Grade.objects.filter(course=course).update(
            is_finalized=True,
            finalized_at=timezone.now()
        )
    
    return JsonResponse({'status': 'ok'})


@instructor_required
def learning_outcomes(request):
    """Show learning outcomes for instructor's own courses only"""
    instructor_user = request.instructor_user
    username = instructor_user.username
    
    instructor_courses = Course.objects.filter(instructor=instructor_user)
    course_names_from_db = [course.name for course in instructor_courses]
    
    instructor_data = get_instructor_data(username)
    course_names_from_json = instructor_data.get('courses', []) or []
    
    course_names = list(set(course_names_from_db + course_names_from_json))
    
    outcomes_qs = ProgramOutcome.objects.filter(
        course_name__in=course_names
    ).select_related('created_by').order_by('-created_at')
    
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
        'instructor/learning_outcomes.html',
        {
            'outcomes_data': outcomes_data,
            'instructor_courses': course_names,
        }
    )


@instructor_required
def course_learning_outcomes(request, course_name):
    """Show learning outcomes for a specific course (only if instructor owns it)"""
    course_name = course_name.replace('-', ' ')
    instructor_user = request.instructor_user
    username = instructor_user.username
    
    instructor_data = get_instructor_data(username)
    instructor_department = instructor_data.get('department')
    instructor_faculty = instructor_data.get('faculty')
    
    # Faculty head department'ı bul
    faculty_head_department = None
    if instructor_department:
        try:
            faculty_head = User.objects.select_related('profile').get(
                profile__role='faculty_head',
                profile__department=instructor_department
            )
            faculty_head_department = faculty_head.profile.department
        except User.DoesNotExist:
            pass
    
    from .models import Faculty
    faculty = None
    if instructor_faculty:
        with transaction.atomic():
            try:
                faculty = Faculty.objects.get(slug=instructor_faculty.lower())
            except Faculty.DoesNotExist:
                faculty, _ = Faculty.objects.get_or_create(
                    slug=instructor_faculty.lower(),
                    defaults={'name': instructor_faculty}
                )
    
    program_outcomes = []
    if faculty:
        program_outcomes_qs = ProgramOutcome.objects.filter(
            faculty=faculty,
            course_name=''
        ).select_related('created_by').order_by('created_at')
        for po in program_outcomes_qs:
            program_outcomes.append({
                'id': po.id,
                'text': po.text,
            })
    
    if request.method == 'POST':
        text = (request.POST.get('text') or '').strip()
        if text:
            selected_program_outcome_ids = request.POST.getlist('program_outcomes')
            error_message = None
            
            if selected_program_outcome_ids:
                from .models import LearningOutcomeProgramOutcome
                program_outcomes_to_link = ProgramOutcome.objects.filter(
                    id__in=selected_program_outcome_ids,
                    faculty=faculty,
                    course_name=''
                )
                for po in program_outcomes_to_link:
                    percentage_key = f'po_percentage_{po.id}'
                    percentage_value = request.POST.get(percentage_key, '').strip()
                    if not percentage_value:
                        error_message = 'You have to enter a percentage on how much the learning outcome affects the program outcome(s).'
                        break
                    try:
                        percentage = int(percentage_value)
                        if percentage < 0:
                            error_message = 'Percentage must be between 0 and 100.'
                            break
                        if percentage > 100:
                            error_message = 'Percentage cannot exceed 100. Please enter a value between 0 and 100.'
                            break
                    except (ValueError, TypeError):
                        error_message = 'Invalid percentage value.'
                        break
                
                if not error_message:
                    learning_outcome = ProgramOutcome.objects.create(
                        text=text, 
                        course_name=course_name, 
                        created_by=instructor_user
                    )
                    for po in program_outcomes_to_link:
                        percentage_key = f'po_percentage_{po.id}'
                        percentage_value = request.POST.get(percentage_key, '').strip()
                        percentage = int(percentage_value)
                        LearningOutcomeProgramOutcome.objects.create(
                            learning_outcome=learning_outcome,
                            program_outcome=po,
                            percentage=percentage
                        )
                    course_name_slug = course_name.replace(' ', '-')
                    return redirect('course_learning_outcomes', course_name=course_name_slug)
                else:
                    outcomes_qs = ProgramOutcome.objects.filter(
                        course_name=course_name
                    ).select_related('created_by').prefetch_related('related_program_outcomes').order_by('-created_at')
                    
                    course = Course.objects.filter(name=course_name, instructor=instructor_user).first()
                    course_id = course.id if course else None
                    
                    outcomes_data = []
                    for o in outcomes_qs:
                        creator_name = o.created_by.get_full_name() or o.created_by.username
                        related_program_outcomes = o.related_program_outcomes.all()
                        outcomes_data.append(
                            {
                                'id': o.id,
                                'text': o.text,
                                'course': o.course_name or '',
                                'created_by': creator_name,
                                'created_at': o.created_at.strftime('%Y-%m-%d %H:%M'),
                                'related_program_outcomes': [{'id': po.id, 'text': po.text} for po in related_program_outcomes],
                            }
                        )
                    
                    return render(
                        request,
                        'instructor/course_learning_outcomes.html',
                        {
                            'course_name': course_name,
                            'course_id': course_id,
                            'outcomes_data': outcomes_data,
                            'program_outcomes': program_outcomes,
                            'error_message': error_message,
                        }
                    )
            else:
                learning_outcome = ProgramOutcome.objects.create(
                    text=text, 
                    course_name=course_name, 
                    created_by=instructor_user
                )
                course_name_slug = course_name.replace(' ', '-')
                return redirect('course_learning_outcomes', course_name=course_name_slug)
    
    outcomes_qs = ProgramOutcome.objects.filter(
        course_name=course_name
    ).select_related('created_by').prefetch_related('related_program_outcomes').order_by('-created_at')
    
    course = Course.objects.filter(name=course_name, instructor=instructor_user).first()
    course_id = course.id if course else None
    
    outcomes_data = []
    for o in outcomes_qs:
        creator_name = o.created_by.get_full_name() or o.created_by.username
        related_program_outcomes = o.related_program_outcomes.all()
        outcomes_data.append(
            {
                'id': o.id,
                'text': o.text,
                'course': o.course_name or '',
                'created_by': creator_name,
                'created_at': o.created_at.strftime('%Y-%m-%d %H:%M'),
                'related_program_outcomes': [{'id': po.id, 'text': po.text} for po in related_program_outcomes],
            }
        )
    
    return render(
        request,
        'instructor/course_learning_outcomes.html',
        {
            'course_name': course_name,
            'course_id': course_id,
            'outcomes_data': outcomes_data,
            'program_outcomes': program_outcomes,
        }
    )


@instructor_required
def update_learning_outcome(request, outcome_id):
    """Update a learning outcome"""
    instructor_user = request.instructor_user
    username = instructor_user.username
    
    outcome = get_object_or_404(ProgramOutcome, id=outcome_id, created_by=instructor_user)
    
    if request.method == 'POST':
        text = (request.POST.get('text') or '').strip()
        if text:
            with transaction.atomic():
                outcome.text = text
                outcome.save()
        course = Course.objects.filter(name=outcome.course_name, instructor=instructor_user).first()
        course_id = course.id if course else None
        if course_id:
            return redirect('learning_outcome_detail', course_id=course_id, outcome_id=outcome_id)
        else:
            course_name_slug = outcome.course_name.replace(' ', '-')
            return redirect('course_learning_outcomes', course_name=course_name_slug)
    
    return JsonResponse({'text': outcome.text})


def learning_outcome_detail(request, course_id, outcome_id):
    """Show detail page for a learning outcome with linked program outcomes"""
    is_faculty_head = False
    instructor_user = None
    faculty = None
    
    if request.user.is_authenticated:
        profile = getattr(request.user, 'profile', None)
        if profile and profile.role == 'faculty_head':
            is_faculty_head = True
            course = get_object_or_404(Course, id=course_id)
            outcome = get_object_or_404(ProgramOutcome, id=outcome_id, course_name=course.name)
            faculty = profile.faculty if profile else None
        else:
            # Instructor kontrolü - Django'nun standart authentication kullan
            if not hasattr(request, 'instructor_user'):
                # User'ın gerçekten instructor olduğunu kontrol et
                try:
                    user_profile = request.user.profile
                    if user_profile.role != 'instructor':
                        from django.http import HttpResponseForbidden
                        return HttpResponseForbidden("You are not allowed here")
                except AttributeError:
                    from django.http import HttpResponseForbidden
                    return HttpResponseForbidden("User profile not found")
                request.instructor_user = request.user
            instructor_user = request.instructor_user
            course = get_object_or_404(Course, id=course_id, instructor=instructor_user)
            outcome = get_object_or_404(ProgramOutcome, id=outcome_id, course_name=course.name, created_by=instructor_user)
            
            instructor_data = get_instructor_data(instructor_user.username)
            instructor_department = instructor_data.get('department')
            instructor_faculty = instructor_data.get('faculty')
            
            from .models import Faculty
            if instructor_faculty:
                with transaction.atomic():
                    try:
                        faculty = Faculty.objects.get(slug=instructor_faculty.lower())
                    except Faculty.DoesNotExist:
                        faculty, _ = Faculty.objects.get_or_create(
                            slug=instructor_faculty.lower(),
                            defaults={'name': instructor_faculty}
                        )
    else:
        from django.shortcuts import redirect
        return redirect('faculty-head-login')
    
    from .models import LearningOutcomeProgramOutcome
    related_program_outcomes = outcome.related_program_outcomes.all().order_by('id')
    
    program_outcomes_data = []
    for po in related_program_outcomes:
        try:
            lo_po = LearningOutcomeProgramOutcome.objects.get(learning_outcome=outcome, program_outcome=po)
            percentage = lo_po.percentage
        except LearningOutcomeProgramOutcome.DoesNotExist:
            percentage = 0
        program_outcomes_data.append({
            'id': po.id,
            'text': po.text,
            'percentage': percentage,
        })
    
    available_program_outcomes = []
    if faculty:
        available_program_outcomes_qs = ProgramOutcome.objects.filter(
            faculty=faculty,
            course_name=''
        ).exclude(id__in=[po.id for po in related_program_outcomes]).select_related('created_by').order_by('created_at')
        for po in available_program_outcomes_qs:
            available_program_outcomes.append({
                'id': po.id,
                'text': po.text,
            })
    
    course_name_slug = outcome.course_name.replace(' ', '-')
    
    return render(
        request,
        'instructor/learning_outcome_detail.html',
        {
            'outcome': outcome,
            'course': course,
            'program_outcomes': program_outcomes_data,
            'available_program_outcomes': available_program_outcomes,
            'course_name_slug': course_name_slug,
            'is_faculty_head': is_faculty_head,
        }
    )

def learning_outcome_graph(request, course_id, outcome_id):
    """Show graph view for learning outcome"""
    is_faculty_head = False
    instructor_user = None
    
    if request.user.is_authenticated:
        profile = getattr(request.user, 'profile', None)
        if profile and profile.role == 'faculty_head':
            is_faculty_head = True
            course = get_object_or_404(Course, id=course_id)
            outcome = get_object_or_404(ProgramOutcome, id=outcome_id, course_name=course.name)
        else:
            # Instructor kontrolü - Django'nun standart authentication kullan
            if not hasattr(request, 'instructor_user'):
                # User'ın gerçekten instructor olduğunu kontrol et
                try:
                    user_profile = request.user.profile
                    if user_profile.role != 'instructor':
                        from django.http import HttpResponseForbidden
                        return HttpResponseForbidden("You are not allowed here")
                except AttributeError:
                    from django.http import HttpResponseForbidden
                    return HttpResponseForbidden("User profile not found")
                request.instructor_user = request.user
            instructor_user = request.instructor_user
            course = get_object_or_404(Course, id=course_id, instructor=instructor_user)
            outcome = get_object_or_404(ProgramOutcome, id=outcome_id, course_name=course.name, created_by=instructor_user)
    else:
        from django.shortcuts import redirect
        return redirect('faculty-head-login')
    
    from .models import LearningOutcomeProgramOutcome
    related_program_outcomes = outcome.related_program_outcomes.all().order_by('id')
    
    program_outcomes_data = []
    for po in related_program_outcomes:
        try:
            lo_po = LearningOutcomeProgramOutcome.objects.get(learning_outcome=outcome, program_outcome=po)
            percentage = lo_po.percentage
        except LearningOutcomeProgramOutcome.DoesNotExist:
            percentage = 0
        program_outcomes_data.append({
            'id': po.id,
            'text': po.text,
            'percentage': percentage,
        })
    
    course_name_slug = outcome.course_name.replace(' ', '-')
    
    return render(
        request,
        'instructor/learning_outcome_graph.html',
        {
            'outcome': outcome,
            'course': course,
            'program_outcomes': program_outcomes_data,
            'course_name_slug': course_name_slug,
            'is_faculty_head': is_faculty_head,
        }
    )


@instructor_required
def update_percentage(request, outcome_id, program_outcome_id):
    """Update percentage for a linked program outcome"""
    from django.http import JsonResponse
    instructor_user = request.instructor_user
    outcome = get_object_or_404(ProgramOutcome, id=outcome_id, created_by=instructor_user)
    
    if request.method == 'POST':
        percentage_value = request.POST.get('percentage', '').strip()
        if not percentage_value:
            return JsonResponse({'status': 'error', 'message': 'You have to enter a percentage on how much the learning outcome affects the program outcome(s).'}, status=400)
        
        try:
            percentage = int(percentage_value)
            if percentage < 0 or percentage > 100:
                return JsonResponse({'status': 'error', 'message': 'Percentage must be between 0 and 100.'}, status=400)
        except (ValueError, TypeError):
            return JsonResponse({'status': 'error', 'message': 'Invalid percentage value.'}, status=400)
        
        from .models import LearningOutcomeProgramOutcome
        program_outcome = get_object_or_404(ProgramOutcome, id=program_outcome_id)
        
        try:
            lo_po = LearningOutcomeProgramOutcome.objects.get(learning_outcome=outcome, program_outcome=program_outcome)
            lo_po.percentage = percentage
            lo_po.save()
        except LearningOutcomeProgramOutcome.DoesNotExist:
            return JsonResponse({'status': 'error', 'message': 'Program outcome is not linked to this learning outcome.'}, status=404)
        
        return JsonResponse({'status': 'success', 'percentage': percentage})
    
    return JsonResponse({'status': 'error', 'message': 'Invalid request method.'}, status=405)

@faculty_head_required
def faculty_head_update_percentage(request, outcome_id, program_outcome_id):
    """Update percentage for a linked program outcome (for faculty head)"""
    from django.http import JsonResponse
    outcome = get_object_or_404(ProgramOutcome, id=outcome_id)
    
    if request.method == 'POST':
        percentage_value = request.POST.get('percentage', '').strip()
        if not percentage_value:
            return JsonResponse({'status': 'error', 'message': 'You have to enter a percentage on how much the learning outcome affects the program outcome(s).'}, status=400)
        
        try:
            percentage = int(percentage_value)
            if percentage < 0 or percentage > 100:
                return JsonResponse({'status': 'error', 'message': 'Percentage must be between 0 and 100.'}, status=400)
        except (ValueError, TypeError):
            return JsonResponse({'status': 'error', 'message': 'Invalid percentage value.'}, status=400)
        
        from .models import LearningOutcomeProgramOutcome
        program_outcome = get_object_or_404(ProgramOutcome, id=program_outcome_id)
        
        try:
            lo_po = LearningOutcomeProgramOutcome.objects.get(learning_outcome=outcome, program_outcome=program_outcome)
            lo_po.percentage = percentage
            lo_po.save()
        except LearningOutcomeProgramOutcome.DoesNotExist:
            return JsonResponse({'status': 'error', 'message': 'Program outcome is not linked to this learning outcome.'}, status=404)
        
        return JsonResponse({'status': 'success', 'percentage': percentage})
    
    return JsonResponse({'status': 'error', 'message': 'Invalid request method.'}, status=405)

@instructor_required
def unlink_program_outcome(request, outcome_id, program_outcome_id):
    """Unlink a program outcome from a learning outcome"""
    instructor_user = request.instructor_user
    outcome = get_object_or_404(ProgramOutcome, id=outcome_id, created_by=instructor_user)
    program_outcome = get_object_or_404(ProgramOutcome, id=program_outcome_id)
    
    with transaction.atomic():
        outcome.related_program_outcomes.remove(program_outcome)
    
    course = Course.objects.filter(name=outcome.course_name, instructor=instructor_user).first()
    course_id = course.id if course else None
    if course_id:
        return redirect('learning_outcome_detail', course_id=course_id, outcome_id=outcome_id)
    else:
        course_name_slug = outcome.course_name.replace(' ', '-')
        return redirect('course_learning_outcomes', course_name=course_name_slug)


@instructor_required
def link_program_outcomes(request, outcome_id):
    """Link program outcomes to a learning outcome"""
    instructor_user = request.instructor_user
    outcome = get_object_or_404(ProgramOutcome, id=outcome_id, created_by=instructor_user)
    
    if request.method == 'POST':
        selected_program_outcome_ids = request.POST.getlist('program_outcomes')
        if selected_program_outcome_ids:
            instructor_department = None
            instructor_data = get_instructor_data(instructor_user.username)
            instructor_faculty = instructor_data.get('faculty')
            
            from .models import Faculty
            faculty = None
            if instructor_faculty:
                with transaction.atomic():
                    try:
                        faculty = Faculty.objects.get(slug=instructor_faculty.lower())
                    except Faculty.DoesNotExist:
                        faculty, _ = Faculty.objects.get_or_create(
                            slug=instructor_faculty.lower(),
                            defaults={'name': instructor_faculty}
                        )
            
            if faculty:
                from .models import LearningOutcomeProgramOutcome
                error_message = None
                program_outcomes_to_link = ProgramOutcome.objects.filter(
                    id__in=selected_program_outcome_ids,
                    faculty=faculty,
                    course_name=''
                )
                for po in program_outcomes_to_link:
                    percentage_key = f'po_percentage_{po.id}'
                    percentage_value = request.POST.get(percentage_key, '').strip()
                    if not percentage_value:
                        error_message = 'You have to enter a percentage on how much the learning outcome affects the program outcome(s).'
                        break
                    try:
                        percentage = int(percentage_value)
                        if percentage < 0:
                            error_message = 'Percentage must be between 0 and 100.'
                            break
                        if percentage > 100:
                            error_message = 'Percentage cannot exceed 100. Please enter a value between 0 and 100.'
                            break
                    except (ValueError, TypeError):
                        error_message = 'Invalid percentage value.'
                        break
                
                if not error_message:
                    with transaction.atomic():
                        for po in program_outcomes_to_link:
                            percentage_key = f'po_percentage_{po.id}'
                            percentage_value = request.POST.get(percentage_key, '').strip()
                            percentage = int(percentage_value)
                            LearningOutcomeProgramOutcome.objects.get_or_create(
                                learning_outcome=outcome,
                                program_outcome=po,
                                defaults={'percentage': percentage}
                            )
                else:
                    course = Course.objects.filter(name=outcome.course_name, instructor=instructor_user).first()
                    course_id = course.id if course else None
                    if course_id:
                        from .models import LearningOutcomeProgramOutcome
                        related_program_outcomes = outcome.related_program_outcomes.all().order_by('id')
                        program_outcomes_data = []
                        for po in related_program_outcomes:
                            try:
                                lo_po = LearningOutcomeProgramOutcome.objects.get(learning_outcome=outcome, program_outcome=po)
                                percentage = lo_po.percentage
                            except LearningOutcomeProgramOutcome.DoesNotExist:
                                percentage = 0
                            program_outcomes_data.append({
                                'id': po.id,
                                'text': po.text,
                                'percentage': percentage,
                            })
                        available_program_outcomes = []
                        if faculty:
                            available_program_outcomes_qs = ProgramOutcome.objects.filter(
                                faculty=faculty,
                                course_name=''
                            ).exclude(id__in=[po.id for po in related_program_outcomes]).select_related('created_by').order_by('created_at')
                            for po in available_program_outcomes_qs:
                                available_program_outcomes.append({
                                    'id': po.id,
                                    'text': po.text,
                                })
                        course_name_slug = outcome.course_name.replace(' ', '-')
                        return render(
                            request,
                            'instructor/learning_outcome_detail.html',
                            {
                                'outcome': outcome,
                                'course': course,
                                'program_outcomes': program_outcomes_data,
                                'available_program_outcomes': available_program_outcomes,
                                'course_name_slug': course_name_slug,
                                'is_faculty_head': False,
                                'error_message': error_message,
                            }
                        )
    
    # course_id'yi bul - learning_outcome_detail için gerekli
    course = Course.objects.filter(
        name=outcome.course_name,
        instructor=instructor_user
    ).first()
    
    if course:
        return redirect(
            'learning_outcome_detail',
            course_id=course.id,
            outcome_id=outcome_id
        )
    else:
        # Course bulunamazsa course_learning_outcomes'a yönlendir
        course_name_slug = outcome.course_name.replace(' ', '-')
        return redirect('course_learning_outcomes', course_name=course_name_slug)


@instructor_required
def delete_learning_outcome(request, outcome_id):
    """Delete a learning outcome"""
    instructor_user = request.instructor_user
    username = instructor_user.username
    
    outcome = get_object_or_404(ProgramOutcome, id=outcome_id, created_by=instructor_user)
    course_name = outcome.course_name
    with transaction.atomic():
        outcome.delete()
    
    course_name_slug = course_name.replace(' ', '-')
    return redirect('course_learning_outcomes', course_name=course_name_slug)


@instructor_required
def create_learning_outcome(request):
    """Create a learning outcome for instructor's own course"""
    instructor_user = request.instructor_user
    username = instructor_user.username
    
    instructor_data = get_instructor_data(username)
    instructor_courses_from_json = instructor_data.get('courses', []) or []
    
    course_names_from_db = [c.name for c in Course.objects.filter(instructor=instructor_user)]
    all_available_courses = list(set(course_names_from_db + instructor_courses_from_json))
    
    if request.method == 'POST':
        text = (request.POST.get('text') or '').strip()
        course_name = (request.POST.get('course_name') or '').strip()
        
        if not course_name or not text:
            instructor_courses = Course.objects.filter(instructor=instructor_user)
            course_names_from_db = [course.name for course in instructor_courses]
            instructor_data = get_instructor_data(username)
            course_names_from_json = instructor_data.get('courses', []) or []
            course_names = list(set(course_names_from_db + course_names_from_json))
            
            return render(
                request,
                'instructor/create_learning_outcome.html',
                {
                    'error': 'Outcome text and course are required.',
                    'course_name': course_name,
                    'instructor_courses': course_names,
                }
            )
        
        with transaction.atomic():
            ProgramOutcome.objects.create(text=text, course_name=course_name, created_by=instructor_user)
        from django.urls import reverse
        course_name_slug = course_name.replace(' ', '-')
        redirect_url = reverse('course_learning_outcomes', args=[course_name_slug])
        redirect_url += f'?username={username}'
        return redirect(redirect_url)
    
    instructor_courses = Course.objects.filter(instructor=instructor_user)
    course_names_from_db = [course.name for course in instructor_courses]
    
    instructor_data = get_instructor_data(username)
    course_names_from_json = instructor_data.get('courses', []) or []
    
    course_names = list(set(course_names_from_db + course_names_from_json))
    
    course_name_from_get = request.GET.get('course', '')
    
    return render(
        request,
        'instructor/create_learning_outcome.html',
        {
            'course_name': course_name_from_get,
            'instructor_courses': course_names,
        }
    )

def student_profile(request):
    if not request.user.is_authenticated:
        return redirect('student-login')
    
    try:
        student = Student.objects.get(user=request.user)
        courses = student.courses.all()
        courses_list = [course.name for course in courses]
        
        profile_data = {
            'name': f"{student.first_name} {student.last_name}".strip() or student.username,
            'username': student.username,
            'student_id': student.student_id,
            'department': student.department,
            'year': student.year,
            'courses': courses_list,
        }
    except Student.DoesNotExist:
        profile_data = {
            'name': request.user.get_full_name() or request.user.username,
            'username': request.user.username,
            'student_id': '-',
            'department': '-',
            'year': '-',
            'courses': [],
        }
    
    return render(request, "student/profile.html", {'profile': profile_data})


def student_courses(request):
    if not request.user.is_authenticated:
        return redirect('student-login')
    
    try:
        student = Student.objects.get(user=request.user)
        courses = student.courses.all().select_related('instructor')
        
        courses_data = []
        for course in courses:
            instructor_name = f"{course.instructor.first_name} {course.instructor.last_name}".strip() or course.instructor.username
            courses_data.append({
                'id': course.id,
                'name': course.name,
                'code': course.code,
                'instructor': instructor_name,
                'department': course.department,
                'credits': course.credits,
            })
    except Student.DoesNotExist:
        courses_data = []
    
    return render(request, "student/courses.html", {
        'courses': courses_data
    })


def student_grades(request):
    if not request.user.is_authenticated:
        return redirect('student-login')
    
    try:
        student = Student.objects.get(user=request.user)
        courses = student.courses.all()
        grades_qs = Grade.objects.filter(student=student).select_related('course')
        
        courses_with_grades = []
        for course in courses:
            grade_obj = grades_qs.filter(course=course).first()
            grades_dict = grade_obj.grades if grade_obj and grade_obj.grades else {}
            
            if not grades_dict and grade_obj:
                if grade_obj.midterm is not None:
                    grades_dict['Midterm'] = grade_obj.midterm
                if grade_obj.assignment is not None:
                    grades_dict['Assignment'] = grade_obj.assignment
                if grade_obj.final is not None:
                    grades_dict['Final'] = grade_obj.final
            
            course_data = {
                'course_name': course.name,
                'grades': grades_dict,
                'credits': course.credits,
            }
            
            if grade_obj:
                course_data['midterm'] = grade_obj.midterm
                course_data['assignment'] = grade_obj.assignment
                course_data['final'] = grade_obj.final
            else:
                course_data['midterm'] = None
                course_data['assignment'] = None
                course_data['final'] = None
            
            courses_with_grades.append(course_data)
    except Student.DoesNotExist:
        courses_with_grades = []
    
    return render(request, "student/grades.html", {
        'courses_with_grades': courses_with_grades
    })


def student_announcements(request):
    return render(request, "student/student_announcement.html")

@instructor_required
def instructor_program_outcomes(request):
    instructor_user = request.instructor_user
    profile = getattr(instructor_user, 'profile', None)
    instructor_department = profile.department if profile else None
    
    if profile:
        faculty = profile.faculty
    else:
        faculty = None
    
    if faculty:
        outcomes_qs = ProgramOutcome.objects.filter(
            faculty=faculty, 
            course_name=''
        ).select_related('created_by').prefetch_related('learning_outcomes__created_by').order_by('-created_at')
    else:
        outcomes_qs = ProgramOutcome.objects.filter(
            course_name=''
        ).select_related('created_by').prefetch_related('learning_outcomes__created_by').order_by('-created_at')
    
    faculty_heads_map = {}
    instructors_map = {}
    
    instructors_json_path = os.path.join(settings.BASE_DIR, 'static', 'json', 'instructors.json')
    try:
        with open(instructors_json_path, encoding='utf-8') as f:
            instructors_list = json.load(f)
            for inst in instructors_list:
                username = inst.get('username')
                first_name = inst.get('firstName', '')
                last_name = inst.get('lastName', '')
                full_name = (first_name + ' ' + last_name).strip()
                if full_name:
                    instructors_map[username] = full_name
    except (OSError, json.JSONDecodeError):
        pass
    
    faculty_heads_map = get_faculty_heads_map()
    
    outcomes_data = []
    for o in outcomes_qs:
        creator_username = o.created_by.username
        creator_name = faculty_heads_map.get(creator_username) or o.created_by.get_full_name() or creator_username
        
        linked_learning_outcomes = []
        seen_course_instructor = set()
        for lo in o.learning_outcomes.all():
            lo_creator_username = lo.created_by.username
            lo_creator_name = instructors_map.get(lo_creator_username) or lo.created_by.get_full_name() or lo_creator_username
            course_instructor_key = (lo.course_name, lo_creator_name)
            if course_instructor_key not in seen_course_instructor:
                seen_course_instructor.add(course_instructor_key)
                linked_learning_outcomes.append({
                    'text': lo.text,
                    'course': lo.course_name,
                    'instructor': lo_creator_name,
                })
        
        outcomes_data.append({
            'id': o.id,
            'text': o.text,
            'created_by': creator_name,
            'created_at': o.created_at.strftime('%Y-%m-%d %H:%M'),
            'linked_learning_outcomes': linked_learning_outcomes,
        })
    
    return render(request, "instructor/program_outcomes.html", {
        'outcomes_data': outcomes_data,
        'department': instructor_department,
        'department': instructor_department,
    })

def student_program_outcomes(request):
    if not request.user.is_authenticated:
        return redirect('student-login')
    
    try:
        student = Student.objects.get(user=request.user)
        student_department = student.department
        
        profile = getattr(request.user, 'profile', None)
        faculty = profile.faculty if profile else None
        
        if not faculty and profile:
            faculty = profile.faculty
        
        if faculty:
            outcomes_qs = ProgramOutcome.objects.filter(
                faculty=faculty, 
                course_name=''
            ).select_related('created_by').prefetch_related('learning_outcomes__created_by').order_by('-created_at')
        else:
            outcomes_qs = ProgramOutcome.objects.filter(
                course_name=''
            ).select_related('created_by').prefetch_related('learning_outcomes__created_by').order_by('-created_at')
        
        faculty_heads_map = get_faculty_heads_map()
        instructors_map = get_instructors_map()
        
        outcomes_data = []
        for o in outcomes_qs:
            creator_username = o.created_by.username
            creator_name = faculty_heads_map.get(creator_username) or o.created_by.get_full_name() or creator_username
            
            linked_learning_outcomes = []
            seen_course_instructor = set()
            for lo in o.learning_outcomes.all():
                lo_creator_username = lo.created_by.username
                lo_creator_name = instructors_map.get(lo_creator_username) or lo.created_by.get_full_name() or lo_creator_username
                course_instructor_key = (lo.course_name, lo_creator_name)
                if course_instructor_key not in seen_course_instructor:
                    seen_course_instructor.add(course_instructor_key)
                    linked_learning_outcomes.append({
                        'text': lo.text,
                        'course': lo.course_name,
                        'instructor': lo_creator_name,
                    })
            
            outcomes_data.append({
                'id': o.id,
                'text': o.text,
                'created_by': creator_name,
                'created_at': o.created_at.strftime('%Y-%m-%d %H:%M'),
                'linked_learning_outcomes': linked_learning_outcomes,
            })
        
    except Student.DoesNotExist:
        outcomes_data = []
        student_department = None
    
    return render(request, "student/program_outcomes.html", {
        'outcomes_data': outcomes_data,
        'department': student_department,
    })

def student_course_learning_outcomes(request, course_id):
    if not request.user.is_authenticated:
        return redirect('student-login')
    
    try:
        student = Student.objects.get(user=request.user)
        course = get_object_or_404(Course, id=course_id)
        
        if course not in student.courses.all():
            return HttpResponseForbidden("You are not enrolled in this course.")
        
        course_name = course.name
        
        outcomes_qs = ProgramOutcome.objects.filter(
            course_name=course_name
        ).select_related('created_by').prefetch_related('related_program_outcomes').order_by('-created_at')
        
        instructors_map = get_instructors_map()
        
        outcomes_data = []
        for o in outcomes_qs:
            creator_name = instructors_map.get(o.created_by.username) or o.created_by.get_full_name() or o.created_by.username
            related_program_outcomes = o.related_program_outcomes.all()
            outcomes_data.append({
                'id': o.id,
                'text': o.text,
                'created_by': creator_name,
                'created_at': o.created_at.strftime('%Y'),
                'related_program_outcomes': [{'id': po.id, 'text': po.text} for po in related_program_outcomes],
            })
        
    except Student.DoesNotExist:
        return redirect('student-login')
    
    return render(request, "student/course_learning_outcomes.html", {
        'course_name': course_name,
        'outcomes_data': outcomes_data,
        'course_id': course_id,
    })

def student_learning_outcome_detail(request, course_id, outcome_id):
    """Show detail page for a learning outcome (read-only for students)"""
    if not request.user.is_authenticated:
        return redirect('student-login')
    
    try:
        student = Student.objects.get(user=request.user)
        course = get_object_or_404(Course, id=course_id)
        
        if course not in student.courses.all():
            return HttpResponseForbidden("You are not enrolled in this course.")
        
        outcome = get_object_or_404(ProgramOutcome, id=outcome_id, course_name=course.name)
        
        from .models import LearningOutcomeProgramOutcome
        related_program_outcomes = outcome.related_program_outcomes.all().order_by('id')
        
        program_outcomes_data = []
        for po in related_program_outcomes:
            try:
                lo_po = LearningOutcomeProgramOutcome.objects.get(learning_outcome=outcome, program_outcome=po)
                percentage = lo_po.percentage
            except LearningOutcomeProgramOutcome.DoesNotExist:
                percentage = 0
            program_outcomes_data.append({
                'id': po.id,
                'text': po.text,
                'percentage': percentage,
            })
        
        course_name_slug = outcome.course_name.replace(' ', '-')
        
        instructors_map = get_instructors_map()
        creator_name = instructors_map.get(outcome.created_by.username) or outcome.created_by.get_full_name() or outcome.created_by.username
        
    except Student.DoesNotExist:
        return redirect('student-login')
    
    return render(
        request,
        'student/learning_outcome_detail.html',
        {
            'outcome': outcome,
            'course': course,
            'program_outcomes': program_outcomes_data,
            'course_name_slug': course_name_slug,
            'created_by': creator_name,
            'created_at': outcome.created_at.strftime('%Y'),
        }
    )

def student_learning_outcome_graph(request, course_id, outcome_id):
    """Show graph view for learning outcome (read-only for students)"""
    if not request.user.is_authenticated:
        return redirect('student-login')
    
    try:
        student = Student.objects.get(user=request.user)
        course = get_object_or_404(Course, id=course_id)
        
        if course not in student.courses.all():
            return HttpResponseForbidden("You are not enrolled in this course.")
        
        outcome = get_object_or_404(ProgramOutcome, id=outcome_id, course_name=course.name)
        
        from .models import LearningOutcomeProgramOutcome
        related_program_outcomes = outcome.related_program_outcomes.all().order_by('id')
        
        program_outcomes_data = []
        for po in related_program_outcomes:
            try:
                lo_po = LearningOutcomeProgramOutcome.objects.get(learning_outcome=outcome, program_outcome=po)
                percentage = lo_po.percentage
            except LearningOutcomeProgramOutcome.DoesNotExist:
                percentage = 0
            program_outcomes_data.append({
                'id': po.id,
                'text': po.text,
                'percentage': percentage,
            })
        
        course_name_slug = outcome.course_name.replace(' ', '-')
        
    except Student.DoesNotExist:
        return redirect('student-login')
    
    return render(
        request,
        'student/learning_outcome_graph.html',
        {
            'outcome': outcome,
            'course': course,
            'program_outcomes': program_outcomes_data,
            'course_name_slug': course_name_slug,
        }
    )

def logout_view(request):
    logout(request)
    return redirect("home")

@faculty_head_required
def faculty_head_announcements(request):
    from .models import Announcement, UserProfile
    faculty_head_user = request.user
    
    faculty_head_data = get_faculty_head_data(faculty_head_user.username)
    faculty_head_department = faculty_head_data.get('department')
    
    instructors = User.objects.filter(profile__role='instructor').select_related('profile')
    faculty_heads = User.objects.filter(profile__role='faculty_head').select_related('profile')
    
    instructors_map = get_instructors_map()
    faculty_heads_map = get_faculty_heads_map()
    
    if request.method == 'POST':
        message = (request.POST.get('message') or '').strip()
        subject = (request.POST.get('subject') or '').strip()
        receivers_str = (request.POST.get('receivers') or '').strip()
        
        if message:
            if not subject:
                subject = 'No Topic'
            
            receivers_list = [r.strip() for r in receivers_str.split(',') if r.strip()]
            
            with transaction.atomic():
                for receiver_username in receivers_list:
                    if receiver_username.startswith('course_'):
                        course_name = receiver_username.replace('course_', '', 1)
                        try:
                            course = Course.objects.get(name=course_name)
                            profile = getattr(faculty_head_user, 'profile', None)
                            if profile and course in profile.courses.all():
                                students = Student.objects.filter(courses=course).select_related('user')
                                course_marker = f"__COURSE:{course_name}__"
                                marked_subject = course_marker + subject if not subject.startswith(course_marker) else subject
                                for student in students:
                                    student_user = student.user
                                    if student_user:
                                        Announcement.objects.create(
                                            sender=faculty_head_user,
                                            receiver=student_user,
                                            subject=marked_subject,
                                            message=message,
                                            sender_role='faculty_head',
                                            receiver_role='student'
                                        )
                        except Course.DoesNotExist:
                            pass
                    else:
                        try:
                            receiver = User.objects.get(username=receiver_username)
                            profile = getattr(receiver, 'profile', None)
                            receiver_role = None
                            if profile:
                                receiver_role = profile.role
                            
                            Announcement.objects.create(
                                sender=faculty_head_user,
                                receiver=receiver,
                                subject=subject,
                                message=message,
                                sender_role='faculty_head',
                                receiver_role=receiver_role
                            )
                        except User.DoesNotExist:
                            pass
            
            return redirect('faculty-head-announcements')
    
    # ORM ile announcements'ları çek - select_related ile JOIN optimizasyonu
    announcements = Announcement.objects.filter(
        Q(sender=faculty_head_user) | Q(receiver=faculty_head_user)
    ).select_related('sender', 'receiver').order_by('-created_at')
    
    all_announcements = []
    for ann in announcements:
        all_announcements.append({
            'id': ann.id,
            'subject': ann.subject,
            'message': ann.message,
            'sender_id': ann.sender.id,
            'receiver_id': ann.receiver.id if ann.receiver else None,
            'sender_username': ann.sender.username,
            'sender_first_name': ann.sender.first_name,
            'sender_last_name': ann.sender.last_name,
            'receiver_username': ann.receiver.username if ann.receiver else None,
            'receiver_first_name': ann.receiver.first_name if ann.receiver else '',
            'receiver_last_name': ann.receiver.last_name if ann.receiver else '',
            'sender_role': ann.sender_role,
            'receiver_role': ann.receiver_role,
            'created_at': ann.created_at,
        })
    
    # Group announcements sent to course students
    from collections import defaultdict
    from datetime import timedelta
    
    # First, process all announcements and group them
    announcements_data = []
    processed_ids = set()
    
    for ann in all_announcements:
        if ann['id'] in processed_ids:
            continue
            
        sender_full_name = f"{ann['sender_first_name']} {ann['sender_last_name']}".strip() if ann['sender_first_name'] or ann['sender_last_name'] else ''
        sender_name = instructors_map.get(ann['sender_username']) or faculty_heads_map.get(ann['sender_username']) or sender_full_name or ann['sender_username']
        
        is_sent = ann['sender_id'] == faculty_head_user.id
        
        # Check if this is part of a course broadcast
        if is_sent:
            # Find all announcements with same subject, message, sender, and sent within 10 seconds
            created_at_str = ann['created_at']
            if isinstance(created_at_str, str):
                from datetime import datetime
                try:
                    created_at_dt = datetime.strptime(created_at_str, '%Y-%m-%d %H:%M:%S.%f')
                except:
                    try:
                        created_at_dt = datetime.strptime(created_at_str, '%Y-%m-%d %H:%M:%S')
                    except:
                        created_at_dt = datetime.now()
            else:
                created_at_dt = created_at_str if hasattr(created_at_str, 'timestamp') else None
                if not created_at_dt:
                    from datetime import datetime
                    created_at_dt = datetime.now()
            
            course_name_from_marker = None
            clean_subject = ann['subject']
            if ann['subject'].startswith('__COURSE:'):
                marker_end = ann['subject'].find('__', 9)  
                if marker_end > 0:
                    course_name_from_marker = ann['subject'][9:marker_end]
                    clean_subject = ann['subject'][marker_end + 2:]
            
            matching_anns = []
            for other_ann in all_announcements:
                if (other_ann['id'] in processed_ids or 
                    other_ann['sender_id'] != ann['sender_id'] or
                    other_ann['message'] != ann['message']):
                    continue
                
                other_subject = other_ann['subject']
                other_course_name = None
                if other_subject.startswith('__COURSE:'):
                    marker_end = other_subject.find('__', 9)
                    if marker_end > 0:
                        other_course_name = other_subject[9:marker_end]
                        other_subject = other_subject[marker_end + 2:]
                
                if other_subject != clean_subject:
                    continue
                
                if course_name_from_marker and other_course_name:
                    if course_name_from_marker != other_course_name:
                        continue
                elif course_name_from_marker or other_course_name:
                    continue
                
                other_created_at_str = other_ann['created_at']
                if isinstance(other_created_at_str, str):
                    try:
                        other_created_at_dt = datetime.strptime(other_created_at_str, '%Y-%m-%d %H:%M:%S.%f')
                    except:
                        try:
                            other_created_at_dt = datetime.strptime(other_created_at_str, '%Y-%m-%d %H:%M:%S')
                        except:
                            continue
                else:
                    other_created_at_dt = other_created_at_str if hasattr(other_created_at_str, 'timestamp') else None
                    if not other_created_at_dt:
                        continue
                
                time_diff = abs((created_at_dt - other_created_at_dt).total_seconds())
                if time_diff <= 10:
                    matching_anns.append(other_ann)
            
            if course_name_from_marker and len(matching_anns) > 1:
                created_at_formatted = created_at_dt.strftime('%Y-%m-%d %H:%M') if hasattr(created_at_dt, 'strftime') else str(created_at_dt)
                announcements_data.append({
                    'id': ann['id'],
                    'subject': clean_subject,
                    'message': ann['message'],
                    'sender': sender_name,
                    'sender_username': ann['sender_username'],
                    'receiver': f'All students in {course_name_from_marker}',
                    'receiver_username': None,
                    'is_sent': True,
                    'created_at': created_at_formatted,
                })
                for ma in matching_anns:
                    processed_ids.add(ma['id'])
                continue
        
        if ann['id'] not in processed_ids:
            receiver_name = "Everyone"
            receiver_username = None
            if ann['receiver_id']:
                receiver_full_name = f"{ann['receiver_first_name']} {ann['receiver_last_name']}".strip() if ann['receiver_first_name'] or ann['receiver_last_name'] else ''
                receiver_name = instructors_map.get(ann['receiver_username']) or faculty_heads_map.get(ann['receiver_username']) or receiver_full_name or ann['receiver_username']
                receiver_username = ann['receiver_username']
            
            created_at_str = ann['created_at']
            if isinstance(created_at_str, str):
                from datetime import datetime
                try:
                    created_at_dt = datetime.strptime(created_at_str, '%Y-%m-%d %H:%M:%S.%f')
                except:
                    try:
                        created_at_dt = datetime.strptime(created_at_str, '%Y-%m-%d %H:%M:%S')
                    except:
                        created_at_dt = datetime.now()
                created_at_formatted = created_at_dt.strftime('%Y-%m-%d %H:%M')
            else:
                created_at_formatted = created_at_str.strftime('%Y-%m-%d %H:%M') if hasattr(created_at_str, 'strftime') else str(created_at_str)
            
            display_subject = ann['subject']
            if display_subject.startswith('__COURSE:'):
                marker_end = display_subject.find('__', 9)
                if marker_end > 0:
                    display_subject = display_subject[marker_end + 2:]
            
            announcements_data.append({
                'id': ann['id'],
                'subject': display_subject,
                'message': ann['message'],
                'sender': sender_name,
                'sender_username': ann['sender_username'],
                'receiver': receiver_name,
                'receiver_username': receiver_username,
                'is_sent': is_sent,
                'created_at': created_at_formatted,
            })
            processed_ids.add(ann['id'])
    
    recipients = []
    
    profile = getattr(faculty_head_user, 'profile', None)
    faculty_head_courses = []
    
    # Courses group - sorted alphabetically by course name
    if profile:
        all_courses = profile.courses.all()
        courses_list = []
        for course in all_courses:
            # Filter by department
            if faculty_head_department and course.department != faculty_head_department:
                continue
            courses_list.append({
                'username': f'course_{course.name}',
                'name': f'All students in {course.name}',
                'role': 'course'
            })
        courses_list.sort(key=lambda x: x['name'])
        recipients.extend(courses_list)
        faculty_head_courses = [c['name'].replace('All students in ', '') for c in courses_list]
    
    # Instructors and Faculty Heads group - sorted alphabetically by name
    professors_list = []
    for inst in instructors:
        if inst.username != faculty_head_user.username:
            inst_profile = getattr(inst, 'profile', None)
            # Filter by department
            if faculty_head_department and inst_profile and inst_profile.department != faculty_head_department:
                continue
            name = instructors_map.get(inst.username) or inst.get_full_name() or inst.username
            professors_list.append({
                'username': inst.username, 
                'name': name, 
                'role': 'instructor'
            })
    
    for fh in faculty_heads:
        if fh.username != faculty_head_user.username:
            fh_profile = getattr(fh, 'profile', None)
            # Filter by department
            if faculty_head_department and fh_profile and fh_profile.department != faculty_head_department:
                continue
            name = faculty_heads_map.get(fh.username) or fh.get_full_name() or fh.username
            professors_list.append({
                'username': fh.username, 
                'name': name, 
                'role': 'faculty_head'
            })
    
    professors_list.sort(key=lambda x: x['name'])
    
    if professors_list:
        professors_list[0]['show_professors_heading'] = True
    
    recipients.extend(professors_list)
    
    # Students group - sorted alphabetically by name
    # Faculty head can see ALL students in their department (not just from their courses)
    if faculty_head_department:
        students = Student.objects.filter(
            user__profile__department=faculty_head_department
        ).distinct().select_related('user')
        
        students_list = []
        for student in students:
            full_name = f"{student.first_name} {student.last_name}".strip() if student.first_name or student.last_name else ''
            if not full_name and student.user:
                full_name = f"{student.user.first_name} {student.user.last_name}".strip()
            name = full_name if full_name else student.username
            students_list.append({
                'username': student.user.username if student.user else student.username,
                'name': name,
                'role': 'student'
            })
        
        students_list.sort(key=lambda x: x['name'])
        recipients.extend(students_list)
    
    sent_messages = [ann for ann in announcements_data if ann['is_sent']]
    received_messages = [ann for ann in announcements_data if not ann['is_sent']]
    
    announcements_json = json.dumps({str(ann['id']): {
        'subject': ann['subject'],
        'message': ann['message'],
        'sender': ann['sender'],
        'receiver': ann['receiver'],
        'created_at': ann['created_at'],
        'is_sent': ann['is_sent']
    } for ann in announcements_data})
    
    return render(request, 'faculty/faculty_announcements.html', {
        'all_announcements': announcements_data,
        'announcements_json': announcements_json,
        'sent_messages': sent_messages,
        'received_messages': received_messages,
        'recipients': recipients,
    })

def faculty_head_logout(request):
    logout(request)
    return redirect("home")


@csrf_exempt
def mark_announcement_as_read(request, announcement_id):
    """Mark an announcement as read by the current user"""
    if not request.user.is_authenticated:
        return JsonResponse({'error': 'Authentication required'}, status=401)
    
    try:
        from .models import Announcement
        announcement = get_object_or_404(Announcement, id=announcement_id)
        
        # Check if user has permission to read this announcement
        if announcement.receiver and announcement.receiver != request.user:
            # Check if it's a broadcast (receiver is None) or user is the receiver
            if announcement.receiver is not None:
                return JsonResponse({'error': 'Permission denied'}, status=403)
        
        # Add user to read_by
        announcement.read_by.add(request.user)
        
        return JsonResponse({'status': 'success', 'message': 'Announcement marked as read'})
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)


@csrf_exempt
def toggle_announcement_pin(request, announcement_id):
    """Toggle pin status of an announcement"""
    if not request.user.is_authenticated:
        return JsonResponse({'error': 'Authentication required'}, status=401)
    
    try:
        from .models import Announcement
        announcement = get_object_or_404(Announcement, id=announcement_id)
        
        # Check if user has permission (must be the receiver)
        if announcement.receiver and announcement.receiver != request.user:
            return JsonResponse({'error': 'Permission denied'}, status=403)
        
        # Toggle pin status
        announcement.is_pinned = not announcement.is_pinned
        announcement.save()
        
        return JsonResponse({
            'status': 'success',
            'is_pinned': announcement.is_pinned,
            'message': 'Announcement pinned' if announcement.is_pinned else 'Announcement unpinned'
        })
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)


def advisor_profile(request, username):
    """Show advisor profile page"""
    if not request.user.is_authenticated:
        return redirect('student-login')
    
    try:
        advisor = User.objects.get(username=username)
        profile = getattr(advisor, 'profile', None)
        
        advisor_data = {
            'username': advisor.username,
            'name': f"{advisor.first_name} {advisor.last_name}".strip() or advisor.username,
            'department': profile.department if profile else '-',
            'faculty': profile.faculty.name if profile and profile.faculty else '-',
            'email': advisor.email or '-',
        }
        
        return render(request, 'student/advisor_profile.html', {
            'advisor': advisor_data
        })
    except User.DoesNotExist:
        return redirect('student')


@faculty_head_required
def faculty_head_department_graph(request):
    """Show department graph for faculty head"""
    from .models import Course, Student
    from django.db.models import Count
    
    faculty_head_data = get_faculty_head_data(request.user.username)
    faculty_head_department = faculty_head_data.get('department')
    
    if not faculty_head_department:
        return render(request, 'faculty/department_graph.html', {
            'error': 'No department assigned'
        })
    
    # Get courses in the department
    courses = Course.objects.filter(department=faculty_head_department)
    
    # Get statistics
    total_courses = courses.count()
    total_students = Student.objects.filter(courses__department=faculty_head_department).distinct().count()
    
    # Course statistics
    course_data = []
    for course in courses:
        student_count = course.students.count()
        course_data.append({
            'name': course.name,
            'code': course.code,
            'students': student_count,
            'credits': course.credits or 0,
        })
    
    # Prepare chart data
    chart_data = {
        'labels': [c['name'] for c in course_data],
        'data': [c['students'] for c in course_data],
    }
    
    return render(request, 'faculty/department_graph.html', {
        'department': faculty_head_department,
        'total_courses': total_courses,
        'total_students': total_students,
        'course_data': course_data,
        'chart_data': chart_data,
        'chart_data_json': json.dumps(chart_data),
    })