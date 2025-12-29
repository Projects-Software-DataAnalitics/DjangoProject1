"""
Script to load email and phone_number from students.json to database
Run this script after adding email and phone_number to students.json
"""
import os
import django
import json

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'DjangoProject2.settings')
django.setup()

from core.models import Student
from django.conf import settings

def load_student_emails_phones():
    json_path = os.path.join(settings.BASE_DIR, 'static', 'json', 'students.json')
    
    if not os.path.exists(json_path):
        print(f"students.json not found at {json_path}")
        return
    
    with open(json_path, 'r', encoding='utf-8') as f:
        students_data = json.load(f)
    
    updated = 0
    not_found = 0
    
    for student_data in students_data:
        username = student_data.get('username')
        email = student_data.get('email', '').strip()
        phone_number = student_data.get('phone_number', '').strip()
        
        if not username:
            continue
        
        try:
            student = Student.objects.get(username=username)
            updated_fields = []
            
            if email:
                student.email = email
                updated_fields.append('email')
            
            if phone_number:
                student.phone_number = phone_number
                updated_fields.append('phone_number')
            
            if updated_fields:
                student.save(update_fields=updated_fields)
                updated += 1
                print(f"Updated {username}: {', '.join(updated_fields)}")
        except Student.DoesNotExist:
            not_found += 1
            print(f"Student not found: {username}")
    
    print(f"\nSummary: {updated} students updated, {not_found} not found")

if __name__ == '__main__':
    load_student_emails_phones()

