from .models import Student, Notification, Announcement, Assignment
from django.db.models import Q
from django.urls import reverse
from django.utils import timezone

def student_info(request):
    if request.user.is_authenticated:
        try:
            student = Student.objects.get(user=request.user)
            # Get unread notifications
            try:
                unread_notifications_list = list(Notification.objects.filter(user=request.user, is_read=False).select_related('assignment', 'announcement').order_by('-created_at')[:10])
            except Exception as e:
                import sys
                print(f"ERROR getting notifications for {request.user.username}: {e}", file=sys.stderr)
                import traceback
                traceback.print_exc(file=sys.stderr)
                unread_notifications_list = []
            
            # Get the last 3 announcements (read or unread) for notification dropdown
            top_notifications = []  # Initialize outside try block
            try:
                student_courses = student.courses.all()
                student_courses_set = set(student.courses.values_list('name', flat=True))
                
                # Get all announcements for the student
                all_announcements = list(Announcement.objects.filter(
                    (Q(receiver=request.user) | Q(receiver__isnull=True))
                ).select_related('sender').order_by('-created_at', '-is_pinned')[:100])
                
                # Filter announcements based on course enrollment (for course broadcasts)
                filtered_announcements = []
                for ann in all_announcements:
                    # Check if this is a course broadcast announcement
                    if ann.subject.startswith('__COURSE:'):
                        marker_end = ann.subject.find('__', 9)
                        if marker_end > 0:
                            course_name_from_marker = ann.subject[9:marker_end]
                            if course_name_from_marker not in student_courses_set:
                                continue  # Skip if student not enrolled
                    filtered_announcements.append(ann)
                
                # Build notification list from announcements (read or unread - doesn't matter)
                notification_list = []
                for ann in filtered_announcements:
                    # Clean subject (remove course marker if present)
                    display_subject = ann.subject
                    if display_subject.startswith('__COURSE:'):
                        marker_end = display_subject.find('__', 9)
                        if marker_end > 0:
                            display_subject = display_subject[marker_end + 2:]
                    
                    # Check if read
                    is_read = ann.read_by.filter(id=request.user.id).exists()
                    
                    sender_name = ann.sender.get_full_name() or ann.sender.username
                    
                    notification_list.append({
                        'title': display_subject or 'New Announcement',
                        'message': ann.message[:100] + ('...' if len(ann.message) > 100 else ''),
                        'url': reverse('student_announcements'),
                        'created_at': ann.created_at,
                        'id': f"ann_{ann.id}",
                        'type': 'announcement',
                        'announcement_id': ann.id,
                        'sender': sender_name,
                        'is_read': is_read,
                    })
                
                # Sort by created_at (most recent first) and take top 3
                notification_list.sort(key=lambda x: x['created_at'], reverse=True)
                top_notifications = notification_list[:3]  # Last 3 announcements (read or unread)
                
            except Exception as e:
                import sys
                print(f"ERROR getting announcements for {request.user.username}: {e}", file=sys.stderr)
                import traceback
                traceback.print_exc(file=sys.stderr)
                top_notifications = []
            
            # Calculate unread count for badge
            unread_count = 0
            # Count unread announcements
            try:
                student_courses = student.courses.all()
                student_courses_set = set(student.courses.values_list('name', flat=True))
                all_announcements = Announcement.objects.filter(
                    (Q(receiver=request.user) | Q(receiver__isnull=True))
                ).select_related('sender')
                
                for ann in all_announcements:
                    # Check if this is a course broadcast announcement
                    if ann.subject.startswith('__COURSE:'):
                        marker_end = ann.subject.find('__', 9)
                        if marker_end > 0:
                            course_name_from_marker = ann.subject[9:marker_end]
                            if course_name_from_marker not in student_courses_set:
                                continue
                    
                    if not ann.read_by.filter(id=request.user.id).exists():
                        unread_count += 1
            except:
                pass
            
            # Add unread notifications count
            unread_count += len(unread_notifications_list)
            
            return {
                'student_info': {
                    'username': student.username,
                    'name': f"{student.first_name} {student.last_name}".strip() or student.username,
                    'student_id': student.student_id,
                },
                'unread_notifications_count': unread_count,
                'unread_notifications': top_notifications,  # Show last 3 announcements (read or unread)
            }
        except Student.DoesNotExist:
            # User is authenticated but not a student - return empty
            return {
                'student_info': {
                    'username': request.user.username,
                    'name': request.user.get_full_name() or request.user.username,
                    'student_id': '-',
                },
                'unread_notifications_count': 0,
                'unread_notifications': [],
            }
        except Exception as e:
            # Log error but don't break the page
            import logging
            import sys
            logger = logging.getLogger(__name__)
            logger.error(f"Error in student_info context processor for user {request.user.username if request.user.is_authenticated else 'anonymous'}: {e}", exc_info=True)
            # Also print to stderr for immediate visibility
            print(f"ERROR in student_info context processor: {e}", file=sys.stderr)
            import traceback
            traceback.print_exc(file=sys.stderr)
            # Return empty but don't break the page
            return {
                'student_info': {
                    'username': request.user.username if request.user.is_authenticated else 'anonymous',
                    'name': request.user.get_full_name() or request.user.username if request.user.is_authenticated else 'anonymous',
                    'student_id': '-',
                },
                'unread_notifications_count': 0, 
                'unread_notifications': [],
            }
    
    # User not authenticated
    import sys
    print(f"DEBUG: User not authenticated, returning empty notifications", file=sys.stderr)
    return {
        'student_info': None, 
        'unread_notifications_count': 0, 
        'unread_notifications': [],
        'debug_notifications': {
            'error': 'User not authenticated',
            'error_type': 'NotAuthenticated'
        }
    }

