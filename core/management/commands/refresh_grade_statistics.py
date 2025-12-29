"""
Management command to refresh the student_grade_statistics materialized view.

This command should be run periodically (e.g., via cron) or after grade updates
to keep the materialized view data current.

Usage:
    python manage.py refresh_grade_statistics
"""

from django.core.management.base import BaseCommand
from django.db import connection


class Command(BaseCommand):
    help = 'Refresh the student_grade_statistics materialized view'

    def handle(self, *args, **options):
        self.stdout.write('Refreshing student_grade_statistics materialized view...')
        
        try:
            with connection.cursor() as cursor:
                cursor.execute("REFRESH MATERIALIZED VIEW CONCURRENTLY student_grade_statistics;")
                self.stdout.write(
                    self.style.SUCCESS(
                        'Successfully refreshed student_grade_statistics materialized view'
                    )
                )
        except Exception as e:
            # If CONCURRENTLY fails (e.g., no unique index), try without it
            try:
                with connection.cursor() as cursor:
                    cursor.execute("REFRESH MATERIALIZED VIEW student_grade_statistics;")
                    self.stdout.write(
                        self.style.SUCCESS(
                            'Successfully refreshed student_grade_statistics materialized view (non-concurrent)'
                        )
                    )
            except Exception as e2:
                self.stdout.write(
                    self.style.ERROR(
                        f'Error refreshing materialized view: {str(e2)}'
                    )
                )

