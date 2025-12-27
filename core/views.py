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
    # TODO: Cache invalidation - When User/Profile/Student is updated, call:
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
    # TODO: Cache invalidation - When User/Profile is updated, call:
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
        # TODO: Cache invalidation - When User/Profile/Course is updated, call:
        # cache.delete(f'faculty_head_data_{username}') to ensure fresh data
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
    # TODO: Cache invalidation - When Student/Course is updated, call:
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
        # TODO: Cache invalidation - When User/Profile/Course is updated, call:
        # cache.delete(f'instructor_data_{username}') to ensure fresh data
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
        
        # Use consistent role check: user.profile.role (same as rest of the system)
        try:
            profile = user.profile
            if profile.role != "faculty_head":
                return HttpResponseForbidden("You are not allowed here")
        except AttributeError:
            return HttpResponseForbidden("User profile not found")

        return view_func(request, *args, **kwargs)

    return wrapper

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

    def parse_score(raw_value, label):
        value = (raw_value or '').strip()
        if value == '':
            raise ValueError(f'{label} must not be empty')
        return float(value)

    # First pass: Validate all rows before any DB operations
    validated_rows = []
    errors = []
    
    try:
        for row_num, row in enumerate(reader, start=2):  # Start at 2 (header is row 1)
            try:
                username = (row[username_source] or '').strip()
                course_name = (row[course_source] or '').strip()

                if not username or not course_name:
                    errors.append(f'Row {row_num}: Username and course_name are required')
                    continue
                
                # Check if student exists
                try:
                    student = Student.objects.get(username=username)
                except Student.DoesNotExist:
                    errors.append(f'Row {row_num}: Student not found: {username}')
                    continue
                except Student.MultipleObjectsReturned:
                    errors.append(f'Row {row_num}: Multiple students found with username: {username}')
                    continue
                
                # Check if course exists
                course = Course.objects.filter(name=course_name).first()
                if not course:
                    errors.append(f'Row {row_num}: Course not found: {course_name}')
                    continue
                
                # Parse scores
                midterm = parse_score(row[midterm_source], 'midterm')
                assignment = parse_score(row[assignment_source], 'assignment')
                final = parse_score(row[final_source], 'final')
                
                validated_rows.append({
                    'student': student,
                    'course': course,
                    'midterm': midterm,
                    'assignment': assignment,
                    'final': final
                })
            except (KeyError, ValueError) as exc:
                errors.append(f'Row {row_num}: {str(exc)}')
        
        # If there are validation errors, return before atomic block
        if errors:
            return JsonResponse({
                'error': 'CSV validation failed',
                'details': errors[:20]  # Show first 20 errors
            }, status=400)
        
        # Second pass: Write to database in atomic transaction
        with transaction.atomic():
            for row_data in validated_rows:
                Grade.objects.update_or_create(
                    student=row_data['student'],
                    course=row_data['course'],
                    defaults={
                        'midterm': row_data['midterm'],
                        'assignment': row_data['assignment'],
                        'final': row_data['final']
                    }
                )

        return JsonResponse({'status': 'ok'})
        
    except Exception as exc:
        return JsonResponse({'error': f'CSV processing error: {str(exc)}'}, status=400)


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
    """
    Instructor login endpoint.
    NOTE: CSRF exempt for login form compatibility. This is acceptable for authentication endpoints.
    """
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
    """
    Faculty head login endpoint.
    NOTE: CSRF exempt for login form compatibility. This is acceptable for authentication endpoints.
    """
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
        
        # Get advisor information
        advisor_name = "-"
        advisor_username = None
        if student.advisor:
            advisor_name = f"{student.advisor.first_name} {student.advisor.last_name}".strip() or student.advisor.username
            advisor_username = student.advisor.username
        
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
        advisor_username = None
        courses_list = []
    
    latest_announcements = Announcement.objects.filter(
        Q(receiver=request.user) | Q(receiver__isnull=True)
    ).select_related('sender').order_by('-created_at')[:5]
    
    announcements_list = []
    for ann in latest_announcements:
        sender_name = ann.sender.get_full_name() or ann.sender.username
        
        # Remove course marker from subject for display
        display_subject = ann.subject
        if display_subject.startswith('__COURSE:'):
            marker_end = display_subject.find('__', 9)
            if marker_end > 0:
                display_subject = display_subject[marker_end + 2:]
        
        announcements_list.append({
            'id': ann.id,
            'subject': display_subject,
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
        'advisor_username': advisor_username,
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
        Q(receiver=instructor_user) | Q(receiver__isnull=True)
    ).exclude(sender=instructor_user).select_related('sender', 'receiver').order_by('-created_at')[:5]
    
    announcements_list = []
    for ann in latest_announcements:
        sender_name = ann.sender.get_full_name() or ann.sender.username
        
        display_subject = ann.subject
        if display_subject.startswith('__COURSE:'):
            marker_end = display_subject.find('__', 9)
            if marker_end > 0:
                display_subject = display_subject[marker_end + 2:]
        
        announcements_list.append({
            'id': ann.id,
            'subject': display_subject,
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
def instructor_my_courses(request):
    from .models import Assignment
    from django.utils import timezone
    
    instructor_user = request.instructor_user
    profile = getattr(instructor_user, 'profile', None)
    
    courses_data = []
    all_assignments = []
    
    if profile:
        courses = profile.courses.all().select_related('instructor').prefetch_related('students', 'assignments')
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
            
            # Get assignments for this course
            from .models import AssignmentSubmission
            assignments = course.assignments.all().order_by('-created_at')
            assignments_list = []
            for assignment in assignments:
                # Get submissions for this assignment
                submissions = AssignmentSubmission.objects.filter(assignment=assignment).select_related('student')
                submissions_list = []
                for submission in submissions:
                    student_name = f"{submission.student.first_name} {submission.student.last_name}".strip() or submission.student.username
                    submissions_list.append({
                        'id': submission.id,
                        'student_name': student_name,
                        'student_id': submission.student.student_id,
                        'file_url': submission.file.url if submission.file else None,
                        'file_name': submission.file.name.split('/')[-1] if submission.file else None,
                        'submitted_at': submission.submitted_at.strftime('%d/%m/%Y %H:%M'),
                    })
                
                assignment_data = {
                    'id': assignment.id,
                    'course_name': course.name,
                    'title': assignment.title,
                    'details': assignment.details,
                    'deadline': assignment.deadline.strftime('%d/%m/%Y %H:%M'),
                    'deadline_datetime': assignment.deadline.isoformat(),
                    'deadline_date': assignment.deadline.strftime('%Y-%m-%d'),
                    'deadline_time': assignment.deadline.strftime('%H:%M'),
                    'file_url': assignment.file.url if assignment.file else None,
                    'file_name': assignment.file.name.split('/')[-1] if assignment.file else None,
                    'created_by_id': assignment.created_by.id,
                    'submissions': json.dumps(submissions_list),
                }
                assignments_list.append(assignment_data)
                all_assignments.append(assignment_data)
            
            courses_data.append({
                'id': course.id,
                'name': course.name,
                'code': course.code,
                'instructor': instructor_name,
                'department': course.department,
                'credits': course.credits,
                'students': students_list,
                'students_json': json.dumps(students_list),
                'assignments': assignments_list,
            })
    
    # Prepare JSON data for template
    courses_json = json.dumps([{
        'id': course['id'],
        'name': course['name'],
        'students': course['students']
    } for course in courses_data])
    
    profile = getattr(instructor_user, 'profile', None)
    instructor_info = {
        'username': instructor_user.username,
        'name': f"{instructor_user.first_name} {instructor_user.last_name}".strip() or instructor_user.username,
        'faculty': profile.faculty.name if profile and profile.faculty else '-',
        'department': profile.department if profile else '-',
    }
    
    return render(request, 'instructor/my_courses.html', {
        'courses': courses_data,
        'courses_json': courses_json,
        'all_assignments': all_assignments,
        'instructor_info': instructor_info,
    })

@instructor_required
def add_assignment(request):
    from .models import Assignment
    from django.utils import timezone
    from datetime import datetime
    
    if request.method == 'POST':
        course_id = request.POST.get('course_id')
        title = request.POST.get('title', '').strip()
        details = request.POST.get('details', '').strip()
        deadline_date = request.POST.get('deadline_date', '').strip()
        deadline_time = request.POST.get('deadline_time', '').strip()
        file = request.FILES.get('file')
        
        if not course_id or not title or not details or not deadline_date or not deadline_time:
            return JsonResponse({'error': 'All fields are required'}, status=400)
        
        try:
            course = Course.objects.get(id=course_id)
            
            # Check if instructor has access to this course
            instructor_user = request.instructor_user
            profile = getattr(instructor_user, 'profile', None)
            if profile and course not in profile.courses.all():
                return JsonResponse({'error': 'You do not have access to this course'}, status=403)
            
            # Parse deadline
            try:
                deadline_str = f"{deadline_date} {deadline_time}"
                deadline = datetime.strptime(deadline_str, '%Y-%m-%d %H:%M')
                deadline = timezone.make_aware(deadline)
            except ValueError:
                return JsonResponse({'error': 'Invalid deadline format'}, status=400)
            
            # Validate file type if provided
            if file:
                if not file.name.lower().endswith('.pdf'):
                    return JsonResponse({'error': 'Only PDF files are allowed'}, status=400)
            
            # Create assignment
            assignment = Assignment.objects.create(
                course=course,
                title=title,
                details=details,
                deadline=deadline,
                file=file,
                created_by=instructor_user
            )
            
            return JsonResponse({
                'success': True,
                'assignment': {
                    'id': assignment.id,
                    'title': assignment.title,
                    'details': assignment.details,
                    'deadline': assignment.deadline.strftime('%d/%m/%Y %H:%M'),
                    'file_url': assignment.file.url if assignment.file else None,
                    'file_name': assignment.file.name.split('/')[-1] if assignment.file else None,
                }
            })
        except Course.DoesNotExist:
            return JsonResponse({'error': 'Course not found'}, status=404)
        except Exception as e:
            return JsonResponse({'error': str(e)}, status=500)
    
    return JsonResponse({'error': 'Invalid request method'}, status=405)

@faculty_head_required
@csrf_exempt
def faculty_head_add_assignment(request):
    from .models import Assignment
    from django.utils import timezone
    from datetime import datetime
    
    if request.method == 'POST':
        course_id = request.POST.get('course_id')
        title = request.POST.get('title', '').strip()
        details = request.POST.get('details', '').strip()
        deadline_date = request.POST.get('deadline_date', '').strip()
        deadline_time = request.POST.get('deadline_time', '').strip()
        file = request.FILES.get('file')
        
        if not course_id or not title or not details or not deadline_date or not deadline_time:
            return JsonResponse({'error': 'All fields are required'}, status=400)
        
        try:
            course = Course.objects.get(id=course_id)
            
            # Check if faculty head has access to this course
            profile = getattr(request.user, 'profile', None)
            if profile and course not in profile.courses.all():
                return JsonResponse({'error': 'You do not have access to this course'}, status=403)
            
            # Parse deadline
            try:
                deadline_str = f"{deadline_date} {deadline_time}"
                deadline = datetime.strptime(deadline_str, '%Y-%m-%d %H:%M')
                deadline = timezone.make_aware(deadline)
            except ValueError:
                return JsonResponse({'error': 'Invalid deadline format'}, status=400)
            
            # Validate file type if provided
            if file:
                if not file.name.lower().endswith('.pdf'):
                    return JsonResponse({'error': 'Only PDF files are allowed'}, status=400)
            
            # Create assignment
            assignment = Assignment.objects.create(
                course=course,
                title=title,
                details=details,
                deadline=deadline,
                file=file,
                created_by=request.user
            )
            
            return JsonResponse({
                'success': True,
                'assignment': {
                    'id': assignment.id,
                    'title': assignment.title,
                    'details': assignment.details,
                    'deadline': assignment.deadline.strftime('%d/%m/%Y %H:%M'),
                    'file_url': assignment.file.url if assignment.file else None,
                    'file_name': assignment.file.name.split('/')[-1] if assignment.file else None,
                }
            })
        except Course.DoesNotExist:
            return JsonResponse({'error': 'Course not found'}, status=404)
        except Exception as e:
            return JsonResponse({'error': str(e)}, status=500)
    
    return JsonResponse({'error': 'Invalid request method'}, status=405)

@faculty_head_required
@csrf_exempt
def faculty_head_update_assignment(request, assignment_id):
    from .models import Assignment
    from django.utils import timezone
    from datetime import datetime
    
    if request.method != 'POST':
        return JsonResponse({'error': 'Only POST allowed'}, status=405)
    
    try:
        assignment = Assignment.objects.get(id=assignment_id)
    except Assignment.DoesNotExist:
        return JsonResponse({'error': 'Assignment not found'}, status=404)
    
    # Check if faculty head has access to this course
    profile = getattr(request.user, 'profile', None)
    if profile and assignment.course not in profile.courses.all():
        return JsonResponse({'error': 'You do not have access to this course'}, status=403)
    
    # Check if faculty head created this assignment
    if assignment.created_by != request.user:
        return JsonResponse({'error': 'You can only edit your own assignments'}, status=403)
    
    title = request.POST.get('title', '').strip()
    details = request.POST.get('details', '').strip()
    deadline_date = request.POST.get('deadline_date', '').strip()
    deadline_time = request.POST.get('deadline_time', '').strip()
    file = request.FILES.get('file')
    
    if not title or not details or not deadline_date or not deadline_time:
        return JsonResponse({'error': 'Title, details, and deadline are required'}, status=400)
    
    # Parse deadline
    try:
        deadline_str = f"{deadline_date} {deadline_time}"
        deadline = datetime.strptime(deadline_str, '%Y-%m-%d %H:%M')
        deadline = timezone.make_aware(deadline)
    except ValueError:
        return JsonResponse({'error': 'Invalid deadline format'}, status=400)
    
    # Validate file type if provided
    if file:
        if not file.name.lower().endswith('.pdf'):
            return JsonResponse({'error': 'Only PDF files are allowed'}, status=400)
        # Delete old file if exists
        if assignment.file:
            assignment.file.delete()
        assignment.file = file
    
    # Update assignment
    assignment.title = title
    assignment.details = details
    assignment.deadline = deadline
    assignment.save()
    
    return JsonResponse({
        'success': True,
        'message': 'Assignment updated successfully',
        'assignment': {
            'id': assignment.id,
            'title': assignment.title,
            'details': assignment.details,
            'deadline': assignment.deadline.strftime('%d/%m/%Y %H:%M'),
            'file_url': assignment.file.url if assignment.file else None,
            'file_name': assignment.file.name.split('/')[-1] if assignment.file else None,
        }
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
    
    if profile and not profile.courses.filter(id=course.id).exists():
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
    
    if profile and not profile.courses.filter(id=course.id).exists():
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
    
    # Second pass: Validate all rows and prepare data for DB operations
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
            return score
        except ValueError as e:
            if 'cannot be' in str(e):
                raise e
            raise ValueError(f'{label} must be a valid number')
            
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
    
    # Validate all rows and prepare data
    validated_rows = []
    validation_errors = []
    
    try:
        for row_num, row in enumerate(reader, start=2):  # Start at 2 (header is row 1)
            try:
                student_id_str = (row[student_id_source] or '').strip()
                if not student_id_str:
                    validation_errors.append(f'Row {row_num}: student_id is required')
                    continue
                
                # Get student by student_id (not by id)
                try:
                    student = Student.objects.get(student_id=student_id_str)
                except Student.DoesNotExist:
                    validation_errors.append(f'Row {row_num}: Student with student_id {student_id_str} not found')
                    continue
                except Student.MultipleObjectsReturned:
                    validation_errors.append(f'Row {row_num}: Multiple students found with student_id {student_id_str}')
                    continue
                
                # Check if student is enrolled in this course
                if not student.courses.filter(id=course.id).exists():
                    validation_errors.append(f'Row {row_num}: Student {student_id_str} is not enrolled in course {course_name}')
                    continue
                
                # Parse score
                score = parse_score(row[score_column], 'score')
                
                validated_rows.append({
                    'student': student,
                    'score': score
                })
                    
            except Exception as e:
                validation_errors.append(f'Row {row_num}: {str(e)}')
        
        # If there are validation errors, return before atomic block
        if validation_errors:
            return JsonResponse({
                'error': 'CSV validation failed',
                'details': validation_errors[:20]  # Show first 20 errors
            }, status=400)
        
        # Third pass: Write to database in atomic transaction
        from django.utils import timezone
        updated_count = 0
        
        with transaction.atomic():
            for row_data in validated_rows:
                student = row_data['student']
                score = row_data['score']
                
                # Get or create grade record
                grade, created = Grade.objects.get_or_create(
                    student=student,
                    course=course
                )
                
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
            
            return JsonResponse(response_data)
            
    except Exception as e:
        return JsonResponse({'error': f'CSV processing error: {str(e)}'}, status=400)

@instructor_required
def delete_assessment_file(request, course_name, assessment_type, assessment_index):
    """
    Delete a specific assessment file (e.g., midterm_1).
    NOTE: CSRF protection is enabled. Frontend must send CSRF token.
    """
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
    
    if profile and not profile.courses.filter(id=course.id).exists():
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
    
    # Optimized query: use exists() instead of loading all courses into memory
    if profile and not profile.courses.filter(id=course.id).exists():
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
        
        # Optimized query: use exists() instead of loading all courses into memory
        if not student.courses.filter(id=course.id).exists():
            return JsonResponse({'error': 'Student is not enrolled in this course'}, status=400)
        
        # Parse and validate score before transaction
            score_value = None
        if score is not None and score != '':
            try:
                score_value = float(score)
                if score_value < 0:
                    return JsonResponse({'error': 'Score cannot be less than 0'}, status=400)
                if score_value > 100:
                    return JsonResponse({'error': 'Score cannot be greater than 100'}, status=400)
            except ValueError:
                return JsonResponse({'error': 'Score must be a valid number'}, status=400)
        
        # All validation passed, now perform DB operations in atomic transaction
        with transaction.atomic():
            # Get or create grade
            grade, created = Grade.objects.get_or_create(
                student=student,
                course=course
            )
            
            # Keep existing file_name if exists (for manual edits)
            existing_file_name = ''
            if grade.assessment_scores and assessment_key in grade.assessment_scores:
                existing_file_name = grade.assessment_scores[assessment_key].get('file_name', '')
            
            # Update score
            if score_value is None:
                # Remove score
                grade.remove_individual_score(assessment_key)
            else:
                # Set individual score
                grade.set_individual_score(assessment_key, score_value, file_name=existing_file_name)
        
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
def update_assessment(request, course_name):
    if request.method != 'POST':
        return JsonResponse({'error': 'Method not allowed'}, status=405)
    
    instructor_user = request.instructor_user
    profile = getattr(instructor_user, 'profile', None)
    
    try:
        course = Course.objects.get(name=course_name)
    except Course.DoesNotExist:
        return JsonResponse({'error': 'Course not found'}, status=404)
    
    # Optimized query: use exists() instead of loading all courses into memory
    if profile and not profile.courses.filter(id=course.id).exists():
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
        
        # All validation passed, now perform DB operations in atomic transaction
        # This ensures config changes are atomic and consistent
        with transaction.atomic():
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
def update_assessment_percentages(request, course_name):
    """
    Update assessment percentages for a course.
    NOTE: CSRF protection is enabled. Frontend must send CSRF token.
    """
    if request.method != 'POST':
        return JsonResponse({'error': 'Method not allowed'}, status=405)
    
    instructor_user = request.instructor_user
    profile = getattr(instructor_user, 'profile', None)
    
    try:
        course = Course.objects.get(name=course_name)
    except Course.DoesNotExist:
        return JsonResponse({'error': 'Course not found'}, status=404)
    
    if profile and not profile.courses.filter(id=course.id).exists():
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


# Helper functions for instructor_announcements view
def send_announcements(sender, message, subject, receivers_list):
    """
    Send announcements to receivers (users or course students).
    Returns number of announcements created.
    """
    from .models import Announcement
    
    if not message:
        return 0
    
    if not subject:
        subject = 'No Topic'
    
    count = 0
    
    with transaction.atomic():
        for receiver_username in receivers_list:
            if receiver_username.startswith('course_'):
                course_name = receiver_username.replace('course_', '', 1)
                try:
                    course = Course.objects.get(name=course_name)
                    profile = getattr(sender, 'profile', None)
                    if profile and profile.courses.filter(id=course.id).exists():
                        students = Student.objects.filter(courses=course).select_related('user')
                        # TODO: Technical debt - Course marker hack in subject field
                        # Better approach: Add course=ForeignKey and is_course_broadcast=BooleanField to Announcement model
                        # This string parsing is fragile and doesn't handle edge cases (e.g., course names with '__')
                        course_marker = f"__COURSE:{course_name}__"
                        marked_subject = course_marker + subject if not subject.startswith(course_marker) else subject
                        for student in students:
                            student_user = student.user
                            if student_user:
                                Announcement.objects.create(
                                    sender=sender,
                                    receiver=student_user,
                                    subject=marked_subject,
                                    message=message,
                                    sender_role='instructor',
                                    receiver_role='student'
                                )
                                count += 1
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
                        sender=sender,
                        receiver=receiver,
                        subject=subject,
                        message=message,
                        sender_role='instructor',
                        receiver_role=receiver_role
                    )
                    count += 1
                except User.DoesNotExist:
                    pass
    
    return count


def group_course_announcements(all_announcements, instructor_user_id, instructors_map, faculty_heads_map):
    """
    Group course broadcast announcements that were sent within 10 seconds.
    
    NOTE: This algorithm uses O(n²) nested loops and is suitable for small datasets.
    For larger datasets, consider using a more efficient approach with batch_id/uuid.
    
    TODO: Technical debt - Time-based heuristic (≤10 seconds) is not deterministic.
    Better approach: Generate batch_id/uuid during broadcast and group by that.
    Current approach may incorrectly group unrelated announcements sent within 10 seconds.
    """
    from datetime import datetime
    
    announcements_data = []
    processed_ids = set()
    
    for ann in all_announcements:
        if ann['id'] in processed_ids:
            continue
            
        sender_full_name = f"{ann['sender_first_name']} {ann['sender_last_name']}".strip() if ann['sender_first_name'] or ann['sender_last_name'] else ''
        sender_name = instructors_map.get(ann['sender_username']) or faculty_heads_map.get(ann['sender_username']) or sender_full_name or ann['sender_username']
        
        is_sent = ann['sender_id'] == instructor_user_id
        
        # Check if this is part of a course broadcast
        if is_sent:
            # Django ORM returns datetime objects, not strings
            created_at_dt = ann['created_at']
            if not isinstance(created_at_dt, datetime):
                # Fallback for edge cases (shouldn't happen with ORM)
                    created_at_dt = datetime.now()
            
            # Extract course name from marker hack
            course_name_from_marker = None
            clean_subject = ann['subject']
            if ann['subject'].startswith('__COURSE:'):
                marker_end = ann['subject'].find('__', 9)  
                if marker_end > 0:
                    course_name_from_marker = ann['subject'][9:marker_end]
                    clean_subject = ann['subject'][marker_end + 2:]
            
            # Find matching announcements (O(n²) - see note above)
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
                
                # Django ORM returns datetime objects
                other_created_at_dt = other_ann['created_at']
                if not isinstance(other_created_at_dt, datetime):
                        continue
                
                time_diff = abs((created_at_dt - other_created_at_dt).total_seconds())
                if time_diff <= 10:
                    matching_anns.append(other_ann)
            
            if course_name_from_marker and len(matching_anns) > 1:
                created_at_formatted = created_at_dt.strftime('%Y-%m-%d %H:%M')
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
        
        # Regular announcement (not grouped)
        if ann['id'] not in processed_ids:
            receiver_name = "Everyone"
            receiver_username = None
            if ann['receiver_id']:
                receiver_full_name = f"{ann['receiver_first_name']} {ann['receiver_last_name']}".strip() if ann['receiver_first_name'] or ann['receiver_last_name'] else ''
                receiver_name = instructors_map.get(ann['receiver_username']) or faculty_heads_map.get(ann['receiver_username']) or receiver_full_name or ann['receiver_username']
                receiver_username = ann['receiver_username']
            
            # Django ORM returns datetime objects
            created_at_dt = ann['created_at']
            if isinstance(created_at_dt, datetime):
                created_at_formatted = created_at_dt.strftime('%Y-%m-%d %H:%M')
            else:
                # Fallback (shouldn't happen)
                created_at_formatted = str(created_at_dt)
            
            # Remove course marker from subject for display
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
    
    return announcements_data


def build_recipients_list(instructor_user, instructors_map, faculty_heads_map):
    """
    Build list of potential recipients for announcements.
    Returns list of dicts with username, name, and role.
    """
    recipients = []
    
    profile = getattr(instructor_user, 'profile', None)
    instructor_courses = []
    
    # Courses group
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
    
    # Instructors and Faculty Heads group
    instructors = User.objects.filter(profile__role='instructor').select_related('profile')
    faculty_heads = User.objects.filter(profile__role='faculty_head').select_related('profile')
    
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
    
    # Students group
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
    
    return recipients


@instructor_required
def instructor_announcements(request):
    from .models import Announcement
    
    instructor_user = request.instructor_user
    instructors_map = get_instructors_map()
    faculty_heads_map = get_faculty_heads_map()
    
    # Handle POST: Send announcements
    if request.method == 'POST':
        message = (request.POST.get('message') or '').strip()
        subject = (request.POST.get('subject') or '').strip()
        receivers_str = (request.POST.get('receivers') or '').strip()
        
        if message:
            receivers_list = [r.strip() for r in receivers_str.split(',') if r.strip()]
            send_announcements(instructor_user, message, subject, receivers_list)
            return redirect('instructor_announcements')
    
    # GET: Display announcements
    # Fetch announcements from database
    announcements = Announcement.objects.filter(
        Q(sender=instructor_user) | Q(receiver=instructor_user)
    ).select_related('sender', 'receiver').order_by('-created_at')
    
    # Convert to dict format for processing
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
            'created_at': ann.created_at,  # Django ORM returns datetime, not string
        })
    
    # Group course broadcast announcements
    announcements_data = group_course_announcements(
        all_announcements, 
        instructor_user.id, 
        instructors_map, 
        faculty_heads_map
    )
    
    # Build recipients list
    recipients = build_recipients_list(instructor_user, instructors_map, faculty_heads_map)
    
    # Separate sent and received messages
    sent_messages = [ann for ann in announcements_data if ann['is_sent']]
    received_messages = [ann for ann in announcements_data if not ann['is_sent']]
    
    # Prepare JSON for frontend
    announcements_json = json.dumps({str(ann['id']): {
        'subject': ann['subject'],
        'message': ann['message'],
        'sender': ann['sender'],
        'receiver': ann['receiver'],
        'created_at': ann['created_at'],
        'is_sent': ann['is_sent']
    } for ann in announcements_data})
    
    # Prepare instructor_info for header
    profile = getattr(instructor_user, 'profile', None)
    instructor_info = {
        'username': instructor_user.username,
        'name': f"{instructor_user.first_name} {instructor_user.last_name}".strip() or instructor_user.username,
        'faculty': profile.faculty.name if profile and profile.faculty else '-',
        'department': profile.department if profile else '-',
    }
    
    return render(request, 'instructor/instructor_announcements.html', {
        'all_announcements': announcements_data,
        'announcements_json': announcements_json,
        'sent_messages': sent_messages,
        'received_messages': received_messages,
        'recipients': recipients,
        'instructor_info': instructor_info,
    })


def set_instructor_session(request):
    """
    Set instructor username in session (only for authenticated instructors).
    Note: CSRF protection is enabled. Frontend must send CSRF token.
    """
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
    # Use profile.department as primary source, fallback to JSON data
    faculty_head_department = profile.department if profile and profile.department else faculty_head_data.get('department')
    
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
        # Filter courses by department - case-insensitive match and exclude empty departments
        courses = Course.objects.filter(
            department__iexact=faculty_head_department
        ).exclude(
            department=''
        ).select_related('instructor').prefetch_related('students')
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
        Q(receiver=faculty_head_user) | Q(receiver__isnull=True)
    ).exclude(sender=faculty_head_user).select_related('sender', 'receiver').order_by('-created_at')[:5]
    
    announcements_list = []
    for ann in latest_announcements:
        sender_name = ann.sender.get_full_name() or ann.sender.username
        
        # Remove course marker from subject for display
        display_subject = ann.subject
        if display_subject and display_subject.startswith('__COURSE:'):
            marker_end = display_subject.find('__', 9)
            if marker_end > 0:
                display_subject = display_subject[marker_end + 2:]
        
        announcements_list.append({
            'id': ann.id,
            'subject': display_subject,
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
                        # Log warning instead of silently failing
                        import logging
                        logger = logging.getLogger(__name__)
                        logger.warning(f"Instructor not found: {instructor_username} when adding course {course_name}")
                
                if not instructor_user:
                    default_instructor = UserProfile.objects.filter(role='instructor').first()
                    instructor_user = default_instructor.user if default_instructor else User.objects.first()
                
                # NOTE: Course name is assumed to be unique system-wide.
                # If Course.name is not unique=True in model, courses with same name in different departments will conflict.
                # This is a design assumption that should be documented in the model.
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
                        # Log warning instead of silently failing
                        import logging
                        logger = logging.getLogger(__name__)
                        logger.warning(f"Instructor not found: {instructor_username} when updating course {course.id}")
                
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
                # Log warning instead of silently failing
                import logging
                logger = logging.getLogger(__name__)
                logger.warning(f"Course not found: {course_id} when updating course")
        
        return redirect('all_courses')
    
    faculty_courses_with_instructors = []
    course_instructor_map = {}
    
    # NOTE: Technical debt - Course-Instructor relationship is stored in 3 places:
    # 1. profile.courses (ManyToMany on UserProfile)
    # 2. user.instructor_courses (reverse ForeignKey from Course.instructor)
    # 3. Course.instructor (ForeignKey on Course model)
    # This creates complexity and potential synchronization issues.
    # In a production system, this would be normalized to a single source of truth.
    # For academic purposes, this is acceptable but should be documented.
    
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
    
    # NOTE: Performance - N+1 query pattern below
    # For each course_name, we query Course and ProgramOutcome separately.
    # This is acceptable for small datasets but will become slow with many courses.
    # Optimization: Prefetch all courses and learning outcomes in bulk queries.
    
    # Optimize: Fetch all courses in one query
    all_courses_dict = {course.name: course for course in Course.objects.filter(name__in=all_course_names).select_related('instructor')}
    
    # Optimize: Fetch all learning outcomes in one query (grouped by course_name)
    # NOTE: Technical debt - ProgramOutcome uses course_name (string) instead of ForeignKey
    # This creates data integrity risk: typos, renames break relationships, no referential integrity
    # Better approach: Add course=ForeignKey(Course) to ProgramOutcome model
    learning_outcomes_by_course = {}
    if all_course_names:
        outcomes = ProgramOutcome.objects.filter(course_name__in=all_course_names).order_by('course_name', '-created_at')
        for outcome in outcomes:
            if outcome.course_name not in learning_outcomes_by_course:
                learning_outcomes_by_course[outcome.course_name] = outcome
    
    for course_name in sorted(all_course_names):
        instructors = course_instructor_map.get(course_name, [])
        
        course = all_courses_dict.get(course_name)
        if course and course.instructor:
            instructor_full_name = (course.instructor.first_name + ' ' + course.instructor.last_name).strip()
            instructor_name = instructor_full_name if instructor_full_name else course.instructor.username
            if instructor_name not in instructors:
                instructors.append(instructor_name)
        
        instructor_display = ', '.join(instructors) if instructors else 'Unknown'
        
        first_learning_outcome = learning_outcomes_by_course.get(course_name)
        
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
    from .models import Assignment, AssignmentSubmission
    
    profile = getattr(request.user, 'profile', None)
    
    # Get faculty head's department
    faculty_head_data = get_faculty_head_data(request.user.username)
    faculty_head_department = faculty_head_data.get('department')
    
    courses_data = []
    all_assignments = []
    
    if profile:
        courses = profile.courses.all().select_related('instructor').prefetch_related('assignments')
        
        # Optimize: Fetch all learning outcomes in one query to avoid N+1 pattern
        # NOTE: Small N+1 risk - For each course, we query ProgramOutcome separately.
        # This is acceptable for faculty heads with limited courses, but could be optimized
        # by prefetching all learning outcomes in bulk.
        course_names = [course.name for course in courses if not faculty_head_department or course.department == faculty_head_department]
        learning_outcomes_dict = {}
        if course_names:
            # Fetch first learning outcome for each course
            outcomes = ProgramOutcome.objects.filter(course_name__in=course_names).order_by('course_name', '-created_at')
            for outcome in outcomes:
                if outcome.course_name not in learning_outcomes_dict:
                    learning_outcomes_dict[outcome.course_name] = outcome
        
        for course in courses:
            # Filter by department - only show courses from faculty head's department
            if faculty_head_department and course.department != faculty_head_department:
                continue
            
            instructor_name = f"{course.instructor.first_name} {course.instructor.last_name}".strip() if course.instructor else ''
            if not instructor_name and course.instructor:
                instructor_name = course.instructor.username
            
            first_learning_outcome = learning_outcomes_dict.get(course.name)
            
            # Get assignments for this course
            assignments = course.assignments.all().order_by('-created_at')
            assignments_list = []
            for assignment in assignments:
                # Get submissions for this assignment
                submissions = AssignmentSubmission.objects.filter(assignment=assignment).select_related('student')
                submissions_list = []
                for submission in submissions:
                    student_name = f"{submission.student.first_name} {submission.student.last_name}".strip() or submission.student.username
                    submissions_list.append({
                        'id': submission.id,
                        'student_name': student_name,
                        'student_id': submission.student.student_id,
                        'file_url': submission.file.url if submission.file else None,
                        'file_name': submission.file.name.split('/')[-1] if submission.file else None,
                        'submitted_at': submission.submitted_at.strftime('%d/%m/%Y %H:%M'),
                    })
                
                assignment_data = {
                    'id': assignment.id,
                    'course_name': course.name,
                    'title': assignment.title,
                    'details': assignment.details,
                    'deadline': assignment.deadline.strftime('%d/%m/%Y %H:%M'),
                    'deadline_datetime': assignment.deadline.isoformat(),
                    'deadline_date': assignment.deadline.strftime('%Y-%m-%d'),
                    'deadline_time': assignment.deadline.strftime('%H:%M'),
                    'file_url': assignment.file.url if assignment.file else None,
                    'file_name': assignment.file.name.split('/')[-1] if assignment.file else None,
                    'created_by_id': assignment.created_by.id,
                    'submissions': json.dumps(submissions_list),
                }
                assignments_list.append(assignment_data)
                all_assignments.append(assignment_data)
            
            courses_data.append({
                'id': course.id,
                'name': course.name,
                'code': course.code,
                'instructor': instructor_name,
                'department': course.department,
                'credits': course.credits,
                'first_lo_id': first_learning_outcome.id if first_learning_outcome else None,
                'assignments': assignments_list,
            })
    
    context = {
        'courses': courses_data,
        'all_assignments': all_assignments,
    }
    return render(request, 'faculty/my_courses.html', context)

# Helper function for program_outcomes view
def build_program_outcomes_data(outcomes_qs, faculty_heads_map, instructors_map):
    """
    Build program outcomes data structure for display.
    This logic is reused in multiple places in program_outcomes view.
    """
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
    return outcomes_data


def generate_faculty_slug(faculty_name):
    """
    Generate consistent faculty slug from name.
    This ensures slug generation is uniform across the codebase.
    """
    if not faculty_name:
        return ''
    return faculty_name.lower().replace(' ', '-')


def generate_course_slug(course_name):
    """
    Generate safe course slug from name using Django's slugify.
    Handles Turkish characters, multiple spaces, and special characters.
    """
    from django.utils.text import slugify
    if not course_name:
        return ''
    return slugify(course_name)


def get_instructor_course_names(instructor_user):
    """
    Get all course names for an instructor from both database and JSON.
    This logic is reused in multiple views - centralizing it here prevents maintenance errors.
    
    Returns: list of unique course names
    """
    instructor_courses = Course.objects.filter(instructor=instructor_user)
    course_names_from_db = [course.name for course in instructor_courses]
    
    instructor_data = get_instructor_data(instructor_user.username)
    course_names_from_json = instructor_data.get('courses', []) or []
    
    course_names = list(set(course_names_from_db + course_names_from_json))
    return course_names


def get_course_for_outcome(profile, course_name):
    """
    Get course for a given course_name, adding it to profile if not already linked.
    This logic is reused in multiple views - centralizing it here.
    
    Returns: (course, course_id) tuple
    """
    if not profile or not course_name:
        return None, None
    
    # First check if course is already in profile
    course = None
    for c in profile.courses.all():
        if c.name.lower() == course_name.lower():
            course = c
            break
    
    # If not found, try to find by name (case-insensitive)
    if not course:
        course = Course.objects.filter(name__iexact=course_name).first()
        if course and profile:
            with transaction.atomic():
                profile.courses.add(course)
    
    course_id = course.id if course else None
    return course, course_id


def build_learning_outcomes_data(outcomes_qs):
    """
    Build learning outcomes data structure for display.
    This logic is reused in course_learning_outcomes view (error and normal cases).
    """
    outcomes_data = []
    for o in outcomes_qs:
        creator_name = o.created_by.get_full_name() or o.created_by.username
        related_program_outcomes = o.related_program_outcomes.all()
        outcomes_data.append({
            'id': o.id,
            'text': o.text,
            'course': o.course_name or '',
            'created_by': creator_name,
            'created_at': o.created_at.strftime('%Y-%m-%d %H:%M'),
            'related_program_outcomes': [{'id': po.id, 'text': po.text} for po in related_program_outcomes],
        })
    return outcomes_data


def get_learning_outcome_context(request, course_id, outcome_id):
    """
    Get common context for learning_outcome_detail and learning_outcome_graph views.
    Handles faculty_head vs instructor authentication and authorization.
    
    Returns: (outcome, course, faculty, is_faculty_head, instructor_user) tuple
    Raises: Http404, HttpResponseForbidden
    """
    is_faculty_head = False
    instructor_user = None
    faculty = None
    
    if not request.user.is_authenticated:
        from django.shortcuts import redirect
        return redirect('faculty-head-login')
    
    profile = getattr(request.user, 'profile', None)
    if profile and profile.role == 'faculty_head':
        is_faculty_head = True
        course = get_object_or_404(Course, id=course_id)
        # CRITICAL: Check faculty access
        outcome = get_object_or_404(ProgramOutcome, id=outcome_id, course_name=course.name)
        if not check_faculty_access(request.user, outcome):
            return HttpResponseForbidden("You don't have permission to access this outcome.")
        faculty = profile.faculty if profile else None
    else:
        # Instructor kontrolü
        if not hasattr(request, 'instructor_user'):
            try:
                user_profile = request.user.profile
                if user_profile.role != 'instructor':
                    return HttpResponseForbidden("You are not allowed here")
            except AttributeError:
                return HttpResponseForbidden("User profile not found")
            request.instructor_user = request.user
        instructor_user = request.instructor_user
        course = get_object_or_404(Course, id=course_id, instructor=instructor_user)
        outcome = get_object_or_404(ProgramOutcome, id=outcome_id, course_name=course.name, created_by=instructor_user)
        
        instructor_data = get_instructor_data(instructor_user.username)
        instructor_faculty = instructor_data.get('faculty')
        
        # Use helper function instead of inline Faculty creation
        if instructor_faculty:
            profile = getattr(instructor_user, 'profile', None)
            faculty = ensure_faculty_for_profile(profile, instructor_faculty)
    
    return outcome, course, faculty, is_faculty_head, instructor_user


def build_program_outcomes_with_percentages(outcome, faculty):
    """
    Build program outcomes data with percentages for learning outcome detail/graph.
    Optimizes N+1 query by prefetching LearningOutcomeProgramOutcome relationships.
    
    Returns: (program_outcomes_data, available_program_outcomes) tuple
    """
    from .models import LearningOutcomeProgramOutcome
    
    # Optimize: Prefetch all relationships in one query
    related_program_outcomes = outcome.related_program_outcomes.all().order_by('id')
    
    # Get all percentages in one query instead of N queries
    lo_po_map = {
        (lo_po.learning_outcome_id, lo_po.program_outcome_id): lo_po.percentage
        for lo_po in LearningOutcomeProgramOutcome.objects.filter(
            learning_outcome=outcome,
            program_outcome__in=related_program_outcomes
        ).select_related('learning_outcome', 'program_outcome')
    }
    
    program_outcomes_data = []
    for po in related_program_outcomes:
        percentage = lo_po_map.get((outcome.id, po.id), 0)
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
        available_program_outcomes = [
            {'id': po.id, 'text': po.text}
            for po in available_program_outcomes_qs
        ]
    
    return program_outcomes_data, available_program_outcomes


def check_faculty_access(user, outcome):
    """
    Check if user has access to modify/delete an outcome based on faculty.
    Returns True if user's faculty matches outcome's faculty, False otherwise.
    """
    profile = getattr(user, 'profile', None)
    if not profile:
        return False
    
    user_faculty = profile.faculty
    outcome_faculty = outcome.faculty
    
    # Both must have faculty and they must match
    if not user_faculty or not outcome_faculty:
        return False
    
    return user_faculty.id == outcome_faculty.id


def ensure_faculty_for_profile(profile, faculty_name_from_json):
    """
    Ensure faculty exists and is linked to profile.
    NOTE: This is data normalization logic that ideally belongs in a service layer,
    but is placed here for academic project simplicity.
    """
    from .models import Faculty
    
    if not profile:
        return None
    
    faculty = profile.faculty
    if not faculty and faculty_name_from_json:
        with transaction.atomic():
            faculty_slug = generate_faculty_slug(faculty_name_from_json)
            try:
                faculty = Faculty.objects.get(slug=faculty_slug)
            except Faculty.DoesNotExist:
                faculty, _ = Faculty.objects.get_or_create(
                    slug=faculty_slug,
                    defaults={'name': faculty_name_from_json}
                )
            profile.faculty = faculty
            profile.save()
    return faculty


@faculty_head_required
def program_outcomes(request):
    from .models import Faculty
    
    profile = getattr(request.user, 'profile', None)
    faculty_head_data = get_faculty_head_data(request.user.username)
    faculty_head_department = faculty_head_data.get('department')
    faculty_name_from_json = faculty_head_data.get('faculty')
    
    # Ensure faculty exists (data normalization)
    faculty = ensure_faculty_for_profile(profile, faculty_name_from_json)
    
    if request.method == 'POST':
        text = (request.POST.get('text') or '').strip()
        # NOTE: creator check is redundant - @faculty_head_required ensures authenticated user
        # This branch will never execute, but kept for defensive programming
        creator = request.user  # Always authenticated due to decorator
        
        faculty_heads_map = get_faculty_heads_map()
        instructors_map = get_instructors_map()
        
        # Get outcomes query (reused logic)
        outcomes_qs = ProgramOutcome.objects.filter(
            faculty=faculty, 
            course_name=''  # NOTE: Technical debt - empty string used to distinguish program outcomes from learning outcomes
        ).select_related('created_by').prefetch_related('learning_outcomes__created_by').order_by('-created_at')
        
        if not text:
            # Validation error: empty text
            outcomes_data = build_program_outcomes_data(outcomes_qs, faculty_heads_map, instructors_map)
            return render(request, 'faculty/program_outcomes.html', {
                'error': 'Outcome text is required.',
                'outcomes_data': outcomes_data,
                'faculty_head_department': faculty_head_department,
            })
        
        # Create new program outcome
        with transaction.atomic():
            ProgramOutcome.objects.create(text=text, course_name='', faculty=faculty, created_by=creator)
        return redirect('program_outcomes')
    
    # GET: Display program outcomes
    faculty_heads_map = get_faculty_heads_map()
    instructors_map = get_instructors_map()
    
    outcomes_qs = ProgramOutcome.objects.filter(
        faculty=faculty, 
        course_name=''  # NOTE: Technical debt - empty string used to distinguish program outcomes from learning outcomes
    ).select_related('created_by').prefetch_related('learning_outcomes__created_by').order_by('-created_at')
    
    outcomes_data = build_program_outcomes_data(outcomes_qs, faculty_heads_map, instructors_map)
    
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
        # Use consistent slug generation
        faculty_slug = generate_faculty_slug(faculty_name_from_json)
        try:
            faculty = Faculty.objects.get(slug=faculty_slug)
        except Faculty.DoesNotExist:
            faculty, _ = Faculty.objects.get_or_create(
                slug=faculty_slug,
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
        # NOTE: creator check is redundant - @faculty_head_required ensures authenticated user
        creator = request.user  # Always authenticated due to decorator
        
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
        
        # NOTE: Technical debt - course_name is stored as string instead of ForeignKey
        # This creates data integrity risk: typos, renames break relationships, no referential integrity
        # Better approach: Add course=ForeignKey(Course, null=True, blank=True) to ProgramOutcome model
        # Current validation and error handling are good for academic level
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
        course_name_slug = generate_course_slug(course_name)
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
        if not profile.courses.filter(id=course.id).exists():
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
    
    course_name_slug = generate_course_slug(outcome.course_name)
    
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
    
    course_name_slug = generate_course_slug(outcome.course_name)
    
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
    profile = getattr(request.user, 'profile', None)
    faculty = profile.faculty if profile else None
    
    # CRITICAL: Check faculty access to prevent unauthorized updates
    outcome = get_object_or_404(ProgramOutcome, id=outcome_id, course_name__isnull=False)
    if not check_faculty_access(request.user, outcome):
        return HttpResponseForbidden("You don't have permission to update this outcome.")
    
    if request.method == 'POST':
        text = (request.POST.get('text') or '').strip()
        if text:
            with transaction.atomic():
                outcome.text = text
                outcome.save()
        
        # Use helper function to get course
        course, course_id = get_course_for_outcome(profile, outcome.course_name)
        if course_id:
            return redirect('faculty_head_learning_outcome_detail', course_id=course_id, outcome_id=outcome_id)
        
        course_name_slug = generate_course_slug(outcome.course_name)
        return redirect('faculty_head_course_learning_outcomes', course_name=course_name_slug)
    
    return JsonResponse({'text': outcome.text})

@faculty_head_required
def faculty_head_delete_learning_outcome(request, outcome_id):
    """Delete a learning outcome (for faculty head)"""
    profile = getattr(request.user, 'profile', None)
    outcome = get_object_or_404(ProgramOutcome, id=outcome_id, course_name__isnull=False)
    
    # CRITICAL: Check faculty access to prevent unauthorized deletions
    if not check_faculty_access(request.user, outcome):
        return HttpResponseForbidden("You don't have permission to delete this outcome.")
    
    course_name = outcome.course_name
    course_name_slug = generate_course_slug(course_name)
    
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
    
    # CRITICAL: Check faculty access for both outcomes
    if not check_faculty_access(request.user, outcome) or not check_faculty_access(request.user, program_outcome):
        return HttpResponseForbidden("You don't have permission to unlink these outcomes.")
    
    with transaction.atomic():
        outcome.related_program_outcomes.remove(program_outcome)
    
    profile = getattr(request.user, 'profile', None)
    # Use helper function to get course
    course, course_id = get_course_for_outcome(profile, outcome.course_name)
    if course_id:
        return redirect('faculty_head_learning_outcome_detail', course_id=course_id, outcome_id=outcome_id)
    
    course_name_slug = generate_course_slug(outcome.course_name)
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
    course_name_slug = generate_course_slug(outcome.course_name)
    return redirect('faculty_head_course_learning_outcomes', course_name=course_name_slug)

@faculty_head_required
def give_grade(request, course_id):
    course = get_object_or_404(Course, id=course_id)
    return render(request, 'faculty/give_grade.html', {'course': course})

@faculty_head_required
def faculty_head_grades(request):
    profile = getattr(request.user, 'profile', None)
    
    faculty_head_data = get_faculty_head_data(request.user.username)
    faculty_head_department = profile.department if profile and profile.department else faculty_head_data.get('department')
    
    courses = []
    if profile and faculty_head_department:
        # Normalize department for comparison
        fh_dept_normalized = faculty_head_department.strip().lower()
        
        # Get courses directly from database filtered by department (case-insensitive)
        # This ensures we only get courses that actually belong to the faculty head's department
        from core.models import Course
        department_courses = Course.objects.filter(
            department__iexact=faculty_head_department
        ).exclude(
            department=''
        )
        
        # Also check that the course is in the profile (additional security check)
        profile_course_names = set(profile.courses.values_list('name', flat=True))
        
        for course in department_courses:
            # Only include courses that are also in the profile
            if course.name in profile_course_names:
                courses.append(course.name)
    
    context = {
        'faculty_head_courses': courses,
        'faculty_head': json.dumps(faculty_head_data),
        'user': request.user,
    }
    return render(request, 'faculty/faculty_head_grades.html', context)

@faculty_head_required
def faculty_head_course_grades(request, course_name):
    from .models import Assessment
    
    profile = getattr(request.user, 'profile', None)
    faculty_head_data = get_faculty_head_data(request.user.username)
    faculty_head_department = profile.department if profile and profile.department else faculty_head_data.get('department')
    
    try:
        course = Course.objects.get(name=course_name)
    except Course.DoesNotExist:
        return redirect('faculty-head-grades')
    
    if profile and course not in profile.courses.all():
        return HttpResponseForbidden("You don't have access to this course")
    
    # Check department match (case-insensitive)
    if faculty_head_department:
        course_dept_normalized = course.department.strip().lower() if course.department else ''
        fh_dept_normalized = faculty_head_department.strip().lower()
        if course_dept_normalized != fh_dept_normalized:
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
    
    # Course'a kayıtlı öğrencileri al
    students = Student.objects.filter(courses=course).order_by('username')
    students_with_grades = []
    for student in students:
        grade_obj = Grade.objects.filter(student=student, course=course).first()
        grades_dict = {}
        is_finalized = False
        
        if grade_obj:
            # Assessment scores'dan notları al
            if grade_obj.assessment_scores:
                # Get individual scores from assessment_scores
                assessment_types = ['midterm', 'final', 'proje', 'homework', 'absence', 'quiz']
                for assessment_type in assessment_types:
                    count = getattr(assessment, assessment_type, 0)
                    for i in range(1, count + 1):
                        key = f'{assessment_type}_{i}'
                        score = grade_obj.get_individual_score(key)
                        if score is not None:
                            assessment_type_labels = {
                                'midterm': 'Midterm',
                                'final': 'Final',
                                'proje': 'Proje',
                                'homework': 'Homework',
                                'absence': 'Absence',
                                'quiz': 'Quiz'
                            }
                            label = assessment_type_labels.get(assessment_type, assessment_type.capitalize())
                            grades_dict[f'{label} {i}'] = score
            
            # Eski alanlardan notları al (geriye dönük uyumluluk)
            if not grades_dict:
                if grade_obj.midterm is not None:
                    grades_dict['Midterm'] = grade_obj.midterm
                if grade_obj.final is not None:
                    grades_dict['Final'] = grade_obj.final
                if grade_obj.proje is not None:
                    grades_dict['Proje'] = grade_obj.proje
                if grade_obj.homework is not None:
                    grades_dict['Homework'] = grade_obj.homework
                if grade_obj.absence is not None:
                    grades_dict['Absence'] = grade_obj.absence
                if grade_obj.quiz is not None:
                    grades_dict['Quiz'] = grade_obj.quiz
            
            is_finalized = getattr(grade_obj, 'is_finalized', False)
        
        students_with_grades.append({
            'student': student,
            'grades': grades_dict,
            'is_finalized': is_finalized
        })
    
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
        'assessment': assessment,
        'students': students,
        'students_with_grades': students_with_grades,
        'students_with_grades_json': students_with_grades_json,
        'uploaded_files_info': json.dumps(uploaded_files_info),
        'is_finalized': is_finalized
    })

@faculty_head_required
def faculty_head_delete_uploaded_csv(request, course_name):
    """
    Delete uploaded CSV file information from grades.
    NOTE: CSRF protection is enabled. Frontend must send CSRF token.
    """
    if request.method != 'POST':
        return JsonResponse({'error': 'Method not allowed'}, status=405)
    
    profile = getattr(request.user, 'profile', None)
    faculty_head_data = get_faculty_head_data(request.user.username)
    faculty_head_department = faculty_head_data.get('department')
    
    # CRITICAL: Filter by department to prevent conflicts if Course.name is not unique
    # NOTE: Course.name is now unique=True, but department filter adds extra safety
    try:
        if faculty_head_department:
            course = Course.objects.get(name=course_name, department=faculty_head_department)
        else:
            course = Course.objects.get(name=course_name)
    except Course.DoesNotExist:
        return JsonResponse({'error': 'Course not found'}, status=404)
    except Course.MultipleObjectsReturned:
        # Fallback: if multiple courses exist, use department filter
        if faculty_head_department:
            course = Course.objects.filter(name=course_name, department=faculty_head_department).first()
            if not course:
                return JsonResponse({'error': 'Course not found'}, status=404)
        else:
            return JsonResponse({'error': 'Multiple courses found with same name'}, status=400)
    
    if profile and not profile.courses.filter(id=course.id).exists():
        return JsonResponse({'error': 'Access denied'}, status=403)
    
    if faculty_head_department:
        course_dept_normalized = course.department.strip().lower() if course.department else ''
        fh_dept_normalized = faculty_head_department.strip().lower()
        if course_dept_normalized != fh_dept_normalized:
            return JsonResponse({'error': 'Access denied'}, status=403)
    
    # Course'daki tüm grade'lerden uploaded file bilgisini temizle
    # assessment_scores JSONField'ından file_name ve uploaded_at bilgilerini kaldır
    from django.db import transaction
    with transaction.atomic():
        grades = Grade.objects.filter(course=course)
        for grade in grades:
            if grade.assessment_scores:
                # Remove file_name and uploaded_at from all assessment entries
                updated_scores = {}
                for key, value in grade.assessment_scores.items():
                    if isinstance(value, dict):
                        # Keep only the score, remove file_name and uploaded_at
                        updated_scores[key] = {'score': value.get('score')}
                    else:
                        # Legacy format, keep as is
                        updated_scores[key] = value
                grade.assessment_scores = updated_scores
                grade.save()
    
    return JsonResponse({'status': 'ok'})

@faculty_head_required
def faculty_head_update_manual_grades(request, course_name):
    if request.method != 'POST':
        return JsonResponse({'error': 'Method not allowed'}, status=405)
    
    profile = getattr(request.user, 'profile', None)
    faculty_head_data = get_faculty_head_data(request.user.username)
    faculty_head_department = faculty_head_data.get('department')
    
    # CRITICAL: Filter by department to prevent conflicts if Course.name is not unique
    # NOTE: Course.name is now unique=True, but department filter adds extra safety
    try:
        if faculty_head_department:
            course = Course.objects.get(name=course_name, department=faculty_head_department)
        else:
            course = Course.objects.get(name=course_name)
    except Course.DoesNotExist:
        return JsonResponse({'error': 'Course not found'}, status=404)
    except Course.MultipleObjectsReturned:
        # Fallback: if multiple courses exist, use department filter
        if faculty_head_department:
            course = Course.objects.filter(name=course_name, department=faculty_head_department).first()
            if not course:
                return JsonResponse({'error': 'Course not found'}, status=404)
        else:
            return JsonResponse({'error': 'Multiple courses found with same name'}, status=400)
    
    if profile and not profile.courses.filter(id=course.id).exists():
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
def faculty_head_finalize_grades(request, course_name):
    if request.method != 'POST':
        return JsonResponse({'error': 'Method not allowed'}, status=405)
    
    from django.utils import timezone
    
    profile = getattr(request.user, 'profile', None)
    faculty_head_data = get_faculty_head_data(request.user.username)
    faculty_head_department = faculty_head_data.get('department')
    
    # CRITICAL: Filter by department to prevent conflicts if Course.name is not unique
    # NOTE: Course.name is now unique=True, but department filter adds extra safety
    try:
        if faculty_head_department:
            course = Course.objects.get(name=course_name, department=faculty_head_department)
        else:
            course = Course.objects.get(name=course_name)
    except Course.DoesNotExist:
        return JsonResponse({'error': 'Course not found'}, status=404)
    except Course.MultipleObjectsReturned:
        # Fallback: if multiple courses exist, use department filter
        if faculty_head_department:
            course = Course.objects.filter(name=course_name, department=faculty_head_department).first()
            if not course:
                return JsonResponse({'error': 'Course not found'}, status=404)
        else:
            return JsonResponse({'error': 'Multiple courses found with same name'}, status=400)
    
    if profile and not profile.courses.filter(id=course.id).exists():
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
    
    # Use helper function to get course names (prevents code duplication)
    course_names = get_instructor_course_names(instructor_user)
    
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
            faculty_slug = generate_faculty_slug(instructor_faculty)
            try:
                faculty = Faculty.objects.get(slug=faculty_slug)
            except Faculty.DoesNotExist:
                faculty, _ = Faculty.objects.get_or_create(
                    slug=faculty_slug,
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
                    course_name_slug = generate_course_slug(course_name)
                    return redirect('course_learning_outcomes', course_name=course_name_slug)
                else:
                    # Error case: Reuse same logic as GET request
                    outcomes_qs = ProgramOutcome.objects.filter(
                        course_name__iexact=course_name
                    ).select_related('created_by').prefetch_related('related_program_outcomes').order_by('-created_at')
                    
                    course = Course.objects.filter(name__iexact=course_name, instructor=instructor_user).first()
                    if not course:
                        profile = getattr(instructor_user, 'profile', None)
                        if profile:
                            course = profile.courses.filter(name__iexact=course_name).first()
                        if not course:
                            course = instructor_user.instructor_courses.filter(name__iexact=course_name).first()
                    course_id = course.id if course else None
                    
                    # Use helper function to build outcomes data
                    outcomes_data = build_learning_outcomes_data(outcomes_qs)
                    
                    # Use title() to capitalize first letter of each word
                    display_course_name = course.name.title() if course and course.name else course_name.title()
                    
                    return render(
                        request,
                        'instructor/course_learning_outcomes.html',
                        {
                            'course_name': display_course_name,
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
                course_name_slug = generate_course_slug(course_name)
                return redirect('course_learning_outcomes', course_name=course_name_slug)
    
    # Use case-insensitive search for course_name to handle name variations
    outcomes_qs = ProgramOutcome.objects.filter(
        course_name__iexact=course_name
    ).select_related('created_by').prefetch_related('related_program_outcomes').order_by('-created_at')
    
    # CRITICAL: Verify instructor owns this course
    # Try to find course - first by instructor, then by name, then from profile
    # Use case-insensitive search (iexact) to handle name variations
    course = Course.objects.filter(name__iexact=course_name, instructor=instructor_user).first()
    if not course:
        # Try to find from instructor's profile courses
        profile = getattr(instructor_user, 'profile', None)
        if profile:
            course = profile.courses.filter(name__iexact=course_name).first()
        if not course:
            course = instructor_user.instructor_courses.filter(name__iexact=course_name).first()
    
    # CRITICAL: If course not found or instructor doesn't own it, deny access
    if not course:
        return HttpResponseForbidden("You don't have access to this course.")
    
    course_id = course.id if course else None
    # Use title() to capitalize first letter of each word (e.g., "computer architecture" -> "Computer Architecture")
    display_course_name = course.name.title() if course.name else course_name.title()
    
    # Use helper function to build outcomes data
    outcomes_data = build_learning_outcomes_data(outcomes_qs)
    
    # Prepare instructor_info for header
    profile = getattr(instructor_user, 'profile', None)
    instructor_info = {
        'username': instructor_user.username,
        'name': f"{instructor_user.first_name} {instructor_user.last_name}".strip() or instructor_user.username,
        'faculty': profile.faculty.name if profile and profile.faculty else '-',
        'department': profile.department if profile else '-',
    }
    
    return render(
        request,
        'instructor/course_learning_outcomes.html',
        {
            'course_name': display_course_name,
            'course_id': course_id,
            'outcomes_data': outcomes_data,
            'program_outcomes': program_outcomes,
            'instructor_info': instructor_info,
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
            course_name_slug = generate_course_slug(outcome.course_name)
            return redirect('course_learning_outcomes', course_name=course_name_slug)
    
    return JsonResponse({'text': outcome.text})


def learning_outcome_detail(request, course_id, outcome_id):
    """Show detail page for a learning outcome with linked program outcomes"""
    # Use helper function for common authentication/authorization logic
    result = get_learning_outcome_context(request, course_id, outcome_id)
    if isinstance(result, HttpResponseForbidden) or hasattr(result, 'status_code'):
        return result
    outcome, course, faculty, is_faculty_head, instructor_user = result
    
    # Use helper function to build program outcomes data (optimizes N+1 query)
    program_outcomes_data, available_program_outcomes = build_program_outcomes_with_percentages(outcome, faculty)
    
    course_name_slug = generate_course_slug(outcome.course_name)
    
    profile = getattr(instructor_user, 'profile', None)
    instructor_info = {
        'username': instructor_user.username,
        'name': f"{instructor_user.first_name} {instructor_user.last_name}".strip() or instructor_user.username,
        'faculty': profile.faculty.name if profile and profile.faculty else '-',
        'department': profile.department if profile else '-',
    }
    
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
            'instructor_info': instructor_info,
        }
    )

def learning_outcome_graph(request, course_id, outcome_id):
    """Show graph view for learning outcome"""
    # Use helper function for common authentication/authorization logic
    result = get_learning_outcome_context(request, course_id, outcome_id)
    if isinstance(result, HttpResponseForbidden) or hasattr(result, 'status_code'):
        return result
    outcome, course, faculty, is_faculty_head, instructor_user = result
    
    # Use helper function to build program outcomes data (optimizes N+1 query)
    program_outcomes_data, _ = build_program_outcomes_with_percentages(outcome, faculty)
    
    course_name_slug = generate_course_slug(outcome.course_name)
    
    instructor_info = None
    if instructor_user and not is_faculty_head:
        profile = getattr(instructor_user, 'profile', None)
        instructor_info = {
            'username': instructor_user.username,
            'name': f"{instructor_user.first_name} {instructor_user.last_name}".strip() or instructor_user.username,
            'faculty': profile.faculty.name if profile and profile.faculty else '-',
            'department': profile.department if profile else '-',
        }
    
    return render(
        request,
        'instructor/learning_outcome_graph.html',
        {
            'outcome': outcome,
            'course': course,
            'program_outcomes': program_outcomes_data,
            'course_name_slug': course_name_slug,
            'is_faculty_head': is_faculty_head,
            'instructor_info': instructor_info,
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
        # CRITICAL: Verify program_outcome belongs to same faculty as instructor
        program_outcome = get_object_or_404(ProgramOutcome, id=program_outcome_id)
        instructor_data = get_instructor_data(instructor_user.username)
        instructor_faculty_name = instructor_data.get('faculty')
        if instructor_faculty_name:
            profile = getattr(instructor_user, 'profile', None)
            instructor_faculty = ensure_faculty_for_profile(profile, instructor_faculty_name)
            if instructor_faculty and program_outcome.faculty and program_outcome.faculty.id != instructor_faculty.id:
                return JsonResponse({'status': 'error', 'message': 'You don\'t have permission to link this program outcome.'}, status=403)
        
        try:
            with transaction.atomic():
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
    profile = getattr(request.user, 'profile', None)
    faculty = profile.faculty if profile else None
    
    # CRITICAL: Check faculty access for both outcomes
    outcome = get_object_or_404(ProgramOutcome, id=outcome_id)
    if not check_faculty_access(request.user, outcome):
        return JsonResponse({'status': 'error', 'message': 'You don\'t have permission to update this outcome.'}, status=403)
    
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
        # CRITICAL: Check program_outcome ownership - must be same faculty
        program_outcome = get_object_or_404(ProgramOutcome, id=program_outcome_id)
        if not check_faculty_access(request.user, program_outcome):
            return JsonResponse({'status': 'error', 'message': 'You don\'t have permission to link this program outcome.'}, status=403)
        
        # NOTE: Finalized check would go here if Grade model had is_finalized field
        # For now, learning outcomes can be updated even if grades are finalized
        
        try:
            with transaction.atomic():
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
        course_name_slug = generate_course_slug(outcome.course_name)
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
                        course_name_slug = generate_course_slug(outcome.course_name)
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
        course_name_slug = generate_course_slug(outcome.course_name)
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
    
    course_name_slug = generate_course_slug(course_name)
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
            
            # Prepare instructor_info for header
            profile = getattr(instructor_user, 'profile', None)
            instructor_info = {
                'username': instructor_user.username,
                'name': f"{instructor_user.first_name} {instructor_user.last_name}".strip() or instructor_user.username,
                'faculty': profile.faculty.name if profile and profile.faculty else '-',
                'department': profile.department if profile else '-',
            }
            
            return render(
                request,
                'instructor/create_learning_outcome.html',
                {
                    'error': 'Outcome text and course are required.',
                    'course_name': course_name,
                    'instructor_courses': course_names,
                    'instructor_info': instructor_info,
                }
            )
        
        with transaction.atomic():
            ProgramOutcome.objects.create(text=text, course_name=course_name, created_by=instructor_user)
        from django.urls import reverse
        course_name_slug = generate_course_slug(course_name)
        redirect_url = reverse('course_learning_outcomes', args=[course_name_slug])
        redirect_url += f'?username={username}'
        return redirect(redirect_url)
    
    # Use helper function to get course names (prevents code duplication)
    course_names = get_instructor_course_names(instructor_user)
    
    course_name_from_get = request.GET.get('course', '')
    
    # Prepare instructor_info for header
    profile = getattr(instructor_user, 'profile', None)
    instructor_info = {
        'username': instructor_user.username,
        'name': f"{instructor_user.first_name} {instructor_user.last_name}".strip() or instructor_user.username,
        'faculty': profile.faculty.name if profile and profile.faculty else '-',
        'department': profile.department if profile else '-',
    }
    
    return render(
        request,
        'instructor/create_learning_outcome.html',
        {
            'course_name': course_name_from_get,
            'instructor_courses': course_names,
            'instructor_info': instructor_info,
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
    from .models import Assignment, AssignmentSubmission
    
    if not request.user.is_authenticated:
        return redirect('student-login')
    
    try:
        student = Student.objects.get(user=request.user)
        courses = student.courses.all().select_related('instructor').prefetch_related('assignments')
        
        courses_data = []
        all_assignments = []
        
        for course in courses:
            instructor_name = f"{course.instructor.first_name} {course.instructor.last_name}".strip() or course.instructor.username
            
            # Get assignments for this course
            assignments = course.assignments.all().order_by('-created_at')
            assignments_list = []
            for assignment in assignments:
                # Check if student has submitted this assignment
                submission = AssignmentSubmission.objects.filter(assignment=assignment, student=student).first()
                
                assignment_data = {
                    'id': assignment.id,
                    'course_name': course.name,
                    'title': assignment.title,
                    'details': assignment.details,
                    'deadline': assignment.deadline.strftime('%d/%m/%Y %H:%M'),
                    'deadline_datetime': assignment.deadline.isoformat(),
                    'file_url': assignment.file.url if assignment.file else None,
                    'file_name': assignment.file.name.split('/')[-1] if assignment.file else None,
                    'has_submission': submission is not None,
                    'submission_file_url': submission.file.url if submission and submission.file else None,
                    'submission_file_name': submission.file.name.split('/')[-1] if submission and submission.file else None,
                    'submitted_at': submission.submitted_at.strftime('%d/%m/%Y %H:%M') if submission else None,
                }
                assignments_list.append(assignment_data)
                all_assignments.append(assignment_data)
            
            courses_data.append({
                'id': course.id,
                'name': course.name,
                'code': course.code,
                'instructor': instructor_name,
                'department': course.department,
                'credits': course.credits,
                'assignments': assignments_list,
            })
    except Student.DoesNotExist:
        courses_data = []
        all_assignments = []
    
    return render(request, "student/courses.html", {
        'courses': courses_data,
        'all_assignments': all_assignments
    })

@csrf_exempt
def submit_assignment(request, assignment_id):
    from .models import Assignment, AssignmentSubmission
    
    if not request.user.is_authenticated:
        return JsonResponse({'error': 'Authentication required'}, status=401)
    
    if request.method != 'POST':
        return JsonResponse({'error': 'Only POST allowed'}, status=405)
    
    try:
        student = Student.objects.get(user=request.user)
    except Student.DoesNotExist:
        return JsonResponse({'error': 'Student profile not found'}, status=404)
    
    try:
        assignment = Assignment.objects.get(id=assignment_id)
    except Assignment.DoesNotExist:
        return JsonResponse({'error': 'Assignment not found'}, status=404)
    
    # Check if student is enrolled in the course
    if assignment.course not in student.courses.all():
        return JsonResponse({'error': 'You are not enrolled in this course'}, status=403)
    
    # Check if deadline has passed
    from django.utils import timezone
    if assignment.deadline < timezone.now():
        return JsonResponse({'error': 'Deadline has passed'}, status=400)
    
    file = request.FILES.get('file')
    if not file:
        return JsonResponse({'error': 'File is required'}, status=400)
    
    # Validate file type
    if not file.name.lower().endswith('.pdf'):
        return JsonResponse({'error': 'Only PDF files are allowed'}, status=400)
    
    # Create or update submission
    submission, created = AssignmentSubmission.objects.update_or_create(
        assignment=assignment,
        student=student,
        defaults={'file': file}
    )
    
    return JsonResponse({
        'success': True,
        'message': 'Assignment submitted successfully',
        'submission': {
            'file_url': submission.file.url if submission.file else None,
            'file_name': submission.file.name.split('/')[-1] if submission.file else None,
            'submitted_at': submission.submitted_at.strftime('%d/%m/%Y %H:%M'),
        }
    })

@csrf_exempt
def delete_submission(request, assignment_id):
    from .models import Assignment, AssignmentSubmission
    
    if not request.user.is_authenticated:
        return JsonResponse({'error': 'Authentication required'}, status=401)
    
    if request.method != 'POST':
        return JsonResponse({'error': 'Only POST allowed'}, status=405)
    
    try:
        student = Student.objects.get(user=request.user)
    except Student.DoesNotExist:
        return JsonResponse({'error': 'Student profile not found'}, status=404)
    
    try:
        assignment = Assignment.objects.get(id=assignment_id)
    except Assignment.DoesNotExist:
        return JsonResponse({'error': 'Assignment not found'}, status=404)
    
    # Check if student is enrolled in the course
    if assignment.course not in student.courses.all():
        return JsonResponse({'error': 'You are not enrolled in this course'}, status=403)
    
    try:
        submission = AssignmentSubmission.objects.get(assignment=assignment, student=student)
        if submission.file:
            submission.file.delete()
        submission.delete()
        return JsonResponse({'success': True, 'message': 'Submission deleted successfully'})
    except AssignmentSubmission.DoesNotExist:
        return JsonResponse({'error': 'Submission not found'}, status=404)

@instructor_required
@csrf_exempt
def delete_student_submission(request, submission_id):
    from .models import AssignmentSubmission
    
    if request.method != 'POST':
        return JsonResponse({'error': 'Only POST allowed'}, status=405)
    
    try:
        submission = AssignmentSubmission.objects.get(id=submission_id)
        assignment = submission.assignment
        
        # Check if instructor has access to this course
        instructor_user = request.instructor_user
        profile = getattr(instructor_user, 'profile', None)
        if profile and assignment.course not in profile.courses.all():
            return JsonResponse({'error': 'You do not have access to this course'}, status=403)
        
        if submission.file:
            submission.file.delete()
        submission.delete()
        return JsonResponse({'success': True, 'message': 'Student submission deleted successfully'})
    except AssignmentSubmission.DoesNotExist:
        return JsonResponse({'error': 'Submission not found'}, status=404)

@instructor_required
@csrf_exempt
def update_assignment(request, assignment_id):
    from .models import Assignment
    from django.utils import timezone
    from datetime import datetime
    
    if request.method != 'POST':
        return JsonResponse({'error': 'Only POST allowed'}, status=405)
    
    try:
        assignment = Assignment.objects.get(id=assignment_id)
    except Assignment.DoesNotExist:
        return JsonResponse({'error': 'Assignment not found'}, status=404)
    
    # Check if instructor has access to this course
    instructor_user = request.instructor_user
    profile = getattr(instructor_user, 'profile', None)
    if profile and assignment.course not in profile.courses.all():
        return JsonResponse({'error': 'You do not have access to this course'}, status=403)
    
    # Check if instructor created this assignment
    if assignment.created_by != instructor_user:
        return JsonResponse({'error': 'You can only edit your own assignments'}, status=403)
    
    title = request.POST.get('title', '').strip()
    details = request.POST.get('details', '').strip()
    deadline_date = request.POST.get('deadline_date', '').strip()
    deadline_time = request.POST.get('deadline_time', '').strip()
    file = request.FILES.get('file')
    
    if not title or not details or not deadline_date or not deadline_time:
        return JsonResponse({'error': 'Title, details, and deadline are required'}, status=400)
    
    # Parse deadline
    try:
        deadline_str = f"{deadline_date} {deadline_time}"
        deadline = datetime.strptime(deadline_str, '%Y-%m-%d %H:%M')
        deadline = timezone.make_aware(deadline)
    except ValueError:
        return JsonResponse({'error': 'Invalid deadline format'}, status=400)
    
    # Validate file type if provided
    if file:
        if not file.name.lower().endswith('.pdf'):
            return JsonResponse({'error': 'Only PDF files are allowed'}, status=400)
        # Delete old file if exists
        if assignment.file:
            assignment.file.delete()
        assignment.file = file
    
    # Update assignment
    assignment.title = title
    assignment.details = details
    assignment.deadline = deadline
    assignment.save()
    
    return JsonResponse({
        'success': True,
        'message': 'Assignment updated successfully',
        'assignment': {
            'id': assignment.id,
            'title': assignment.title,
            'details': assignment.details,
            'deadline': assignment.deadline.strftime('%d/%m/%Y %H:%M'),
            'file_url': assignment.file.url if assignment.file else None,
            'file_name': assignment.file.name.split('/')[-1] if assignment.file else None,
        }
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
    """Show all announcements for the logged-in student"""
    if not request.user.is_authenticated:
        return redirect('student-login')
    
    from .models import Announcement, Student
    
    # Get student profile to check enrolled courses
    try:
        student = Student.objects.get(user=request.user)
        student_courses = set(student.courses.values_list('name', flat=True))
    except Student.DoesNotExist:
        student_courses = set()
    
    # Get all announcements for this student:
    # 1. Direct messages (receiver=this user)
    # 2. Broadcast messages (receiver=None)
    # 3. Course broadcast messages (subject contains __COURSE:CourseName__)
    announcements = Announcement.objects.filter(
        Q(receiver=request.user) | Q(receiver__isnull=True)
    ).select_related('sender', 'receiver').order_by('-created_at', '-is_pinned')
    
    # Process announcements for display
    received_messages = []
    all_announcements = []
    unread_count = 0
    
    for ann in announcements:
        # Check if this is a course broadcast announcement
        is_course_broadcast = False
        course_name_from_marker = None
        display_subject = ann.subject
        
        if ann.subject.startswith('__COURSE:'):
            marker_end = ann.subject.find('__', 9)
            if marker_end > 0:
                course_name_from_marker = ann.subject[9:marker_end]
                display_subject = ann.subject[marker_end + 2:]
                is_course_broadcast = True
        
        # If it's a course broadcast, check if student is enrolled in that course
        if is_course_broadcast and course_name_from_marker:
            if course_name_from_marker not in student_courses:
                continue  # Skip this announcement - student not enrolled
        
        # Check if announcement is read by this user
        is_read = ann.read_by.filter(id=request.user.id).exists()
        if not is_read:
            unread_count += 1
        
        # Get sender name
        sender_name = ann.sender.get_full_name() or ann.sender.username
        
        announcement_data = {
            'id': ann.id,
            'subject': display_subject,
            'message': ann.message,
            'sender': sender_name,
            'created_at': ann.created_at.strftime('%Y-%m-%d %H:%M'),
            'is_read': is_read,
            'is_pinned': ann.is_pinned,
        }
        
        received_messages.append(announcement_data)
        all_announcements.append(announcement_data)
    
    # Sort: pinned messages first, then by created_at
    received_messages.sort(key=lambda x: (not x['is_pinned'], x['created_at']), reverse=True)
    
    return render(request, "student/student_announcement.html", {
        'received_messages': received_messages,
        'all_announcements': all_announcements,
        'unread_count': unread_count,
    })

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
    
    # Prepare instructor_info for header
    profile = getattr(instructor_user, 'profile', None)
    instructor_info = {
        'username': instructor_user.username,
        'name': f"{instructor_user.first_name} {instructor_user.last_name}".strip() or instructor_user.username,
        'faculty': profile.faculty.name if profile and profile.faculty else '-',
        'department': profile.department if profile else '-',
    }
    
    return render(request, "instructor/program_outcomes.html", {
        'outcomes_data': outcomes_data,
        'department': instructor_department,
        'instructor_info': instructor_info,
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
        
        if not student.courses.filter(id=course.id).exists():
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
        
        if not student.courses.filter(id=course.id).exists():
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
        
        course_name_slug = generate_course_slug(outcome.course_name)
        
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
        
        if not student.courses.filter(id=course.id).exists():
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
        
        course_name_slug = generate_course_slug(outcome.course_name)
        
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


def toggle_announcement_pin(request, announcement_id):
    """
    Toggle pin status of an announcement.
    NOTE: CSRF protection is enabled. Frontend must send CSRF token.
    """
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
        
        # Get courses from profile or instructor_courses
        courses_list = []
        if profile:
            courses_list = [course.name for course in profile.courses.all()]
        # Also check instructor_courses (reverse ForeignKey from Course.instructor)
        instructor_courses = [course.name for course in advisor.instructor_courses.all()]
        courses_list = list(set(courses_list + instructor_courses))  # Remove duplicates
        
        advisor_data = {
            'username': advisor.username,
            'name': f"{advisor.first_name} {advisor.last_name}".strip() or advisor.username,
            'role': profile.role if profile else '-',
            'department': profile.department if profile else '-',
            'faculty': profile.faculty.name if profile and profile.faculty else '-',
            'courses': courses_list,
        }
        
        return render(request, 'student/advisor_profile.html', {
            'advisor': advisor_data
        })
    except User.DoesNotExist:
        return redirect('student')


@faculty_head_required
def faculty_head_department_graph(request):
    """Show department graph for faculty head"""
    from .models import Course, Student, Faculty, LearningOutcomeProgramOutcome
    
    faculty_head_data = get_faculty_head_data(request.user.username)
    faculty_head_department = faculty_head_data.get('department')
    
    if not faculty_head_department:
        return render(request, 'faculty/department_graph.html', {
            'error': 'No department assigned'
        })
    
    # Get faculty head's profile and faculty
    profile = getattr(request.user, 'profile', None)
    faculty = profile.faculty if profile else None
    
    # Get courses in the department
    courses = Course.objects.filter(department=faculty_head_department)
    course_names = [course.name for course in courses]
    
    # Get learning outcomes for all courses in the department
    learning_outcomes_list = []
    if course_names:
        learning_outcomes_qs = ProgramOutcome.objects.filter(
            course_name__in=course_names
        ).select_related('created_by').prefetch_related('related_program_outcomes').order_by('course_name', 'created_at')
        
        for lo in learning_outcomes_qs:
            # Get linked program outcomes with percentages
            linked_pos = []
            related_pos = lo.related_program_outcomes.all()
            for po in related_pos:
                try:
                    lo_po = LearningOutcomeProgramOutcome.objects.get(
                        learning_outcome=lo,
                        program_outcome=po
                    )
                    percentage = lo_po.percentage
                except LearningOutcomeProgramOutcome.DoesNotExist:
                    percentage = 0
                
                linked_pos.append({
                    'id': po.id,
                    'text': po.text,
                    'percentage': percentage
                })
            
            learning_outcomes_list.append({
                'id': lo.id,
                'text': lo.text,
                'course': lo.course_name,
                'linked_pos': linked_pos
            })
    
    # Get program outcomes for the faculty
    program_outcomes_list = []
    if faculty:
        program_outcomes_qs = ProgramOutcome.objects.filter(
            faculty=faculty,
            course_name=''
        ).select_related('created_by').order_by('created_at')
        
        for po in program_outcomes_qs:
            program_outcomes_list.append({
                'id': po.id,
                'text': po.text
            })
    
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
        'learning_outcomes': learning_outcomes_list,
        'program_outcomes': program_outcomes_list,
    })