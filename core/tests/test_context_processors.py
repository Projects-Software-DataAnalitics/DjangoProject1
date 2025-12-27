from django.test import TestCase, RequestFactory
from django.contrib.auth.models import User
from core.models import Student
from core.context_processors import student_info


class ContextProcessorTest(TestCase):
    def setUp(self):
        self.factory = RequestFactory()
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
            user=self.user
        )

    def test_student_info_with_student(self):
        request = self.factory.get('/')
        request.user = self.user
        
        context = student_info(request)
        
        self.assertIn('student_info', context)
        self.assertIsNotNone(context['student_info'])
        self.assertEqual(context['student_info']['username'], 'teststudent')
        self.assertEqual(context['student_info']['student_id'], 'ST001')
        self.assertEqual(context['student_info']['name'], 'Test Student')

    def test_student_info_without_student(self):
        user_no_student = User.objects.create_user(
            username='nostudent',
            password='testpass123',
            first_name='No',
            last_name='Student'
        )
        
        request = self.factory.get('/')
        request.user = user_no_student
        
        context = student_info(request)
        
        self.assertIn('student_info', context)
        self.assertIsNotNone(context['student_info'])
        self.assertEqual(context['student_info']['username'], 'nostudent')
        self.assertEqual(context['student_info']['student_id'], '-')
        self.assertEqual(context['student_info']['name'], 'No Student')

    def test_student_info_unauthenticated(self):
        from django.contrib.auth.models import AnonymousUser
        
        request = self.factory.get('/')
        request.user = AnonymousUser()
        
        context = student_info(request)
        
        self.assertIn('student_info', context)
        self.assertIsNone(context['student_info'])

