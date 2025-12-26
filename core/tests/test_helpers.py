from django.test import TestCase
from django.contrib.auth.models import User
from django.core.cache import cache
from core.models import Student, Course, Faculty, UserProfile
from core.views import get_instructors_map, get_students_data, get_faculty_heads_map


class HelperFunctionsTest(TestCase):
    def setUp(self):
        self.faculty = Faculty.objects.create(
            name='Engineering',
            slug='engineering'
        )
        
        self.instructor1 = User.objects.create_user(
            username='instructor1',
            password='testpass123',
            first_name='John',
            last_name='Doe'
        )
        self.instructor2 = User.objects.create_user(
            username='instructor2',
            password='testpass123',
            first_name='Jane',
            last_name='Smith'
        )
        
        self.instructor1_profile = UserProfile.objects.create(
            user=self.instructor1,
            role='instructor',
            faculty=self.faculty
        )
        self.instructor2_profile = UserProfile.objects.create(
            user=self.instructor2,
            role='instructor',
            faculty=self.faculty
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
        
        self.student_user = User.objects.create_user(
            username='student1',
            password='testpass123'
        )
        self.student = Student.objects.create(
            username='student1',
            student_id='ST001',
            first_name='Student',
            last_name='One',
            department='Computer Engineering',
            year=3,
            user=self.student_user
        )

    def test_get_instructors_map(self):
        cache.clear()
        instructors_map = get_instructors_map()
        
        self.assertIsInstance(instructors_map, dict)
        self.assertIn('instructor1', instructors_map)
        self.assertIn('instructor2', instructors_map)
        self.assertEqual(instructors_map['instructor1'], 'John Doe')
        self.assertEqual(instructors_map['instructor2'], 'Jane Smith')

    def test_get_instructors_map_caching(self):
        cache.clear()
        map1 = get_instructors_map()
        
        instructor3 = User.objects.create_user(
            username='instructor3',
            password='testpass123',
            first_name='New',
            last_name='Instructor'
        )
        UserProfile.objects.create(
            user=instructor3,
            role='instructor',
            faculty=self.faculty
        )
        
        map2 = get_instructors_map()
        self.assertEqual(map1, map2)
        
        cache.clear()
        map3 = get_instructors_map()
        self.assertIn('instructor3', map3)

    def test_get_students_data(self):
        cache.clear()
        students_data = get_students_data()
        
        self.assertIsInstance(students_data, list)
        self.assertEqual(len(students_data), 1)
        self.assertEqual(students_data[0]['username'], 'student1')
        self.assertEqual(students_data[0]['firstName'], 'Student')
        self.assertEqual(students_data[0]['lastName'], 'One')
        self.assertEqual(students_data[0]['department'], 'Computer Engineering')
        self.assertEqual(students_data[0]['year'], 3)

    def test_get_faculty_heads_map(self):
        cache.clear()
        faculty_heads_map = get_faculty_heads_map()
        
        self.assertIsInstance(faculty_heads_map, dict)
        self.assertIn('facultyhead1', faculty_heads_map)
        self.assertEqual(faculty_heads_map['facultyhead1'], 'Faculty Head')

