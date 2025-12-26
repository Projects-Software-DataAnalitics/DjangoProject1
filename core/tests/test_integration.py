from django.test import TestCase
from django.contrib.auth.models import User
from core.models import Student, Course, Grade


class EdgeCasesIntegrationTest(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username='teststudent',
            password='testpass123'
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

    def test_student_without_user(self):
        student = Student.objects.create(
            username='nostudent',
            student_id='ST002',
            first_name='No',
            last_name='User',
            user=None
        )
        
        self.assertIsNone(student.user)
        self.assertEqual(student.username, 'nostudent')
        self.assertEqual(str(student), 'nostudent')

    def test_grade_both_formats(self):
        student = Student.objects.create(
            username='teststudent',
            student_id='ST001',
            user=self.user
        )
        student.courses.add(self.course)
        
        grade = Grade.objects.create(
            student=student,
            course=self.course,
            midterm=85.0,
            assignment=90.0,
            final=88.0,
            grades={'Project': 95, 'Quiz': 80}
        )
        
        self.assertEqual(grade.midterm, 85.0)
        self.assertEqual(grade.assignment, 90.0)
        self.assertEqual(grade.final, 88.0)
        self.assertEqual(grade.grades['Project'], 95)
        self.assertEqual(grade.grades['Quiz'], 80)
        self.assertEqual(len(grade.grades), 2)

