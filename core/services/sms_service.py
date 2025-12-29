"""
SMS service for sending notifications to students
"""
from django.conf import settings
import os


def send_announcement_sms(student, announcement):
    """
    Send SMS notification to student about a new announcement
    
    Args:
        student: Student model instance
        announcement: Announcement model instance
    
    Returns:
        bool: True if SMS sent successfully, False otherwise
    """
    if not student.phone_number:
        return False
    
    # Check if SMS service is configured
    sms_backend = getattr(settings, 'SMS_BACKEND', 'twilio')
    
    if sms_backend == 'twilio':
        return _send_twilio_sms(student, announcement)
    elif sms_backend == 'netgsm':
        return _send_netgsm_sms(student, announcement)
    else:
        print(f"SMS backend '{sms_backend}' not implemented")
        return False


def send_assignment_sms(student, assignment):
    """
    Send SMS notification to student about a new assignment
    
    Args:
        student: Student model instance
        assignment: Assignment model instance
    
    Returns:
        bool: True if SMS sent successfully, False otherwise
    """
    if not student.phone_number:
        return False
    
    # Check if SMS service is configured
    sms_backend = getattr(settings, 'SMS_BACKEND', 'twilio')
    
    if sms_backend == 'twilio':
        return _send_twilio_sms_assignment(student, assignment)
    elif sms_backend == 'netgsm':
        return _send_netgsm_sms_assignment(student, assignment)
    else:
        print(f"SMS backend '{sms_backend}' not implemented")
        return False


def _send_twilio_sms(student, announcement):
    """
    Send SMS using Twilio service
    """
    try:
        from twilio.rest import Client
        
        account_sid = getattr(settings, 'TWILIO_ACCOUNT_SID', None)
        auth_token = getattr(settings, 'TWILIO_AUTH_TOKEN', None)
        from_number = getattr(settings, 'TWILIO_PHONE_NUMBER', None)
        
        if not all([account_sid, auth_token, from_number]):
            print("Twilio credentials not configured")
            return False
        
        client = Client(account_sid, auth_token)
        
        # Format phone number (ensure it starts with +)
        phone = student.phone_number
        if not phone.startswith('+'):
            phone = '+' + phone.lstrip('0')
        
        # Create SMS message (max 160 characters for standard SMS)
        sender_name = announcement.sender.get_full_name() or announcement.sender.username
        message_body = f"New announcement: {announcement.subject[:50]}"
        if len(announcement.subject) > 50:
            message_body += "..."
        
        message = client.messages.create(
            body=message_body,
            from_=from_number,
            to=phone
        )
        
        return message.sid is not None
    except ImportError:
        print("Twilio library not installed. Install with: pip install twilio")
        return False
    except Exception as e:
        print(f"Twilio SMS error for {student.phone_number}: {e}")
        return False


def _send_twilio_sms_assignment(student, assignment):
    """
    Send assignment SMS using Twilio service
    """
    try:
        from twilio.rest import Client
        
        account_sid = getattr(settings, 'TWILIO_ACCOUNT_SID', None)
        auth_token = getattr(settings, 'TWILIO_AUTH_TOKEN', None)
        from_number = getattr(settings, 'TWILIO_PHONE_NUMBER', None)
        
        if not all([account_sid, auth_token, from_number]):
            print("Twilio credentials not configured")
            return False
        
        client = Client(account_sid, auth_token)
        
        # Format phone number
        phone = student.phone_number
        if not phone.startswith('+'):
            phone = '+' + phone.lstrip('0')
        
        # Create SMS message
        message_body = f"New assignment: {assignment.title[:40]} - {assignment.course.name[:20]}"
        if len(assignment.title) > 40 or len(assignment.course.name) > 20:
            message_body += "..."
        
        message = client.messages.create(
            body=message_body,
            from_=from_number,
            to=phone
        )
        
        return message.sid is not None
    except ImportError:
        print("Twilio library not installed. Install with: pip install twilio")
        return False
    except Exception as e:
        print(f"Twilio SMS error for {student.phone_number}: {e}")
        return False


def _send_netgsm_sms(student, announcement):
    """
    Send SMS using NetGSM service (for Turkey)
    """
    # TODO: Implement NetGSM integration if needed
    print("NetGSM SMS not yet implemented")
    return False


def _send_netgsm_sms_assignment(student, assignment):
    """
    Send assignment SMS using NetGSM service (for Turkey)
    """
    # TODO: Implement NetGSM integration if needed
    print("NetGSM SMS not yet implemented")
    return False


def send_bulk_sms(students, sms_type, **kwargs):
    """
    Send SMS to multiple students
    
    Args:
        students: QuerySet or list of Student instances
        sms_type: 'announcement' or 'assignment'
        **kwargs: Additional arguments (announcement or assignment)
    
    Returns:
        dict: {'sent': count, 'failed': count}
    """
    sent = 0
    failed = 0
    
    for student in students:
        try:
            if sms_type == 'announcement' and 'announcement' in kwargs:
                success = send_announcement_sms(student, kwargs['announcement'])
            elif sms_type == 'assignment' and 'assignment' in kwargs:
                success = send_assignment_sms(student, kwargs['assignment'])
            else:
                continue
            
            if success:
                sent += 1
            else:
                failed += 1
        except Exception as e:
            print(f"Error sending SMS to {student.username}: {e}")
            failed += 1
    
    return {'sent': sent, 'failed': failed}

