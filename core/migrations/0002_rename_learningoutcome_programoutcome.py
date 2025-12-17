from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0001_initial'),
    ]

    operations = [
        migrations.RenameModel(
            old_name='LearningOutcome',
            new_name='ProgramOutcome',
        ),
    ]

