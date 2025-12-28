from .models import Student, Notification, Announcement, Assignment
from django.db.models import Q

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
            
            # Get unread announcements (not read by user)
            try:
                unread_announcements = Announcement.objects.filter(
                    (Q(receiver=request.user) | Q(receiver__isnull=True))
                ).exclude(read_by=request.user).select_related('sender').order_by('-created_at')[:10]
            except Exception as e:
                import sys
                print(f"ERROR getting announcements for {request.user.username}: {e}", file=sys.stderr)
                import traceback
                traceback.print_exc(file=sys.stderr)
                unread_announcements = Announcement.objects.none()
            
            # Get recent assignments from student's courses
            try:
                student_courses = student.courses.all()
                recent_assignments = Assignment.objects.filter(
                    course__in=student_courses
                ).select_related('course', 'created_by').order_by('-created_at')[:10]
            except Exception as e:
                import sys
                print(f"ERROR getting assignments for {request.user.username}: {e}", file=sys.stderr)
                import traceback
                traceback.print_exc(file=sys.stderr)
                recent_assignments = Assignment.objects.none()
            
            # Combine all notifications
            all_notifications = []
            
            # Add Notification objects
            for notif in unread_notifications_list:
                all_notifications.append({
                    'id': f"notif_{notif.id}",
                    'title': notif.title,
                    'message': notif.message,
                    'created_at': notif.created_at,
                    'is_assignment': notif.assignment is not None,
                    'assignment_id': notif.assignment.id if notif.assignment else None,
                    'announcement_id': notif.announcement.id if notif.announcement else None,
                    'type': 'notification'
                })
            
            # Add Announcement objects
            for ann in unread_announcements:
                # Clean subject
                display_subject = ann.subject
                if display_subject.startswith('__COURSE:'):
                    marker_end = display_subject.find('__', 9)
                    if marker_end > 0:
                        display_subject = display_subject[marker_end + 2:]
                
                all_notifications.append({
                    'id': f"ann_{ann.id}",
                    'title': display_subject,
                    'message': ann.message,
                    'created_at': ann.created_at,
                    'is_assignment': False,
                    'assignment_id': None,
                    'type': 'announcement',
                    'announcement_id': ann.id
                })
            
            # Count assignments that don't have notifications (before adding them to list)
            from datetime import timedelta
            from django.utils import timezone
            assignments_without_notifications = 0
            assignment_notifications_to_add = []
            
            for assignment in recent_assignments:
                # Check if there's already a notification for this assignment
                has_notification = any(n.get('assignment_id') == assignment.id for n in all_notifications)
                if not has_notification:
                    # Only show assignments from last 7 days to avoid too many notifications
                    if assignment.created_at >= timezone.now() - timedelta(days=7):
                        assignments_without_notifications += 1
                        assignment_notifications_to_add.append({
                            'id': f"assignment_{assignment.id}",
                            'title': f"New Assignment: {assignment.title}",
                            'message': f"A new assignment has been added to {assignment.course.name}",
                            'created_at': assignment.created_at,
                            'is_assignment': True,
                            'assignment_id': assignment.id,
                            'type': 'assignment'
                        })
            
            # Add assignment notifications
            all_notifications.extend(assignment_notifications_to_add)
            
            # Sort by created_at (most recent first) and take top 10
            all_notifications.sort(key=lambda x: x['created_at'], reverse=True)
            all_notifications = all_notifications[:10]
            
            # Count total unread (notifications + announcements + assignments without notifications)
            unread_count = len(unread_notifications_list) + unread_announcements.count() + assignments_without_notifications
            
            return {
                'student_info': {
                    'username': student.username,
                    'name': f"{student.first_name} {student.last_name}".strip() or student.username,
                    'student_id': student.student_id,
                },
                'unread_notifications_count': unread_count,
                'unread_notifications': all_notifications
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
                'unread_notifications': []
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
            # Return empty but with debug info
            return {
                'student_info': {
                    'username': request.user.username if request.user.is_authenticated else 'anonymous',
                    'name': request.user.get_full_name() or request.user.username if request.user.is_authenticated else 'anonymous',
                    'student_id': '-',
                },
                'unread_notifications_count': 0, 
                'unread_notifications': [],
                'debug_error': str(e)
            }
    
    return {'student_info': None, 'unread_notifications_count': 0, 'unread_notifications': []}

def instructor_info(request):
    if request.user.is_authenticated:
        try:
            profile = request.user.profile
            if profile and profile.role == 'instructor':
                unread_count = Notification.objects.filter(user=request.user, is_read=False).count()
                unread_notifications = list(Notification.objects.filter(user=request.user, is_read=False).order_by('-created_at')[:10])
                return {
                    'instructor_info': {
                        'username': request.user.username,
                        'name': f"{request.user.first_name} {request.user.last_name}".strip() or request.user.username,
                        'faculty': profile.faculty.name if profile.faculty else '-',
                        'department': profile.department if profile else '-',
                    },
                    'unread_notifications_count': unread_count,
                    'unread_notifications': unread_notifications
                }
        except AttributeError:
            pass
    return {'instructor_info': None, 'unread_notifications_count': 0, 'unread_notifications': []}

def faculty_head_info(request):
    if request.user.is_authenticated:
        try:
            profile = request.user.profile
            if profile and profile.role == 'faculty_head':
                return {
                    'faculty_head_info': {
                        'username': request.user.username,
                        'name': f"{request.user.first_name} {request.user.last_name}".strip() or request.user.username,
                        'faculty': profile.faculty.name if profile.faculty else '-',
                        'department': profile.department if profile else '-',
                    }
                }
        except AttributeError:
            pass
    return {'faculty_head_info': None}