def instructor_info(request):
    if request.user.is_authenticated:
        try:
            profile = request.user.profile
            if profile and profile.role == 'instructor':
                # Get the last 3 announcements (read or unread) for notification dropdown
                top_notifications = []
                try:
                    # Get all announcements for the instructor
                    all_announcements = list(Announcement.objects.filter(
                        Q(sender=request.user) | Q(receiver=request.user)
                    ).select_related('sender', 'receiver').order_by('-created_at', '-is_pinned')[:100])
                    
                    # Build notification list from announcements
                    notification_list = []
                    for ann in all_announcements:
                        display_subject = ann.subject
                        if display_subject.startswith('__COURSE:'):
                            marker_end = display_subject.find('__', 9)
                            if marker_end > 0:
                                display_subject = display_subject[marker_end + 2:]
                        
                        # Check if read
                        is_read = ann.read_by.filter(id=request.user.id).exists()
                        
                        sender_name = ann.sender.get_full_name() or ann.sender.username
                        
                        notification_list.append({
                            'title': display_subject or 'New Announcement',
                            'message': ann.message[:100] + ('...' if len(ann.message) > 100 else ''),
                            'url': reverse('instructor_announcements'),
                            'created_at': ann.created_at,
                            'id': f"ann_{ann.id}",
                            'type': 'announcement',
                            'announcement_id': ann.id,
                            'sender': sender_name,
                            'is_read': is_read,
                        })
                    
                    # Sort by created_at (most recent first) and take top 3
                    notification_list.sort(key=lambda x: x['created_at'], reverse=True)
                    top_notifications = notification_list[:3]
                except Exception as e:
                    pass
                
                # Calculate unread count
                unread_count = Notification.objects.filter(user=request.user, is_read=False).count()
                
                return {
                    'instructor_info': {
                        'username': request.user.username,
                        'name': f"{request.user.first_name} {request.user.last_name}".strip() or request.user.username,
                        'faculty': profile.faculty.name if profile.faculty else '-',
                        'department': profile.department if profile else '-',
                    },
                    'unread_notifications_count': unread_count,
                    'unread_notifications': top_notifications,  # Show last 3 announcements (read or unread)
                }
        except AttributeError:
            pass
    return {'instructor_info': None, 'unread_notifications_count': 0, 'unread_notifications': []}

def faculty_head_info(request):
    if request.user.is_authenticated:
        try:
            profile = request.user.profile
            if profile and profile.role == 'faculty_head':
                top_notifications = []
                unread_count = 0
                
                try:
                    from .models import Announcement
                    from django.db.models import Q
                    from django.urls import reverse
                    
                    # Get faculty head's department
                    faculty_head_department = profile.department
                    
                    # Get courses in the faculty head's department
                    from .models import Course
                    department_courses = Course.objects.filter(department=faculty_head_department)
                    department_course_names = set(department_courses.values_list('name', flat=True))
                    
                    # Get only received announcements (not sent by faculty head)
                    all_announcements = list(Announcement.objects.filter(
                        Q(receiver=request.user) & ~Q(sender=request.user)
                    ).select_related('sender').order_by('-created_at')[:50])
                    
                    notification_list = []
                    for ann in all_announcements:
                        # Filter course-specific announcements by department
                        is_course_broadcast = ann.subject.startswith('__COURSE:')
                        if is_course_broadcast:
                            marker_end = ann.subject.find('__', 9)
                            if marker_end > 0:
                                course_name_from_marker = ann.subject[9:marker_end]
                                if course_name_from_marker not in department_course_names:
                                    continue  # Skip if not in department
                        
                        is_read = ann.read_by.filter(id=request.user.id).exists()
                        sender_name = ann.sender.get_full_name() or ann.sender.username
                        
                        # Clean subject for display
                        display_subject = ann.subject
                        if display_subject.startswith('__COURSE:'):
                            marker_end = display_subject.find('__', 9)
                            if marker_end > 0:
                                display_subject = display_subject[marker_end + 2:]
                        
                        notification_list.append({
                            'title': display_subject or 'New Announcement',
                            'message': ann.message[:100] + ('...' if len(ann.message) > 100 else ''),
                            'url': reverse('faculty-head-announcements'),
                            'created_at': ann.created_at,
                            'id': f"ann_{ann.id}",
                            'type': 'announcement',
                            'announcement_id': ann.id,
                            'sender': sender_name,
                            'is_read': is_read,
                        })
                    
                    notification_list.sort(key=lambda x: x['created_at'], reverse=True)
                    top_notifications = notification_list[:3]
                    
                    # Calculate unread count (only received announcements)
                    unread_count = Announcement.objects.filter(
                        Q(receiver=request.user) & ~Q(sender=request.user)
                    ).exclude(read_by=request.user).count()
                except Exception as e:
                    pass
                
                return {
                    'faculty_head_info': {
                        'username': request.user.username,
                        'name': f"{request.user.first_name} {request.user.last_name}".strip() or request.user.username,
                        'faculty': profile.faculty.name if profile.faculty else '-',
                        'department': profile.department if profile else '-',
                    },
                    'faculty_head_unread_notifications_count': unread_count,
                    'faculty_head_unread_notifications': top_notifications,
                    # Also set unread_notifications for template compatibility
                    'unread_notifications_count': unread_count,
                    'unread_notifications': top_notifications,
                }
        except AttributeError:
            pass
    return {
        'faculty_head_info': None,
        'faculty_head_unread_notifications_count': 0,
        'faculty_head_unread_notifications': [],
        'unread_notifications_count': 0,
        'unread_notifications': [],
    }

