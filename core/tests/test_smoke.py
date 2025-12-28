"""
Smoke test to verify the test runner works.
"""
from django.test import TestCase


class SmokeTest(TestCase):
    """Basic test that always passes to verify the test runner works."""
    
    def test_smoke(self):
        """A simple test that always passes."""
        self.assertTrue(True)

