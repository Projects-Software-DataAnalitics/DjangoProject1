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
            
            # Get all announcements for the student (both read and unread) - same as announcements page
            try:
                student_courses = student.courses.all()
                student_courses_set = set(student.courses.values_list('name', flat=True))
                
                # Get all announcements for the student (same query as student_announcements view)
                all_announcements = Announcement.objects.filter(
                    (Q(receiver=request.user) | Q(receiver__isnull=True))
                ).select_related('sender').order_by('-created_at', '-is_pinned')[:10]
                
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
                
                # Also get assignments from student's courses (same as announcements page)
                assignments = Assignment.objects.filter(
                    course__in=student_courses
                ).select_related('course', 'created_by').order_by('-created_at')[:10]
                
            except Exception as e:
                import sys
                print(f"ERROR getting announcements for {request.user.username}: {e}", file=sys.stderr)
                import traceback
                traceback.print_exc(file=sys.stderr)
                filtered_announcements = []
                assignments = []
            
            # Combine all notifications - Show all announcements and assignments (same as announcements page)
            all_notifications = []
            unread_count = 0
            
            # 1. Add all Announcement objects (both read and unread)
            for ann in filtered_announcements:
                # Clean subject (remove course marker if present)
                display_subject = ann.subject
                if display_subject.startswith('__COURSE:'):
                    marker_end = display_subject.find('__', 9)
                    if marker_end > 0:
                        display_subject = display_subject[marker_end + 2:]
                
                # Check if read
                is_read = ann.read_by.filter(id=request.user.id).exists()
                if not is_read:
                    unread_count += 1
                
                sender_name = ann.sender.get_full_name() or ann.sender.username
                
                all_notifications.append({
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
            
            # 2. Add assignments as announcements (same format as announcements page)
            for assignment in assignments:
                # Check if assignment has been read (via Notification model)
                assignment_read = False
                try:
                    assignment_notification = Notification.objects.filter(
                        user=request.user,
                        assignment=assignment
                    ).first()
                    if assignment_notification and assignment_notification.is_read:
                        assignment_read = True
                except:
                    pass
                
                if not assignment_read:
                    unread_count += 1
                
                creator_name = assignment.created_by.get_full_name() if assignment.created_by else None
                if not creator_name and assignment.created_by:
                    creator_name = assignment.created_by.username
                
                all_notifications.append({
                    'title': f'New Assignment: {assignment.title}',
                    'message': f'A new assignment has been added to {assignment.course.name}',
                    'url': reverse('student_announcements'),
                    'created_at': assignment.created_at,
                    'id': f"assignment_{assignment.id}",
                    'type': 'assignment',
                    'assignment_id': assignment.id,
                    'sender': creator_name or '',
                    'is_read': assignment_read,
                })
            
            # Sort by created_at (most recent first) and take top 10
            all_notifications.sort(key=lambda x: x['created_at'], reverse=True)
            all_notifications = all_notifications[:10]
            
            # Add unread notifications count
            unread_count += len(unread_notifications_list)
            
            return {
                'student_info': {
                    'username': student.username,
                    'name': f"{student.first_name} {student.last_name}".strip() or student.username,
                    'student_id': student.student_id,
                },
                'unread_notifications_count': unread_count,
                'unread_notifications': all_notifications,
                'debug_notifications': {
                    'unread_notifications_list_count': len(unread_notifications_list),
                    'announcements_count': len(filtered_announcements),
                    'assignments_count': len(assignments),
                    'all_notifications_length': len(all_notifications),
                    'total_count': unread_count
                }
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
                'debug_notifications': {
                    'unread_notifications_list_count': 0,
                    'unread_announcements_count': 0,
                    'all_notifications_length': 0,
                    'total_count': 0,
                    'error': 'Student.DoesNotExist'
                }
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
                'debug_notifications': {
                    'error': str(e),
                    'error_type': type(e).__name__
                }
            }
    
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

