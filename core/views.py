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
from django.db import connection
from .models import Grade, Student, Course, ProgramOutcome

User = get_user_model()


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


def instructor_login(request):
    if request.method == 'POST':
        username = request.POST.get('username', '').strip()
        password = request.POST.get('password', '').strip()
        
        user = authenticate(request, username=username, password=password)
        if user:
            try:
                profile = user.profile
                if profile.role == 'instructor':
                    auth_login(request, user)
                    request.session['instructor_username'] = username
                    return JsonResponse({'status': 'success', 'username': username})
                else:
                    return JsonResponse({'status': 'error', 'message': 'User is not an instructor'}, status=403)
            except AttributeError:
                return JsonResponse({'status': 'error', 'message': 'User profile not found'}, status=403)
        else:
            return JsonResponse({'status': 'error', 'message': 'Invalid username or password'}, status=401)
    
    return render(request, 'instructor_login.html')


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
        
        from .models import UserProfile, Faculty
        
        first_name = faculty_head.get('firstName') or faculty_head.get('first_name', '')
        last_name = faculty_head.get('lastName') or faculty_head.get('last_name', '')
        
        user, created = User.objects.get_or_create(
            username=username,
            defaults={'first_name': first_name, 'last_name': last_name}
        )
        
        if created:
            user.set_unusable_password()
            user.save()
        
        profile, _ = UserProfile.objects.get_or_create(
            user=user,
            defaults={'role': 'faculty_head'}
        )
        
        if profile.role != 'faculty_head':
            profile.role = 'faculty_head'
            profile.save()
        
        if faculty_head.get('faculty'):
            faculty_name = faculty_head['faculty']
            faculty_slug = faculty_name.lower().replace(' ', '-')
            try:
                faculty = Faculty.objects.get(slug=faculty_slug)
            except Faculty.DoesNotExist:
                faculty, _ = Faculty.objects.get_or_create(
                    slug=faculty_slug,
                    defaults={'name': faculty_name}
                )
            profile.faculty = faculty
            profile.save()
        
        auth_login(request, user)
        return redirect('faculty-head')
    
    return render(request, 'faculty_head_login.html')


def student_dashboard(request):
    username = request.GET.get('username', '')
    
    courses_with_grades = []
    if username:
        try:
            student = Student.objects.get(username=username)
            grades_qs = Grade.objects.filter(student=student).select_related('course')
            
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
        except Student.DoesNotExist:
            pass
    
    return render(request, 'student.html', {
        'grades': None,
        'courses_with_grades': courses_with_grades
    })


def instructor_required(view_func):
    """Decorator to check if user is an instructor (based on session)"""
    def wrapper(request, *args, **kwargs):
        username = request.session.get('instructor_username')
        
        if not username:
            from django.shortcuts import redirect
            return redirect('instructor-login')
        
        user, created = User.objects.get_or_create(username=username)
        if created:
            user.set_unusable_password()
            user.save()
        
        from .models import UserProfile
        profile, profile_created = UserProfile.objects.get_or_create(
            user=user,
            defaults={'role': 'instructor'}
        )
        if not profile_created and profile.role != 'instructor':
            profile.role = 'instructor'
            profile.save()
        
        request.instructor_user = user
        return view_func(request, *args, **kwargs)
    return wrapper


