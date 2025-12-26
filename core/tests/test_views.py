from django.test import TestCase, Client
from django.contrib.auth.models import User
from django.urls import reverse
from datetime import datetime
from core.models import Student, Course, Grade, Faculty, UserProfile, Announcement, ProgramOutcome


class StudentDashboardViewTest(TestCase):
    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user(
            username='teststudent',
            password='testpass123',
            first_name='Test',
            last_name='Student'
        )
        self.student = Student.objects.create(
            username='teststudent',
            student_id='ST001',
            first_name='Test',
            last_name='Student',
            department='Computer Engineering',
            year=3,
            user=self.user
        )
        self.instructor = User.objects.create_user(
            username='instructor1',
            password='testpass123',
            first_name='John',
            last_name='Doe'
        )
        self.course = Course.objects.create(
            name='Data Structures',
            code='CS201',
            instructor=self.instructor,
            credits=3
        )
        self.student.courses.add(self.course)
        
        self.faculty = Faculty.objects.create(
            name='Engineering',
            slug='engineering'
        )
        self.instructor_profile = UserProfile.objects.create(
            user=self.instructor,
            role='instructor',
            faculty=self.faculty
        )
        
        self.announcement = Announcement.objects.create(
            sender=self.instructor,
            receiver=None,
            subject='Test Announcement',
            message='This is a test announcement',
            sender_role='instructor'
        )

    def test_student_dashboard_requires_authentication(self):
        response = self.client.get(reverse('student'))
        self.assertEqual(response.status_code, 302)
        self.assertIn('/student-login', response.url)

    def test_student_dashboard_authenticated(self):
        self.client.force_login(self.user)
        response = self.client.get(reverse('student'))
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'student.html')

    def test_student_dashboard_academic_term_calculation(self):
        self.client.force_login(self.user)
        response = self.client.get(reverse('student'))
        
        self.assertEqual(response.status_code, 200)
        self.assertIn('academic_term', response.context)
        
        academic_term = response.context['academic_term']
        self.assertIsNotNone(academic_term)
        self.assertNotEqual(academic_term, '-')
        
        current_month = datetime.now().month
        current_year = datetime.now().year
        
        if current_month >= 9:
            expected_term = f"{current_year}-{current_year + 1} Fall"
        elif current_month >= 2:
            expected_term = f"{current_year - 1}-{current_year} Spring"
        else:
            expected_term = f"{current_year - 1}-{current_year} Fall"
        
        self.assertEqual(academic_term, expected_term)
        self.assertIn('Fall', academic_term) if current_month >= 9 or current_month < 2 else self.assertIn('Spring', academic_term)

    def test_student_dashboard_context_data(self):
        self.client.force_login(self.user)
        response = self.client.get(reverse('student'))
        
        self.assertEqual(response.status_code, 200)
        self.assertIn('student_info', response.context)
        self.assertIn('academic_term', response.context)
        self.assertIn('year_display', response.context)
        self.assertIn('department_display', response.context)
        self.assertIn('advisor_name', response.context)
        self.assertIn('courses_list', response.context)
        self.assertIn('latest_announcements', response.context)
        
        self.assertEqual(response.context['student_info']['username'], 'teststudent')
        self.assertEqual(response.context['student_info']['student_id'], 'ST001')
        self.assertEqual(response.context['year_display'], '3. Year')
        self.assertEqual(response.context['department_display'], 'Computer Engineering')
        self.assertEqual(len(response.context['courses_list']), 1)
        self.assertEqual(response.context['courses_list'][0]['name'], 'Data Structures')
        self.assertEqual(len(response.context['latest_announcements']), 1)


