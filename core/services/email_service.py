"""
Email service for sending notifications to students
"""
from django.core.mail import send_mail
from django.conf import settings
from django.template.loader import render_to_string
from django.utils.html import strip_tags


def send_announcement_email(student, announcement):
    """
    Send email notification to student about a new announcement
    
    Args:
        student: Student model instance
        announcement: Announcement model instance
    
    Returns:
        bool: True if email sent successfully, False otherwise
    """
    if not student.email:
        return False
    
    subject = f"New Announcement: {announcement.subject}"
    
    # Create email message
    sender_name = announcement.sender.get_full_name() or announcement.sender.username
    message = f"""
Hello {student.first_name or student.username},

You have received a new announcement:

Subject: {announcement.subject}

Message:
{announcement.message}

From: {sender_name}
Date: {announcement.created_at.strftime('%d/%m/%Y %H:%M')}

---
This is an automated message from the University Management System.
"""
    
    try:
        send_mail(
            subject=subject,
            message=strip_tags(message),
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[student.email],
            fail_silently=False,
        )
        return True
    except Exception as e:
        print(f"Email error for {student.email}: {e}")
        import traceback
        print("Full error traceback:")
        traceback.print_exc()
        return False


def send_assignment_email(student, assignment):
    """
    Send email notification to student about a new assignment
    
    Args:
        student: Student model instance
        assignment: Assignment model instance
    
    Returns:
        bool: True if email sent successfully, False otherwise
    """
    if not student.email:
        return False
    
    subject = f"New Assignment: {assignment.title}"
    
    # Create email message
    creator_name = assignment.created_by.get_full_name() or assignment.created_by.username
    deadline_str = assignment.deadline.strftime('%d/%m/%Y %H:%M')
    
    message = f"""
Hello {student.first_name or student.username},

A new assignment has been added to your course:

Course: {assignment.course.name}
Title: {assignment.title}

Details:
{assignment.details}

Deadline: {deadline_str}
Created by: {creator_name}
"""
    
    if assignment.file:
        message += f"\nFile attached: {assignment.file.name.split('/')[-1]}"
    
    message += "\n\n---\nThis is an automated message from the University Management System."
    
    try:
        send_mail(
            subject=subject,
            message=strip_tags(message),
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[student.email],
            fail_silently=False,
        )
        return True
    except Exception as e:
        print(f"Email error for {student.email}: {e}")
        import traceback
        print("Full error traceback:")
        traceback.print_exc()
        return False


def send_bulk_emails(students, email_type, **kwargs):
    """
    Send emails to multiple students
    
    Args:
        students: QuerySet or list of Student instances
        email_type: 'announcement' or 'assignment'
        **kwargs: Additional arguments (announcement or assignment)
    
    Returns:
        dict: {'sent': count, 'failed': count}
    """
    sent = 0
    failed = 0
    
    for student in students:
        try:
            if email_type == 'announcement' and 'announcement' in kwargs:
                success = send_announcement_email(student, kwargs['announcement'])
            elif email_type == 'assignment' and 'assignment' in kwargs:
                success = send_assignment_email(student, kwargs['assignment'])
            else:
                continue
            
            if success:
                sent += 1
            else:
                failed += 1
        except Exception as e:
            print(f"Error sending email to {student.username}: {e}")
            failed += 1
    
    return {'sent': sent, 'failed': failed}

