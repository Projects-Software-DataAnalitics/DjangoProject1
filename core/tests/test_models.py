"""
Tests for Django models.
"""
from django.test import TestCase
from core.models import Faculty


class ModelTests(TestCase):
    """Tests for Django models."""
    
    def test_faculty_creation(self):
        """Test creating a Faculty instance with required fields."""
        faculty = Faculty.objects.create(
            name='Computer Science',
            slug='computer-science'
        )
        self.assertEqual(faculty.name, 'Computer Science')
        self.assertEqual(faculty.slug, 'computer-science')
        self.assertIsNotNone(faculty.id)

