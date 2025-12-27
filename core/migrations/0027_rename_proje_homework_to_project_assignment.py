# Generated migration to rename proje to project and homework to assignment

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0026_merge_20251227_1421'),
    ]

    operations = [
        # Rename Assessment model fields
        migrations.RenameField(
            model_name='assessment',
            old_name='proje',
            new_name='project',
        ),
        migrations.RenameField(
            model_name='assessment',
            old_name='homework',
            new_name='assignment',
        ),
        migrations.RenameField(
            model_name='assessment',
            old_name='proje_percentage',
            new_name='project_percentage',
        ),
        migrations.RenameField(
            model_name='assessment',
            old_name='homework_percentage',
            new_name='assignment_percentage',
        ),
        # Rename Grade model fields
        migrations.RenameField(
            model_name='grade',
            old_name='proje',
            new_name='project',
        ),
        migrations.RenameField(
            model_name='grade',
            old_name='homework',
            new_name='assignment',
        ),
    ]