class StudentProfileViewTest(TestCase):
    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user(
            username='teststudent',
            password='testpass123',
            first_name='Test',
            last_name='Student'
        )
        self.student = Student.objects.create(
            username='teststudent',
            student_id='ST001',
            first_name='Test',
            last_name='Student',
            department='Computer Engineering',
            year=3,
            user=self.user
        )
        self.instructor = User.objects.create_user(
            username='instructor1',
            password='testpass123'
        )
        self.course = Course.objects.create(
            name='Data Structures',
            code='CS201',
            instructor=self.instructor,
            credits=3
        )
        self.student.courses.add(self.course)

    def test_student_profile_authenticated(self):
        self.client.force_login(self.user)
        response = self.client.get(reverse('student_profile'))
        
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'student/profile.html')
        self.assertIn('profile', response.context)
        self.assertEqual(response.context['profile']['username'], 'teststudent')
        self.assertEqual(response.context['profile']['student_id'], 'ST001')
        self.assertEqual(response.context['profile']['department'], 'Computer Engineering')
        self.assertEqual(response.context['profile']['year'], 3)
        self.assertIn('Data Structures', response.context['profile']['courses'])

    def test_student_profile_no_student_record(self):
        user_no_student = User.objects.create_user(
            username='nostudent',
            password='testpass123'
        )
        self.client.force_login(user_no_student)
        response = self.client.get(reverse('student_profile'))
        
        self.assertEqual(response.status_code, 200)
        self.assertIn('profile', response.context)
        self.assertEqual(response.context['profile']['username'], 'nostudent')
        self.assertEqual(response.context['profile']['student_id'], '-')


class StudentCoursesViewTest(TestCase):
    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user(
            username='teststudent',
            password='testpass123'
        )
        self.student = Student.objects.create(
            username='teststudent',
            student_id='ST001',
            user=self.user
        )
        self.instructor = User.objects.create_user(
            username='instructor1',
            password='testpass123',
            first_name='John',
            last_name='Doe'
        )

    def test_student_courses_with_courses(self):
        course1 = Course.objects.create(
            name='Data Structures',
            code='CS201',
            instructor=self.instructor,
            credits=3
        )
        course2 = Course.objects.create(
            name='Algorithms',
            code='CS202',
            instructor=self.instructor,
            credits=4
        )
        self.student.courses.add(course1, course2)
        
        self.client.force_login(self.user)
        response = self.client.get(reverse('student_courses'))
        
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'student/courses.html')
        self.assertIn('courses', response.context)
        self.assertEqual(len(response.context['courses']), 2)
        self.assertEqual(response.context['courses'][0]['name'], 'Data Structures')
        self.assertEqual(response.context['courses'][0]['credits'], 3)
        self.assertEqual(response.context['courses'][1]['name'], 'Algorithms')
        self.assertEqual(response.context['courses'][1]['credits'], 4)

    def test_student_courses_empty(self):
        self.client.force_login(self.user)
        response = self.client.get(reverse('student_courses'))
        
        self.assertEqual(response.status_code, 200)
        self.assertIn('courses', response.context)
        self.assertEqual(len(response.context['courses']), 0)


class StudentGradesViewTest(TestCase):
    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user(
            username='teststudent',
            password='testpass123'
        )
        self.student = Student.objects.create(
            username='teststudent',
            student_id='ST001',
            user=self.user
        )
        self.instructor = User.objects.create_user(
            username='instructor1',
            password='testpass123'
        )
        self.course = Course.objects.create(
            name='Data Structures',
            code='CS201',
            instructor=self.instructor,
            credits=3
        )
        self.student.courses.add(self.course)

    def test_student_grades_with_grades(self):
        grade_old = Grade.objects.create(
            student=self.student,
            course=self.course,
            midterm=85.0,
            assignment=90.0,
            final=88.0
        )
        
        self.client.force_login(self.user)
        response = self.client.get(reverse('student_grades'))
        
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'student/grades.html')
        self.assertIn('courses_with_grades', response.context)
        self.assertEqual(len(response.context['courses_with_grades']), 1)
        self.assertEqual(response.context['courses_with_grades'][0]['course_name'], 'Data Structures')
        self.assertEqual(response.context['courses_with_grades'][0]['midterm'], 85.0)
        self.assertEqual(response.context['courses_with_grades'][0]['assignment'], 90.0)
        self.assertEqual(response.context['courses_with_grades'][0]['final'], 88.0)
        
        grade_new = Grade.objects.get(student=self.student, course=self.course)
        grade_new.grades = {'Midterm': 85, 'Final': 90, 'Project': 95}
        grade_new.save()
        
        response = self.client.get(reverse('student_grades'))
        self.assertIn('grades', response.context['courses_with_grades'][0])
        self.assertEqual(response.context['courses_with_grades'][0]['grades']['Midterm'], 85)

    def test_student_grades_no_grades(self):
        self.client.force_login(self.user)
        response = self.client.get(reverse('student_grades'))
        
        self.assertEqual(response.status_code, 200)
        self.assertIn('courses_with_grades', response.context)
        self.assertEqual(len(response.context['courses_with_grades']), 1)
        self.assertEqual(response.context['courses_with_grades'][0]['course_name'], 'Data Structures')
        self.assertIsNone(response.context['courses_with_grades'][0]['midterm'])
        self.assertIsNone(response.context['courses_with_grades'][0]['assignment'])
        self.assertIsNone(response.context['courses_with_grades'][0]['final'])


