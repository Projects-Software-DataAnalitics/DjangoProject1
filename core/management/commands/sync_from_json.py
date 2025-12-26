import json
import os
from django.core.management.base import BaseCommand
from django.contrib.auth.models import User
from django.conf import settings
from core.models import Student, Course, UserProfile, Faculty


class Command(BaseCommand):
    help = 'Sync users from JSON files to database'

    def handle(self, *args, **options):
        self.stdout.write('Starting sync from JSON files...')
        
        faculty, _ = Faculty.objects.get_or_create(
            name='Engineering',
            defaults={'slug': 'engineering'}
        )
        
        students_path = os.path.join(settings.BASE_DIR, 'static', 'json', 'students.json')
        instructors_path = os.path.join(settings.BASE_DIR, 'static', 'json', 'instructors.json')
        faculty_heads_path = os.path.join(settings.BASE_DIR, 'static', 'json', 'faculty_heads.json')
        
        students_data = []
        instructors_data = []
        faculty_heads_data = []
        
        if os.path.exists(students_path):
            with open(students_path, encoding='utf-8') as f:
                students_data = json.load(f)
        
        if os.path.exists(instructors_path):
            with open(instructors_path, encoding='utf-8') as f:
                instructors_data = json.load(f)
        
        if os.path.exists(faculty_heads_path):
            with open(faculty_heads_path, encoding='utf-8') as f:
                faculty_heads_data = json.load(f)
        
        all_courses = {}
        
        for student_data in students_data:
            username = student_data.get('username')
            if not username:
                continue
            
            user, created = User.objects.get_or_create(
                username=username,
                defaults={
                    'first_name': student_data.get('firstName', ''),
                    'last_name': student_data.get('lastName', ''),
                }
            )
            
            if not created:
                user.first_name = student_data.get('firstName', '')
                user.last_name = student_data.get('lastName', '')
                user.save()
            
            if student_data.get('password'):
                user.set_password(student_data['password'])
                user.save()
            
            student, _ = Student.objects.get_or_create(
                username=username,
                defaults={
                    'student_id': student_data.get('student_id', username),
                    'first_name': student_data.get('firstName', ''),
                    'last_name': student_data.get('lastName', ''),
                    'department': student_data.get('department', ''),
                    'year': int(student_data['year']) if isinstance(student_data.get('year'), str) and student_data.get('year').isdigit() else student_data.get('year'),
                    'user': user,
                }
            )
            
            if not _:
                student.first_name = student_data.get('firstName', '')
                student.last_name = student_data.get('lastName', '')
                student.department = student_data.get('department', '')
                student.year = int(student_data['year']) if isinstance(student_data.get('year'), str) and student_data.get('year').isdigit() else student_data.get('year')
                student.user = user
                student.save()
            
            # Clear existing courses and add new ones from JSON
            student.courses.clear()
            for course_name in student_data.get('courses', []):
                course_obj = Course.objects.filter(name=course_name).first()
                if course_obj:
                    student.courses.add(course_obj)
            
            self.stdout.write(self.style.SUCCESS(f'Synced student: {username}'))
        
        for instructor_data in instructors_data:
            username = instructor_data.get('username')
            if not username:
                continue
            
            user, created = User.objects.get_or_create(
                username=username,
                defaults={
                    'first_name': instructor_data.get('firstName', ''),
                    'last_name': instructor_data.get('lastName', ''),
                }
            )
            
            if not created:
                user.first_name = instructor_data.get('firstName', '')
                user.last_name = instructor_data.get('lastName', '')
                user.save()
            
            if instructor_data.get('password'):
                user.set_password(instructor_data['password'])
                user.save()
            
            profile, _ = UserProfile.objects.get_or_create(
                user=user,
                defaults={
                    'role': 'instructor',
                    'department': instructor_data.get('department', ''),
                    'faculty': faculty,
                }
            )
            
            if not _:
                profile.role = 'instructor'
                profile.department = instructor_data.get('department', '')
                profile.faculty = faculty
                profile.save()
            
            # Clear existing courses for instructor
            profile.courses.clear()
            
            for course_name in instructor_data.get('courses', []):
                if course_name not in all_courses:
                    all_courses[course_name] = []
                all_courses[course_name].append(profile)
            
            self.stdout.write(self.style.SUCCESS(f'Synced instructor: {username}'))
        
        for faculty_head_data in faculty_heads_data:
            username = faculty_head_data.get('username')
            if not username:
                continue
            
            user, created = User.objects.get_or_create(
                username=username,
                defaults={
                    'first_name': faculty_head_data.get('firstName', ''),
                    'last_name': faculty_head_data.get('lastName', ''),
                }
            )
            
            if not created:
                user.first_name = faculty_head_data.get('firstName', '')
                user.last_name = faculty_head_data.get('lastName', '')
                user.save()
            
            if faculty_head_data.get('password'):
                user.set_password(faculty_head_data['password'])
                user.save()
            
            profile, _ = UserProfile.objects.get_or_create(
                user=user,
                defaults={
                    'role': 'faculty_head',
                    'department': faculty_head_data.get('department', ''),
                    'faculty': faculty,
                }
            )
            
            if not _:
                profile.role = 'faculty_head'
                profile.department = faculty_head_data.get('department', '')
                profile.faculty = faculty
                profile.save()
            
            for course_name in faculty_head_data.get('courses', []):
                if course_name not in all_courses:
                    all_courses[course_name] = []
                all_courses[course_name].append(profile)
            
            self.stdout.write(self.style.SUCCESS(f'Synced faculty head: {username}'))
        
        course_instructor_map = {}
        for instructor_data in instructors_data:
            username = instructor_data.get('username')
            if username:
                try:
                    user = User.objects.get(username=username)
                    for course_name in instructor_data.get('courses', []):
                        if course_name not in course_instructor_map:
                            course_instructor_map[course_name] = user
                except User.DoesNotExist:
                    pass
        
        for faculty_head_data in faculty_heads_data:
            username = faculty_head_data.get('username')
            if username:
                try:
                    user = User.objects.get(username=username)
                    for course_name in faculty_head_data.get('courses', []):
                        if course_name not in course_instructor_map:
                            course_instructor_map[course_name] = user
                except User.DoesNotExist:
                    pass
        
        default_instructor = UserProfile.objects.filter(role='instructor').first()
        default_instructor_user = default_instructor.user if default_instructor else User.objects.first()
        
        for course_name in sorted(all_courses.keys()):
            department = instructors_data[0].get('department', '') if instructors_data else (
                faculty_heads_data[0].get('department', '') if faculty_heads_data else ''
            )
            
            instructor_user = course_instructor_map.get(course_name, default_instructor_user)
            
            course, created = Course.objects.get_or_create(
                name=course_name,
                defaults={
                    'code': '',
                    'department': department,
                    'instructor': instructor_user,
                }
            )
            
            if not created:
                course.department = department
                course.instructor = instructor_user
                course.save()
            
            for profile in all_courses[course_name]:
                profile.courses.add(course)
            
            self.stdout.write(self.style.SUCCESS(f'Synced course: {course_name} (instructor: {instructor_user.username})'))
        
        self.stdout.write(self.style.SUCCESS('\nSync completed successfully!'))

