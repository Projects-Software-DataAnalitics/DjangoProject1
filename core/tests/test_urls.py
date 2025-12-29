"""
Tests for URL routing.
"""
from django.test import TestCase


class URLTests(TestCase):
    """Tests for URL routing."""
    
    def test_admin_url_redirects(self):
        """Test that /admin/ URL returns 302 (redirect to login)."""
        response = self.client.get('/admin/')
        self.assertEqual(response.status_code, 302)