class StudentAnnouncementsViewTest(TestCase):
    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user(
            username='teststudent',
            password='testpass123'
        )
        self.student = Student.objects.create(
            username='teststudent',
            student_id='ST001',
            user=self.user
        )

    def test_student_announcements_access(self):
        self.client.force_login(self.user)
        response = self.client.get(reverse('student_announcements'))
        
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'student/student_announcement.html')


class StudentCourseLearningOutcomesViewTest(TestCase):
    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user(
            username='teststudent',
            password='testpass123'
        )
        self.student = Student.objects.create(
            username='teststudent',
            student_id='ST001',
            user=self.user
        )
        self.instructor = User.objects.create_user(
            username='instructor1',
            password='testpass123',
            first_name='John',
            last_name='Doe'
        )
        self.course = Course.objects.create(
            name='Data Structures',
            code='CS201',
            instructor=self.instructor,
            credits=3
        )
        self.student.courses.add(self.course)
        
        self.faculty = Faculty.objects.create(
            name='Engineering',
            slug='engineering'
        )
        self.instructor_profile = UserProfile.objects.create(
            user=self.instructor,
            role='instructor',
            faculty=self.faculty
        )
        
        self.program_outcome = ProgramOutcome.objects.create(
            text='Test Learning Outcome',
            course_name='Data Structures',
            created_by=self.instructor
        )

    def test_student_course_learning_outcomes_enrolled(self):
        self.client.force_login(self.user)
        response = self.client.get(reverse('student_course_learning_outcomes', args=[self.course.id]))
        
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'student/course_learning_outcomes.html')
        self.assertIn('course_name', response.context)
        self.assertIn('outcomes_data', response.context)
        self.assertEqual(response.context['course_name'], 'Data Structures')

    def test_student_course_learning_outcomes_not_enrolled(self):
        other_course = Course.objects.create(
            name='Algorithms',
            code='CS202',
            instructor=self.instructor,
            credits=4
        )
        
        self.client.force_login(self.user)
        response = self.client.get(reverse('student_course_learning_outcomes', args=[other_course.id]))
        
        self.assertEqual(response.status_code, 403)


class StudentProgramOutcomesViewTest(TestCase):
    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user(
            username='teststudent',
            password='testpass123'
        )
        self.student = Student.objects.create(
            username='teststudent',
            student_id='ST001',
            department='Computer Engineering',
            user=self.user
        )
        self.faculty = Faculty.objects.create(
            name='Engineering',
            slug='engineering'
        )
        self.faculty_head = User.objects.create_user(
            username='facultyhead1',
            password='testpass123',
            first_name='Faculty',
            last_name='Head'
        )
        self.faculty_head_profile = UserProfile.objects.create(
            user=self.faculty_head,
            role='faculty_head',
            faculty=self.faculty
        )
        self.program_outcome = ProgramOutcome.objects.create(
            text='Test Program Outcome',
            course_name='',
            faculty=self.faculty,
            created_by=self.faculty_head
        )

    def test_student_program_outcomes_access(self):
        self.client.force_login(self.user)
        response = self.client.get(reverse('student_program_outcomes'))
        
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'student/program_outcomes.html')
        self.assertIn('outcomes_data', response.context)

