"""
Debug script to check notifications and context processor
Run this in Django shell: python manage.py shell < debug_notifications.py
Or run: python manage.py shell
Then copy-paste the code below
"""

from django.contrib.auth.models import User
from core.models import Notification, Student, Course, Assignment, Announcement
from core.context_processors import student_info
from django.test import RequestFactory
from django.db.models import Q

# Check if models exist
print("=== Checking Models ===")
print(f"Notification model exists: {Notification is not None}")
print(f"Announcement model exists: {Announcement is not None}")
print(f"Assignment model exists: {Assignment is not None}")

# Check all notifications
all_notifications = Notification.objects.all()
print(f"\n=== Total Notifications in DB: {all_notifications.count()} ===")
for notif in all_notifications[:5]:
    print(f"- User: {notif.user.username}, Title: {notif.title}, Read: {notif.is_read}, Assignment: {notif.assignment}")

# Check unread notifications
unread_notifications = Notification.objects.filter(is_read=False)
print(f"\n=== Unread Notifications: {unread_notifications.count()} ===")
for notif in unread_notifications[:5]:
    print(f"- User: {notif.user.username}, Title: {notif.title}")

# Check announcements
all_announcements = Announcement.objects.all()
print(f"\n=== Total Announcements in DB: {all_announcements.count()} ===")
for ann in all_announcements[:5]:
    read_by_count = ann.read_by.count()
    print(f"- Subject: {ann.subject[:50]}, Sender: {ann.sender.username}, Receiver: {ann.receiver.username if ann.receiver else 'Everyone'}, Read by: {read_by_count} users")

# Check assignments
all_assignments = Assignment.objects.all()
print(f"\n=== Total Assignments in DB: {all_assignments.count()} ===")
for assignment in all_assignments[:5]:
    print(f"- Title: {assignment.title}, Course: {assignment.course.name}, Created: {assignment.created_at}")

# Test context processor with a student
print("\n=== Testing Context Processor ===")
students = Student.objects.all()[:3]
for student in students:
    if student.user:
        print(f"\n--- Testing for Student: {student.username} (User: {student.user.username}) ---")
        
        # Get notifications for this user
        user_notifications = Notification.objects.filter(user=student.user, is_read=False)
        print(f"Unread notifications for user: {user_notifications.count()}")
        
        # Get unread announcements
        unread_anns = Announcement.objects.filter(
            (Q(receiver=student.user) | Q(receiver__isnull=True))
        ).exclude(read_by=student.user)
        print(f"Unread announcements for user: {unread_anns.count()}")
        
        # Get student courses
        student_courses = student.courses.all()
        print(f"Student courses: {student_courses.count()}")
        
        # Get assignments from student courses
        assignments = Assignment.objects.filter(course__in=student_courses)
        print(f"Assignments in student courses: {assignments.count()}")
        
        # Test context processor
        factory = RequestFactory()
        request = factory.get('/')
        request.user = student.user
        
        try:
            context = student_info(request)
            print(f"Context processor result:")
            print(f"  - unread_notifications_count: {context.get('unread_notifications_count', 0)}")
            print(f"  - unread_notifications list length: {len(context.get('unread_notifications', []))}")
            print(f"  - First 3 notifications:")
            for notif in context.get('unread_notifications', [])[:3]:
                print(f"    * {notif.get('title', 'No title')} (Type: {notif.get('type', 'unknown')})")
        except Exception as e:
            print(f"ERROR in context processor: {e}")
            import traceback
            traceback.print_exc()

print("\n=== Debug Complete ===")
