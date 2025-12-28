from django.core.management.base import BaseCommand
from django.utils import timezone
from datetime import timedelta
from core.models import Assignment, Notification, Announcement, Student

class Command(BaseCommand):
    help = 'Check assignment deadlines and create notifications/announcements 1 day before deadline'

    def handle(self, *args, **options):
        # Get assignments that have deadline in 1 day (between 23-25 hours from now)
        now = timezone.now()
        one_day_later = now + timedelta(days=1)
        one_day_earlier = now + timedelta(hours=23)
        
        assignments = Assignment.objects.filter(
            deadline__gte=one_day_earlier,
            deadline__lte=one_day_later
        )
        
        for assignment in assignments:
            # Get all students enrolled in the course
            students = assignment.course.students.all()
            
            for student in students:
                if not student.user:
                    continue
                
                # Check if notification already exists for this assignment and student
                existing_notification = Notification.objects.filter(
                    user=student.user,
                    assignment=assignment,
                    notification_type='assignment_deadline'
                ).first()
                
                if not existing_notification:
                    # Create notification
                    Notification.objects.create(
                        user=student.user,
                        notification_type='assignment_deadline',
                        title=f'Assignment Deadline Reminder: {assignment.title}',
                        message=f'The assignment "{assignment.title}" for {assignment.course.name} is due in 1 day.',
                        assignment=assignment
                    )
            
            # Create announcement for all students in the course
            announcement_message = f'Reminder: Assignment "{assignment.title}" for {assignment.course.name} is due in 1 day. Please submit your work before the deadline.'
            
            # Check if announcement already exists
            existing_announcement = Announcement.objects.filter(
                subject=f'Assignment Deadline: {assignment.title}',
                message=announcement_message,
                created_at__gte=now - timedelta(hours=2)
            ).first()
            
            if not existing_announcement:
                # Create announcement (sent to all students in the course)
                Announcement.objects.create(
                    sender=assignment.created_by,
                    receiver=None,  # None means all students
                    subject=f'Assignment Deadline: {assignment.title}',
                    message=announcement_message,
                    sender_role='instructor' if assignment.created_by.profile.role == 'instructor' else 'faculty_head'
                )
        
        self.stdout.write(self.style.SUCCESS(f'Checked {assignments.count()} assignments for deadline reminders'))