@instructor_required
def instructor_dashboard(request):
    return render(request, 'instructor.html', {'show_welcome': True})

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
        courses = profile.courses.all().select_related('instructor')
        for course in courses:
            instructor_name = f"{course.instructor.first_name} {course.instructor.last_name}".strip() or course.instructor.username
            courses_data.append({
                'id': course.id,
                'name': course.name,
                'code': course.code,
                'instructor': instructor_name,
                'department': course.department,
            })
    
    return render(request, 'instructor.html', {
        'show_welcome': False,
        'page': 'my_courses',
        'courses': courses_data
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
def instructor_announcements(request):
    from .models import Announcement, UserProfile
    instructor_user = request.instructor_user
    
    instructors = User.objects.filter(profile__role='instructor').select_related('profile')
    faculty_heads = User.objects.filter(profile__role='faculty_head').select_related('profile')
    
    instructors_json_path = os.path.join(settings.BASE_DIR, 'static', 'json', 'instructors.json')
    faculty_heads_json_path = os.path.join(settings.BASE_DIR, 'static', 'json', 'faculty_heads.json')
    
    instructors_map = {}
    try:
        with open(instructors_json_path, encoding='utf-8') as f:
            instructors_data = json.load(f)
            for inst in instructors_data:
                username = inst.get('username')
                first_name = inst.get('firstName', '')
                last_name = inst.get('lastName', '')
                full_name = (first_name + ' ' + last_name).strip()
                if full_name:
                    instructors_map[username] = full_name
    except (OSError, json.JSONDecodeError):
        pass
    
    faculty_heads_map = {}
    try:
        with open(faculty_heads_json_path, encoding='utf-8') as f:
            faculty_heads_data = json.load(f)
            for fh in faculty_heads_data:
                username = fh.get('username')
                first_name = fh.get('firstName', '')
                last_name = fh.get('lastName', '')
                full_name = (first_name + ' ' + last_name).strip()
                if full_name:
                    faculty_heads_map[username] = full_name
    except (OSError, json.JSONDecodeError):
        pass
    
    if request.method == 'POST':
        message = (request.POST.get('message') or '').strip()
        subject = (request.POST.get('subject') or '').strip()
        receiver_username = (request.POST.get('receiver') or '').strip()
        
        if message:
            if not subject:
                subject = 'No Topic'
            
            receiver_id = None
            receiver_role = None
            if receiver_username:
                try:
                    receiver = User.objects.get(username=receiver_username)
                    receiver_id = receiver.id
                    profile = getattr(receiver, 'profile', None)
                    if profile:
                        receiver_role = profile.role
                except User.DoesNotExist:
                    pass
            
            from datetime import datetime
            with connection.cursor() as cursor:
                cursor.execute("""
                    INSERT INTO core_announcement (sender_id, receiver_id, subject, message, sender_role, receiver_role, created_at)
                    VALUES (%s, %s, %s, %s, %s, %s, %s)
                """, [instructor_user.id, receiver_id, subject, message, 'instructor', receiver_role, datetime.now()])
            
            return redirect('instructor_announcements')
    
    with connection.cursor() as cursor:
        cursor.execute("""
            SELECT 
                a.id, a.subject, a.message, a.sender_role, a.receiver_role, a.created_at,
                a.sender_id, a.receiver_id,
                sender.username as sender_username, sender.first_name as sender_first_name, sender.last_name as sender_last_name,
                receiver.username as receiver_username, receiver.first_name as receiver_first_name, receiver.last_name as receiver_last_name
            FROM core_announcement a
            INNER JOIN auth_user sender ON a.sender_id = sender.id
            LEFT JOIN auth_user receiver ON a.receiver_id = receiver.id
            WHERE a.sender_id = %s OR a.receiver_id = %s
            ORDER BY a.created_at DESC
        """, [instructor_user.id, instructor_user.id])
        
        rows = cursor.fetchall()
        all_announcements = []
        for row in rows:
            ann_id, subject, message, sender_role, receiver_role, created_at, sender_id, receiver_id, sender_username, sender_first_name, sender_last_name, receiver_username, receiver_first_name, receiver_last_name = row
            all_announcements.append({
                'id': ann_id,
                'subject': subject,
                'message': message,
                'sender_id': sender_id,
                'receiver_id': receiver_id,
                'sender_username': sender_username,
                'sender_first_name': sender_first_name,
                'sender_last_name': sender_last_name,
                'receiver_username': receiver_username,
                'receiver_first_name': receiver_first_name,
                'receiver_last_name': receiver_last_name,
                'sender_role': sender_role,
                'receiver_role': receiver_role,
                'created_at': created_at,
            })
    
    announcements_data = []
    for ann in all_announcements:
        sender_full_name = f"{ann['sender_first_name']} {ann['sender_last_name']}".strip() if ann['sender_first_name'] or ann['sender_last_name'] else ''
        sender_name = instructors_map.get(ann['sender_username']) or faculty_heads_map.get(ann['sender_username']) or sender_full_name or ann['sender_username']
        
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
        
        announcements_data.append({
            'id': ann['id'],
            'subject': ann['subject'],
            'message': ann['message'],
            'sender': sender_name,
            'sender_username': ann['sender_username'],
            'receiver': receiver_name,
            'receiver_username': receiver_username,
            'is_sent': ann['sender_id'] == instructor_user.id,
            'created_at': created_at_formatted,
        })
    
    recipients = []
    for inst in instructors:
        if inst.username != instructor_user.username:
            name = instructors_map.get(inst.username) or inst.get_full_name() or inst.username
            recipients.append({'username': inst.username, 'name': name, 'role': 'instructor'})
    
    for fh in faculty_heads:
        name = faculty_heads_map.get(fh.username) or fh.get_full_name() or fh.username
        recipients.append({'username': fh.username, 'name': name, 'role': 'faculty_head'})
    
    sent_messages = [ann for ann in announcements_data if ann['is_sent']]
    received_messages = [ann for ann in announcements_data if not ann['is_sent']]
    
    return render(request, 'instructor/instructor_announcements.html', {
        'all_announcements': announcements_data,
        'sent_messages': sent_messages,
        'received_messages': received_messages,
        'recipients': recipients,
    })


@csrf_exempt
def set_instructor_session(request):
    """Set instructor username in session"""
    if request.method == 'POST':
        username = request.POST.get('username')
        if username:
            request.session['instructor_username'] = username
            return JsonResponse({'status': 'ok'})
    return JsonResponse({'status': 'error'}, status=400)


@faculty_head_required
def faculty_head_dashboard(request):
    return render(request, 'faculty_head.html', {'show_welcome': True})

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
    faculty_heads_json_path = os.path.join(settings.BASE_DIR, 'static', 'json', 'faculty_heads.json')
    faculty_head_data = {}
    faculty_head_department = None
    try:
        with open(faculty_heads_json_path, encoding='utf-8') as f:
            faculty_heads_list = json.load(f)
            for fh in faculty_heads_list:
                if fh.get('username') == request.user.username:
                    faculty_head_data = fh
                    faculty_head_department = fh.get('department')
                    break
    except (OSError, json.JSONDecodeError):
        pass
    
    faculty_courses_with_instructors = []
    course_instructor_map = {}
    
    instructors_json_path = os.path.join(settings.BASE_DIR, 'static', 'json', 'instructors.json')
    try:
        with open(instructors_json_path, encoding='utf-8') as f:
            instructors_list = json.load(f)
            
            for inst in instructors_list:
                inst_department = inst.get('department')
                if faculty_head_department:
                    if inst_department != faculty_head_department:
                        continue
                
                inst_courses = inst.get('courses', []) or []
                full_name = (inst.get('firstName', '') + ' ' + inst.get('lastName', '')).strip()
                instructor_name = full_name if full_name else 'Unknown'
                
                for course_name in inst_courses:
                    if course_name not in course_instructor_map:
                        course_instructor_map[course_name] = []
                    course_instructor_map[course_name].append(instructor_name)
    except (OSError, json.JSONDecodeError):
        pass
    
    try:
        with open(faculty_heads_json_path, encoding='utf-8') as f:
            faculty_heads_list = json.load(f)
            for fh in faculty_heads_list:
                fh_department = fh.get('department')
                if faculty_head_department and fh_department != faculty_head_department:
                    continue
                
                fh_courses = fh.get('courses', []) or []
                full_name = (fh.get('firstName', '') + ' ' + fh.get('lastName', '')).strip()
                faculty_head_name = full_name if full_name else 'Unknown'
                
                for course_name in fh_courses:
                    if course_name not in course_instructor_map:
                        course_instructor_map[course_name] = []
                    course_instructor_map[course_name].append(faculty_head_name)
    except (OSError, json.JSONDecodeError):
        pass
    
    for course_name, instructors in sorted(course_instructor_map.items()):
        instructor_display = ', '.join(instructors) if instructors else 'Unknown'
        
        course = Course.objects.filter(name=course_name).first()
        first_learning_outcome = None
        if course:
            learning_outcomes = ProgramOutcome.objects.filter(course_name=course_name).order_by('-created_at')
            first_learning_outcome = learning_outcomes.first()
        
        faculty_courses_with_instructors.append({
            'course': course_name,
            'instructor': instructor_display,
            'course_id': course.id if course else None,
            'first_lo_id': first_learning_outcome.id if first_learning_outcome else None,
        })
    
    import json as json_module
    context = {
        'faculty_head': faculty_head_data,
        'faculty_courses': faculty_courses_with_instructors,
        'faculty_courses_json': json_module.dumps(faculty_courses_with_instructors),
    }
    return render(request, 'faculty/all_courses.html', context)

@faculty_head_required
def my_courses(request):
    profile = getattr(request.user, 'profile', None)
    
    courses_data = []
    if profile:
        courses = profile.courses.all().select_related('instructor')
        for course in courses:
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
    
    faculty_heads_json_path = os.path.join(settings.BASE_DIR, 'static', 'json', 'faculty_heads.json')
    faculty_head_department = None
    faculty_name_from_json = None
    try:
        with open(faculty_heads_json_path, encoding='utf-8') as f:
            faculty_heads_list = json.load(f)
            for fh in faculty_heads_list:
                if fh.get('username') == request.user.username:
                    faculty_head_department = fh.get('department')
                    faculty_name_from_json = fh.get('faculty')
                    break
    except (OSError, json.JSONDecodeError):
        pass
    
    if not faculty and faculty_name_from_json:
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
        
        faculty_heads_map = {}
        try:
            with open(faculty_heads_json_path, encoding='utf-8') as f:
                faculty_heads_list = json.load(f)
                for fh in faculty_heads_list:
                    username = fh.get('username')
                    first_name = fh.get('firstName', '')
                    last_name = fh.get('lastName', '')
                    full_name = (first_name + ' ' + last_name).strip()
                    if full_name:
                        faculty_heads_map[username] = full_name
        except (OSError, json.JSONDecodeError):
            pass
        
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
        
        ProgramOutcome.objects.create(text=text, course_name='', faculty=faculty, created_by=creator)
        return redirect('program_outcomes')
    
    faculty_heads_map = {}
    try:
        with open(faculty_heads_json_path, encoding='utf-8') as f:
            faculty_heads_list = json.load(f)
            for fh in faculty_heads_list:
                username = fh.get('username')
                first_name = fh.get('firstName', '')
                last_name = fh.get('lastName', '')
                full_name = (first_name + ' ' + last_name).strip()
                if full_name:
                    faculty_heads_map[username] = full_name
    except (OSError, json.JSONDecodeError):
        pass
    
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
    
    faculty_heads_json_path = os.path.join(settings.BASE_DIR, 'static', 'json', 'faculty_heads.json')
    faculty_name_from_json = None
    try:
        with open(faculty_heads_json_path, encoding='utf-8') as f:
            faculty_heads_list = json.load(f)
            for fh in faculty_heads_list:
                if fh.get('username') == request.user.username:
                    faculty_name_from_json = fh.get('faculty')
                    break
    except (OSError, json.JSONDecodeError):
        pass
    
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
            outcome.text = text
            outcome.save()
        return redirect('program_outcomes')
    
    return JsonResponse({'text': outcome.text})


@faculty_head_required
def delete_program_outcome(request, outcome_id):
    profile = getattr(request.user, 'profile', None)
    faculty = profile.faculty if profile else None
    
    outcome = get_object_or_404(ProgramOutcome, id=outcome_id, faculty=faculty, created_by=request.user)
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
    
    faculty_heads_json_path = os.path.join(settings.BASE_DIR, 'static', 'json', 'faculty_heads.json')
    faculty_head_department = None
    try:
        with open(faculty_heads_json_path, encoding='utf-8') as f:
            faculty_heads_list = json.load(f)
            for fh in faculty_heads_list:
                if fh.get('username') == request.user.username:
                    faculty_head_department = fh.get('department')
                    break
    except (OSError, json.JSONDecodeError):
        pass
    
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
    
    faculty_heads_map = {}
    faculty_heads_json_path = os.path.join(settings.BASE_DIR, 'static', 'json', 'faculty_heads.json')
    try:
        with open(faculty_heads_json_path, encoding='utf-8') as f:
            faculty_heads_list = json.load(f)
            for fh in faculty_heads_list:
                username = fh.get('username')
                first_name = fh.get('firstName', '')
                last_name = fh.get('lastName', '')
                full_name = (first_name + ' ' + last_name).strip()
                if full_name:
                    faculty_heads_map[username] = full_name
    except (OSError, json.JSONDecodeError):
        pass
    
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
    
    program_outcomes_data = []
    for po in related_program_outcomes:
        program_outcomes_data.append({
            'id': po.id,
            'text': po.text,
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
        'faculty/learning_outcome_detail.html',
        {
            'outcome': outcome,
            'course': course,
            'program_outcomes': program_outcomes_data,
            'available_program_outcomes': available_program_outcomes,
            'course_name_slug': course_name_slug,
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
    
    program_outcomes_data = []
    for po in related_program_outcomes:
        program_outcomes_data.append({
            'id': po.id,
            'text': po.text,
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
                    profile.courses.add(course)
            course_id = course.id if course else None
            if course_id:
                return redirect('faculty_head_learning_outcome_detail', course_id=course_id, outcome_id=outcome_id)
        course_name_slug = outcome.course_name.replace(' ', '-')
        return redirect('faculty_head_course_learning_outcomes', course_name=course_name_slug)
    
    return JsonResponse({'text': outcome.text})

@faculty_head_required
def faculty_head_unlink_program_outcome(request, outcome_id, program_outcome_id):
    """Unlink a program outcome from a learning outcome (for faculty head)"""
    outcome = get_object_or_404(ProgramOutcome, id=outcome_id)
    program_outcome = get_object_or_404(ProgramOutcome, id=program_outcome_id)
    
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
    faculty_heads_json_path = os.path.join(settings.BASE_DIR, 'static', 'json', 'faculty_heads.json')
    faculty_head_data = {}
    try:
        with open(faculty_heads_json_path, encoding='utf-8') as f:
            faculty_heads_list = json.load(f)
            for fh in faculty_heads_list:
                if fh.get('username') == request.user.username:
                    faculty_head_data = fh
                    break
    except (OSError, json.JSONDecodeError):
        pass
    
    context = {
        'faculty_head': json.dumps(faculty_head_data),
        'user': request.user,
    }
    return render(request, 'faculty/faculty_head_grades.html', context)


@instructor_required
def learning_outcomes(request):
    """Show learning outcomes for instructor's own courses only"""
    instructor_user = request.instructor_user
    username = instructor_user.username
    
    instructor_courses = Course.objects.filter(instructor=instructor_user)
    course_names_from_db = [course.name for course in instructor_courses]
    
    course_names_from_json = []
    instructors_json_path = os.path.join(settings.BASE_DIR, 'static', 'json', 'instructors.json')
    try:
        with open(instructors_json_path, encoding='utf-8') as f:
            instructors_data = json.load(f)
            for inst in instructors_data:
                if inst.get('username') == username:
                    course_names_from_json = inst.get('courses', []) or []
                    break
    except (OSError, json.JSONDecodeError):
        pass
    
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
    
    instructor_department = None
    instructor_faculty = None
    instructors_json_path = os.path.join(settings.BASE_DIR, 'static', 'json', 'instructors.json')
    try:
        with open(instructors_json_path, encoding='utf-8') as f:
            instructors_data = json.load(f)
            for inst in instructors_data:
                if inst.get('username') == username:
                    instructor_department = inst.get('department')
                    instructor_faculty = inst.get('faculty')
                    break
    except (OSError, json.JSONDecodeError):
        pass
    
    faculty_head_department = None
    faculty_heads_json_path = os.path.join(settings.BASE_DIR, 'static', 'json', 'faculty_heads.json')
    try:
        with open(faculty_heads_json_path, encoding='utf-8') as f:
            faculty_heads_list = json.load(f)
            for fh in faculty_heads_list:
                if fh.get('department') == instructor_department:
                    faculty_head_department = fh.get('department')
                    break
    except (OSError, json.JSONDecodeError):
        pass
    
    from .models import Faculty
    faculty = None
    if instructor_faculty:
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
            learning_outcome = ProgramOutcome.objects.create(
                text=text, 
                course_name=course_name, 
                created_by=instructor_user
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
            if not hasattr(request, 'instructor_user'):
                username = request.session.get('instructor_username')
                if not username:
                    from django.shortcuts import redirect
                    return redirect('instructor-login')
                user, created = User.objects.get_or_create(username=username)
                if created:
                    user.set_unusable_password()
                    user.save()
                from .models import UserProfile
                profile, profile_created = UserProfile.objects.get_or_create(
                    user=user,
                    defaults={'role': 'instructor'}
                )
                if not profile_created and profile.role != 'instructor':
                    profile.role = 'instructor'
                    profile.save()
                request.instructor_user = user
            instructor_user = request.instructor_user
            course = get_object_or_404(Course, id=course_id, instructor=instructor_user)
            outcome = get_object_or_404(ProgramOutcome, id=outcome_id, course_name=course.name, created_by=instructor_user)
            
            instructor_department = None
            instructor_faculty = None
            instructors_json_path = os.path.join(settings.BASE_DIR, 'static', 'json', 'instructors.json')
            try:
                with open(instructors_json_path, encoding='utf-8') as f:
                    instructors_data = json.load(f)
                    for inst in instructors_data:
                        if inst.get('username') == instructor_user.username:
                            instructor_department = inst.get('department')
                            instructor_faculty = inst.get('faculty')
                            break
            except (OSError, json.JSONDecodeError):
                pass
            
            from .models import Faculty
            if instructor_faculty:
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
    
    related_program_outcomes = outcome.related_program_outcomes.all().order_by('id')
    
    program_outcomes_data = []
    for po in related_program_outcomes:
        program_outcomes_data.append({
            'id': po.id,
            'text': po.text,
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
            if not hasattr(request, 'instructor_user'):
                username = request.session.get('instructor_username')
                if not username:
                    from django.shortcuts import redirect
                    return redirect('instructor-login')
                user, created = User.objects.get_or_create(username=username)
                if created:
                    user.set_unusable_password()
                    user.save()
                from .models import UserProfile
                profile, profile_created = UserProfile.objects.get_or_create(
                    user=user,
                    defaults={'role': 'instructor'}
                )
                if not profile_created and profile.role != 'instructor':
                    profile.role = 'instructor'
                    profile.save()
                request.instructor_user = user
            instructor_user = request.instructor_user
            course = get_object_or_404(Course, id=course_id, instructor=instructor_user)
            outcome = get_object_or_404(ProgramOutcome, id=outcome_id, course_name=course.name, created_by=instructor_user)
    else:
        from django.shortcuts import redirect
        return redirect('faculty-head-login')
    
    related_program_outcomes = outcome.related_program_outcomes.all().order_by('id')
    
    program_outcomes_data = []
    for po in related_program_outcomes:
        program_outcomes_data.append({
            'id': po.id,
            'text': po.text,
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
def unlink_program_outcome(request, outcome_id, program_outcome_id):
    """Unlink a program outcome from a learning outcome"""
    instructor_user = request.instructor_user
    outcome = get_object_or_404(ProgramOutcome, id=outcome_id, created_by=instructor_user)
    program_outcome = get_object_or_404(ProgramOutcome, id=program_outcome_id)
    
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
            instructor_faculty = None
            instructors_json_path = os.path.join(settings.BASE_DIR, 'static', 'json', 'instructors.json')
            try:
                with open(instructors_json_path, encoding='utf-8') as f:
                    instructors_data = json.load(f)
                    for inst in instructors_data:
                        if inst.get('username') == instructor_user.username:
                            instructor_faculty = inst.get('faculty')
                            break
            except (OSError, json.JSONDecodeError):
                pass
            
            from .models import Faculty
            faculty = None
            if instructor_faculty:
                try:
                    faculty = Faculty.objects.get(slug=instructor_faculty.lower())
                except Faculty.DoesNotExist:
                    faculty, _ = Faculty.objects.get_or_create(
                        slug=instructor_faculty.lower(),
                        defaults={'name': instructor_faculty}
                    )
            
            if faculty:
                program_outcomes_to_link = ProgramOutcome.objects.filter(
                    id__in=selected_program_outcome_ids,
                    faculty=faculty,
                    course_name=''
                )
                outcome.related_program_outcomes.add(*program_outcomes_to_link)
    
    return redirect('learning_outcome_detail', outcome_id=outcome_id)


@instructor_required
def delete_learning_outcome(request, outcome_id):
    """Delete a learning outcome"""
    instructor_user = request.instructor_user
    username = instructor_user.username
    
    outcome = get_object_or_404(ProgramOutcome, id=outcome_id, created_by=instructor_user)
    course_name = outcome.course_name
    outcome.delete()
    
    course_name_slug = course_name.replace(' ', '-')
    return redirect('course_learning_outcomes', course_name=course_name_slug)


@instructor_required
def create_learning_outcome(request):
    """Create a learning outcome for instructor's own course"""
    instructor_user = request.instructor_user
    username = instructor_user.username
    
    instructor_courses_from_json = []
    instructors_json_path = os.path.join(settings.BASE_DIR, 'static', 'json', 'instructors.json')
    try:
        with open(instructors_json_path, encoding='utf-8') as f:
            instructors_data = json.load(f)
            for inst in instructors_data:
                if inst.get('username') == username:
                    instructor_courses_from_json = inst.get('courses', []) or []
                    break
    except (OSError, json.JSONDecodeError):
        pass
    
    course_names_from_db = [c.name for c in Course.objects.filter(instructor=instructor_user)]
    all_available_courses = list(set(course_names_from_db + instructor_courses_from_json))
    
    if request.method == 'POST':
        text = (request.POST.get('text') or '').strip()
        course_name = (request.POST.get('course_name') or '').strip()
        
        if not course_name or not text:
            instructor_courses = Course.objects.filter(instructor=instructor_user)
            course_names_from_db = [course.name for course in instructor_courses]
            course_names_from_json = []
            instructors_json_path = os.path.join(settings.BASE_DIR, 'static', 'json', 'instructors.json')
            try:
                with open(instructors_json_path, encoding='utf-8') as f:
                    instructors_data = json.load(f)
                    for inst in instructors_data:
                        if inst.get('username') == username:
                            course_names_from_json = inst.get('courses', []) or []
                            break
            except (OSError, json.JSONDecodeError):
                pass
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
        
        ProgramOutcome.objects.create(text=text, course_name=course_name, created_by=instructor_user)
        from django.urls import reverse
        course_name_slug = course_name.replace(' ', '-')
        redirect_url = reverse('course_learning_outcomes', args=[course_name_slug])
        redirect_url += f'?username={username}'
        return redirect(redirect_url)
    
    instructor_courses = Course.objects.filter(instructor=instructor_user)
    course_names_from_db = [course.name for course in instructor_courses]
    
    course_names_from_json = []
    instructors_json_path = os.path.join(settings.BASE_DIR, 'static', 'json', 'instructors.json')
    try:
        with open(instructors_json_path, encoding='utf-8') as f:
            instructors_data = json.load(f)
            for inst in instructors_data:
                if inst.get('username') == username:
                    course_names_from_json = inst.get('courses', []) or []
                    break
    except (OSError, json.JSONDecodeError):
        pass
    
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
            courses_with_grades.append({
                'course_name': course.name,
                'midterm': grade_obj.midterm if grade_obj else None,
                'assignment': grade_obj.assignment if grade_obj else None,
                'final': grade_obj.final if grade_obj else None,
            })
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
    
    faculty_heads_json_path = os.path.join(settings.BASE_DIR, 'static', 'json', 'faculty_heads.json')
    try:
        with open(faculty_heads_json_path, encoding='utf-8') as f:
            faculty_heads_list = json.load(f)
            for fh in faculty_heads_list:
                username = fh.get('username')
                first_name = fh.get('firstName', '')
                last_name = fh.get('lastName', '')
                full_name = (first_name + ' ' + last_name).strip()
                if full_name:
                    faculty_heads_map[username] = full_name
    except (OSError, json.JSONDecodeError):
        pass
    
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
        
        faculty_heads_json_path = os.path.join(settings.BASE_DIR, 'static', 'json', 'faculty_heads.json')
        try:
            with open(faculty_heads_json_path, encoding='utf-8') as f:
                faculty_heads_list = json.load(f)
                for fh in faculty_heads_list:
                    username = fh.get('username')
                    first_name = fh.get('firstName', '')
                    last_name = fh.get('lastName', '')
                    full_name = (first_name + ' ' + last_name).strip()
                    if full_name:
                        faculty_heads_map[username] = full_name
        except (OSError, json.JSONDecodeError):
            pass
        
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
        
        outcomes_data = []
        for o in outcomes_qs:
            creator_name = instructors_map.get(o.created_by.username) or o.created_by.get_full_name() or o.created_by.username
            related_program_outcomes = o.related_program_outcomes.all()
            outcomes_data.append({
                'id': o.id,
                'text': o.text,
                'created_by': creator_name,
                'created_at': o.created_at.strftime('%Y-%m-%d %H:%M'),
                'related_program_outcomes': [{'id': po.id, 'text': po.text} for po in related_program_outcomes],
            })
        
    except Student.DoesNotExist:
        return redirect('student-login')
    
    return render(request, "student/course_learning_outcomes.html", {
        'course_name': course_name,
        'outcomes_data': outcomes_data,
    })

def logout_view(request):
    logout(request)
    return redirect("home")

@faculty_head_required
def faculty_head_announcements(request):
    from .models import Announcement, UserProfile
    faculty_head_user = request.user

    instructors = User.objects.filter(profile__role='instructor').select_related('profile')
    faculty_heads = User.objects.filter(profile__role='faculty_head').select_related('profile')
    

    instructors_json_path = os.path.join(settings.BASE_DIR, 'static', 'json', 'instructors.json')
    faculty_heads_json_path = os.path.join(settings.BASE_DIR, 'static', 'json', 'faculty_heads.json')
    
    instructors_map = {}
    try:
        with open(instructors_json_path, encoding='utf-8') as f:
            instructors_data = json.load(f)
            for inst in instructors_data:
                username = inst.get('username')
                first_name = inst.get('firstName', '')
                last_name = inst.get('lastName', '')
                full_name = (first_name + ' ' + last_name).strip()
                if full_name:
                    instructors_map[username] = full_name
    except (OSError, json.JSONDecodeError):
        pass
    
    faculty_heads_map = {}
    try:
        with open(faculty_heads_json_path, encoding='utf-8') as f:
            faculty_heads_data = json.load(f)
            for fh in faculty_heads_data:
                username = fh.get('username')
                first_name = fh.get('firstName', '')
                last_name = fh.get('lastName', '')
                full_name = (first_name + ' ' + last_name).strip()
                if full_name:
                    faculty_heads_map[username] = full_name
    except (OSError, json.JSONDecodeError):
        pass
    
    if request.method == 'POST':
        message = (request.POST.get('message') or '').strip()
        subject = (request.POST.get('subject') or '').strip()
        receiver_username = (request.POST.get('receiver') or '').strip()
        
        if message:
            if not subject:
                subject = 'No Topic'
            
            receiver_id = None
            receiver_role = None
            if receiver_username:
                try:
                    receiver = User.objects.get(username=receiver_username)
                    receiver_id = receiver.id
                    profile = getattr(receiver, 'profile', None)
                    if profile:
                        receiver_role = profile.role
                except User.DoesNotExist:
                    pass
            
            from datetime import datetime
            with connection.cursor() as cursor:
                cursor.execute("""
                    INSERT INTO core_announcement (sender_id, receiver_id, subject, message, sender_role, receiver_role, created_at)
                    VALUES (%s, %s, %s, %s, %s, %s, %s)
                """, [faculty_head_user.id, receiver_id, subject, message, 'faculty_head', receiver_role, datetime.now()])
            
            return redirect('faculty-head-announcements')
    
    with connection.cursor() as cursor:
        cursor.execute("""
            SELECT 
                a.id, a.subject, a.message, a.sender_role, a.receiver_role, a.created_at,
                a.sender_id, a.receiver_id,
                sender.username as sender_username, sender.first_name as sender_first_name, sender.last_name as sender_last_name,
                receiver.username as receiver_username, receiver.first_name as receiver_first_name, receiver.last_name as receiver_last_name
            FROM core_announcement a
            INNER JOIN auth_user sender ON a.sender_id = sender.id
            LEFT JOIN auth_user receiver ON a.receiver_id = receiver.id
            WHERE a.sender_id = %s OR a.receiver_id = %s
            ORDER BY a.created_at DESC
        """, [faculty_head_user.id, faculty_head_user.id])
        
        rows = cursor.fetchall()
        all_announcements = []
        for row in rows:
            ann_id, subject, message, sender_role, receiver_role, created_at, sender_id, receiver_id, sender_username, sender_first_name, sender_last_name, receiver_username, receiver_first_name, receiver_last_name = row
            all_announcements.append({
                'id': ann_id,
                'subject': subject,
                'message': message,
                'sender_id': sender_id,
                'receiver_id': receiver_id,
                'sender_username': sender_username,
                'sender_first_name': sender_first_name,
                'sender_last_name': sender_last_name,
                'receiver_username': receiver_username,
                'receiver_first_name': receiver_first_name,
                'receiver_last_name': receiver_last_name,
                'sender_role': sender_role,
                'receiver_role': receiver_role,
                'created_at': created_at,
            })
    
    announcements_data = []
    for ann in all_announcements:
        sender_full_name = f"{ann['sender_first_name']} {ann['sender_last_name']}".strip() if ann['sender_first_name'] or ann['sender_last_name'] else ''
        sender_name = instructors_map.get(ann['sender_username']) or faculty_heads_map.get(ann['sender_username']) or sender_full_name or ann['sender_username']
        
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
        
        announcements_data.append({
            'id': ann['id'],
            'subject': ann['subject'],
            'message': ann['message'],
            'sender': sender_name,
            'sender_username': ann['sender_username'],
            'receiver': receiver_name,
            'receiver_username': receiver_username,
            'is_sent': ann['sender_id'] == faculty_head_user.id,
            'created_at': created_at_formatted,
        })
    
    recipients = []
    for inst in instructors:
        name = instructors_map.get(inst.username) or inst.get_full_name() or inst.username
        recipients.append({'username': inst.username, 'name': name, 'role': 'instructor'})
    
    for fh in faculty_heads:
        if fh.username != faculty_head_user.username:
            name = faculty_heads_map.get(fh.username) or fh.get_full_name() or fh.username
            recipients.append({'username': fh.username, 'name': name, 'role': 'faculty_head'})
    
    sent_messages = [ann for ann in announcements_data if ann['is_sent']]
    received_messages = [ann for ann in announcements_data if not ann['is_sent']]
    
    return render(request, "faculty/faculty_announcements.html", {
        'all_announcements': announcements_data,
        'sent_messages': sent_messages,
        'received_messages': received_messages,
        'recipients': recipients,
    })

def faculty_head_logout(request):
    logout(request)
    return redirect("home")