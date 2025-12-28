"""
Tests for Django views.
"""
from django.test import TestCase
from django.urls import reverse


class ViewTests(TestCase):
    """Tests for Django views."""
    
    def test_index_view(self):
        """Test that the index view returns a successful response."""
        response = self.client.get('/')
        # Index view should return 200 (OK) or 302 (redirect)
        self.assertIn(response.status_code, [200, 302])

