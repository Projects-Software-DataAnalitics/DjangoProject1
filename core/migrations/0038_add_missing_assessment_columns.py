# Generated manually to add missing Assessment columns
# These columns were added manually to the database via SQL script
# This migration is marked as already applied (fake) to keep migration history consistent

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0037_student_email_student_phone_number'),
    ]

    operations = [
        # Add missing columns to Assessment model
        # Note: These columns already exist in the database (added via fix_assessment_all_columns.sql)
        # This migration is for migration history consistency only
        migrations.AddField(
            model_name='assessment',
            name='assignment',
            field=models.IntegerField(default=0),
        ),
        migrations.AddField(
            model_name='assessment',
            name='absence',
            field=models.IntegerField(default=0),
        ),
        migrations.AddField(
            model_name='assessment',
            name='quiz',
            field=models.IntegerField(default=0),
        ),
        migrations.AddField(
            model_name='assessment',
            name='project_percentage',
            field=models.IntegerField(default=0),
        ),
        migrations.AddField(
            model_name='assessment',
            name='assignment_percentage',
            field=models.IntegerField(default=0),
        ),
        migrations.AddField(
            model_name='assessment',
            name='absence_percentage',
            field=models.IntegerField(default=0),
        ),
        migrations.AddField(
            model_name='assessment',
            name='quiz_percentage',
            field=models.IntegerField(default=0),
        ),
    ]

