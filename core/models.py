from django.db import models
from django.contrib.auth.models import User


class UserProfile(models.Model):
    ROLE_CHOICES = [
        ('student', 'Student'),
        ('instructor', 'Instructor'),
        ('faculty_head', 'Faculty Head'),
    ]

    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='profile')
    role = models.CharField(max_length=20, choices=ROLE_CHOICES)

    def __str__(self):
        return f"{self.user.username} ({self.role})"


class Student(models.Model):
    username = models.CharField(max_length=100, unique=True)
    student_id = models.CharField(max_length=20, unique=True)

    def __str__(self):
        return self.username

class Course(models.Model):
    name = models.CharField(max_length=100)
    code = models.CharField(max_length=20)
    instructor = models.ForeignKey(User, on_delete=models.CASCADE)

    def __str__(self):
        return f"{self.code} - {self.name}"

class Grade(models.Model):
    student = models.ForeignKey(Student, on_delete=models.CASCADE)
    course = models.ForeignKey(Course, on_delete=models.CASCADE)

    midterm = models.FloatField()
    assignment = models.FloatField()
    final = models.FloatField()

    def __str__(self):
        return f"{self.student.username} - {self.course.name}"

class ProgramOutcome(models.Model):
    text = models.CharField(max_length=255)
    course_name = models.CharField(max_length=255, blank=True, default="")
    created_by = models.ForeignKey(User, on_delete=models.CASCADE)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.text
