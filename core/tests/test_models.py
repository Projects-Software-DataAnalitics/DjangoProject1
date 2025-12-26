from django.test import TestCase
from django.contrib.auth.models import User
from core.models import Student, Course, Grade, Faculty, UserProfile, Announcement


class StudentModelTest(TestCase):
    def setUp(self):
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

    def test_student_creation(self):
        self.assertEqual(self.student.username, 'teststudent')
        self.assertEqual(self.student.student_id, 'ST001')
        self.assertEqual(self.student.first_name, 'Test')
        self.assertEqual(self.student.last_name, 'Student')
        self.assertEqual(self.student.department, 'Computer Engineering')
        self.assertEqual(self.student.year, 3)
        self.assertEqual(self.student.user, self.user)

    def test_student_user_relationship(self):
        self.assertEqual(self.student.user, self.user)
        self.assertEqual(self.user.student_profile, self.student)
        self.assertIsNotNone(self.student.user)

    def test_student_courses_relationship(self):
        instructor = User.objects.create_user(
            username='instructor1',
            password='testpass123'
        )
        course1 = Course.objects.create(
            name='Data Structures',
            code='CS201',
            instructor=instructor,
            credits=3
        )
        course2 = Course.objects.create(
            name='Algorithms',
            code='CS202',
            instructor=instructor,
            credits=4
        )
        
        self.student.courses.add(course1, course2)
        
        self.assertEqual(self.student.courses.count(), 2)
        self.assertIn(course1, self.student.courses.all())
        self.assertIn(course2, self.student.courses.all())


class CourseModelTest(TestCase):
    def setUp(self):
        self.instructor = User.objects.create_user(
            username='instructor1',
            password='testpass123',
            first_name='John',
            last_name='Doe'
        )

    def test_course_creation(self):
        course = Course.objects.create(
            name='Software Engineering',
            code='CS301',
            instructor=self.instructor,
            department='Computer Engineering',
            credits=3
        )
        
        self.assertEqual(course.name, 'Software Engineering')
        self.assertEqual(course.code, 'CS301')
        self.assertEqual(course.instructor, self.instructor)
        self.assertEqual(course.department, 'Computer Engineering')
        self.assertEqual(course.credits, 3)

    def test_course_string_representation(self):
        course_with_code = Course.objects.create(
            name='Database Systems',
            code='CS302',
            instructor=self.instructor
        )
        course_without_code = Course.objects.create(
            name='Operating Systems',
            instructor=self.instructor
        )
        
        self.assertEqual(str(course_with_code), 'CS302 - Database Systems')
        self.assertEqual(str(course_without_code), 'Operating Systems')


class GradeModelTest(TestCase):
    def setUp(self):
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

    def test_grade_creation(self):
        course2 = Course.objects.create(
            name='Algorithms',
            code='CS202',
            instructor=self.instructor,
            credits=4
        )
        
        grade_old_format = Grade.objects.create(
            student=self.student,
            course=self.course,
            midterm=85.0,
            assignment=90.0,
            final=88.0
        )
        
        self.assertEqual(grade_old_format.student, self.student)
        self.assertEqual(grade_old_format.course, self.course)
        self.assertEqual(grade_old_format.midterm, 85.0)
        self.assertEqual(grade_old_format.assignment, 90.0)
        self.assertEqual(grade_old_format.final, 88.0)
        
        grade_new_format = Grade.objects.create(
            student=self.student,
            course=course2,
            grades={'Midterm': 85, 'Final': 90, 'Project': 95}
        )
        
        self.assertEqual(grade_new_format.grades['Midterm'], 85)
        self.assertEqual(grade_new_format.grades['Final'], 90)
        self.assertEqual(grade_new_format.grades['Project'], 95)

    def test_grade_unique_constraint(self):
        Grade.objects.create(
            student=self.student,
            course=self.course,
            midterm=85.0
        )
        
        with self.assertRaises(Exception):
            Grade.objects.create(
                student=self.student,
                course=self.course,
                midterm=90.0
            )


class AnnouncementModelTest(TestCase):
    def setUp(self):
        self.instructor = User.objects.create_user(
            username='instructor1',
            password='testpass123',
            first_name='John',
            last_name='Doe'
        )
        self.student_user = User.objects.create_user(
            username='student1',
            password='testpass123'
        )

    def test_announcement_creation(self):
        announcement = Announcement.objects.create(
            sender=self.instructor,
            receiver=self.student_user,
            subject='Test Subject',
            message='Test message content',
            sender_role='instructor'
        )
        
        self.assertEqual(announcement.sender, self.instructor)
        self.assertEqual(announcement.receiver, self.student_user)
        self.assertEqual(announcement.subject, 'Test Subject')
        self.assertEqual(announcement.message, 'Test message content')
        self.assertEqual(announcement.sender_role, 'instructor')

    def test_announcement_broadcast(self):
        announcement = Announcement.objects.create(
            sender=self.instructor,
            receiver=None,
            subject='Broadcast Announcement',
            message='This is for everyone',
            sender_role='instructor'
        )
        
        self.assertIsNone(announcement.receiver)
        self.assertEqual(str(announcement), 'instructor1 -> Everyone: Broadcast Announcement')

