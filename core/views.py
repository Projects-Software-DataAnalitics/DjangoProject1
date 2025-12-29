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
from .models import Grade, Student, Course, ProgramOutcome, Assessment, UserProfile, Notification, Assignment, Announcement

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
    
    cache.set(cache_key, instructors_map, 3600)
    return instructors_map


def get_course_schedule_from_json():
    """
    Get course schedule information from JSON files.
    Returns a dict mapping course_name -> {'day': ..., 'time': ..., 'room': ...}
    """
    import json
    import os
    from django.conf import settings
    
    course_schedule = {}
    
    # Course schedule mapping - based on typical academic schedule
    # This can be extended to read from a separate schedule.json file if needed
    default_schedule = {
        "Algorithms": {"day": "Monday", "time": "09:00-10:30", "room": "A101"},
        "Computer Architecture": {"day": "Tuesday", "time": "11:00-12:30", "room": "A102"},
        "Operating Systems": {"day": "Wednesday", "time": "14:00-15:30", "room": "A103"},
        "Linear Algebra": {"day": "Thursday", "time": "09:00-10:30", "room": "A104"},
        "Embedded Systems": {"day": "Friday", "time": "11:00-12:30", "room": "LAB101"},
        "Electronics": {"day": "Monday", "time": "14:00-15:30", "room": "LAB102"},
        "Data Systems": {"day": "Monday", "time": "14:00-15:30", "room": "A103"},
        "Software": {"day": "Tuesday", "time": "16:00-17:30", "room": "A103"},
    }
    
    # Try to read from a schedule.json file if it exists
    schedule_path = os.path.join(settings.BASE_DIR, 'static', 'json', 'schedule.json')
    if os.path.exists(schedule_path):
        try:
            with open(schedule_path, 'r', encoding='utf-8') as f:
                schedule_data = json.load(f)
                course_schedule.update(schedule_data)
        except Exception:
            pass
    
    # Merge with default schedule (default takes precedence if schedule.json exists)
    course_schedule.update(default_schedule)
    
    return course_schedule

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
        
        # Try to get courses from JSON file first (source of truth)
        courses_from_json = []
        try:
            import json
            import os
            from django.conf import settings
            json_path = os.path.join(settings.BASE_DIR, 'static', 'json', 'faculty_heads.json')
            if os.path.exists(json_path):
                with open(json_path, 'r', encoding='utf-8') as f:
                    faculty_heads_data = json.load(f)
                    for fh_data in faculty_heads_data:
                        if fh_data.get('username') == username:
                            courses_from_json = fh_data.get('courses', [])
                            break
        except Exception:
            pass
        
        # If JSON courses exist, use them; otherwise use profile courses
        if courses_from_json:
            courses = courses_from_json
        else:
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


