"""
Management command to backup the PostgreSQL database.

This command creates a SQL dump of the database using pg_dump and saves it
to a backups directory with a timestamp.

Usage:
    python manage.py backup_database

The backup file will be saved as:
    backups/backup_YYYY-MM-DD_HH-MM-SS.sql
"""

import os
import subprocess
from datetime import datetime
from django.core.management.base import BaseCommand
from django.conf import settings


class Command(BaseCommand):
    help = 'Backup the PostgreSQL database to a SQL file'

    def add_arguments(self, parser):
        parser.add_argument(
            '--output-dir',
            type=str,
            default='backups',
            help='Directory to save backup files (default: backups)',
        )

    def handle(self, *args, **options):
        output_dir = options['output_dir']
        
        # Get database settings
        db_settings = settings.DATABASES['default']
        db_name = db_settings['NAME']
        db_user = db_settings['USER']
        db_password = db_settings['PASSWORD']
        db_host = db_settings['HOST']
        db_port = db_settings['PORT']
        
        # Create backups directory if it doesn't exist
        if not os.path.exists(output_dir):
            os.makedirs(output_dir)
            self.stdout.write(f'Created directory: {output_dir}')
        
        # Generate backup filename with timestamp
        timestamp = datetime.now().strftime('%Y-%m-%d_%H-%M-%S')
        backup_filename = f'backup_{timestamp}.sql'
        backup_path = os.path.join(output_dir, backup_filename)
        
        self.stdout.write(f'Backing up database: {db_name}...')
        self.stdout.write(f'Backup file: {backup_path}')
        
        try:
            # Build pg_dump command
            # Note: pg_dump must be in PATH or use full path
            cmd = [
                'pg_dump',
                '-h', db_host,
                '-p', str(db_port),
                '-U', db_user,
                '-d', db_name,
                '-F', 'p',  # Plain text format
                '-f', backup_path,
            ]
            
            # Set password via environment variable
            env = os.environ.copy()
            if db_password:
                env['PGPASSWORD'] = db_password
            
            # Run pg_dump
            result = subprocess.run(
                cmd,
                env=env,
                capture_output=True,
                text=True,
                check=True
            )
            
            # Get file size
            if os.path.exists(backup_path):
                file_size = os.path.getsize(backup_path)
                file_size_mb = file_size / (1024 * 1024)
                
                self.stdout.write(
                    self.style.SUCCESS(
                        f'\nDatabase backup created successfully!'
                    )
                )
                self.stdout.write(f'  File: {backup_path}')
                self.stdout.write(f'  Size: {file_size_mb:.2f} MB')
                self.stdout.write(
                    self.style.SUCCESS(
                        f'\nTo restore this backup, use:'
                    )
                )
                self.stdout.write(
                    f'  psql -h {db_host} -p {db_port} -U {db_user} -d {db_name} -f {backup_path}'
                )
            else:
                self.stdout.write(
                    self.style.ERROR('Backup file was not created!')
                )
                
        except subprocess.CalledProcessError as e:
            self.stdout.write(
                self.style.ERROR(f'Error running pg_dump: {str(e)}')
            )
            if e.stderr:
                self.stdout.write(self.style.ERROR(f'Error details: {e.stderr}'))
            self.stdout.write(
                self.style.WARNING(
                    '\nMake sure pg_dump is installed and in your PATH.\n'
                    'On Windows, pg_dump is usually in: C:\\Program Files\\PostgreSQL\\15\\bin\\'
                )
            )
        except FileNotFoundError:
            self.stdout.write(
                self.style.ERROR(
                    'pg_dump command not found!\n'
                    'Please make sure PostgreSQL client tools are installed.\n'
                    'On Windows, add PostgreSQL bin directory to PATH:\n'
                    '  C:\\Program Files\\PostgreSQL\\15\\bin\\'
                )
            )
        except Exception as e:
            self.stdout.write(
                self.style.ERROR(f'Unexpected error: {str(e)}')
            )

