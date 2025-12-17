from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0002_rename_learningoutcome_programoutcome'),
    ]

    operations = [
        migrations.AddField(
            model_name='programoutcome',
            name='course_name',
            field=models.CharField(blank=True, default='', max_length=255),
        ),
    ]