def clean_announcement_subject(subject):
    if subject and subject.startswith('__COURSE:'):
        end_marker = subject.find('__', 9)  
        if end_marker != -1:
            return subject[end_marker + 2:]
    return subject


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
    from .models import Announcement, Assignment
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
        
        # Format year as 1st, 2nd, 3rd, 4th Year
        if student.year:
            if student.year == 1:
                year_display = "1st Year"
            elif student.year == 2:
                year_display = "2nd Year"
            elif student.year == 3:
                year_display = "3rd Year"
            elif student.year == 4:
                year_display = "4th Year"
            else:
                year_display = f"{student.year}th Year"
        else:
            year_display = "-"
        department_display = student.department or "-"
        
        advisor_name = "-"
        advisor_username = None
        # If department is Computer Engineering, set advisor to Prof. Dr. Ahmet Bulut
        if department_display and department_display.lower().strip() == "computer engineering":
            advisor_name = "Prof. Dr. Ahmet Bulut"
        elif student.advisor:
            advisor_name = f"{student.advisor.first_name} {student.advisor.last_name}".strip() or student.advisor.username
            advisor_username = student.advisor.username
        
        courses = student.courses.all().select_related('instructor')
        # Get course schedule from JSON
        course_schedule_map = get_course_schedule_from_json()
        
        courses_list = []
        for course in courses:
            # Get schedule from JSON first, fallback to database
            schedule_info = course_schedule_map.get(course.name, {})
            courses_list.append({
                'name': course.name,
                'code': course.code,
                'credits': course.credits,
                'day': schedule_info.get('day') or course.day,
                'time': schedule_info.get('time') or course.time,
                'room': schedule_info.get('room') or course.room,
            })
        
        # Calculate GPA (same logic as student_grades view)
        # GPA is only calculated if ALL courses have overall_score determined
        from .models import Assessment, Grade
        grades_qs = Grade.objects.filter(student=student).select_related('course')
        
        total_weighted_score = 0
        total_credits = 0
        all_courses_have_scores = True
        
        for course in courses:
            grade_obj = grades_qs.filter(course=course).first()
            if grade_obj:
                grade_obj.calculate_overall_score()
                grade_obj.save(update_fields=['overall_score', 'letter_grade'])
                overall_score = grade_obj.overall_score
            else:
                overall_score = None
            
            if overall_score is None:
                # If any course doesn't have overall_score, GPA cannot be calculated
                all_courses_have_scores = False
                break
            
            credits = course.credits or 0
            if credits > 0:
                total_weighted_score += overall_score * credits
                total_credits += credits
        
        gpa = None
        # Only calculate GPA if all courses have overall_score and total_credits > 0
        if all_courses_have_scores and total_credits > 0:
            average_score = total_weighted_score / total_credits
            gpa = average_score / 25.0
        
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
        gpa = None
    
    # Get announcements
    latest_announcements = Announcement.objects.filter(
        Q(receiver=request.user) | Q(receiver__isnull=True)
    ).select_related('sender').order_by('-created_at')[:10]
    
    announcements_list = []
    for ann in latest_announcements:
        sender_name = ann.sender.get_full_name() or ann.sender.username
        # Clean subject (remove course marker if present)
        display_subject = ann.subject
        if display_subject.startswith('__COURSE:'):
            marker_end = display_subject.find('__', 9)
            if marker_end > 0:
                display_subject = display_subject[marker_end + 2:]
        
        announcements_list.append({
            'id': ann.id,
            'subject': clean_announcement_subject(ann.subject),
            'sender': sender_name,
            'created_at': ann.created_at.strftime('%Y-%m-%d %H:%M'),
            'is_assignment': False,
        })
    
    # Get assignments from student's courses
    upcoming_assignments = []
    try:
        student = Student.objects.get(user=request.user)
        student_courses = student.courses.all()
        from django.utils import timezone
        from datetime import timedelta
        
        # Get assignments with deadlines, ordered by deadline (soonest first)
        # Show both future and past assignments, but prioritize future ones
        now = timezone.now()
        all_assignments_qs = Assignment.objects.filter(
            course__in=student_courses
        ).select_related('course', 'created_by')
        
        # Convert to list to sort
        all_assignments_list = list(all_assignments_qs)
        
        # Separate future and past assignments
        future_assignments = [a for a in all_assignments_list if a.deadline >= now]
        past_assignments = [a for a in all_assignments_list if a.deadline < now]
        
        # Sort each group by deadline
        future_assignments.sort(key=lambda x: x.deadline)
        past_assignments.sort(key=lambda x: x.deadline, reverse=True)  # Most recent past first
        
        # Show future assignments first, then past ones (limit to 10 total)
        assignments = (future_assignments + past_assignments)[:10]
        
        instructors_map = get_instructors_map()
        faculty_heads_map = get_faculty_heads_map()
        
        for assignment in assignments:
            creator_name = instructors_map.get(assignment.created_by.username) or faculty_heads_map.get(assignment.created_by.username) or assignment.created_by.get_full_name() or assignment.created_by.username
            
            # Check if deadline is approaching (within 7 days)
            time_diff = assignment.deadline - now
            days_until_deadline = time_diff.days
            # If less than 24 hours, count as 0 days
            if time_diff.total_seconds() < 86400 and time_diff.total_seconds() >= 0:
                days_until_deadline = 0
            elif time_diff.total_seconds() < 0:
                # Past deadline
                days_until_deadline = -1
            is_urgent = days_until_deadline <= 3 and days_until_deadline >= 0
            
            announcements_list.append({
                'id': f"assignment_{assignment.id}",
                'subject': f"New Assignment: {assignment.title}",
                'sender': creator_name,
                'created_at': assignment.created_at.strftime('%Y-%m-%d %H:%M'),
                'is_assignment': True,
            })
            
            upcoming_assignments.append({
                'id': assignment.id,
                'title': assignment.title,
                'course_name': assignment.course.name,
                'deadline': assignment.deadline.strftime('%d/%m/%Y %H:%M'),
                'deadline_datetime': assignment.deadline.isoformat(),
                'days_until': days_until_deadline,
                'is_urgent': is_urgent,
            })
    except Student.DoesNotExist:
        pass
    
    # Sort by created_at and take top 5
    announcements_list.sort(key=lambda x: x['created_at'], reverse=True)
    announcements_list = announcements_list[:5]
    
    # Prepare schedule data for template
    days = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday']
    time_slots = ['09:00-10:30', '11:00-12:30', '14:00-15:30', '16:00-17:30']
    
    return render(request, 'student.html', {
        'student_info': student_info,
        'latest_announcements': announcements_list,
        'academic_term': academic_term,
        'year_display': year_display,
        'department_display': department_display,
        'advisor_name': advisor_name,
        'advisor_username': advisor_username,
        'courses_list': courses_list,
        'gpa': gpa,
        'days': days,
        'time_slots': time_slots,
        'upcoming_assignments': upcoming_assignments,
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
                from django.http import JsonResponse
                # Check if request expects JSON (AJAX request)
                is_ajax = request.headers.get('Accept', '').find('application/json') != -1 or request.path.startswith('/instructor/learning-outcomes/')
                if is_ajax:
                    return JsonResponse({
                        'success': False,
                        'error': 'You are not allowed here'
                    }, status=403)
                from django.http import HttpResponseForbidden
                return HttpResponseForbidden("You are not allowed here")
        except AttributeError:
            from django.http import JsonResponse
            # Check if request expects JSON (AJAX request)
            is_ajax = request.headers.get('Accept', '').find('application/json') != -1 or request.path.startswith('/instructor/learning-outcomes/')
            if is_ajax:
                return JsonResponse({
                    'success': False,
                    'error': 'User profile not found'
                }, status=403)
            from django.http import HttpResponseForbidden
            return HttpResponseForbidden("User profile not found")
        
        request.instructor_user = request.user
        return view_func(request, *args, **kwargs)
    return wrapper


@instructor_required
def instructor_dashboard(request):
    from datetime import datetime
    from .models import Announcement, Assignment
    from django.db.models import Q
    from django.utils import timezone
    
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
    
    # Get assignments from instructor's courses
    upcoming_assignments = []
    
    if profile:
        courses = profile.courses.all().select_related('instructor').prefetch_related('students')
        # Get course schedule from JSON
        course_schedule_map = get_course_schedule_from_json()
        
        for course in courses:
            students = course.students.all()
            student_count = students.count()
            
            for student in students:
                total_students_set.add(student.id)
            
            # Get schedule from JSON first, fallback to database
            schedule_info = course_schedule_map.get(course.name, {})
            courses_list.append({
                'id': course.id,
                'name': course.name,
                'code': course.code,
                'credits': course.credits,
                'student_count': student_count,
                'day': schedule_info.get('day') or course.day,
                'time': schedule_info.get('time') or course.time,
                'room': schedule_info.get('room') or course.room,
            })
            
            chart_data['labels'].append(course.name)
            chart_data['data'].append(student_count)
        
        # Get assignments with deadlines, ordered by deadline (soonest first)
        # Show both future and past assignments, but prioritize future ones
        now = timezone.now()
        all_assignments_qs = Assignment.objects.filter(
            course__in=courses
        ).select_related('course', 'created_by')
        
        # Convert to list to sort
        all_assignments_list = list(all_assignments_qs)
        
        # Separate future and past assignments
        future_assignments = [a for a in all_assignments_list if a.deadline >= now]
        past_assignments = [a for a in all_assignments_list if a.deadline < now]
        
        # Sort each group by deadline
        future_assignments.sort(key=lambda x: x.deadline)
        past_assignments.sort(key=lambda x: x.deadline, reverse=True)  # Most recent past first
        
        # Show future assignments first, then past ones (limit to 10 total)
        assignments = (future_assignments + past_assignments)[:10]
        
        instructors_map = get_instructors_map()
        faculty_heads_map = get_faculty_heads_map()
        
        for assignment in assignments:
            creator_name = instructors_map.get(assignment.created_by.username) or faculty_heads_map.get(assignment.created_by.username) or assignment.created_by.get_full_name() or assignment.created_by.username
            
            # Check if deadline is approaching (within 7 days)
            time_diff = assignment.deadline - now
            days_until_deadline = time_diff.days
            # If less than 24 hours, count as 0 days
            if time_diff.total_seconds() < 86400 and time_diff.total_seconds() >= 0:
                days_until_deadline = 0
            elif time_diff.total_seconds() < 0:
                # Past deadline
                days_until_deadline = -1
            is_urgent = days_until_deadline <= 3 and days_until_deadline >= 0
            
            upcoming_assignments.append({
                'id': assignment.id,
                'title': assignment.title,
                'course_name': assignment.course.name,
                'deadline': assignment.deadline.strftime('%d/%m/%Y %H:%M'),
                'deadline_datetime': assignment.deadline.isoformat(),
                'days_until': days_until_deadline,
                'is_urgent': is_urgent,
            })
    
    total_courses = len(courses_list)
    total_students = len(total_students_set)
    
    latest_announcements = Announcement.objects.filter(
        Q(receiver=instructor_user) | Q(receiver__isnull=True)
    ).exclude(sender=instructor_user).select_related('sender', 'receiver').order_by('-created_at')[:5]
    
    announcements_list = []
    for ann in latest_announcements:
        sender_name = ann.sender.get_full_name() or ann.sender.username
        announcements_list.append({
            'id': ann.id,
            'subject': clean_announcement_subject(ann.subject),
            'sender': sender_name,
            'created_at': ann.created_at.strftime('%Y-%m-%d %H:%M'),
        })
    
    chart_data_json = json.dumps(chart_data)
    
    # Prepare schedule data for template
    days = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday']
    time_slots = ['09:00-10:30', '11:00-12:30', '14:00-15:30', '16:00-17:30']
    
    return render(request, 'instructor_main.html', {
        'instructor_info': instructor_info,
        'academic_term': academic_term,
        'courses_list': courses_list,
        'total_courses': total_courses,
        'total_students': total_students,
        'chart_data': chart_data,
        'chart_data_json': chart_data_json,
        'latest_announcements': announcements_list,
        'upcoming_assignments': upcoming_assignments,
        'days': days,
        'time_slots': time_slots,
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
    # Get course schedule from JSON
    course_schedule_map = get_course_schedule_from_json()
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
            
            # Get schedule from JSON first, fallback to database
            schedule_info = course_schedule_map.get(course.name, {})
            
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
                'day': schedule_info.get('day') or course.day,
                'time': schedule_info.get('time') or course.time,
                'room': schedule_info.get('room') or course.room,
            })
    
    # Prepare JSON data for template
    courses_json = json.dumps([{
        'id': course['id'],
        'name': course['name'],
        'students': course['students']
    } for course in courses_data])
    
    # Prepare schedule data for template
    days = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday']
    time_slots = ['09:00-10:30', '11:00-12:30', '14:00-15:30', '16:00-17:30']
    
    return render(request, 'instructor.html', {
        'show_welcome': False,
        'page': 'my_courses',
        'courses': courses_data,
        'courses_json': courses_json,
        'all_assignments': all_assignments,
        'days': days,
        'time_slots': time_slots
    })

@instructor_required
def instructor_assignments(request):
    from .models import Assignment, AssignmentSubmission
    from django.utils import timezone
    
    instructor_user = request.instructor_user
    profile = getattr(instructor_user, 'profile', None)
    
    all_assignments = []
    courses_list = []
    
    if profile:
        courses = profile.courses.all().select_related('instructor').prefetch_related('assignments')
        courses_list = [{'id': course.id, 'name': course.name} for course in courses]
        
        for course in courses:
            # Get assignments for this course
            assignments = course.assignments.all().order_by('-created_at')
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
                    'course_code': course.code,
                    'title': assignment.title,
                    'details': assignment.details,
                    'deadline': assignment.deadline.strftime('%d/%m/%Y %H:%M'),
                    'deadline_datetime': assignment.deadline.isoformat(),
                    'deadline_date': assignment.deadline.strftime('%Y-%m-%d'),
                    'deadline_time': assignment.deadline.strftime('%H:%M'),
                    'file_url': assignment.file.url if assignment.file else None,
                    'file_name': assignment.file.name.split('/')[-1] if assignment.file else None,
                    'created_by_id': assignment.created_by.id,
                    'created_at': assignment.created_at.strftime('%d/%m/%Y %H:%M'),
                    'submissions': json.dumps(submissions_list),
                    'submissions_count': len(submissions_list),
                }
                all_assignments.append(assignment_data)
    
    # Sort by created_at (most recent first)
    all_assignments.sort(key=lambda x: x['created_at'], reverse=True)
    
    return render(request, 'instructor/assignments.html', {
        'assignments': all_assignments,
        'courses': courses_list
    })

@instructor_required
def add_assignment(request):
    from .models import Assignment, Notification
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
            
            # Create notifications for all students enrolled in the course
            students = course.students.all()
            for student in students:
                if student.user:
                    Notification.objects.create(
                        user=student.user,
                        notification_type='assignment_created',
                        title=f'New Assignment: {assignment.title}',
                        message=f'A new assignment "{assignment.title}" has been added to {course.name}.',
                        assignment=assignment
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
    from .models import Assignment, Notification
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
            
            # Create notifications for all students enrolled in the course
            students = course.students.all()
            for student in students:
                if student.user:
                    Notification.objects.create(
                        user=student.user,
                        notification_type='assignment_created',
                        title=f'New Assignment: {assignment.title}',
                        message=f'A new assignment "{assignment.title}" has been added to {course.name}.',
                        assignment=assignment
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
    
    # Get courses from both sources (profile.courses and Course.instructor)
    courses_from_profile = []
    courses_from_instructor = []
    
    if profile:
        courses_from_profile = profile.courses.all().select_related('instructor').prefetch_related('students')
    
    # Also get courses where this user is the instructor (primary source of truth)
    courses_from_instructor = instructor_user.instructor_courses.all().select_related('instructor').prefetch_related('students')
    
    # Combine courses and deduplicate by name, keeping Course objects
    all_courses_dict = {}
    for course in list(courses_from_profile) + list(courses_from_instructor):
        if course.name not in all_courses_dict:
            all_courses_dict[course.name] = course
    
    # Convert to list of dictionaries with course info
    courses_list = []
    for course in all_courses_dict.values():
        student_count = course.students.count()
        courses_list.append({
            'name': course.name,
            'credits': course.credits if course.credits is not None else '-',
            'student_count': student_count
        })
    
    return render(request, 'instructor/instructor_grades_page.html', {
        'instructor_courses': courses_list,
        'page': 'grades'  # Add page context
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
    
    # Check access: instructor must have course in profile OR be the course instructor
    has_access = False
    if profile and profile.courses.filter(id=course.id).exists():
        has_access = True
    elif course.instructor == instructor_user:
        has_access = True
    
    if not has_access:
        return HttpResponseForbidden("You don't have access to this course")
    
    # Assessment'ı al veya oluştur (default değerlerle)
    # Her zaman database'den güncel değerleri almak için get_or_create sonrası refresh_from_db kullanıyoruz
    try:
        assessment = Assessment.objects.get(course=course)
        # Mevcut assessment'ı database'den yeniden oku (güncel değerler için)
        assessment.refresh_from_db()
    except Assessment.DoesNotExist:
        # Assessment yoksa, default değerlerle oluştur
        assessment = Assessment.objects.create(
            course=course,
            midterm=2,
            final=1,
            project=0,
            assignment=0,
            absence=0,
            quiz=0,
            assessment_count=3,
            midterm_percentage=60,
            final_percentage=40,
            project_percentage=0,
            assignment_percentage=0,
            absence_percentage=0,
            quiz_percentage=0
        )
    
    # Get students enrolled in this course
    students = course.students.all().order_by('first_name', 'last_name', 'username')
    students_list = [{'id': student.id, 'student_id': student.student_id, 'name': f"{student.first_name} {student.last_name}".strip() or student.username} for student in students]
    
    # Get uploaded file info for each assessment (from first student as sample)
    uploaded_files_info = {}
    sample_grade = Grade.objects.filter(course=course).first()
    if sample_grade and sample_grade.assessment_scores:
        assessment_types = ['midterm', 'final', 'project', 'assignment', 'absence', 'quiz']
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
        'project': 'Project',
        'assignment': 'Assignment',
        'absence': 'Absence',
        'quiz': 'Quiz'
    }
    
    for assessment_type in ['midterm', 'final', 'project', 'assignment', 'absence', 'quiz']:
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
        # Refresh from database to ensure we have the latest saved data
        if grade_obj:
            grade_obj.refresh_from_db()
        student_data = {
            'student_id': student.student_id,
            'full_name': f"{student.first_name} {student.last_name}".strip() or student.username,
            'grades': {}
        }
        
        if grade_obj:
            # Ensure assessment_scores is loaded from database
            # For JSONField, we need to explicitly access it to trigger database read
            _ = grade_obj.assessment_scores
            
            # Get individual scores for each assessment column
            for col in assessment_columns:
                score = grade_obj.get_individual_score(col['key'])
                if score is not None:
                    student_data['grades'][col['key']] = float(score)
                else:
                    # If individual score doesn't exist, check if average is available
                    # But for table display, we show individual scores only
                    student_data['grades'][col['key']] = None
            
            # Add overall_score and letter_grade to student data
            # Recalculate to ensure it's up to date based on current assessment_scores
            grade_obj.calculate_overall_score()
            # Save only if overall_score or letter_grade changed (don't overwrite assessment_scores)
            grade_obj.save(update_fields=['overall_score', 'letter_grade', 'last_changes_at'])
            student_data['overall_score'] = grade_obj.overall_score
            student_data['letter_grade'] = grade_obj.letter_grade
        else:
            student_data['overall_score'] = None
            student_data['letter_grade'] = None
        
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

@csrf_exempt
def upload_assessment_grades(request, course_name, assessment_type, assessment_index):
    """
    Upload grades for a specific assessment file (e.g., midterm_1, midterm_2)
    CSV format: student_id, score (single column for scores)
    Only calculates average when ALL files for that assessment type are uploaded
    Works for both instructor and faculty_head
    """
    if request.method != 'POST':
        return JsonResponse({'error': 'Only POST allowed'}, status=405)
    
    # Check if user is authenticated
    if not request.user.is_authenticated:
        return JsonResponse({'error': 'Authentication required'}, status=401)
    
    # Check if user is instructor or faculty_head
    profile = getattr(request.user, 'profile', None)
    if not profile:
        return JsonResponse({'error': 'User profile not found'}, status=403)
    
    if profile.role not in ['instructor', 'faculty_head']:
        return JsonResponse({'error': 'Access denied'}, status=403)
    
    # Valid assessment types
    valid_types = ['midterm', 'final', 'project', 'assignment', 'absence', 'quiz']
    if assessment_type not in valid_types:
        return JsonResponse({'error': f'Invalid assessment type. Must be one of: {", ".join(valid_types)}'}, status=400)
    
    try:
        assessment_index = int(assessment_index)
        if assessment_index < 1:
            return JsonResponse({'error': 'Assessment index must be >= 1'}, status=400)
    except ValueError:
        return JsonResponse({'error': 'Invalid assessment index'}, status=400)
    
    try:
        course = Course.objects.get(name=course_name)
    except Course.DoesNotExist:
        return JsonResponse({'error': 'Course not found'}, status=404)
    
    # Check access: instructor must have course in profile OR be the course instructor, faculty_head must have course in profile or department match
    if profile.role == 'instructor':
        has_access = False
        if course in profile.courses.all():
            has_access = True
        elif course.instructor == request.user:
            has_access = True
        if not has_access:
            return JsonResponse({'error': 'Access denied'}, status=403)
    elif profile.role == 'faculty_head':
        # Faculty head can access if course is in their profile or department matches
        faculty_head_data = get_faculty_head_data(request.user.username)
        faculty_head_department = faculty_head_data.get('department')
        if course not in profile.courses.all():
            if faculty_head_department and course.department != faculty_head_department:
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
    
    # Read CSV file into memory once to avoid I/O operation on closed file errors
    try:
        csv_file.file.seek(0)  # Reset file pointer
        text_file = io.TextIOWrapper(csv_file.file, encoding='utf-8')
        csv_content = text_file.read()
        text_file.close()  # Close the wrapper explicitly
    except Exception as e:
        return JsonResponse({'error': f'Invalid CSV file: {str(e)}'}, status=400)
    
    def normalize(name):
        if not name:
            return ''
        # Remove dots, underscores, hyphens, spaces and normalize
        # Keep the original for matching but normalize for comparison
        normalized = name.strip().lower().lstrip('\ufeff').replace('.', '').replace('_', '').replace('-', '').replace(' ', '')
        return normalized
    
    # Parse CSV content from memory (using StringIO instead of file)
    # Try different delimiters (comma, semicolon, tab)
    csv_string_io = io.StringIO(csv_content)
    detected_delimiter = ','
    
    # Try comma first (most common)
    reader = csv.DictReader(csv_string_io, delimiter=',')
    
    # If no fieldnames found or only one column, try semicolon
    if not reader.fieldnames or (reader.fieldnames and len(reader.fieldnames) == 1):
        csv_string_io.seek(0)
        reader = csv.DictReader(csv_string_io, delimiter=';')
        if reader.fieldnames and len(reader.fieldnames) > 1:
            detected_delimiter = ';'
    
    # If still no fieldnames or only one column, try tab
    if not reader.fieldnames or (reader.fieldnames and len(reader.fieldnames) == 1):
        csv_string_io.seek(0)
        reader = csv.DictReader(csv_string_io, delimiter='\t')
        if reader.fieldnames and len(reader.fieldnames) > 1:
            detected_delimiter = '\t'
    
    # Expected columns: student_id, score
    if not reader.fieldnames:
        return JsonResponse({'error': 'CSV file appears to be empty or invalid. Please ensure the file has headers and data rows.'}, status=400)
    
    if len(reader.fieldnames) == 1:
        return JsonResponse({
            'error': f'CSV appears to have only one column. Found: {reader.fieldnames[0]}. Please check the delimiter (should be comma).',
            'details': [f'Try saving the CSV file with comma (,) as delimiter']
        }, status=400)
    
    normalized_fields = {normalize(col): col for col in reader.fieldnames}
    
    # Check for student_id (can be 'student_id', 'student.student_id', etc.)
    student_id_column = None
    possible_student_id_names = ['studentid', 'student_id', 'student.student_id', 'student_student_id']
    for name in possible_student_id_names:
        normalized_name = normalize(name)
        if normalized_name in normalized_fields:
            student_id_column = normalized_fields[normalized_name]
            break
    
    if not student_id_column:
        available_cols = ', '.join(reader.fieldnames)
        return JsonResponse({
            'error': f'CSV must include "student_id" column. Available columns: {available_cols}',
            'details': [f'Found columns: {available_cols}']
        }, status=400)
    
    # Check for score column (can be named 'score', 'scores', or assessment_type_index)
    score_column = None
    possible_score_names = ['score', 'scores', f'{assessment_type}{assessment_index}', f'{assessment_type}_{assessment_index}']
    for name in possible_score_names:
        normalized_name = normalize(name)
        if normalized_name in normalized_fields:
            score_column = normalized_fields[normalized_name]
            break
    
    if not score_column:
        available_cols = ', '.join(reader.fieldnames)
        return JsonResponse({
            'error': f'CSV must include a score column (named: score, scores, {assessment_type}_{assessment_index}, or {assessment_type}{assessment_index}). Available columns: {available_cols}',
            'details': [f'Found columns: {available_cols}']
        }, status=400)
    
    student_id_source = student_id_column
    assessment_key = f'{assessment_type}_{assessment_index}'
    
    # First pass: Validate all scores (0-100 range) before processing
    validation_errors = []
    csv_string_io.seek(0)  # Reset StringIO pointer
    validation_reader = csv.DictReader(csv_string_io, delimiter=detected_delimiter)
    normalized_fields_validation = {normalize(col): col for col in (validation_reader.fieldnames or [])}
    
    # Find score column for validation
    score_column_validation = None
    for name in possible_score_names:
        normalized_name = normalize(name)
        if normalized_name in normalized_fields_validation:
            score_column_validation = normalized_fields_validation[normalized_name]
            break
    
    has_below_zero = False
    has_over_hundred = False
    
    for row_num, row in enumerate(validation_reader, start=2):
        score_value = (row.get(score_column_validation, '') or '').strip()
        if score_value != '':  # Only validate non-empty values (empty is allowed)
            try:
                score = float(score_value)
                if score < 0:
                    validation_errors.append(f'Row {row_num}: Grade cannot be below 0 (value: {score_value})')
                    has_below_zero = True
                elif score > 100:
                    validation_errors.append(f'Row {row_num}: Grade cannot be over 100 (value: {score_value})')
                    has_over_hundred = True
            except ValueError:
                validation_errors.append(f'Row {row_num}: Invalid number format (value: {score_value})')
    
    # If there are validation errors, return early without processing
    if validation_errors:
        # Determine error message based on error types
        if has_below_zero and has_over_hundred:
            error_message = "Grades can't be below 0 and over 100. Please check your grades."
        elif has_below_zero:
            error_message = "Grades can't be below 0. Please check your grades."
        elif has_over_hundred:
            error_message = "Grades can't be over 100. Please check your grades."
        else:
            # Only format errors (shouldn't happen, but just in case)
            error_message = "Invalid grade format. Please check your grades."
        
        return JsonResponse({
            'error': error_message
        }, status=400)
    
    # Second pass: Process valid scores
    csv_string_io.seek(0)  # Reset StringIO pointer again
    reader = csv.DictReader(csv_string_io, delimiter=detected_delimiter)
    normalized_fields = {normalize(col): col for col in (reader.fieldnames or [])}
    
    # Find student_id column again
    student_id_source = None
    for name in possible_student_id_names:
        normalized_name = normalize(name)
        if normalized_name in normalized_fields:
            student_id_source = normalized_fields[normalized_name]
            break
    
    # Find score column again
    score_column = None
    for name in possible_score_names:
        normalized_name = normalize(name)
        if normalized_name in normalized_fields:
            score_column = normalized_fields[normalized_name]
            break
    
    # Define parse_score function before validation (instructor grades style)
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
    
    # Validate all rows and prepare data (instructor grades style)
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
        
        # Write to database in atomic transaction (instructor grades style)
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
                
                # Save assessment_scores changes first
                grade.save(update_fields=['assessment_scores'])
                
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
                
                # Calculate overall score and letter grade
                grade.calculate_overall_score()
                
                # Update last_changes_at
                grade.last_changes_at = timezone.now()
                
                # Save all changes (assessment_scores already saved, but save again to include all fields)
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

@csrf_exempt
def upload_all_assessments(request, course_name):
    """
    Upload all assessments for a course in a single CSV file
    CSV format: student_id, midterm_1, midterm_2, ..., final_1, final_2, ..., project_1, ..., assignment_1, ..., absence_1, ..., quiz_1, ...
    Works for both instructor and faculty_head
    """
    if request.method != 'POST':
        return JsonResponse({'error': 'Only POST allowed'}, status=405)
    
    # Check if user is authenticated
    if not request.user.is_authenticated:
        return JsonResponse({'error': 'Authentication required'}, status=401)
    
    # Check if user is instructor or faculty_head
    profile = getattr(request.user, 'profile', None)
    if not profile:
        return JsonResponse({'error': 'User profile not found'}, status=403)
    
    if profile.role not in ['instructor', 'faculty_head']:
        return JsonResponse({'error': 'Access denied'}, status=403)
    
    try:
        course = Course.objects.get(name=course_name)
    except Course.DoesNotExist:
        return JsonResponse({'error': 'Course not found'}, status=404)
    
    # Check access: instructor must have course in profile OR be the course instructor, faculty_head must have course in profile or department match
    if profile.role == 'instructor':
        has_access = False
        if course in profile.courses.all():
            has_access = True
        elif course.instructor == request.user:
            has_access = True
        if not has_access:
            return JsonResponse({'error': 'Access denied'}, status=403)
    elif profile.role == 'faculty_head':
        # Faculty head can access if course is in their profile or department matches
        faculty_head_data = get_faculty_head_data(request.user.username)
        faculty_head_department = faculty_head_data.get('department')
        if course not in profile.courses.all():
            if faculty_head_department and course.department != faculty_head_department:
                return JsonResponse({'error': 'Access denied'}, status=403)
    
    # Get assessment for this course
    try:
        assessment = Assessment.objects.get(course=course)
    except Assessment.DoesNotExist:
        return JsonResponse({'error': 'Assessment not found for this course. Please configure assessment first.'}, status=404)
    
    csv_file = request.FILES.get('csv_file')
    if not csv_file:
        return JsonResponse({'error': 'CSV file required'}, status=400)
    
    # Read CSV file into memory
    try:
        csv_file.file.seek(0)
        text_file = io.TextIOWrapper(csv_file.file, encoding='utf-8')
        csv_content = text_file.read()
        text_file.close()
    except Exception as e:
        return JsonResponse({'error': f'Invalid CSV file: {str(e)}'}, status=400)
    
    def normalize(name):
        if not name:
            return ''
        normalized = name.strip().lower().lstrip('\ufeff').replace('.', '').replace('_', '').replace('-', '').replace(' ', '')
        return normalized
    
    # Parse CSV content
    csv_string_io = io.StringIO(csv_content)
    detected_delimiter = ','
    
    # Try comma first
    reader = csv.DictReader(csv_string_io, delimiter=',')
    
    # If no fieldnames found or only one column, try semicolon
    if not reader.fieldnames or (reader.fieldnames and len(reader.fieldnames) == 1):
        csv_string_io.seek(0)
        reader = csv.DictReader(csv_string_io, delimiter=';')
        if reader.fieldnames and len(reader.fieldnames) > 1:
            detected_delimiter = ';'
    
    # If still no fieldnames or only one column, try tab
    if not reader.fieldnames or (reader.fieldnames and len(reader.fieldnames) == 1):
        csv_string_io.seek(0)
        reader = csv.DictReader(csv_string_io, delimiter='\t')
        if reader.fieldnames and len(reader.fieldnames) > 1:
            detected_delimiter = '\t'
    
    if not reader.fieldnames:
        return JsonResponse({'error': 'CSV file appears to be empty or invalid. Please ensure the file has headers and data rows.'}, status=400)
    
    if len(reader.fieldnames) == 1:
        return JsonResponse({
            'error': f'CSV appears to have only one column. Found: {reader.fieldnames[0]}. Please check the delimiter (should be comma).',
            'details': [f'Try saving the CSV file with comma (,) as delimiter']
        }, status=400)
    
    normalized_fields = {normalize(col): col for col in reader.fieldnames}
    
    # Check for student_id
    student_id_column = None
    possible_student_id_names = ['studentid', 'student_id', 'student.student_id', 'student_student_id']
    for name in possible_student_id_names:
        normalized_name = normalize(name)
        if normalized_name in normalized_fields:
            student_id_column = normalized_fields[normalized_name]
            break
    
    if not student_id_column:
        available_cols = ', '.join(reader.fieldnames)
        return JsonResponse({
            'error': f'CSV must include "student_id" column. Available columns: {available_cols}',
            'details': [f'Found columns: {available_cols}']
        }, status=400)
    
    # Build expected columns based on assessment counts
    assessment_types = ['midterm', 'final', 'project', 'assignment', 'absence', 'quiz']
    expected_columns = {}
    for assessment_type in assessment_types:
        count = getattr(assessment, assessment_type, 0)
        if count > 0:
            for i in range(1, count + 1):
                key = f'{assessment_type}_{i}'
                expected_columns[key] = {
                    'type': assessment_type,
                    'index': i,
                    'key': key
                }
    
    # Check which columns are present in CSV
    found_columns = {}
    missing_columns = []
    
    for key, info in expected_columns.items():
        # Try to find column with various naming formats
        found = False
        possible_names = [
            key,  # midterm_1
            key.replace('_', ''),  # midterm1
            key.replace('_', '-'),  # midterm-1
            key.replace('_', ' '),  # midterm 1
            key.upper(),  # MIDTERM_1
            key.lower(),  # midterm_1
        ]
        
        for name in possible_names:
            normalized_name = normalize(name)
            if normalized_name in normalized_fields:
                found_columns[key] = {
                    'column_name': normalized_fields[normalized_name],
                    'type': info['type'],
                    'index': info['index'],
                    'key': key
                }
                found = True
                break
        
        if not found:
            missing_columns.append(key)
    
    # If no assessment columns found, return error
    if not found_columns:
        return JsonResponse({
            'error': 'No assessment columns found in CSV. Expected columns: ' + ', '.join(expected_columns.keys()),
            'details': [f'Found columns: {", ".join(reader.fieldnames)}']
        }, status=400)
    
    # Parse score function
    def parse_score(raw_value, label):
        value = (raw_value or '').strip()
        if value == '':
            return None
        try:
            score = float(value)
            if score < 0:
                raise ValueError(f'{label} cannot be below 0')
            if score > 100:
                raise ValueError(f'{label} cannot be over 100')
            return score
        except ValueError as e:
            if 'cannot be' in str(e):
                raise e
            raise ValueError(f'{label} must be a valid number')
    
    # Validate all rows
    validated_rows = []
    validation_errors = []
    
    csv_string_io.seek(0)
    reader = csv.DictReader(csv_string_io, delimiter=detected_delimiter)
    normalized_fields = {normalize(col): col for col in (reader.fieldnames or [])}
    
    # Find student_id column again
    student_id_source = None
    for name in possible_student_id_names:
        normalized_name = normalize(name)
        if normalized_name in normalized_fields:
            student_id_source = normalized_fields[normalized_name]
            break
    
    try:
        for row_num, row in enumerate(reader, start=2):
            try:
                student_id_str = (row[student_id_source] or '').strip()
                if not student_id_str:
                    validation_errors.append(f'Row {row_num}: student_id is required')
                    continue
                
                # Get student
                try:
                    student = Student.objects.get(student_id=student_id_str)
                except Student.DoesNotExist:
                    validation_errors.append(f'Row {row_num}: Student with student_id {student_id_str} not found')
                    continue
                except Student.MultipleObjectsReturned:
                    validation_errors.append(f'Row {row_num}: Multiple students found with student_id {student_id_str}')
                    continue
                
                # Check if student is enrolled
                if not student.courses.filter(id=course.id).exists():
                    validation_errors.append(f'Row {row_num}: Student {student_id_str} is not enrolled in course {course_name}')
                    continue
                
                # Parse all assessment scores
                row_scores = {}
                for key, info in found_columns.items():
                    column_name = info['column_name']
                    score_value = (row.get(column_name, '') or '').strip()
                    if score_value != '':
                        try:
                            score = parse_score(score_value, key)
                            row_scores[key] = score
                        except ValueError as e:
                            validation_errors.append(f'Row {row_num}, {key}: {str(e)}')
                
                validated_rows.append({
                    'student': student,
                    'scores': row_scores
                })
                    
            except Exception as e:
                validation_errors.append(f'Row {row_num}: {str(e)}')
        
        # If there are validation errors, return before processing
        if validation_errors:
            return JsonResponse({
                'error': 'CSV validation failed',
                'details': validation_errors[:20]
            }, status=400)
        
        # Write to database in atomic transaction
        from django.utils import timezone
        updated_count = 0
        
        with transaction.atomic():
            for row_data in validated_rows:
                student = row_data['student']
                scores = row_data['scores']
                
                # Get or create grade record
                grade, created = Grade.objects.get_or_create(
                    student=student,
                    course=course
                )
                
                # Store all scores
                for key, score in scores.items():
                    grade.set_individual_score(key, score, file_name=csv_file.name)
                
                # Calculate averages for each assessment type
                for assessment_type in assessment_types:
                    count = getattr(assessment, assessment_type, 0)
                    if count > 0:
                        all_scores = []
                        for i in range(1, count + 1):
                            key = f'{assessment_type}_{i}'
                            individual_score = grade.get_individual_score(key)
                            if individual_score is not None:
                                all_scores.append(individual_score)
                        
                        # Set average if all files are present
                        if len(all_scores) == count and count > 0:
                            average_score = sum(all_scores) / len(all_scores)
                            setattr(grade, assessment_type, average_score)
                        else:
                            # If not all files present, don't change existing average
                            # Only set to None if we explicitly uploaded scores and some are missing
                            pass
                
                # Calculate overall score and letter grade
                grade.calculate_overall_score()
                
                # Update last_changes_at
                grade.last_changes_at = timezone.now()
                
                # Save all changes
                grade.save()
                updated_count += 1
        
        response_data = {
            'status': 'ok',
            'updated_count': updated_count,
            'assessments_uploaded': list(found_columns.keys()),
            'file_name': csv_file.name
        }
        
        return JsonResponse(response_data)
            
    except Exception as e:
        return JsonResponse({'error': f'CSV processing error: {str(e)}'}, status=400)

@csrf_exempt
def delete_assessment_file(request, course_name, assessment_type, assessment_index):
    """Delete a specific assessment file (e.g., midterm_1)
    Works for both instructor and faculty_head
    """
    if request.method != 'POST':
        return JsonResponse({'error': 'Only POST allowed'}, status=405)
    
    # Check if user is authenticated
    if not request.user.is_authenticated:
        return JsonResponse({'error': 'Authentication required'}, status=401)
    
    # Check if user is instructor or faculty_head
    profile = getattr(request.user, 'profile', None)
    if not profile:
        return JsonResponse({'error': 'User profile not found'}, status=403)
    
    if profile.role not in ['instructor', 'faculty_head']:
        return JsonResponse({'error': 'Access denied'}, status=403)
    
    valid_types = ['midterm', 'final', 'project', 'assignment', 'absence', 'quiz']
    if assessment_type not in valid_types:
        return JsonResponse({'error': f'Invalid assessment type'}, status=400)
    
    try:
        assessment_index = int(assessment_index)
        if assessment_index < 1:
            return JsonResponse({'error': 'Assessment index must be >= 1'}, status=400)
    except ValueError:
        return JsonResponse({'error': 'Invalid assessment index'}, status=400)
    
    try:
        course = Course.objects.get(name=course_name)
    except Course.DoesNotExist:
        return JsonResponse({'error': 'Course not found'}, status=404)
    
    # Check access: instructor must have course in profile OR be the course instructor, faculty_head must have course in profile or department match
    if profile.role == 'instructor':
        has_access = False
        if course in profile.courses.all():
            has_access = True
        elif course.instructor == request.user:
            has_access = True
        if not has_access:
            return JsonResponse({'error': 'Access denied'}, status=403)
    elif profile.role == 'faculty_head':
        # Faculty head can access if course is in their profile or department matches
        faculty_head_data = get_faculty_head_data(request.user.username)
        faculty_head_department = faculty_head_data.get('department')
        if course not in profile.courses.all():
            if faculty_head_department and course.department != faculty_head_department:
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
                    
                    # Save assessment_scores changes first
                    grade.save(update_fields=['assessment_scores'])
                    
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
                    
                    # Calculate overall score and letter grade
                    grade.calculate_overall_score()
                    
                    # Update last_changes_at
                    from django.utils import timezone
                    grade.last_changes_at = timezone.now()
                    
                    # Save all changes
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

@csrf_exempt
def update_individual_grade(request, course_name):
    """Update individual grade score from table cell edit
    Works for both instructor and faculty_head
    """
    if request.method != 'POST':
        return JsonResponse({'error': 'Only POST allowed'}, status=405)
    
    # Check if user is authenticated
    if not request.user.is_authenticated:
        return JsonResponse({'error': 'Authentication required'}, status=401)
    
    # Check if user is instructor or faculty_head
    profile = getattr(request.user, 'profile', None)
    if not profile:
        return JsonResponse({'error': 'User profile not found'}, status=403)
    
    if profile.role not in ['instructor', 'faculty_head']:
        return JsonResponse({'error': 'Access denied'}, status=403)
    
    try:
        course = Course.objects.get(name=course_name)
    except Course.DoesNotExist:
        return JsonResponse({'error': 'Course not found'}, status=404)
    
    # Check access: instructor must have course in profile OR be the course instructor, faculty_head must have course in profile or department match
    if profile.role == 'instructor':
        has_access = False
        if course in profile.courses.all():
            has_access = True
        elif course.instructor == request.user:
            has_access = True
        if not has_access:
            return JsonResponse({'error': 'Access denied'}, status=403)
    elif profile.role == 'faculty_head':
        # Faculty head can access if course is in their profile or department matches
        faculty_head_data = get_faculty_head_data(request.user.username)
        faculty_head_department = faculty_head_data.get('department')
        if course not in profile.courses.all():
            if faculty_head_department and course.department != faculty_head_department:
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
        # If score is None, null, empty string, or "-", treat as delete (score_value stays None)
        if score is not None and score != '' and score != '-':
            try:
                # Try to convert to float
                score_value = float(score)
                if score_value < 0:
                    return JsonResponse({'error': 'Score cannot be less than 0'}, status=400)
                if score_value > 100:
                    return JsonResponse({'error': 'Score cannot be greater than 100'}, status=400)
            except (ValueError, TypeError):
                # If conversion fails, treat as delete
                score_value = None
        
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
            
            # Save assessment_scores changes first
            grade.save(update_fields=['assessment_scores'])
            
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
                    
                    # Only set average if ALL assessments are entered
                    if len(all_scores) == assessment_count and assessment_count > 0:
                        average_score = sum(all_scores) / len(all_scores)
                        setattr(grade, assessment_type, average_score)
                    else:
                        # Not all assessments entered, clear average
                        setattr(grade, assessment_type, None)
            except Assessment.DoesNotExist:
                pass
            
            # Calculate overall score
            grade.calculate_overall_score()
            
            # Update last_changes_at
            from django.utils import timezone
            grade.last_changes_at = timezone.now()
            
            # Save all changes
            grade.save()
        
        # Refresh from database to ensure we have the latest data
        grade.refresh_from_db()
        
        # Verify the score was saved correctly
        saved_score = grade.get_individual_score(assessment_key)
        
        return JsonResponse({
            'status': 'ok',
            'score': saved_score,  # Return the actual saved score from database
            'assessment_key': assessment_key,
            'overall_score': grade.overall_score,  # Return updated overall_score
            'letter_grade': grade.letter_grade,  # Return updated letter_grade
            'last_changes_at': grade.last_changes_at.isoformat() if grade.last_changes_at else None
        })
        
    except Exception as e:
        return JsonResponse({'error': f'Update error: {str(e)}'}, status=400)

@csrf_exempt
def update_multiple_grades(request, course_name):
    """Update multiple individual grade scores from table edits in batch
    Works for both instructor and faculty_head
    """
    if request.method != 'POST':
        return JsonResponse({'error': 'Only POST allowed'}, status=405)
    
    # Check if user is authenticated
    if not request.user.is_authenticated:
        return JsonResponse({'error': 'Authentication required'}, status=401)
    
    # Check if user is instructor or faculty_head
    profile = getattr(request.user, 'profile', None)
    if not profile:
        return JsonResponse({'error': 'User profile not found'}, status=403)
    
    if profile.role not in ['instructor', 'faculty_head']:
        return JsonResponse({'error': 'Access denied'}, status=403)
    
    try:
        course = Course.objects.get(name=course_name)
    except Course.DoesNotExist:
        return JsonResponse({'error': 'Course not found'}, status=404)
    
    # Check access: instructor must have course in profile OR be the course instructor, faculty_head must have course in profile or department match
    if profile.role == 'instructor':
        has_access = False
        if course in profile.courses.all():
            has_access = True
        elif course.instructor == request.user:
            has_access = True
        if not has_access:
            return JsonResponse({'error': 'Access denied'}, status=403)
    elif profile.role == 'faculty_head':
        # Faculty head can access if course is in their profile or department matches
        faculty_head_data = get_faculty_head_data(request.user.username)
        faculty_head_department = faculty_head_data.get('department')
        if course not in profile.courses.all():
            if faculty_head_department and course.department != faculty_head_department:
                return JsonResponse({'error': 'Access denied'}, status=403)
    
    try:
        data = json.loads(request.body)
        changes = data.get('changes', [])  # List of {student_id, assessment_key, score}
        
        if not changes or len(changes) == 0:
            return JsonResponse({'error': 'No changes provided'}, status=400)
        
        # Validate all changes first
        validated_changes = []
        for change in changes:
            student_id = change.get('student_id')
            assessment_key = change.get('assessment_key')
            score = change.get('score')
            
            if not student_id or not assessment_key:
                continue
            
            # Get student
            try:
                student = Student.objects.get(student_id=student_id)
            except Student.DoesNotExist:
                continue
            
            # Check if student is enrolled
            if not student.courses.filter(id=course.id).exists():
                continue
            
            # Parse and validate score
            score_value = None
            # If score is None, null, empty string, or "-", treat as delete (score_value stays None)
            if score is not None and score != '' and score != '-':
                try:
                    score_value = float(score)
                    if score_value < 0 or score_value > 100:
                        continue
                except (ValueError, TypeError):
                    # If conversion fails, treat as delete
                    score_value = None
            
            validated_changes.append({
                'student': student,
                'assessment_key': assessment_key,
                'score': score_value
            })
        
        if len(validated_changes) == 0:
            return JsonResponse({'error': 'No valid changes'}, status=400)
        
        # Process all changes in a single transaction
        from django.utils import timezone
        from collections import defaultdict
        
        # Group changes by student
        changes_by_student = defaultdict(list)
        for change in validated_changes:
            student = change['student']
            changes_by_student[student].append(change)
        
        # Debug: Log grouped changes
        import logging
        logger = logging.getLogger(__name__)
        for student, student_changes in changes_by_student.items():
            logger.info(f"Student {student.student_id}: {len(student_changes)} changes: {[(c['assessment_key'], c['score']) for c in student_changes]}")
        
        updated_count = 0
        results = []
        
        with transaction.atomic():
            for student, student_changes in changes_by_student.items():
                # Get or create grade once per student
                grade, created = Grade.objects.get_or_create(
                    student=student,
                    course=course
                )
                
                if not grade.assessment_scores:
                    grade.assessment_scores = {}
                
                from django.utils import timezone
                from copy import deepcopy
                new_assessment_scores = deepcopy(grade.assessment_scores) if grade.assessment_scores else {}
                
                for change in student_changes:
                    assessment_key = change['assessment_key']
                    score_value = change['score']
                    
                    existing_file_name = ''
                    if assessment_key in new_assessment_scores:
                        existing_file_name = new_assessment_scores[assessment_key].get('file_name', '')
                    
                    if score_value is None:
                        if assessment_key in new_assessment_scores:
                            del new_assessment_scores[assessment_key]
                    else:
                        new_assessment_scores[assessment_key] = {
                            'score': float(score_value),
                            'uploaded_at': timezone.now().isoformat(),
                            'file_name': existing_file_name or ''
                        }
                
                # Update assessment_scores
                grade.assessment_scores = new_assessment_scores
                
                # Calculate assessment averages BEFORE saving
                try:
                    assessment = Assessment.objects.get(course=course)
                    assessment_types = ['midterm', 'final', 'project', 'assignment', 'absence', 'quiz']
                    
                    for assessment_type in assessment_types:
                        assessment_count = getattr(assessment, assessment_type, 0)
                        
                        if assessment_count > 0:
                            all_scores = []
                            for i in range(1, assessment_count + 1):
                                key = f'{assessment_type}_{i}'
                                # Get score from new_assessment_scores directly
                                if key in new_assessment_scores:
                                    score_data = new_assessment_scores[key]
                                    if score_data and 'score' in score_data:
                                        score = score_data['score']
                                        if score is not None:
                                            all_scores.append(float(score))
                            
                            # Only set average if ALL assessments are entered
                            if len(all_scores) == assessment_count and assessment_count > 0:
                                average_score = sum(all_scores) / len(all_scores)
                                setattr(grade, assessment_type, average_score)
                            else:
                                setattr(grade, assessment_type, None)
                except Assessment.DoesNotExist:
                    pass
                
                # Calculate overall score
                grade.calculate_overall_score()
                
                # Update last_changes_at
                grade.last_changes_at = timezone.now()
                
                # Save ALL fields at once (including assessment_scores, averages, overall_score, letter_grade)
                # Don't use update_fields for JSONField - save everything to ensure JSONField is persisted
                grade.save()
                
                # Force database commit by refreshing - this ensures data is read from database
                # For JSONField, refresh_from_db() is critical to ensure we get the saved data
                grade.refresh_from_db()
                
                # Verify assessment_scores was saved correctly
                # Access the field to trigger database read
                _ = grade.assessment_scores
                
                for change in student_changes:
                    assessment_key = change['assessment_key']
                    updated_count += 1
                    # Get score from database after refresh
                    # This should now return the saved value
                    saved_score = grade.get_individual_score(assessment_key)
                    results.append({
                        'student_id': student.student_id,
                        'assessment_key': assessment_key,
                        'score': saved_score,
                        'overall_score': grade.overall_score,
                        'letter_grade': grade.letter_grade
                    })
        
        # Get the most recent last_changes_at from the results
        # All grades in the transaction should have the same last_changes_at
        last_changes_at_value = None
        if results:
            # Get the last_changes_at from the first grade (all should be the same)
            # We need to query the database to get the actual saved value
            try:
                first_result = results[0]
                first_grade = Grade.objects.filter(
                    student__student_id=first_result['student_id'],
                    course=course
                ).first()
                if first_grade:
                    last_changes_at_value = first_grade.last_changes_at
            except Exception:
                pass
        
        # Fallback to current time if we couldn't get it from database
        if not last_changes_at_value:
            last_changes_at_value = timezone.now()
        
        return JsonResponse({
            'status': 'ok',
            'updated_count': updated_count,
            'results': results,
            'last_changes_at': last_changes_at_value.isoformat() if last_changes_at_value else timezone.now().isoformat()
        })
        
    except Exception as e:
        return JsonResponse({'error': f'Update error: {str(e)}'}, status=400)

@csrf_exempt
def update_assessment(request, course_name):
    """Update assessment counts
    Works for both instructor and faculty_head
    """
    if request.method != 'POST':
        return JsonResponse({'error': 'Method not allowed'}, status=405)
    
    # Check if user is authenticated
    if not request.user.is_authenticated:
        return JsonResponse({'error': 'Authentication required'}, status=401)
    
    # Check if user is instructor or faculty_head
    profile = getattr(request.user, 'profile', None)
    if not profile:
        return JsonResponse({'error': 'User profile not found'}, status=403)
    
    if profile.role not in ['instructor', 'faculty_head']:
        return JsonResponse({'error': 'Access denied'}, status=403)
    
    try:
        course = Course.objects.get(name=course_name)
    except Course.DoesNotExist:
        return JsonResponse({'error': 'Course not found'}, status=404)
    
    # Check access: instructor must have course in profile OR be the course instructor, faculty_head must have course in profile or department match
    if profile.role == 'instructor':
        has_access = False
        if course in profile.courses.all():
            has_access = True
        elif course.instructor == request.user:
            has_access = True
        if not has_access:
            return JsonResponse({'error': 'Access denied'}, status=403)
    elif profile.role == 'faculty_head':
        # Faculty head can access if course is in their profile or department matches
        faculty_head_data = get_faculty_head_data(request.user.username)
        faculty_head_department = faculty_head_data.get('department')
        if course not in profile.courses.all():
            if faculty_head_department and course.department != faculty_head_department:
                return JsonResponse({'error': 'Access denied'}, status=403)
    
    try:
        data = json.loads(request.body)
        midterm = data.get('midterm')
        final = data.get('final')
        project = data.get('project')
        assignment = data.get('assignment')
        absence = data.get('absence')
        quiz = data.get('quiz')
        
        # Validation: Integer kontrolü ve 10'dan küçük olması
        values = {
            'midterm': midterm,
            'final': final,
            'project': project,
            'assignment': assignment,
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
        from django.db import transaction
        with transaction.atomic():
            try:
                assessment = Assessment.objects.select_for_update().get(course=course)
                # Eski değerleri sakla (assessment_scores temizleme için)
                old_values = {
                    'midterm': assessment.midterm or 0,
                    'final': assessment.final or 0,
                    'project': assessment.project or 0,
                    'assignment': assessment.assignment or 0,
                    'absence': assessment.absence or 0,
                    'quiz': assessment.quiz or 0
                }
                
                # Mevcut assessment'ı güncelle
                assessment.midterm = values['midterm']
                assessment.final = values['final']
                assessment.project = values['project']
                assessment.assignment = values['assignment']
                assessment.absence = values['absence']
                assessment.quiz = values['quiz']
                # save() metodu assessment_count'u otomatik hesaplayacak
                assessment.save()
            except Assessment.DoesNotExist:
                # Assessment yoksa oluştur
                old_values = {
                    'midterm': 0,
                    'final': 0,
                    'project': 0,
                    'assignment': 0,
                    'absence': 0,
                    'quiz': 0
                }
                assessment = Assessment.objects.create(
                    course=course,
                    midterm=values['midterm'],
                    final=values['final'],
                    project=values['project'],
                    assignment=values['assignment'],
                    absence=values['absence'],
                    quiz=values['quiz']
                )
        
        # Database'den yeniden oku (güncel değerleri garantilemek için)
        assessment.refresh_from_db()
        
        # Update assessment_scores for all grades in this course
        # Remove assessment scores that are no longer valid (e.g., if midterm count changed from 3 to 2, remove midterm_3)
        grades = Grade.objects.filter(course=course)
        assessment_types = ['midterm', 'final', 'project', 'assignment', 'absence', 'quiz']
        
        for grade in grades:
            if not grade.assessment_scores:
                grade.assessment_scores = {}
            
            # Create a copy to modify
            from copy import deepcopy
            updated_assessment_scores = deepcopy(grade.assessment_scores) if grade.assessment_scores else {}
            scores_changed = False
            
            # For each assessment type, remove scores that exceed the new count
            for assessment_type in assessment_types:
                old_count = old_values[assessment_type]
                new_count = values[assessment_type]
                
                # If count decreased, remove scores beyond the new count
                if new_count < old_count:
                    for i in range(new_count + 1, old_count + 1):
                        key = f'{assessment_type}_{i}'
                        if key in updated_assessment_scores:
                            del updated_assessment_scores[key]
                            scores_changed = True
            
            # Update grade if scores were changed
            if scores_changed:
                grade.assessment_scores = updated_assessment_scores
                grade.save(update_fields=['assessment_scores'])
            
            # Recalculate overall_score for all grades
            # (Assessment counts changed, so overall scores might need recalculation)
            grade.calculate_overall_score()
            grade.save(update_fields=['overall_score', 'letter_grade'])
        
        return JsonResponse({
            'status': 'ok',
            'assessment_count': assessment.assessment_count
        })
        
    except Exception as e:
        import traceback
        error_trace = traceback.format_exc()
        return JsonResponse({'error': f'Update error: {str(e)}\n{error_trace}'}, status=400)

@csrf_exempt
def update_assessment_percentages(request, course_name):
    """Update assessment percentages
    Works for both instructor and faculty_head
    """
    if request.method != 'POST':
        return JsonResponse({'error': 'Method not allowed'}, status=405)
    
    # Check if user is authenticated
    if not request.user.is_authenticated:
        return JsonResponse({'error': 'Authentication required'}, status=401)
    
    # Check if user is instructor or faculty_head
    profile = getattr(request.user, 'profile', None)
    if not profile:
        return JsonResponse({'error': 'User profile not found'}, status=403)
    
    if profile.role not in ['instructor', 'faculty_head']:
        return JsonResponse({'error': 'Access denied'}, status=403)
    
    try:
        course = Course.objects.get(name=course_name)
    except Course.DoesNotExist:
        return JsonResponse({'error': 'Course not found'}, status=404)
    
    # Check access: instructor must have course in profile OR be the course instructor, faculty_head must have course in profile or department match
    if profile.role == 'instructor':
        has_access = False
        if course in profile.courses.all():
            has_access = True
        elif course.instructor == request.user:
            has_access = True
        if not has_access:
            return JsonResponse({'error': 'Access denied'}, status=403)
    elif profile.role == 'faculty_head':
        # Faculty head can access if course is in their profile or department matches
        faculty_head_data = get_faculty_head_data(request.user.username)
        faculty_head_department = faculty_head_data.get('department')
        if course not in profile.courses.all():
            if faculty_head_department and course.department != faculty_head_department:
                return JsonResponse({'error': 'Access denied'}, status=403)
    
    try:
        data = json.loads(request.body)
        midterm_percentage = data.get('midterm_percentage')
        final_percentage = data.get('final_percentage')
        project_percentage = data.get('project_percentage')
        assignment_percentage = data.get('assignment_percentage')
        absence_percentage = data.get('absence_percentage')
        quiz_percentage = data.get('quiz_percentage')
        
        try:
            assessment = Assessment.objects.get(course=course)
            counts = {
                'midterm': assessment.midterm or 0,
                'final': assessment.final or 0,
                'project': assessment.project or 0,
                'assignment': assessment.assignment or 0,
                'absence': assessment.absence or 0,
                'quiz': assessment.quiz or 0
            }
        except Assessment.DoesNotExist:
            counts = {
                'midterm': 0,
                'final': 0,
                'project': 0,
                'assignment': 0,
                'absence': 0,
                'quiz': 0
            }
        
        # Validation: Integer kontrolü (only for assessments with count > 0)
        values = {}
        percentage_mapping = {
            'midterm_percentage': 'midterm',
            'final_percentage': 'final',
            'project_percentage': 'project',
            'assignment_percentage': 'assignment',
            'absence_percentage': 'absence',
            'quiz_percentage': 'quiz'
        }
        
        for key, value in [
            ('midterm_percentage', midterm_percentage),
            ('final_percentage', final_percentage),
            ('project_percentage', project_percentage),
            ('assignment_percentage', assignment_percentage),
            ('absence_percentage', absence_percentage),
            ('quiz_percentage', quiz_percentage)
        ]:
            count_key = percentage_mapping[key]
            count = counts[count_key]
            
            if count == 0:
                if value is None:
                    values[key] = 0
                else:
                    try:
                        int_value = int(value)
                        if int_value != 0:
                            return JsonResponse({'error': f'{key} should be 0 when {count_key} count is 0'}, status=400)
                        values[key] = 0
                    except (ValueError, TypeError):
                        return JsonResponse({'error': f'{key} must be an integer'}, status=400)
            else:
                if value is None:
                    return JsonResponse({'error': f'Percentages: {key} is required'}, status=400)
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
        from django.db import transaction
        with transaction.atomic():
            try:
                assessment = Assessment.objects.select_for_update().get(course=course)
                # Mevcut assessment'ı güncelle
                assessment.midterm_percentage = values['midterm_percentage']
                assessment.final_percentage = values['final_percentage']
                assessment.project_percentage = values['project_percentage']
                assessment.assignment_percentage = values['assignment_percentage']
                assessment.absence_percentage = values['absence_percentage']
                assessment.quiz_percentage = values['quiz_percentage']
                assessment.save()
            except Assessment.DoesNotExist:
                # Assessment yoksa oluştur (default count değerleriyle)
                assessment = Assessment.objects.create(
                    course=course,
                    midterm_percentage=values['midterm_percentage'],
                    final_percentage=values['final_percentage'],
                    project_percentage=values['project_percentage'],
                    assignment_percentage=values['assignment_percentage'],
                    absence_percentage=values['absence_percentage'],
                    quiz_percentage=values['quiz_percentage']
                )
        
        # Database'den yeniden oku (güncel değerleri garantilemek için)
        assessment.refresh_from_db()
        
        # Recalculate overall_score and letter_grade for all grades in this course
        grades = Grade.objects.filter(course=course)
        for grade in grades:
            grade.calculate_overall_score()
            grade.save(update_fields=['overall_score', 'letter_grade'])
        
        return JsonResponse({
            'status': 'ok',
            'percentage_count': assessment.percentage_count
        })
        
    except Exception as e:
        import traceback
        error_trace = traceback.format_exc()
        return JsonResponse({'error': f'Update error: {str(e)}\n{error_trace}'}, status=400)


# Helper functions for instructor_announcements view
def send_announcements(sender, message, subject, receivers_list):
    """
    Send announcements to receivers (users or course students).
    Returns number of announcements created.
    """
    from .models import Announcement, Notification
    
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
                                announcement = Announcement.objects.create(
                                    sender=sender,
                                    receiver=student_user,
                                    subject=marked_subject,
                                    message=message,
                                    sender_role='instructor',
                                    receiver_role='student'
                                )
                                # Create notification for the student
                                Notification.objects.create(
                                    user=student_user,
                                    notification_type='announcement_created',
                                    title=clean_announcement_subject(marked_subject),
                                    message=message[:100] + ('...' if len(message) > 100 else ''),
                                    assignment=None,
                                    announcement=announcement
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
                    
                    announcement = Announcement.objects.create(
                        sender=sender,
                        receiver=receiver,
                        subject=subject,
                        message=message,
                        sender_role='instructor',
                        receiver_role=receiver_role
                    )
                    # Create notification for the receiver (if student)
                    if receiver_role == 'student' or (profile and profile.role == 'student'):
                        Notification.objects.create(
                            user=receiver,
                            notification_type='announcement_created',
                            title=subject,
                            message=message[:100] + ('...' if len(message) > 100 else ''),
                            assignment=None,
                            announcement=announcement
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
    
    return render(request, 'instructor/instructor_announcements.html', {
        'all_announcements': announcements_data,
        'announcements_json': announcements_json,
        'sent_messages': sent_messages,
        'received_messages': received_messages,
        'recipients': recipients,
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
    from .models import Announcement, Assignment
    from django.db.models import Q
    from django.utils import timezone
    
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
    
    # Get assignments from faculty head's department courses
    upcoming_assignments = []
    
    if faculty_head_department:
        # Get all courses from the department
        courses = Course.objects.filter(department__iexact=faculty_head_department).exclude(department='').select_related('instructor').prefetch_related('students')
        
        # Get all students from the department (not just enrolled in courses)
        department_students = Student.objects.filter(department__iexact=faculty_head_department).exclude(department='')
        for student in department_students:
            total_students_set.add(student.id)
        
        for course in courses:
            students = course.students.all()
            student_count = students.count()
            
            # Only count instructor if they are not a faculty_head
            if course.instructor:
                instructor_profile = getattr(course.instructor, 'profile', None)
                if instructor_profile and instructor_profile.role != 'faculty_head':
                    total_instructors_set.add(course.instructor.id)
            
            instructor_name = f"{course.instructor.first_name} {course.instructor.last_name}".strip() if course.instructor else 'Unknown'
            if not instructor_name or instructor_name == ' ':
                instructor_name = course.instructor.username if course.instructor else 'Unknown'
            
            # Get schedule from JSON first, fallback to database
            schedule_info = get_course_schedule_from_json().get(course.name, {})
            courses_list.append({
                'id': course.id,
                'name': course.name,
                'code': course.code,
                'credits': course.credits,
                'instructor': instructor_name,
                'student_count': student_count,
                'day': schedule_info.get('day') or course.day,
                'time': schedule_info.get('time') or course.time,
                'room': schedule_info.get('room') or course.room,
            })
            
            chart_data['labels'].append(course.name)
            chart_data['data'].append(student_count)
        
        # Get assignments with deadlines, ordered by deadline (soonest first)
        # Show both future and past assignments, but prioritize future ones
        now = timezone.now()
        all_assignments_qs = Assignment.objects.filter(
            course__in=courses
        ).select_related('course', 'created_by')
        
        # Convert to list to sort
        all_assignments_list = list(all_assignments_qs)
        
        # Separate future and past assignments
        future_assignments = [a for a in all_assignments_list if a.deadline >= now]
        past_assignments = [a for a in all_assignments_list if a.deadline < now]
        
        # Sort each group by deadline
        future_assignments.sort(key=lambda x: x.deadline)
        past_assignments.sort(key=lambda x: x.deadline, reverse=True)  # Most recent past first
        
        # Show future assignments first, then past ones (limit to 10 total)
        assignments = (future_assignments + past_assignments)[:10]
        
        instructors_map = get_instructors_map()
        faculty_heads_map = get_faculty_heads_map()
        
        for assignment in assignments:
            creator_name = instructors_map.get(assignment.created_by.username) or faculty_heads_map.get(assignment.created_by.username) or assignment.created_by.get_full_name() or assignment.created_by.username
            
            # Check if deadline is approaching (within 7 days)
            time_diff = assignment.deadline - now
            days_until_deadline = time_diff.days
            # If less than 24 hours, count as 0 days
            if time_diff.total_seconds() < 86400 and time_diff.total_seconds() >= 0:
                days_until_deadline = 0
            elif time_diff.total_seconds() < 0:
                # Past deadline
                days_until_deadline = -1
            is_urgent = days_until_deadline <= 3 and days_until_deadline >= 0
            
            upcoming_assignments.append({
                'id': assignment.id,
                'title': assignment.title,
                'course_name': assignment.course.name,
                'deadline': assignment.deadline.strftime('%d/%m/%Y %H:%M'),
                'deadline_datetime': assignment.deadline.isoformat(),
                'days_until': days_until_deadline,
                'is_urgent': is_urgent,
            })
    
    total_courses = len(courses_list)
    total_students = len(total_students_set)
    total_instructors = len(total_instructors_set)
    
    # Get department course names for filtering announcements
    department_course_names = set()
    if faculty_head_department:
        department_course_names = set(courses.values_list('name', flat=True))
    
    # Filter announcements: only show those related to faculty head's department courses
    all_announcements = Announcement.objects.filter(
        Q(receiver=faculty_head_user)
    ).exclude(sender=faculty_head_user).select_related('sender', 'receiver').order_by('-created_at')
    
    # Filter announcements by department courses
    filtered_announcements = []
    for ann in all_announcements:
        # Check if announcement is related to a course in faculty head's department
        if ann.subject and ann.subject.startswith('__COURSE:'):
            # Extract course name from subject
            end_marker = ann.subject.find('__', 9)
            if end_marker != -1:
                course_name = ann.subject[9:end_marker]
                # Only include if course is in faculty head's department
                if course_name in department_course_names:
                    filtered_announcements.append(ann)
        else:
            # Announcements without course marker - only show if receiver is faculty head
            # (general announcements sent directly to faculty head)
            if ann.receiver == faculty_head_user:
                filtered_announcements.append(ann)
    
    # Take top 5
    latest_announcements = filtered_announcements[:5]
    
    announcements_list = []
    for ann in latest_announcements:
        sender_name = ann.sender.get_full_name() or ann.sender.username
        announcements_list.append({
            'id': ann.id,
            'subject': clean_announcement_subject(ann.subject),
            'sender': sender_name,
            'created_at': ann.created_at.strftime('%Y-%m-%d %H:%M'),
        })
    
    chart_data_json = json.dumps(chart_data)
    
    # Prepare schedule data for template
    days = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday']
    time_slots = ['09:00-10:30', '11:00-12:30', '14:00-15:30', '16:00-17:30']
    
    return render(request, 'faculty_head_main.html', {
        'faculty_head_info': faculty_head_info,
        'academic_term': academic_term,
        'courses_list': courses_list,
        'days': days,
        'time_slots': time_slots,
        'total_courses': total_courses,
        'total_students': total_students,
        'total_instructors': total_instructors,
        'chart_data': chart_data,
        'chart_data_json': chart_data_json,
        'latest_announcements': announcements_list,
        'upcoming_assignments': upcoming_assignments,
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
def upload_academic_calendar(request):
    from .models import AcademicCalendar, AcademicCalendarEvent
    import csv
    import io
    from django.http import JsonResponse
    from django.shortcuts import render
    
    if request.method == 'POST':
        try:
            file = request.FILES.get('calendar_file')
            academic_year = request.POST.get('academic_year', '')
            semester = request.POST.get('semester', '')
            
            if not file:
                return JsonResponse({'error': 'No file uploaded'}, status=400)
            
            # Check file extension
            file_ext = file.name.split('.')[-1].lower()
            if file_ext not in ['pdf', 'csv']:
                return JsonResponse({'error': 'Only PDF and CSV files are allowed'}, status=400)
            
            # Create calendar record
            calendar = AcademicCalendar.objects.create(
                academic_year=academic_year,
                semester=semester,
                uploaded_by=request.user
            )
            
            # Parse CSV if CSV file
            if file_ext == 'csv':
                # Save file
                calendar.file = file
                calendar.save()
                
                # Parse CSV
                file.seek(0)
                try:
                    content = file.read().decode('utf-8')
                except UnicodeDecodeError:
                    content = file.read().decode('utf-8-sig')  # Handle BOM
                
                csv_reader = csv.DictReader(io.StringIO(content))
                events_created = 0
                errors = []
                
                for row_num, row in enumerate(csv_reader, start=2):  # Start at 2 (header is row 1)
                    try:
                        # Try multiple column name variations
                        event_name = (row.get('Event Name', '') or 
                                     row.get('Calendar Name', '') or 
                                     row.get('Takvim Adı', '') or 
                                     row.get('event_name', '') or
                                     row.get('calendar_name', ''))
                        if not event_name or not event_name.strip():
                            continue
                            
                        start_str = (row.get('Start Date', '') or 
                                   row.get('Başlangıç Tarihi', '') or 
                                   row.get('start_date', ''))
                        end_str = (row.get('End Date', '') or 
                                 row.get('Bitiş Tarihi', '') or 
                                 row.get('end_date', ''))
                        
                        if not start_str or not start_str.strip():
                            continue
                        
                        # Parse dates (format: DD.MM.YYYY HH:MM)
                        from datetime import datetime
                        from django.utils import timezone
                        naive_start = datetime.strptime(start_str.strip(), '%d.%m.%Y %H:%M')
                        start_date = timezone.make_aware(naive_start)
                        end_date = None
                        if end_str and end_str.strip():
                            naive_end = datetime.strptime(end_str.strip(), '%d.%m.%Y %H:%M')
                            end_date = timezone.make_aware(naive_end)
                        
                        AcademicCalendarEvent.objects.create(
                            calendar=calendar,
                            event_name=event_name.strip(),
                            start_date=start_date,
                            end_date=end_date
                        )
                        events_created += 1
                    except Exception as e:
                        error_msg = f"Row {row_num}: {str(e)}"
                        errors.append(error_msg)
                        print(f"Error parsing row {row_num}: {e}")
                        continue
                
                if events_created == 0 and errors:
                    return JsonResponse({'error': f'No events created. Errors: {"; ".join(errors[:5])}'}, status=400)
                elif events_created == 0:
                    return JsonResponse({'error': 'No events found in CSV file. Please check the format.'}, status=400)
            
            return JsonResponse({'success': True, 'message': 'Academic calendar uploaded successfully'})
            
        except Exception as e:
            return JsonResponse({'error': str(e)}, status=400)
    
    # GET request - show upload form
    from .models import AcademicCalendar
    latest_calendar = AcademicCalendar.objects.first()
    return render(request, 'faculty/academic_calendar_upload.html', {
        'latest_calendar': latest_calendar
    })

def view_academic_calendar(request):
    """View academic calendar for all users"""
    from .models import AcademicCalendar, AcademicCalendarEvent
    from django.shortcuts import render, redirect
    
    if not request.user.is_authenticated:
        return redirect('student-login')
    
    latest_calendar = AcademicCalendar.objects.first()
    events = []
    
    if latest_calendar:
        events = latest_calendar.events.all()
    
    # Determine which template to use based on user role
    profile = getattr(request.user, 'profile', None)
    if profile:
        if profile.role == 'student':
            template_name = 'student/academic_calendar.html'
        elif profile.role == 'instructor':
            template_name = 'instructor/academic_calendar.html'
        elif profile.role == 'faculty_head':
            template_name = 'faculty/academic_calendar.html'
        else:
            template_name = 'student/academic_calendar.html'
    else:
        template_name = 'student/academic_calendar.html'
    
    return render(request, template_name, {
        'calendar': latest_calendar,
        'events': events,
        'is_faculty_head': profile and profile.role == 'faculty_head' if profile else False
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
                    old_instructor = course.instructor
                    course.instructor = instructor_user
                    if credits is not None:
                        course.credits = credits
                    course.save()
                    
                    # Eski instructor'ın profile.courses'undan çıkar
                    if old_instructor and old_instructor != instructor_user:
                        old_profile = getattr(old_instructor, 'profile', None)
                        if old_profile and course in old_profile.courses.all():
                            old_profile.courses.remove(course)
                
                # Yeni instructor'ın profile.courses'una ekle
                if instructor_user:
                    instructor_profile = getattr(instructor_user, 'profile', None)
                    if instructor_profile and instructor_profile.role in ['instructor', 'faculty_head']:
                        if course not in instructor_profile.courses.all():
                            instructor_profile.courses.add(course)
        
        elif action == 'update_course':
            course_id = request.POST.get('course_id')
            course_name = request.POST.get('course_name', '').strip()
            instructor_username = request.POST.get('instructor_username', '').strip()
            credits_str = request.POST.get('credits', '').strip()
            
            try:
                course = Course.objects.get(id=course_id)
                
                if course_name:
                    course.name = course_name
                
                old_instructor = course.instructor
                
                if instructor_username:
                    try:
                        instructor_user = User.objects.get(username=instructor_username)
                        course.instructor = instructor_user
                    except User.DoesNotExist:
                        # Log warning instead of silently failing
                        import logging
                        logger = logging.getLogger(__name__)
                        logger.warning(f"Instructor not found: {instructor_username} when updating course {course.id}")
                        instructor_user = None
                else:
                    instructor_user = course.instructor
                
                if credits_str:
                    try:
                        credits = int(credits_str)
                        course.credits = credits
                    except ValueError:
                        pass
                else:
                    course.credits = None
                
                course.save()
                
                # Eski instructor'ın profile.courses'undan çıkar
                if old_instructor and old_instructor != instructor_user:
                    old_profile = getattr(old_instructor, 'profile', None)
                    if old_profile and course in old_profile.courses.all():
                        old_profile.courses.remove(course)
                
                # Yeni instructor'ın profile.courses'una ekle
                if instructor_user:
                    instructor_profile = getattr(instructor_user, 'profile', None)
                    if instructor_profile and instructor_profile.role in ['instructor', 'faculty_head']:
                        if course not in instructor_profile.courses.all():
                            instructor_profile.courses.add(course)
            except Course.DoesNotExist:
                # Log warning instead of silently failing
                import logging
                logger = logging.getLogger(__name__)
                logger.warning(f"Course not found: {course_id} when updating course")
        
        return redirect('all_courses')
    
    faculty_courses_with_instructors = []
    
    # IMPORTANT: Course.instructor (ForeignKey) is the PRIMARY source of truth for course-instructor relationships
    # We only use Course.instructor to ensure the table reflects the actual PostgreSQL database state
    # Note: Course.instructor can be either an instructor OR a faculty_head (both are User objects)
    
    # Get all courses from the department
    if faculty_head_department:
        courses_qs = Course.objects.filter(department=faculty_head_department).select_related('instructor', 'instructor__profile')
    else:
        courses_qs = Course.objects.all().select_related('instructor', 'instructor__profile')
    
    # Optimize: Fetch all learning outcomes in one query
    course_names = [course.name for course in courses_qs]
    learning_outcomes_by_course = {}
    if course_names:
        outcomes = ProgramOutcome.objects.filter(course_name__in=course_names).order_by('course_name', '-created_at')
        for outcome in outcomes:
            if outcome.course_name not in learning_outcomes_by_course:
                learning_outcomes_by_course[outcome.course_name] = outcome
    
    # Build courses list directly from Course.instructor (the source of truth)
    # This includes both instructors and faculty_heads who are assigned to courses
    from django.db.models import Avg
    from .models import Grade
    
    for course in courses_qs.order_by('name'):
        # Get instructor name from Course.instructor (PostgreSQL'deki gerçek durum)
        # Course.instructor can be either instructor or faculty_head
        if course.instructor:
            instructor_full_name = (course.instructor.first_name + ' ' + course.instructor.last_name).strip()
            instructor_name = instructor_full_name if instructor_full_name else course.instructor.username
        else:
            instructor_name = 'Unknown'
        
        first_learning_outcome = learning_outcomes_by_course.get(course.name)
        
        # Calculate average overall score for this course
        # Get all grades for this course where overall_score is not None
        grades_with_scores = Grade.objects.filter(course=course, overall_score__isnull=False)
        average_score = None
        
        if grades_with_scores.exists():
            # Calculate average
            avg_result = grades_with_scores.aggregate(avg_score=Avg('overall_score'))
            if avg_result['avg_score'] is not None:
                average_score = round(avg_result['avg_score'], 2)
        
        # Get students enrolled in this course with their overall scores
        students_list = []
        students = course.students.all().order_by('first_name', 'last_name', 'student_id')
        for student in students:
            grade_obj = Grade.objects.filter(student=student, course=course).first()
            overall_score = None
            if grade_obj and grade_obj.overall_score is not None:
                overall_score = round(grade_obj.overall_score, 2)
            
            student_name = f"{student.first_name} {student.last_name}".strip()
            if not student_name:
                student_name = student.username
            
            students_list.append({
                'student_id': student.student_id,
                'student_name': student_name,
                'overall_score': overall_score,
            })
        
        faculty_courses_with_instructors.append({
            'course': course.name,
            'instructor': instructor_name,
            'course_id': course.id,
            'credits': course.credits,
            'first_lo_id': first_learning_outcome.id if first_learning_outcome else None,
            'instructor_username': course.instructor.username if course.instructor else None,
            'average_score': average_score,
            'students': students_list,
        })
    
    available_instructors_list = []
    # Get instructors
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
            'role': 'instructor',
        })
    
    # Get faculty heads
    available_faculty_heads_qs = User.objects.filter(profile__role='faculty_head').select_related('profile')
    for user in available_faculty_heads_qs:
        profile = user.profile
        fh_department = profile.department
        if faculty_head_department:
            if fh_department != faculty_head_department:
                continue
        
        full_name = (user.first_name + ' ' + user.last_name).strip()
        faculty_head_name = full_name if full_name else user.username
        available_instructors_list.append({
            'username': user.username,
            'name': faculty_head_name,
            'role': 'faculty_head',
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
        courses = profile.courses.all().select_related('instructor').prefetch_related('students', 'assignments')
        
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
            
            if course.instructor and course.instructor != request.user:
                continue
            
            instructor_name = f"{course.instructor.first_name} {course.instructor.last_name}".strip() if course.instructor else ''
            if not instructor_name and course.instructor:
                instructor_name = course.instructor.username
            
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
            
            first_learning_outcome = learning_outcomes_dict.get(course.name)
            
            courses_data.append({
                'id': course.id,
                'name': course.name,
                'code': course.code,
                'instructor': instructor_name,
                'department': course.department,
                'credits': course.credits,
                'first_lo_id': first_learning_outcome.id if first_learning_outcome else None,
                'day': course.day,
                'time': course.time,
                'room': course.room,
            })
    
    # Prepare schedule data for template
    days = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday']
    time_slots = ['09:00-10:30', '11:00-12:30', '14:00-15:30', '16:00-17:30']
    
    context = {
        'courses': courses_data,
        'days': days,
        'time_slots': time_slots
    }
    return render(request, 'faculty/my_courses.html', context)

@faculty_head_required
def faculty_head_assignments(request):
    from .models import Assignment, AssignmentSubmission
    
    profile = getattr(request.user, 'profile', None)
    
    # Get faculty head's department
    faculty_head_data = get_faculty_head_data(request.user.username)
    faculty_head_department = faculty_head_data.get('department')
    
    all_assignments = []
    courses_list = []
    
    if profile:
        courses = profile.courses.all().select_related('instructor').prefetch_related('assignments')
        
        # Filter by department if faculty head has a department
        if faculty_head_department:
            courses = courses.filter(department=faculty_head_department)
        
        courses_list = [{'id': course.id, 'name': course.name} for course in courses]
        
        for course in courses:
            # Get assignments for this course
            assignments = course.assignments.all().order_by('-created_at')
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
                    'course_code': course.code,
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
                    'submissions_count': len(submissions_list),
                }
                all_assignments.append(assignment_data)
    
    context = {
        'assignments': all_assignments,
        'courses': courses_list,
    }
    return render(request, 'faculty/assignments.html', context)

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
        # Note: profile.courses will be synced automatically via signals when Course.instructor is set
    
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
        
        # Use flexible course lookup (same as course_learning_outcomes)
        course = Course.objects.filter(id=course_id, instructor=instructor_user).first()
        if not course:
            profile = getattr(instructor_user, 'profile', None)
            if profile:
                course = profile.courses.filter(id=course_id).first()
            if not course:
                course = instructor_user.instructor_courses.filter(id=course_id).first()
        
        if not course:
            return HttpResponseForbidden("You don't have access to this course.")
        
        # Use case-insensitive search for outcome (same as course_learning_outcomes)
        outcome = ProgramOutcome.objects.filter(
            id=outcome_id,
            course_name__iexact=course.name,
            created_by=instructor_user
        ).first()
        
        if not outcome:
            return HttpResponseForbidden("You don't have access to this learning outcome.")
        
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
    """Redirect to my courses page"""
    from django.shortcuts import redirect
    return redirect('my_courses')

@faculty_head_required
def faculty_head_get_existing_learning_outcomes(request):
    """Get existing learning outcomes from department courses (AJAX) for faculty head"""
    from django.http import JsonResponse
    import traceback
    
    try:
        from .models import ProgramOutcome, Course, User
        
        # Get faculty head's department
        faculty_head_data = get_faculty_head_data(request.user.username)
        faculty_head_department = faculty_head_data.get('department', '')
        
        if not faculty_head_department:
            return JsonResponse({
                'learning_outcomes': [],
                'error': 'Faculty head department not found.'
            })
        
        # Get current course name to exclude (if provided)
        exclude_course = request.GET.get('exclude_course', '').strip()
        
        # Get all courses in the department
        department_courses = Course.objects.filter(
            department=faculty_head_department
        ).values_list('name', flat=True).distinct()
        
        # Also get courses from instructors in the same department
        department_instructors = User.objects.filter(
            profile__role='instructor',
            profile__department=faculty_head_department
        ).select_related('profile')
        
        instructor_courses = Course.objects.filter(
            instructor__in=department_instructors
        ).values_list('name', flat=True).distinct()
        
        # Combine all course names
        all_course_names = list(set(list(department_courses) + list(instructor_courses)))
        
        if not all_course_names:
            return JsonResponse({
                'learning_outcomes': [],
                'error': f'No courses found for {faculty_head_department} department.'
            })
        
        # Get all learning outcomes from department courses
        outcomes_qs = ProgramOutcome.objects.filter(
            course_name__in=all_course_names
        ).exclude(course_name='')
        
        # Exclude current course if provided (to avoid showing LO's already in current course)
        if exclude_course:
            # Normalize course name for comparison (case-insensitive)
            exclude_course_normalized = exclude_course.strip()
            
            # First exclude by course name (case-insensitive)
            outcomes_qs = outcomes_qs.exclude(course_name__iexact=exclude_course_normalized)
            
            # Also exclude learning outcomes that are already in the current course (by text)
            # This ensures that even if the same text exists in another course, 
            # if it's already in the current course, it won't be shown
            current_course_outcomes = ProgramOutcome.objects.filter(
                course_name__iexact=exclude_course_normalized
            ).values_list('text', flat=True).distinct()
            
            if current_course_outcomes:
                outcomes_qs = outcomes_qs.exclude(text__in=current_course_outcomes)
        
        outcomes_qs = outcomes_qs.select_related('created_by').order_by('-created_at', 'course_name')
        
        learning_outcomes = []
        for outcome in outcomes_qs:
            learning_outcomes.append({
                'id': outcome.id,
                'text': outcome.text,
                'course_name': outcome.course_name,
                'created_by': outcome.created_by.get_full_name() or outcome.created_by.username,
                'created_at': outcome.created_at.strftime('%Y-%m-%d %H:%M'),
            })
        
        return JsonResponse({'learning_outcomes': learning_outcomes})
    except Exception as e:
        import traceback
        error_trace = traceback.format_exc()
        return JsonResponse({
            'learning_outcomes': [],
            'error': f'Error loading learning outcomes: {str(e)}'
        }, status=500)


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
            # Note: profile.courses will be synced automatically via signals when Course.instructor is set
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
                    with transaction.atomic():
                        learning_outcome = ProgramOutcome.objects.create(
                            text=text,
                            course_name=course_name,
                            created_by=request.user
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
                    return redirect('faculty_head_course_learning_outcomes', course_name=course_name_slug)
                else:
                    # Error case: Re-render with error message
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
                    
                    display_course_name = course.name if course else course_name.title()
                    page_title = f"{display_course_name} - Learning Outcome"
                    
                    return render(
                        request,
                        'faculty/course_learning_outcomes.html',
                        {
                            'course_name': course_name,
                            'display_course_name': display_course_name,
                            'page_title': page_title,
                            'course_id': course_id,
                            'outcomes_data': outcomes_data,
                            'program_outcomes': program_outcomes,
                            'error_message': error_message,
                        }
                    )
            else:
                # No PO selected - LO can be created without PO
                with transaction.atomic():
                    learning_outcome = ProgramOutcome.objects.create(
                        text=text,
                        course_name=course_name,
                        created_by=request.user
                    )
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
    
    display_course_name = course.name if course else course_name.title()
    page_title = f"{display_course_name} - Learning Outcome"
    
    return render(
        request,
        'faculty/course_learning_outcomes.html',
        {
            'course_name': course_name,
            'display_course_name': display_course_name,
            'page_title': page_title,
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
    # Note: profile.courses will be synced automatically via signals when Course.instructor is set
    
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
    
    from .models import AssessmentLORelation
    all_lo_instances = ProgramOutcome.objects.filter(
        text=outcome.text.strip()
    ).values_list('id', flat=True)
    
    assessment_relations = AssessmentLORelation.objects.filter(
        learning_outcome_id__in=all_lo_instances
    ).select_related('assessment', 'assessment__course').order_by('assessment__course__name', 'assessment__id')
    
    assessments_data = []
    assessment_type_labels = {
        'midterm': 'Midterm',
        'final': 'Final',
        'project': 'Project',
        'assignment': 'Assignment',
        'absence': 'Absence',
        'quiz': 'Quiz'
    }
    
    seen_assessments = set()
    for rel in assessment_relations:
        assessment = rel.assessment
        course_obj = assessment.course
        assessment_type_key = rel.assessment_type
        assessment_type_label = assessment_type_labels.get(assessment_type_key, assessment_type_key.title())
        
        # Create display name with index if needed
        if rel.assessment_index > 1:
            display_name = f"{assessment_type_label} {rel.assessment_index}"
        else:
            display_name = assessment_type_label
        
        # Avoid duplicates (same assessment linked to multiple LO instances)
        assessment_key = (assessment.id, assessment_type_key, rel.assessment_index)
        if assessment_key in seen_assessments:
            continue
        seen_assessments.add(assessment_key)
        
        assessments_data.append({
            'id': assessment.id,
            'course_name': course_obj.name,
            'assessment_type': display_name,
            'assessment_type_key': assessment_type_key,
            'contribution_percentage': rel.contribution_percentage,
            'relation_id': rel.id,
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
            'assessments_data': assessments_data,
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
    
    from .models import AssessmentLORelation
    # Get all ProgramOutcome instances with the same text (same LO in different courses)
    all_lo_instances = ProgramOutcome.objects.filter(
        text=outcome.text.strip()
    ).values_list('id', flat=True)
    
    # Get all assessment relations for all instances of this learning outcome
    assessment_relations = AssessmentLORelation.objects.filter(
        learning_outcome_id__in=all_lo_instances
    ).select_related('assessment', 'assessment__course').order_by('assessment__course__name', 'assessment__id')
    
    assessments_data = []
    assessment_type_labels = {
        'midterm': 'Midterm',
        'final': 'Final',
        'project': 'Project',
        'assignment': 'Assignment',
        'absence': 'Absence',
        'quiz': 'Quiz'
    }
    
    seen_assessments = set()
    for rel in assessment_relations:
        assessment = rel.assessment
        course_obj = assessment.course
        assessment_type_key = rel.assessment_type
        assessment_type_label = assessment_type_labels.get(assessment_type_key, assessment_type_key.title())
        
        # Create display name with index if needed
        if rel.assessment_index > 1:
            display_name = f"{assessment_type_label} {rel.assessment_index}"
        else:
            display_name = assessment_type_label
        
        # Avoid duplicates (same assessment linked to multiple LO instances)
        assessment_key = (assessment.id, assessment_type_key, rel.assessment_index)
        if assessment_key in seen_assessments:
            continue
        seen_assessments.add(assessment_key)
        
        assessments_data.append({
            'id': assessment.id,
            'course_name': course_obj.name,
            'assessment_type': display_name,
            'assessment_type_key': assessment_type_key,
            'contribution_percentage': rel.contribution_percentage,
            'relation_id': rel.id,
        })
    
    course_name_slug = generate_course_slug(outcome.course_name)
    
    return render(
        request,
        'faculty/learning_outcome_graph.html',
        {
            'outcome': outcome,
            'course': course,
            'program_outcomes': program_outcomes_data,
            'assessments_data': assessments_data,
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
            # Note: profile.courses will be synced automatically via signals when Course.instructor is set
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
def faculty_head_grades(request, course_name=None):
    from .models import Assessment
    
    profile = getattr(request.user, 'profile', None)
    
    # Get faculty head's department
    faculty_head_data = get_faculty_head_data(request.user.username)
    faculty_head_department = faculty_head_data.get('department')
    
    # If no course_name provided, show course selection page
    if not course_name:
        courses_list = []
        if profile:
            faculty_head_courses_from_data = faculty_head_data.get('courses', [])
            
            if faculty_head_department:
                for course_name_from_data in faculty_head_courses_from_data:
                    try:
                        course = Course.objects.get(name=course_name_from_data)
                        if course.department and course.department.strip():
                            if course.department.lower().strip() == faculty_head_department.lower().strip():
                                student_count = course.students.count()
                                courses_list.append({
                                    'name': course.name,
                                    'credits': course.credits if course.credits is not None else '-',
                                    'student_count': student_count
                                })
                    except Course.DoesNotExist:
                        continue
            else:
                for course_name_from_data in faculty_head_courses_from_data:
                    try:
                        course = Course.objects.get(name=course_name_from_data)
                        student_count = course.students.count()
                        courses_list.append({
                            'name': course.name,
                            'credits': course.credits if course.credits is not None else '-',
                            'student_count': student_count
                        })
                    except Course.DoesNotExist:
                        continue
        
        return render(request, 'faculty/faculty_head_grades.html', {
            'show_course_selection': True,
            'faculty_head_courses': courses_list
        })
    
    # Get course
    try:
        course = Course.objects.get(name=course_name)
    except Course.DoesNotExist:
        return redirect('faculty-head-grades')
    
    if profile and course not in profile.courses.all():
        return HttpResponseForbidden("You don't have access to this course")
    
    if faculty_head_department:
        if not course.department or course.department.lower() != faculty_head_department.lower():
            return HttpResponseForbidden("You don't have access to this course")
    
    # Assessment'ı al veya oluştur (default değerlerle)
    try:
        assessment = Assessment.objects.get(course=course)
        assessment.refresh_from_db()
    except Assessment.DoesNotExist:
        assessment = Assessment.objects.create(
            course=course,
            midterm=2,
            final=1,
            project=0,
            assignment=0,
            absence=0,
            quiz=0,
            assessment_count=3,
            midterm_percentage=60,
            final_percentage=40,
            project_percentage=0,
            assignment_percentage=0,
            absence_percentage=0,
            quiz_percentage=0
        )
    
    # Get students enrolled in this course
    students = course.students.all().order_by('first_name', 'last_name', 'username')
    students_list = [{'id': student.id, 'student_id': student.student_id, 'name': f"{student.first_name} {student.last_name}".strip() or student.username} for student in students]
    
    # Get uploaded file info for each assessment (from first student as sample)
    uploaded_files_info = {}
    sample_grade = Grade.objects.filter(course=course).first()
    if sample_grade and sample_grade.assessment_scores:
        assessment_types = ['midterm', 'final', 'project', 'assignment', 'absence', 'quiz']
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
    assessment_columns = []
    
    # Build assessment columns based on assessment counts
    assessment_type_labels = {
        'midterm': 'Midterm',
        'final': 'Final',
        'project': 'Project',
        'assignment': 'Assignment',
        'absence': 'Absence',
        'quiz': 'Quiz'
    }
    
    for assessment_type in ['midterm', 'final', 'project', 'assignment', 'absence', 'quiz']:
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
                    student_data['grades'][col['key']] = None
            
            # Add overall_score and letter_grade to student data
            grade_obj.calculate_overall_score()
            grade_obj.save(update_fields=['overall_score', 'letter_grade'])
            student_data['overall_score'] = grade_obj.overall_score
            student_data['letter_grade'] = grade_obj.letter_grade
        else:
            student_data['overall_score'] = None
            student_data['letter_grade'] = None
        
        grades_data.append(student_data)
    
    # Get last changes timestamp (from any grade in this course)
    last_changes_at = None
    any_grade = Grade.objects.filter(course=course).exclude(last_changes_at__isnull=True).order_by('-last_changes_at').first()
    if any_grade and any_grade.last_changes_at:
        last_changes_at = any_grade.last_changes_at.isoformat()
    
    return render(request, 'faculty/faculty_head_grades.html', {
        'course': course,
        'assessment': assessment,
        'students': students,  # Pass students queryset directly
        'uploaded_files_info': json.dumps(uploaded_files_info),
        'grades_data': json.dumps(grades_data),
        'assessment_columns': json.dumps(assessment_columns),
        'last_changes_at': last_changes_at,
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
    
    if faculty_head_department and course.department != faculty_head_department:
        return JsonResponse({'error': 'Access denied'}, status=403)
    
    # Course'daki tüm grade'lerden uploaded file bilgisini temizle
    Grade.objects.filter(course=course).update(
        uploaded_file_name='',
        uploaded_at=None
    )
    
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
def get_existing_learning_outcomes(request):
    from django.http import JsonResponse
    import traceback
    
    try:
        from .models import ProgramOutcome, Course
        
        instructor_user = request.instructor_user
        instructor_data = get_instructor_data(instructor_user.username)
        instructor_department = instructor_data.get('department', '')
        
        if not instructor_department:
            return JsonResponse({
                'learning_outcomes': [],
                'error': 'Instructor department not found.'
            })
        
        department_instructors = User.objects.filter(
            profile__role='instructor',
            profile__department=instructor_department
        ).select_related('profile')
        
        instructor_courses = Course.objects.filter(
            instructor__in=department_instructors
        ).values_list('name', flat=True).distinct()
        
        department_courses = Course.objects.filter(
            department=instructor_department
        ).values_list('name', flat=True).distinct()
        
        all_course_names = list(set(list(instructor_courses) + list(department_courses)))
        
        if not all_course_names:
            return JsonResponse({
                'learning_outcomes': [],
                'error': f'No courses found for {instructor_department} department.'
            })
        
        outcomes_qs = ProgramOutcome.objects.filter(
            course_name__in=all_course_names
        ).exclude(course_name='').select_related('created_by').prefetch_related('related_program_outcomes').order_by('-created_at', 'course_name')
        
        from .models import LearningOutcomeProgramOutcome
        learning_outcomes = []
        for outcome in outcomes_qs:
            # Get linked program outcomes with percentages
            linked_program_outcomes = []
            related_pos = outcome.related_program_outcomes.all()
            for po in related_pos:
                try:
                    lo_po = LearningOutcomeProgramOutcome.objects.get(
                        learning_outcome=outcome,
                        program_outcome=po
                    )
                    percentage = lo_po.percentage
                except LearningOutcomeProgramOutcome.DoesNotExist:
                    percentage = 0
                
                linked_program_outcomes.append({
                    'id': po.id,
                    'text': po.text,
                    'percentage': percentage
                })
            
            learning_outcomes.append({
                'id': outcome.id,
                'text': outcome.text,
                'course_name': outcome.course_name,
                'created_by': outcome.created_by.get_full_name() or outcome.created_by.username,
                'created_at': outcome.created_at.strftime('%Y-%m-%d %H:%M'),
                'linked_program_outcomes': linked_program_outcomes
            })
        
        return JsonResponse({'learning_outcomes': learning_outcomes})
    except Exception as e:
        import traceback
        error_trace = traceback.format_exc()
        return JsonResponse({
            'learning_outcomes': [],
            'error': f'Error loading learning outcomes: {str(e)}'
        }, status=500)

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
                    # Use case-insensitive search for course_name
                    outcomes_qs = ProgramOutcome.objects.filter(
                        course_name__iexact=course_name
                    ).select_related('created_by').prefetch_related('related_program_outcomes').order_by('-created_at')
                    
                    course = Course.objects.filter(name__iexact=course_name, instructor=instructor_user).first()
                    if not course:
                        # Try from profile or instructor_courses
                        profile = getattr(instructor_user, 'profile', None)
                        if profile:
                            course = profile.courses.filter(name__iexact=course_name).first()
                        if not course:
                            course = instructor_user.instructor_courses.filter(name__iexact=course_name).first()
                    course_id = course.id if course else None
                    
                    # Use helper function to build outcomes data
                    outcomes_data = build_learning_outcomes_data(outcomes_qs)
                    
                    display_course_name = course.name if course else course_name.title()
                    page_title = f"{display_course_name} - Learning Outcomes"
                    
                    return render(
                        request,
                        'instructor/course_learning_outcomes.html',
                        {
                            'course_name': course_name,
                            'display_course_name': display_course_name,
                            'page_title': page_title,
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
    
    # CRITICAL: Verify instructor owns this course
    course = Course.objects.filter(name__iexact=course_name, instructor=instructor_user).first()
    if not course:
        profile = getattr(instructor_user, 'profile', None)
        if profile:
            course = profile.courses.filter(name__iexact=course_name).first()
        if not course:
            course = instructor_user.instructor_courses.filter(name__iexact=course_name).first()
    
    # CRITICAL: If course not found or instructor doesn't own it, deny access
    if not course:
        instructor_course_names = get_instructor_course_names(instructor_user)
        course_name_lower = course_name.lower()
        if not any(cn.lower() == course_name_lower for cn in instructor_course_names):
            return HttpResponseForbidden("You don't have access to this course.")
        actual_course_name = next((cn for cn in instructor_course_names if cn.lower() == course_name_lower), course_name)
        course = Course.objects.filter(name__iexact=actual_course_name).first()
        if not course:
            return HttpResponseForbidden("You don't have access to this course.")
        course_name = course.name
    
    outcomes_qs = ProgramOutcome.objects.filter(
        course_name__iexact=course_name
    ).select_related('created_by').prefetch_related('related_program_outcomes').order_by('-created_at')
    
    course_id = course.id if course else None
    
    # Use helper function to build outcomes data
    outcomes_data = build_learning_outcomes_data(outcomes_qs)
    
    display_course_name = course.name if course else course_name.title()
    page_title = f"{display_course_name} - Learning Outcome"
    
    return render(
        request,
        'instructor/course_learning_outcomes.html',
        {
            'course_name': course_name,
            'display_course_name': display_course_name,
            'page_title': page_title,
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
    
    from .models import AssessmentLORelation
    # Get all ProgramOutcome instances with the same text (same LO in different courses)
    all_lo_instances = ProgramOutcome.objects.filter(
        text=outcome.text.strip()
    ).values_list('id', flat=True)
    
    # Get all assessment relations for all instances of this learning outcome
    assessment_relations = AssessmentLORelation.objects.filter(
        learning_outcome_id__in=all_lo_instances
    ).select_related('assessment', 'assessment__course').order_by('assessment__course__name', 'assessment__id')
    
    assessments_data = []
    assessment_type_labels = {
        'midterm': 'Midterm',
        'final': 'Final',
        'project': 'Project',
        'assignment': 'Assignment',
        'absence': 'Absence',
        'quiz': 'Quiz'
    }
    
    seen_assessments = set()
    for rel in assessment_relations:
        assessment = rel.assessment
        course_obj = assessment.course
        assessment_type_key = rel.assessment_type
        assessment_type_label = assessment_type_labels.get(assessment_type_key, assessment_type_key.title())
        
        # Create display name with index if needed
        if rel.assessment_index > 1:
            display_name = f"{assessment_type_label} {rel.assessment_index}"
        else:
            display_name = assessment_type_label
        
        # Avoid duplicates (same assessment linked to multiple LO instances)
        assessment_key = (assessment.id, assessment_type_key, rel.assessment_index)
        if assessment_key in seen_assessments:
            continue
        seen_assessments.add(assessment_key)
        
        assessments_data.append({
            'id': assessment.id,
            'course_name': course_obj.name,
            'assessment_type': display_name,
            'assessment_type_key': assessment_type_key,
            'contribution_percentage': rel.contribution_percentage,
            'relation_id': rel.id,
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
            'assessments_data': assessments_data,
            'course_name_slug': course_name_slug,
            'is_faculty_head': is_faculty_head,
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
    
    from .models import AssessmentLORelation
    # Get all ProgramOutcome instances with the same text (same LO in different courses)
    all_lo_instances = ProgramOutcome.objects.filter(
        text=outcome.text.strip()
    ).values_list('id', flat=True)
    
    # Get all assessment relations for all instances of this learning outcome
    assessment_relations = AssessmentLORelation.objects.filter(
        learning_outcome_id__in=all_lo_instances
    ).select_related('assessment', 'assessment__course').order_by('assessment__course__name', 'assessment__id')
    
    assessments_data = []
    assessment_type_labels = {
        'midterm': 'Midterm',
        'final': 'Final',
        'project': 'Project',
        'assignment': 'Assignment',
        'absence': 'Absence',
        'quiz': 'Quiz'
    }
    
    seen_assessments = set()
    for rel in assessment_relations:
        assessment = rel.assessment
        course_obj = assessment.course
        assessment_type_key = rel.assessment_type
        assessment_type_label = assessment_type_labels.get(assessment_type_key, assessment_type_key.title())
        
        # Create display name with index if needed
        if rel.assessment_index > 1:
            display_name = f"{assessment_type_label} {rel.assessment_index}"
        else:
            display_name = assessment_type_label
        
        # Avoid duplicates (same assessment linked to multiple LO instances)
        assessment_key = (assessment.id, assessment_type_key, rel.assessment_index)
        if assessment_key in seen_assessments:
            continue
        seen_assessments.add(assessment_key)
        
        assessments_data.append({
            'id': assessment.id,
            'course_name': course_obj.name,
            'assessment_type': display_name,
            'display_name': f"{course_obj.name} - {display_name}",
            'assessment_type_key': assessment_type_key,
            'contribution_percentage': rel.contribution_percentage,
            'relation_id': rel.id,
        })
    
    course_name_slug = generate_course_slug(outcome.course_name)
    
    return render(
        request,
        'instructor/learning_outcome_graph.html',
        {
            'outcome': outcome,
            'course': course,
            'assessments_data': assessments_data,
            'program_outcomes': program_outcomes_data,
            'course_name_slug': course_name_slug,
            'is_faculty_head': is_faculty_head,
        }
    )


@instructor_required
def get_available_assessments(request, outcome_id):
    from django.http import JsonResponse
    from django.db import transaction
    import traceback
    
    try:
        instructor_user = request.instructor_user
        
        source_outcome = get_object_or_404(ProgramOutcome, id=outcome_id)
        
        target_course_name = request.POST.get('course_name', '').strip()
        if not target_course_name:
            return JsonResponse({
                'success': False,
                'error': 'Course name is required.'
            }, status=400)
        
        # Verify instructor has access to target course
        # Check in multiple ways: Course model, instructor_courses, profile.courses
        from .models import Course
        
        # Try to find the course (case-insensitive)
        course = Course.objects.filter(name__iexact=target_course_name).first()
        
        if not course:
            return JsonResponse({
                'success': False,
                'error': f'Course "{target_course_name}" not found.'
            }, status=404)
        
        has_access = False
        
        if course.instructor == instructor_user:
            has_access = True
        
        if not has_access:
            profile = getattr(instructor_user, 'profile', None)
            if profile and profile.courses.filter(id=course.id).exists():
                has_access = True
        
        if not has_access:
            if instructor_user.instructor_courses.filter(id=course.id).exists():
                has_access = True
        
        if not has_access:
            instructor_course_names = get_instructor_course_names(instructor_user)
            instructor_course_names_lower = [cn.lower() for cn in instructor_course_names]
            if course.name.lower() in instructor_course_names_lower:
                has_access = True
        
        if not has_access:
            course_name_lower = course.name.lower()
            if instructor_user.instructor_courses.filter(name__iexact=course_name_lower).exists():
                has_access = True
            if not has_access:
                profile = getattr(instructor_user, 'profile', None)
                if profile and profile.courses.filter(name__iexact=course_name_lower).exists():
                    has_access = True
        
        if not has_access:
            print("=" * 80)
            print("ACCESS DENIED - Debug Information:")
            print(f"Hata: Kullanıcı={instructor_user.id} ({instructor_user.username})")
            print(f"Ders_Hocası={course.instructor.id if course.instructor else 'None'} ({course.instructor.username if course.instructor else 'None'})")
            print(f"Gelen_Course_Name={target_course_name}")
            print(f"Database_Course_Name={course.name}")
            print(f"Course_ID={course.id}")
            print(f"Course.instructor == instructor_user: {course.instructor == instructor_user}")
            
            profile = getattr(instructor_user, 'profile', None)
            if profile:
                profile_course_ids = list(profile.courses.values_list('id', flat=True))
                print(f"Profile.courses IDs: {profile_course_ids}")
                print(f"Course ID in profile.courses: {course.id in profile_course_ids}")
            else:
                print("Profile: None")
            
            instructor_course_ids = list(instructor_user.instructor_courses.values_list('id', flat=True))
            print(f"Instructor.instructor_courses IDs: {instructor_course_ids}")
            print(f"Course ID in instructor_courses: {course.id in instructor_course_ids}")
            
            instructor_course_names = get_instructor_course_names(instructor_user)
            print(f"Instructor course names (from JSON/DB): {instructor_course_names}")
            print(f"Course name in list (case-insensitive): {course.name.lower() in [cn.lower() for cn in instructor_course_names]}")
            print("=" * 80)
            
            return JsonResponse({
                'success': False,
                'error': f'You do not have access to course "{course.name}". Please contact administrator.'
            }, status=403)
        
        target_course_name = course.name
        
        from .models import ProgramOutcome, LearningOutcomeProgramOutcome
        
        with transaction.atomic():
            new_outcome = ProgramOutcome.objects.create(
                text=source_outcome.text,
                course_name=target_course_name,
                created_by=instructor_user,
                faculty=source_outcome.faculty  
            )
            
            source_po_relations = LearningOutcomeProgramOutcome.objects.filter(
                learning_outcome=source_outcome
            )
            
            for source_rel in source_po_relations:
                LearningOutcomeProgramOutcome.objects.create(
                    learning_outcome=new_outcome,
                    program_outcome=source_rel.program_outcome,
                    percentage=source_rel.percentage
                )
        
        return JsonResponse({
            'success': True,
            'message': 'Learning outcome cloned successfully.',
            'outcome_id': new_outcome.id
        })
    except Exception as e:
        import traceback
        error_trace = traceback.format_exc()
        print(f"Error in clone_learning_outcome: {str(e)}")
        print(f"Traceback: {error_trace}")
        return JsonResponse({
            'success': False,
            'error': f'Error cloning learning outcome: {str(e)}'
        }, status=500)


@instructor_required
def get_available_assessments(request, outcome_id):
    from django.http import JsonResponse
    instructor_user = request.instructor_user
    outcome = get_object_or_404(ProgramOutcome, id=outcome_id, created_by=instructor_user)
    
    from .models import Assessment, AssessmentLORelation, Course
    
    instructor_courses = Course.objects.filter(instructor=instructor_user)
    profile = getattr(instructor_user, 'profile', None)
    if profile:
        profile_courses = profile.courses.all()
        instructor_courses = instructor_courses.union(profile_courses)
    
    instructor_course_ids = instructor_courses.values_list('id', flat=True)
    assessments = Assessment.objects.filter(course_id__in=instructor_course_ids).select_related('course')
    
    if not assessments.exists():
        return JsonResponse({'assessments': [], 'error': 'No assessments found for your courses'})
    
    assessments_list = []
    assessment_types = ['midterm', 'final', 'project', 'assignment', 'absence', 'quiz']
    assessment_type_labels = {
        'midterm': 'Midterm',
        'final': 'Final',
        'project': 'Project',
        'assignment': 'Assignment',
        'absence': 'Absence',
        'quiz': 'Quiz'
    }
    
    # Get already linked assessment relations for this learning outcome
    linked_relations = AssessmentLORelation.objects.filter(
        learning_outcome=outcome
    ).select_related('assessment')
    
    # Create a set of (assessment_id, assessment_type, assessment_index) tuples for quick lookup
    linked_set = set()
    for rel in linked_relations:
        linked_set.add((rel.assessment.id, rel.assessment_type, rel.assessment_index))
    
    # Process each assessment
    for assessment in assessments:
        course = assessment.course
        for atype in assessment_types:
            count = getattr(assessment, atype, 0)
            if count > 0:
                label = assessment_type_labels[atype]
                # If count > 1, create multiple entries with numbered display names
                if count > 1:
                    for i in range(1, count + 1):
                        # Only add if this (assessment, type, index) is not already linked
                        if (assessment.id, atype, i) not in linked_set:
                            assessments_list.append({
                                'id': assessment.id,
                                'course_name': course.name,
                                'assessment_type': atype,  
                                'assessment_type_label': label,
                                'display_name': f'{course.name} - {label} {i}',
                                'assessment_index': i
                            })
                else:
                    # Single assessment - index is always 1
                    if (assessment.id, atype, 1) not in linked_set:
                        assessments_list.append({
                            'id': assessment.id,
                            'course_name': course.name,
                            'assessment_type': atype,  
                            'assessment_type_label': label,
                            'display_name': f'{course.name} - {label}',
                            'assessment_index': 1
                        })
    
    return JsonResponse({'assessments': assessments_list})


@instructor_required
def link_assessment_to_lo(request, outcome_id):
    """Link an assessment to a learning outcome with contribution percentage"""
    from django.http import JsonResponse
    instructor_user = request.instructor_user
    outcome = get_object_or_404(ProgramOutcome, id=outcome_id, created_by=instructor_user)
    
    if request.method == 'POST':
        assessment_id = request.POST.get('assessment_id', '').strip()
        assessment_type = request.POST.get('assessment_type', '').strip()
        percentage_value = request.POST.get('percentage', '').strip()
        assessment_index_str = request.POST.get('assessment_index', '1').strip()
        
        if not assessment_id:
            return JsonResponse({'status': 'error', 'message': 'Assessment ID is required.'}, status=400)
        
        if not assessment_type:
            return JsonResponse({'status': 'error', 'message': 'Assessment type is required.'}, status=400)
        
        if not percentage_value:
            return JsonResponse({'status': 'error', 'message': 'Contribution percentage is required.'}, status=400)
        
        valid_types = ['midterm', 'final', 'project', 'assignment', 'absence', 'quiz']
        if assessment_type not in valid_types:
            return JsonResponse({'status': 'error', 'message': 'Invalid assessment type.'}, status=400)
        
        try:
            percentage = int(percentage_value)
            if percentage < 0 or percentage > 100:
                return JsonResponse({'status': 'error', 'message': 'Percentage must be between 0 and 100.'}, status=400)
        except (ValueError, TypeError):
            return JsonResponse({'status': 'error', 'message': 'Invalid percentage value.'}, status=400)
        
        try:
            assessment_index = int(assessment_index_str)
            if assessment_index < 1:
                return JsonResponse({'status': 'error', 'message': 'Assessment index must be at least 1.'}, status=400)
        except (ValueError, TypeError):
            assessment_index = 1  # Default to 1 if not provided or invalid
        
        from .models import Assessment, AssessmentLORelation
        from django.db import transaction
        assessment = get_object_or_404(Assessment, id=assessment_id)
        
        with transaction.atomic():
            # Link assessment to learning outcome
            relation, created = AssessmentLORelation.objects.get_or_create(
                assessment=assessment,
                learning_outcome=outcome,
                assessment_type=assessment_type,
                assessment_index=assessment_index,
                defaults={'contribution_percentage': percentage}
            )
            
            if not created:
                relation.contribution_percentage = percentage
                relation.save()
            
            # If assessment's course is different from LO's course, add LO to assessment's course
            if assessment.course.name != outcome.course_name:
                # Check if LO with same text already exists in assessment's course
                existing_lo = ProgramOutcome.objects.filter(
                    text=outcome.text,
                    course_name=assessment.course.name
                ).first()
                
                if not existing_lo:
                    # Create new LO in assessment's course
                    new_lo = ProgramOutcome.objects.create(
                        text=outcome.text,
                        course_name=assessment.course.name,
                        created_by=outcome.created_by,
                        faculty=outcome.faculty
                    )
                    
                    # Copy linked program outcomes to new LO
                    from .models import LearningOutcomeProgramOutcome
                    for lo_po in LearningOutcomeProgramOutcome.objects.filter(learning_outcome=outcome):
                        LearningOutcomeProgramOutcome.objects.get_or_create(
                            learning_outcome=new_lo,
                            program_outcome=lo_po.program_outcome,
                            defaults={'percentage': lo_po.percentage}
                        )
        
        return JsonResponse({
            'status': 'success',
            'message': 'Assessment linked successfully.',
            'relation_id': relation.id,
            'course_name': assessment.course.name,
            'assessment_type': assessment_type,
            'assessment_index': assessment_index,
            'percentage': percentage
        })
    
    return JsonResponse({'status': 'error', 'message': 'Invalid request method.'}, status=405)


@instructor_required
def update_assessment_lo_percentage(request, outcome_id, relation_id):
    """Update contribution percentage for an assessment-LO relation"""
    from django.http import JsonResponse
    instructor_user = request.instructor_user
    outcome = get_object_or_404(ProgramOutcome, id=outcome_id, created_by=instructor_user)
    
    if request.method == 'POST':
        percentage_value = request.POST.get('percentage', '').strip()
        
        if not percentage_value:
            return JsonResponse({'status': 'error', 'message': 'Contribution percentage is required.'}, status=400)
        
        try:
            percentage = int(percentage_value)
            if percentage < 0 or percentage > 100:
                return JsonResponse({'status': 'error', 'message': 'Percentage must be between 0 and 100.'}, status=400)
        except (ValueError, TypeError):
            return JsonResponse({'status': 'error', 'message': 'Invalid percentage value.'}, status=400)
        
        from .models import AssessmentLORelation
        relation = get_object_or_404(AssessmentLORelation, id=relation_id, learning_outcome=outcome)
        
        relation.contribution_percentage = percentage
        relation.save()
        
        return JsonResponse({'status': 'success', 'message': 'Percentage updated successfully.', 'percentage': percentage})
    
    return JsonResponse({'status': 'error', 'message': 'Invalid request method.'}, status=405)


@instructor_required
def unlink_assessment_from_lo(request, outcome_id, relation_id):
    """Unlink an assessment from a learning outcome"""
    from django.http import JsonResponse
    instructor_user = request.instructor_user
    outcome = get_object_or_404(ProgramOutcome, id=outcome_id, created_by=instructor_user)
    
    if request.method == 'POST':
        from .models import AssessmentLORelation
        relation = get_object_or_404(AssessmentLORelation, id=relation_id, learning_outcome=outcome)
        relation.delete()
        
        return JsonResponse({'status': 'success', 'message': 'Assessment unlinked successfully.'})
    
    return JsonResponse({'status': 'error', 'message': 'Invalid request method.'}, status=405)


@faculty_head_required
def faculty_head_get_available_assessments(request, outcome_id):
    from django.http import JsonResponse
    profile = getattr(request.user, 'profile', None)
    outcome = get_object_or_404(ProgramOutcome, id=outcome_id, course_name__isnull=False)
    
    from .models import Assessment, AssessmentLORelation, Course
    
    # Get faculty head's department
    faculty_head_data = get_faculty_head_data(request.user.username)
    faculty_head_department = faculty_head_data.get('department')
    
    # Get all courses for this faculty head (by department or by profile)
    faculty_head_courses = Course.objects.none()
    if faculty_head_department:
        faculty_head_courses = Course.objects.filter(department=faculty_head_department)
    if profile:
        profile_courses = profile.courses.all()
        if faculty_head_courses.exists():
            faculty_head_courses = faculty_head_courses.union(profile_courses)
        else:
            faculty_head_courses = profile_courses
    
    # Also include courses where faculty head is the instructor
    instructor_courses = Course.objects.filter(instructor=request.user)
    if faculty_head_courses.exists():
        faculty_head_courses = faculty_head_courses.union(instructor_courses)
    else:
        faculty_head_courses = instructor_courses
    
    if not faculty_head_courses.exists():
        return JsonResponse({'assessments': [], 'error': 'No courses found'})
    
    # Get all assessments for faculty head's courses
    faculty_head_course_ids = faculty_head_courses.values_list('id', flat=True)
    assessments = Assessment.objects.filter(course_id__in=faculty_head_course_ids).select_related('course')
    
    if not assessments.exists():
        return JsonResponse({'assessments': [], 'error': 'No assessments found for your courses'})
    
    assessments_list = []
    assessment_types = ['midterm', 'final', 'project', 'assignment', 'absence', 'quiz']
    assessment_type_labels = {
        'midterm': 'Midterm',
        'final': 'Final',
        'project': 'Project',
        'assignment': 'Assignment',
        'absence': 'Absence',
        'quiz': 'Quiz'
    }
    
    # Get already linked assessment relations for this learning outcome
    linked_relations = AssessmentLORelation.objects.filter(
        learning_outcome=outcome
    ).select_related('assessment')
    
    # Create a set of (assessment_id, assessment_type, assessment_index) tuples for quick lookup
    linked_set = set()
    for rel in linked_relations:
        linked_set.add((rel.assessment.id, rel.assessment_type, rel.assessment_index))
    
    # Process each assessment
    for assessment in assessments:
        course = assessment.course
        for atype in assessment_types:
            count = getattr(assessment, atype, 0)
            if count > 0:
                label = assessment_type_labels[atype]
                # If count > 1, create multiple entries with numbered display names
                if count > 1:
                    for i in range(1, count + 1):
                        # Only add if this (assessment, type, index) is not already linked
                        if (assessment.id, atype, i) not in linked_set:
                            assessments_list.append({
                                'id': assessment.id,
                                'course_name': course.name,
                                'assessment_type': atype,  
                                'assessment_type_label': label,
                                'display_name': f'{course.name} - {label} {i}',
                                'assessment_index': i
                            })
                else:
                    # Single assessment - index is always 1
                    if (assessment.id, atype, 1) not in linked_set:
                        assessments_list.append({
                            'id': assessment.id,
                            'course_name': course.name,
                            'assessment_type': atype,  
                            'assessment_type_label': label,
                            'display_name': f'{course.name} - {label}',
                            'assessment_index': 1
                        })
    
    return JsonResponse({'assessments': assessments_list})


@faculty_head_required
def faculty_head_link_assessment_to_lo(request, outcome_id):
    """Link an assessment to a learning outcome with contribution percentage (for faculty head)"""
    from django.http import JsonResponse
    profile = getattr(request.user, 'profile', None)
    outcome = get_object_or_404(ProgramOutcome, id=outcome_id, course_name__isnull=False)
    
    if request.method == 'POST':
        assessment_id = request.POST.get('assessment_id', '').strip()
        assessment_type = request.POST.get('assessment_type', '').strip()
        percentage_value = request.POST.get('percentage', '').strip()
        assessment_index_str = request.POST.get('assessment_index', '1').strip()
        
        if not assessment_id:
            return JsonResponse({'status': 'error', 'message': 'Assessment ID is required.'}, status=400)
        
        if not assessment_type:
            return JsonResponse({'status': 'error', 'message': 'Assessment type is required.'}, status=400)
        
        if not percentage_value:
            return JsonResponse({'status': 'error', 'message': 'Contribution percentage is required.'}, status=400)
        
        valid_types = ['midterm', 'final', 'project', 'assignment', 'absence', 'quiz']
        if assessment_type not in valid_types:
            return JsonResponse({'status': 'error', 'message': 'Invalid assessment type.'}, status=400)
        
        try:
            percentage = int(percentage_value)
            if percentage < 0 or percentage > 100:
                return JsonResponse({'status': 'error', 'message': 'Percentage must be between 0 and 100.'}, status=400)
        except (ValueError, TypeError):
            return JsonResponse({'status': 'error', 'message': 'Invalid percentage value.'}, status=400)
        
        try:
            assessment_index = int(assessment_index_str)
            if assessment_index < 1:
                return JsonResponse({'status': 'error', 'message': 'Assessment index must be at least 1.'}, status=400)
        except (ValueError, TypeError):
            assessment_index = 1  # Default to 1 if not provided or invalid
        
        from .models import Assessment, AssessmentLORelation
        from django.db import transaction
        assessment = get_object_or_404(Assessment, id=assessment_id)
        
        with transaction.atomic():
            # Link assessment to learning outcome
            relation, created = AssessmentLORelation.objects.get_or_create(
                assessment=assessment,
                learning_outcome=outcome,
                assessment_type=assessment_type,
                assessment_index=assessment_index,
                defaults={'contribution_percentage': percentage}
            )
            
            if not created:
                relation.contribution_percentage = percentage
                relation.save()
            
            # If assessment's course is different from LO's course, add LO to assessment's course
            if assessment.course.name != outcome.course_name:
                # Check if LO with same text already exists in assessment's course
                existing_lo = ProgramOutcome.objects.filter(
                    text=outcome.text,
                    course_name=assessment.course.name
                ).first()
                
                if not existing_lo:
                    # Get faculty from profile if available
                    faculty = profile.faculty if profile else outcome.faculty
                    
                    # Create new LO in assessment's course
                    new_lo = ProgramOutcome.objects.create(
                        text=outcome.text,
                        course_name=assessment.course.name,
                        created_by=outcome.created_by,
                        faculty=faculty
                    )
                    
                    # Copy linked program outcomes to new LO
                    from .models import LearningOutcomeProgramOutcome
                    for lo_po in LearningOutcomeProgramOutcome.objects.filter(learning_outcome=outcome):
                        LearningOutcomeProgramOutcome.objects.get_or_create(
                            learning_outcome=new_lo,
                            program_outcome=lo_po.program_outcome,
                            defaults={'percentage': lo_po.percentage}
                        )
        
        return JsonResponse({
            'status': 'success',
            'message': 'Assessment linked successfully.',
            'relation_id': relation.id,
            'course_name': assessment.course.name,
            'assessment_type': assessment_type,
            'assessment_index': assessment_index,
            'percentage': percentage
        })
    
    return JsonResponse({'status': 'error', 'message': 'Invalid request method.'}, status=405)


@faculty_head_required
def faculty_head_update_assessment_lo_percentage(request, outcome_id, relation_id):
    from django.http import JsonResponse
    profile = getattr(request.user, 'profile', None)
    outcome = get_object_or_404(ProgramOutcome, id=outcome_id, course_name__isnull=False)
    
    if request.method == 'POST':
        percentage_value = request.POST.get('percentage', '').strip()
        
        if not percentage_value:
            return JsonResponse({'status': 'error', 'message': 'Contribution percentage is required.'}, status=400)
        
        try:
            percentage = int(percentage_value)
            if percentage < 0 or percentage > 100:
                return JsonResponse({'status': 'error', 'message': 'Percentage must be between 0 and 100.'}, status=400)
        except (ValueError, TypeError):
            return JsonResponse({'status': 'error', 'message': 'Invalid percentage value.'}, status=400)
        
        from .models import AssessmentLORelation
        relation = get_object_or_404(AssessmentLORelation, id=relation_id, learning_outcome=outcome)
        
        relation.contribution_percentage = percentage
        relation.save()
        
        return JsonResponse({'status': 'success', 'message': 'Percentage updated successfully.', 'percentage': percentage})
    
    return JsonResponse({'status': 'error', 'message': 'Invalid request method.'}, status=405)


@faculty_head_required
def faculty_head_unlink_assessment_from_lo(request, outcome_id, relation_id):
    """Unlink an assessment from a learning outcome (for faculty head)"""
    from django.http import JsonResponse
    profile = getattr(request.user, 'profile', None)
    outcome = get_object_or_404(ProgramOutcome, id=outcome_id, course_name__isnull=False)
    
    if request.method == 'POST':
        from .models import AssessmentLORelation
        relation = get_object_or_404(AssessmentLORelation, id=relation_id, learning_outcome=outcome)
        relation.delete()
        
        return JsonResponse({'status': 'success', 'message': 'Assessment unlinked successfully.'})
    
    return JsonResponse({'status': 'error', 'message': 'Invalid request method.'}, status=405)


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
        course_name_slug = generate_course_slug(course_name)
        redirect_url = reverse('course_learning_outcomes', args=[course_name_slug])
        redirect_url += f'?username={username}'
        return redirect(redirect_url)
    
    # Use helper function to get course names (prevents code duplication)
    course_names = get_instructor_course_names(instructor_user)
    
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


def student_advisor_info(request):
    if not request.user.is_authenticated:
        return redirect('student-login')
    
    try:
        student = Student.objects.get(user=request.user)
        advisor_info = None
        
        # Only Computer Engineering students have advisor (Ahmet Bulut)
        if student.department and student.department.lower() == 'computer engineering':
            # Get Ahmet Bulut's information
            try:
                advisor_user = User.objects.get(username='ahmet.bulut')
                advisor_profile = getattr(advisor_user, 'profile', None)
                
                # Get advisor's courses
                advisor_courses = Course.objects.filter(instructor=advisor_user).select_related('instructor')
                
                # Prepare schedule data - get all unique time slots from advisor's courses
                days = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday']
                # Get all unique time slots from courses
                all_time_slots = set()
                for course in advisor_courses:
                    if course.time:
                        all_time_slots.add(course.time)
                # Sort time slots and create list
                time_slots = sorted(list(all_time_slots))
                # If no time slots found, use default
                if not time_slots:
                    time_slots = ['08:00-09:30', '09:30-11:00', '11:00-12:30', '13:00-14:30', '14:30-16:00', '16:00-17:30']
                
                schedule_data = {}
                for course in advisor_courses:
                    if course.day and course.time:
                        if course.day not in schedule_data:
                            schedule_data[course.day] = {}
                        schedule_data[course.day][course.time] = {
                            'name': course.name,
                            'code': course.code,
                            'room': course.room or '',
                        }
                
                advisor_info = {
                    'name': f"{advisor_user.first_name} {advisor_user.last_name}".strip() or advisor_user.username,
                    'username': advisor_user.username,
                    'department': advisor_profile.department if advisor_profile else 'Computer Engineering',
                    'email': 'ahmetbulut@gmail.com',
                    'office': 'B block 2nd floor',
                    'courses': [{'name': course.name, 'code': course.code} for course in advisor_courses],
                    'courses_for_schedule': advisor_courses,  # For schedule table rendering
                    'days': days,
                    'time_slots': time_slots,
                }
            except User.DoesNotExist:
                advisor_info = None
    except Student.DoesNotExist:
        advisor_info = None
    
    return render(request, "student/advisor_info.html", {'advisor_info': advisor_info})


def student_courses(request):
    from .models import Assignment, AssignmentSubmission
    
    if not request.user.is_authenticated:
        return redirect('student-login')
    
    try:
        student = Student.objects.get(user=request.user)
        courses = student.courses.all().select_related('instructor').prefetch_related('assignments')
        
        # Get course schedule from JSON
        course_schedule_map = get_course_schedule_from_json()
        
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
            
            # Get schedule from JSON first, fallback to database
            schedule_info = course_schedule_map.get(course.name, {})
            
            courses_data.append({
                'id': course.id,
                'name': course.name,
                'code': course.code,
                'instructor': instructor_name,
                'department': course.department,
                'credits': course.credits,
                'assignments': assignments_list,
                'day': schedule_info.get('day') or course.day,
                'time': schedule_info.get('time') or course.time,
                'room': schedule_info.get('room') or course.room,
            })
    except Student.DoesNotExist:
        courses_data = []
        all_assignments = []
    
    # Prepare schedule data for template
    days = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday']
    time_slots = ['09:00-10:30', '11:00-12:30', '14:00-15:30', '16:00-17:30']
    
    return render(request, "student/courses.html", {
        'courses': courses_data,
        'all_assignments': all_assignments,
        'days': days,
        'time_slots': time_slots
    })

def student_assignments(request):
    from .models import Assignment, AssignmentSubmission
    
    if not request.user.is_authenticated:
        return redirect('student-login')
    
    try:
        student = Student.objects.get(user=request.user)
        courses = student.courses.all().select_related('instructor').prefetch_related('assignments')
        
        all_assignments = []
        
        for course in courses:
            # Get assignments for this course
            assignments = course.assignments.all().order_by('-created_at')
            for assignment in assignments:
                # Check if student has submitted this assignment
                submission = AssignmentSubmission.objects.filter(assignment=assignment, student=student).first()
                
                assignment_data = {
                    'id': assignment.id,
                    'course_name': course.name,
                    'course_code': course.code,
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
                    'created_at': assignment.created_at.strftime('%d/%m/%Y %H:%M'),
                }
                all_assignments.append(assignment_data)
        
        # Sort by created_at (most recent first)
        all_assignments.sort(key=lambda x: x['created_at'], reverse=True)
        
    except Student.DoesNotExist:
        all_assignments = []
    
    return render(request, "student/assignments.html", {
        'assignments': all_assignments
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
    
    from .models import Assessment
    
    try:
        student = Student.objects.get(user=request.user)
        courses = student.courses.all().order_by('name')
        grades_qs = Grade.objects.filter(student=student).select_related('course')
        
        courses_with_grades = []
        for course in courses:
            grade_obj = grades_qs.filter(course=course).first()
            
            # Get assessment configuration for this course
            try:
                assessment = Assessment.objects.get(course=course)
            except Assessment.DoesNotExist:
                assessment = None
            
            # Build assessment columns and grades
            assessment_columns = []
            
            if assessment:
                assessment_type_labels = {
                    'midterm': 'Midterm',
                    'final': 'Final',
                    'project': 'Project',
                    'assignment': 'Assignment',
                    'absence': 'Absence',
                    'quiz': 'Quiz'
                }
                
                for assessment_type in ['midterm', 'final', 'project', 'assignment', 'absence', 'quiz']:
                    count = getattr(assessment, assessment_type, 0)
                    label = assessment_type_labels[assessment_type]
                    
                    if count > 0:
                        # Multiple assessments (e.g., midterm_1, midterm_2)
                        if count > 1:
                            for i in range(1, count + 1):
                                key = f'{assessment_type}_{i}'
                                score = None
                                if grade_obj:
                                    score = grade_obj.get_individual_score(key)
                                assessment_columns.append({
                                    'key': key,
                                    'label': f'{label} {i}',
                                    'type': assessment_type,
                                    'score': score
                                })
                        else:
                            # Single assessment - show average
                            score = None
                            if grade_obj:
                                score = grade_obj.get_assessment_score(assessment_type)
                            assessment_columns.append({
                                'key': assessment_type,
                                'label': label,
                                'type': assessment_type,
                                'score': score
                            })
            
            # Get assessment percentages
            assessment_percentages = {}
            if assessment:
                assessment_type_labels = {
                    'midterm': 'Midterm',
                    'final': 'Final',
                    'project': 'Project',
                    'assignment': 'Assignment',
                    'absence': 'Absence',
                    'quiz': 'Quiz'
                }
                
                for assessment_type in ['midterm', 'final', 'project', 'assignment', 'absence', 'quiz']:
                    count = getattr(assessment, assessment_type, 0)
                    percentage = getattr(assessment, f'{assessment_type}_percentage', 0)
                    if count > 0 and percentage > 0:
                        label = assessment_type_labels[assessment_type]
                        assessment_percentages[assessment_type] = {
                            'label': label,
                            'count': count,
                            'percentage': percentage
                        }
            
            # Get instructor name
            instructor_name = ''
            if course.instructor:
                full_name = f"{course.instructor.first_name} {course.instructor.last_name}".strip()
                instructor_name = full_name if full_name else course.instructor.username
            
            course_data = {
                'course_name': course.name,
                'course_code': getattr(course, 'code', ''),
                'credits': course.credits or 0,
                'instructor_name': instructor_name,
                'assessment_columns': assessment_columns,
                'assessment_percentages': assessment_percentages,
                'overall_score': grade_obj.overall_score if grade_obj else None,
                'letter_grade': grade_obj.letter_grade if grade_obj else None,
            }
            
            courses_with_grades.append(course_data)
    except Student.DoesNotExist:
        courses_with_grades = []
    except Exception as e:
        # Log the error for debugging
        import logging
        logger = logging.getLogger(__name__)
        logger.error(f"Error in student_grades view: {str(e)}", exc_info=True)
        # Return empty list on error
        courses_with_grades = []
    
    import json
    # Convert assessment_percentages to JSON-serializable format
    courses_json = []
    for course_data in courses_with_grades:
        course_json = {
            'course_name': course_data['course_name'],
            'assessment_percentages': course_data['assessment_percentages']
        }
        courses_json.append(course_json)
    
    # Calculate GPA
    # Formula: (sum of (overall_score × credits) for all courses) / (sum of credits) / 25
    # GPA is only calculated if ALL courses have overall_score determined
    total_weighted_score = 0
    total_credits = 0
    all_courses_have_scores = True
    
    for course_data in courses_with_grades:
        overall_score = course_data.get('overall_score')
        credits = course_data.get('credits', 0)
        
        if overall_score is None:
            # If any course doesn't have overall_score, GPA cannot be calculated
            all_courses_have_scores = False
            break
        
        if credits > 0:
            total_weighted_score += overall_score * credits
            total_credits += credits
    
    gpa = None
    # Only calculate GPA if all courses have overall_score and total_credits > 0
    if all_courses_have_scores and total_credits > 0:
        average_score = total_weighted_score / total_credits
        gpa = average_score / 25.0
    
    return render(request, "student/grades.html", {
        'courses_with_grades': courses_with_grades,
        'courses_json': json.dumps(courses_json),
        'gpa': gpa
    })


def student_announcements(request):
    if not request.user.is_authenticated:
        return redirect('student-login')
    
    from django.db.models import Q
    from datetime import datetime
    
    try:
        student = Student.objects.get(user=request.user)
        # Get all courses the student is enrolled in
        student_courses = student.courses.all()
        student_courses_set = set(student.courses.values_list('name', flat=True))
    except Student.DoesNotExist:
        student_courses = []
        student_courses_set = set()
    
    # Get all announcements for the student
    announcements = Announcement.objects.filter(
        Q(receiver=request.user) | Q(receiver__isnull=True)
    ).select_related('sender', 'receiver').order_by('-created_at', '-is_pinned')
    
    # Get all assignments from courses the student is enrolled in
    assignments = Assignment.objects.filter(
        course__in=student_courses
    ).select_related('course', 'created_by').order_by('-created_at')
    
    # Get instructors and faculty heads maps for name formatting
    instructors_map = get_instructors_map()
    faculty_heads_map = get_faculty_heads_map()
    
    # Format announcements
    announcements_data = []
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
            if course_name_from_marker not in student_courses_set:
                continue  # Skip this announcement - student not enrolled
        
        sender_name = instructors_map.get(ann.sender.username) or faculty_heads_map.get(ann.sender.username) or ann.sender.get_full_name() or ann.sender.username
        
        # Check if read
        is_read = ann.read_by.filter(id=request.user.id).exists()
        
        announcements_data.append({
            'id': ann.id,
            'subject': display_subject,
            'message': ann.message,
            'sender': sender_name,
            'created_at': ann.created_at.strftime('%Y-%m-%d %H:%M'),
            'is_read': is_read,
            'is_pinned': ann.is_pinned,
            'is_assignment': False,
        })
    
    # Format assignments as announcements
    for assignment in assignments:
        creator_name = instructors_map.get(assignment.created_by.username) or faculty_heads_map.get(assignment.created_by.username) or assignment.created_by.get_full_name() or assignment.created_by.username
        
        # Create assignment message with details
        assignment_message = f"Course: {assignment.course.name}\n\n"
        assignment_message += f"Details: {assignment.details}\n\n"
        assignment_message += f"Deadline: {assignment.deadline.strftime('%d/%m/%Y %H:%M')}"
        if assignment.file:
            assignment_message += f"\n\nFile attached: {assignment.file.name.split('/')[-1]}"
        
        # Use a special ID format to distinguish assignments (negative or with prefix)
        # We'll use assignment.id + 1000000 to avoid conflicts with announcement IDs
        assignment_ann_id = f"assignment_{assignment.id}"
        
        announcements_data.append({
            'id': assignment_ann_id,
            'subject': f"New Assignment: {assignment.title}",
            'message': assignment_message,
            'sender': creator_name,
            'created_at': assignment.created_at.strftime('%Y-%m-%d %H:%M'),
            'is_read': False,  # Assignments are always unread initially (or we could check notifications)
            'is_pinned': False,
            'is_assignment': True,
            'assignment_id': assignment.id,
            'assignment_course': assignment.course.name,
            'assignment_deadline': assignment.deadline.strftime('%d/%m/%Y %H:%M'),
            'assignment_file_url': assignment.file.url if assignment.file else None,
        })
    
    # Sort: pinned messages first, then by created_at
    announcements_data.sort(key=lambda x: (not x['is_pinned'], x['created_at']), reverse=True)
    
    # Separate received messages (all announcements for students are received)
    received_messages = announcements_data.copy()
    
    # Count unread
    unread_count = sum(1 for msg in received_messages if not msg['is_read'])
    
    return render(request, "student/student_announcement.html", {
        'received_messages': received_messages,
        'all_announcements': announcements_data,
        'unread_count': unread_count,
    })

def debug_notifications(request):
    """Debug view to check notifications"""
    if not request.user.is_authenticated:
        return JsonResponse({'error': 'Not authenticated'}, status=401)
    
    from .models import Notification, Student
    
    try:
        student = Student.objects.get(user=request.user)
    except Student.DoesNotExist:
        student = None
    
    notifications = Notification.objects.filter(user=request.user)
    unread_notifications = notifications.filter(is_read=False)
    
    debug_info = {
        'user': request.user.username,
        'student_exists': student is not None,
        'student_username': student.username if student else None,
        'total_notifications': notifications.count(),
        'unread_count': unread_notifications.count(),
        'unread_notifications': [
            {
                'id': n.id,
                'title': n.title,
                'message': n.message,
                'is_read': n.is_read,
                'created_at': n.created_at.isoformat(),
            }
            for n in unread_notifications[:10]
        ]
    }
    
    return JsonResponse(debug_info, safe=False)

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

def student_my_progress(request):
    """Show student's progress across all courses with 3-column graph"""
    if not request.user.is_authenticated:
        return redirect('student-login')
    
    try:
        student = Student.objects.get(user=request.user)
        courses = student.courses.all().order_by('name')
        
        from .models import Assessment, AssessmentLORelation, Grade, ProgramOutcome, LearningOutcomeProgramOutcome
        from django.db.models import Q
        import json
        
        assessments_list = []
        learning_outcomes_list = []
        program_outcomes_list = []
        
        assessment_type_labels = {
            'midterm': 'Midterm',
            'final': 'Final',
            'project': 'Project',
            'assignment': 'Assignment',
            'absence': 'Absence',
            'quiz': 'Quiz'
        }
        
        all_assessment_relations = {}
        all_lo_scores = {}
        all_po_scores = {}
        
        for course in courses:
            try:
                grade = Grade.objects.get(student=student, course=course)
            except Grade.DoesNotExist:
                grade = None
            
            try:
                assessment = Assessment.objects.get(course=course)
            except Assessment.DoesNotExist:
                assessment = None
            
            if assessment and grade:
                assessment_types = ['midterm', 'final', 'project', 'assignment', 'absence', 'quiz']
                for assessment_type in assessment_types:
                    assessment_count = getattr(assessment, assessment_type, 0)
                    if assessment_count > 0:
                        for i in range(1, assessment_count + 1):
                            assessment_key = f"{assessment_type}_{i}"
                            score = grade.get_individual_score(assessment_key)
                            if score is not None:
                                display_name = f"{assessment_type_labels[assessment_type]} {i}" if assessment_count > 1 else assessment_type_labels[assessment_type]
                                
                                assessment_id = f"{course.id}_{assessment_type}_{i}"
                                assessments_list.append({
                                    'id': assessment_id,
                                    'course_name': course.name,
                                    'assessment_type': display_name,
                                    'assessment_type_key': assessment_type,
                                    'assessment_index': i,
                                    'score': round(score, 2),
                                    'course_id': course.id
                                })
                                
                                all_assessment_relations[assessment_id] = []
        
        course_names = [course.name for course in courses]
        if course_names:
            learning_outcomes_qs = ProgramOutcome.objects.filter(
                course_name__in=course_names
            ).exclude(course_name='').select_related('created_by').prefetch_related('related_program_outcomes').order_by('text', 'course_name')
            
            lo_groups = {}
            for lo in learning_outcomes_qs:
                lo_text = lo.text.strip()
                if lo_text not in lo_groups:
                    lo_groups[lo_text] = {
                        'ids': [],
                        'courses': [],
                        'linked_pos_dict': {},
                        'linked_assessments': []
                    }
                
                lo_groups[lo_text]['ids'].append(lo.id)
                if lo.course_name and lo.course_name not in lo_groups[lo_text]['courses']:
                    lo_groups[lo_text]['courses'].append(lo.course_name)
                
                related_pos = lo.related_program_outcomes.all()
                for po in related_pos:
                    try:
                        lo_po = LearningOutcomeProgramOutcome.objects.get(learning_outcome=lo, program_outcome=po)
                        percentage = lo_po.percentage
                    except LearningOutcomeProgramOutcome.DoesNotExist:
                        percentage = 0
                    
                    if po.id not in lo_groups[lo_text]['linked_pos_dict']:
                        lo_groups[lo_text]['linked_pos_dict'][po.id] = {
                            'id': po.id,
                            'text': po.text,
                            'percentage': percentage
                        }
                    else:
                        lo_groups[lo_text]['linked_pos_dict'][po.id]['percentage'] = max(
                            lo_groups[lo_text]['linked_pos_dict'][po.id]['percentage'],
                            percentage
                        )
                
                assessment_relations = AssessmentLORelation.objects.filter(
                    learning_outcome=lo
                ).select_related('assessment', 'assessment__course').order_by('assessment__course__name', 'assessment__id')
                
                for rel in assessment_relations:
                    assessment = rel.assessment
                    course_obj = assessment.course
                    assessment_type_key = rel.assessment_type
                    assessment_type_label = assessment_type_labels.get(assessment_type_key, assessment_type_key.title())
                    
                    if rel.assessment_index > 1:
                        display_name = f"{assessment_type_label} {rel.assessment_index}"
                    else:
                        display_name = assessment_type_label
                    
                    assessment_id = f"{course_obj.id}_{assessment_type_key}_{rel.assessment_index}"
                    lo_groups[lo_text]['linked_assessments'].append({
                        'id': assessment_id,
                        'course_name': course_obj.name,
                        'assessment_type': display_name,
                        'assessment_type_key': assessment_type_key,
                        'assessment_index': rel.assessment_index,
                        'contribution_percentage': rel.contribution_percentage,
                        'relation_id': rel.id
                    })
                    
                    if assessment_id in all_assessment_relations:
                        all_assessment_relations[assessment_id].append({
                            'lo_id': lo_groups[lo_text]['ids'][0],
                            'lo_text': lo_text,
                            'contribution_percentage': rel.contribution_percentage
                        })
            
            for lo_text, group_data in lo_groups.items():
                sorted_courses = sorted(group_data['courses'])
                course_display = " - ".join(sorted_courses)
                
                linked_pos_list = list(group_data['linked_pos_dict'].values())
                
                lo_score = None
                total_weighted_score = 0.0
                total_contribution = 0
                
                for assessment_link in group_data['linked_assessments']:
                    assessment_id = assessment_link['id']
                    for assessment_data in assessments_list:
                        if assessment_data['id'] == assessment_id:
                            contribution = assessment_link['contribution_percentage']
                            if contribution > 0:
                                total_weighted_score += assessment_data['score'] * contribution
                                total_contribution += contribution
                            break
                
                if total_contribution > 0:
                    lo_score = round(total_weighted_score / total_contribution, 2)
                
                all_lo_scores[group_data['ids'][0]] = lo_score
                
                learning_outcomes_list.append({
                    'id': group_data['ids'][0],
                    'ids': group_data['ids'],
                    'text': lo_text,
                    'course': course_display,
                    'courses': sorted_courses,
                    'linked_pos': linked_pos_list,
                    'linked_assessments': group_data['linked_assessments'],
                    'score': lo_score
                })
            
            faculty = None
            from .models import Faculty
            
            if student.department:
                try:
                    faculty = Faculty.objects.get(name=student.department)
                except Faculty.DoesNotExist:
                    pass
            
            if not faculty and courses.exists():
                course_departments = courses.values_list('department', flat=True).distinct()
                for dept in course_departments:
                    if dept:
                        try:
                            faculty = Faculty.objects.get(name=dept)
                            break
                        except Faculty.DoesNotExist:
                            continue
            
            if faculty:
                program_outcomes_qs = ProgramOutcome.objects.filter(
                    faculty=faculty,
                    course_name=''
                ).select_related('created_by').order_by('created_at')
                
                for po in program_outcomes_qs:
                    po_score = None
                    total_weighted_score = 0.0
                    total_percentage = 0
                    
                    for lo_data in learning_outcomes_list:
                        for linked_po in lo_data['linked_pos']:
                            if linked_po['id'] == po.id:
                                lo_score = all_lo_scores.get(lo_data['id'])
                                if lo_score is not None:
                                    percentage = linked_po['percentage']
                                    if percentage > 0:
                                        total_weighted_score += lo_score * percentage
                                        total_percentage += percentage
                                break
                    
                    if total_percentage > 0:
                        po_score = round(total_weighted_score / total_percentage, 2)
                    
                    all_po_scores[po.id] = po_score
                    
                    program_outcomes_list.append({
                        'id': po.id,
                        'text': po.text,
                        'score': po_score
                    })
            else:
                program_outcomes_qs = ProgramOutcome.objects.filter(
                    course_name=''
                ).select_related('created_by').order_by('created_at')
                
                for po in program_outcomes_qs:
                    po_score = None
                    total_weighted_score = 0.0
                    total_percentage = 0
                    
                    for lo_data in learning_outcomes_list:
                        for linked_po in lo_data['linked_pos']:
                            if linked_po['id'] == po.id:
                                lo_score = all_lo_scores.get(lo_data['id'])
                                if lo_score is not None:
                                    percentage = linked_po['percentage']
                                    if percentage > 0:
                                        total_weighted_score += lo_score * percentage
                                        total_percentage += percentage
                                break
                    
                    if total_percentage > 0:
                        po_score = round(total_weighted_score / total_percentage, 2)
                    
                    all_po_scores[po.id] = po_score
                    
                    program_outcomes_list.append({
                        'id': po.id,
                        'text': po.text,
                        'score': po_score
                    })
        
        learning_outcomes_json = json.dumps(learning_outcomes_list)
        
        return render(request, 'student/my_progress.html', {
            'assessments': assessments_list,
            'learning_outcomes': learning_outcomes_list,
            'learning_outcomes_json': learning_outcomes_json,
            'program_outcomes': program_outcomes_list,
        })
        
    except Student.DoesNotExist:
        return redirect('student-login')

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
                                        announcement = Announcement.objects.create(
                                            sender=faculty_head_user,
                                            receiver=student_user,
                                            subject=marked_subject,
                                            message=message,
                                            sender_role='faculty_head',
                                            receiver_role='student'
                                        )
                                        # Create notification for the student
                                        from .models import Notification
                                        Notification.objects.create(
                                            user=student_user,
                                            notification_type='announcement_created',
                                            title=clean_announcement_subject(marked_subject),
                                            message=message[:100] + ('...' if len(message) > 100 else ''),
                                            assignment=None,
                                            announcement=announcement
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
                            
                            announcement = Announcement.objects.create(
                                sender=faculty_head_user,
                                receiver=receiver,
                                subject=subject,
                                message=message,
                                sender_role='faculty_head',
                                receiver_role=receiver_role
                            )
                            # Create notification for the receiver (if student)
                            if receiver_role == 'student' or (profile and profile.role == 'student'):
                                from .models import Notification
                                Notification.objects.create(
                                    user=receiver,
                                    notification_type='announcement_created',
                                    title=subject,
                                    message=message[:100] + ('...' if len(message) > 100 else ''),
                                    assignment=None,
                                    announcement=announcement
                                )
                        except User.DoesNotExist:
                            pass
            
            return redirect('faculty-head-announcements')
    
    # Get department course names for filtering announcements
    department_course_names = set()
    if faculty_head_department:
        department_courses = Course.objects.filter(department__iexact=faculty_head_department).exclude(department='')
        department_course_names = set(department_courses.values_list('name', flat=True))
    
    # ORM ile announcements'ları çek - select_related ile JOIN optimizasyonu
    all_announcements_raw = Announcement.objects.filter(
        Q(sender=faculty_head_user) | Q(receiver=faculty_head_user)
    ).select_related('sender', 'receiver').order_by('-created_at')
    
    # Filter announcements by department courses
    all_announcements = []
    for ann in all_announcements_raw:
        # If faculty head sent it, always show it
        if ann.sender == faculty_head_user:
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
        # If received, only show if related to department courses
        elif ann.receiver == faculty_head_user:
            # Check if announcement is related to a course in faculty head's department
            if ann.subject and ann.subject.startswith('__COURSE:'):
                # Extract course name from subject
                end_marker = ann.subject.find('__', 9)
                if end_marker != -1:
                    course_name = ann.subject[9:end_marker]
                    # Only include if course is in faculty head's department
                    if course_name in department_course_names:
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
            else:
                # Announcements without course marker - only show if receiver is faculty head
                # (general announcements sent directly to faculty head)
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


def mark_notification_read(request, notification_id):
    """Mark notification as read and redirect based on notification type"""
    if not request.user.is_authenticated:
        return redirect('student-login')
    
    try:
        notification = Notification.objects.get(id=notification_id, user=request.user)
        notification.is_read = True
        notification.save()
        
        # Redirect based on notification type
        if notification.assignment:
            # Assignment notification - redirect to assignments page
            return redirect('student_assignments')
        elif notification.announcement:
            # Announcement notification - redirect to announcements page
            return redirect('student_announcements')
        else:
            # Default: redirect based on user role
            if hasattr(request.user, 'student_profile') and request.user.student_profile:
                return redirect('student_announcements')
            elif hasattr(request.user, 'profile') and request.user.profile.role == 'instructor':
                return redirect('instructor_my_courses')
            elif hasattr(request.user, 'profile') and request.user.profile.role == 'faculty_head':
                return redirect('my_courses')
            else:
                return redirect('student_announcements')
    except Notification.DoesNotExist:
        # If notification doesn't exist, just redirect
        if hasattr(request.user, 'student_profile') and request.user.student_profile:
            return redirect('student_announcements')
        elif hasattr(request.user, 'profile') and request.user.profile.role == 'instructor':
            return redirect('instructor_my_courses')
        elif hasattr(request.user, 'profile') and request.user.profile.role == 'faculty_head':
            return redirect('my_courses')
        else:
            return redirect('student_announcements')

@csrf_exempt
def mark_all_notifications_read(request):
    """Mark all unread notifications as read for the current user"""
    if not request.user.is_authenticated:
        return JsonResponse({'error': 'Authentication required'}, status=401)
    
    try:
        Notification.objects.filter(user=request.user, is_read=False).update(is_read=True)
        return JsonResponse({'status': 'success', 'message': 'All notifications marked as read'})
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)

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
    assessments_list = []
    assessment_type_labels = {
        'midterm': 'Midterm',
        'final': 'Final',
        'project': 'Project',
        'assignment': 'Assignment',
        'absence': 'Absence',
        'quiz': 'Quiz'
    }
    
    if course_names:
        from .models import AssessmentLORelation
        learning_outcomes_qs = ProgramOutcome.objects.filter(
            course_name__in=course_names
        ).select_related('created_by').prefetch_related('related_program_outcomes').order_by('text', 'course_name', 'created_at')
        
        # Group learning outcomes by text (same LO in different courses)
        lo_groups = {}
        lo_dict = {}  
        for lo in learning_outcomes_qs:
            lo_text = lo.text.strip()
            lo_dict[lo.id] = lo
            if lo_text not in lo_groups:
                lo_groups[lo_text] = {
                    'ids': [],
                    'courses': [],
                    'linked_pos_dict': {},  # po_id -> {percentage, text}
                    'linked_assessments': []
                }
            
            lo_groups[lo_text]['ids'].append(lo.id)
            if lo.course_name and lo.course_name not in lo_groups[lo_text]['courses']:
                lo_groups[lo_text]['courses'].append(lo.course_name)
        
        for lo_text, group_data in lo_groups.items():
            for lo_id in group_data['ids']:
                if lo_id not in lo_dict:
                    continue
                lo = lo_dict[lo_id]
                
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
                    
                    if po.id not in group_data['linked_pos_dict']:
                        group_data['linked_pos_dict'][po.id] = {
                            'id': po.id,
                            'text': po.text,
                            'percentage': percentage
                        }
                    else:
                        existing_percentage = group_data['linked_pos_dict'][po.id]['percentage']
                        group_data['linked_pos_dict'][po.id]['percentage'] = max(
                            existing_percentage,
                            percentage
                        )
        
        all_lo_ids = [lo_id for group in lo_groups.values() for lo_id in group['ids']]
        assessment_relations_for_all_los = AssessmentLORelation.objects.filter(
            learning_outcome_id__in=all_lo_ids
        ).select_related('assessment', 'assessment__course', 'learning_outcome')
        
        for rel in assessment_relations_for_all_los:
            lo_text = rel.learning_outcome.text.strip()
            assessment_course = rel.assessment.course.name
            
            if lo_text in lo_groups and assessment_course in course_names:
                if assessment_course not in lo_groups[lo_text]['courses']:
                    lo_groups[lo_text]['courses'].append(assessment_course)
        
        for lo_text, group_data in lo_groups.items():
            for lo_id in group_data['ids']:
                if lo_id not in lo_dict:
                    continue
                lo = lo_dict[lo_id]
                
                assessment_relations = AssessmentLORelation.objects.filter(
                    learning_outcome=lo
                ).select_related('assessment', 'assessment__course').order_by('assessment__course__name', 'assessment__id')
            
            for rel in assessment_relations:
                assessment = rel.assessment
                course_obj = assessment.course
                assessment_type_key = rel.assessment_type
                assessment_type_label = assessment_type_labels.get(assessment_type_key, assessment_type_key.title())
                
                # Create display name with index if needed
                if rel.assessment_index > 1:
                    display_name = f"{assessment_type_label} {rel.assessment_index}"
                else:
                    display_name = assessment_type_label
                
                # Use the first LO ID from the group for linking
                group_lo_id = lo_groups[lo_text]['ids'][0]
                
                lo_groups[lo_text]['linked_assessments'].append({
                    'id': assessment.id,
                    'course_name': course_obj.name,
                    'assessment_type': display_name,
                    'assessment_type_key': assessment_type_key,
                    'contribution_percentage': rel.contribution_percentage,
                    'relation_id': rel.id,
                    'lo_id': group_lo_id
                })
                
                # Add to global assessments list if not already there
                assessment_exists = any(
                    a['id'] == assessment.id and 
                    a['course_name'] == course_obj.name and 
                    a['assessment_type'] == display_name and
                    a['lo_id'] == group_lo_id
                    for a in assessments_list
                )
                if not assessment_exists:
                    assessments_list.append({
                        'id': assessment.id,
                        'course_name': course_obj.name,
                        'assessment_type': display_name,
                        'contribution_percentage': rel.contribution_percentage,
                        'lo_id': group_lo_id
                    })
        
        # Convert grouped data to list format
        for lo_text, group_data in lo_groups.items():
            # Sort courses alphabetically
            sorted_courses = sorted(group_data['courses'])
            # Join course names with " - "
            course_display = " - ".join(sorted_courses)
            
            # Convert linked_pos_dict to list
            linked_pos_list = list(group_data['linked_pos_dict'].values())
            
            learning_outcomes_list.append({
                'id': group_data['ids'][0],  # Use first ID as primary
                'ids': group_data['ids'],  # Keep all IDs for reference
                'text': lo_text,
                'course': course_display,  # Combined course names
                'courses': sorted_courses,  # Individual course names
                'linked_pos': linked_pos_list,
                'linked_assessments': group_data['linked_assessments']
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
    
    # Prepare JSON data for learning outcomes (to avoid template syntax in JavaScript)
    learning_outcomes_json = json.dumps(learning_outcomes_list)
    
    return render(request, 'faculty/department_graph.html', {
        'department': faculty_head_department,
        'total_courses': total_courses,
        'total_students': total_students,
        'course_data': course_data,
        'chart_data': chart_data,
        'chart_data_json': json.dumps(chart_data),
        'learning_outcomes': learning_outcomes_list,
        'learning_outcomes_json': learning_outcomes_json,
        'program_outcomes': program_outcomes_list,
        'assessments_data': assessments_list,
    })