from django.db import models
from django.contrib.auth.models import User


class Faculty(models.Model):
    name = models.CharField(max_length=200)
    slug = models.SlugField(max_length=200, unique=True)

    def __str__(self):
        return self.name


class UserProfile(models.Model):
    ROLE_CHOICES = [
        ('student', 'Student'),
        ('instructor', 'Instructor'),
        ('faculty_head', 'Faculty Head'),
    ]

    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='profile')
    role = models.CharField(max_length=20, choices=ROLE_CHOICES)
    faculty = models.ForeignKey(Faculty, null=True, blank=True, on_delete=models.SET_NULL)
    department = models.CharField(max_length=200, blank=True)
    courses = models.ManyToManyField('Course', blank=True, related_name='user_profiles')

    def __str__(self):
        return f"{self.user.username} ({self.role})"


class Student(models.Model):
    username = models.CharField(max_length=100, unique=True)
    student_id = models.CharField(max_length=20, unique=True)
    first_name = models.CharField(max_length=100, blank=True)
    last_name = models.CharField(max_length=100, blank=True)
    department = models.CharField(max_length=200, blank=True)
    year = models.IntegerField(null=True, blank=True)
    user = models.OneToOneField(User, null=True, blank=True, on_delete=models.SET_NULL, related_name='student_profile')
    courses = models.ManyToManyField('Course', blank=True, related_name='students')

    def __str__(self):
        return self.username

class Course(models.Model):
    name = models.CharField(max_length=100)
    code = models.CharField(max_length=20, blank=True)
    instructor = models.ForeignKey(User, on_delete=models.CASCADE, related_name='instructor_courses')
    department = models.CharField(max_length=200, blank=True)

    def __str__(self):
        if self.code:
            return f"{self.code} - {self.name}"
        return self.name

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
    faculty = models.ForeignKey(Faculty, null=True, blank=True, on_delete=models.CASCADE, related_name='program_outcomes')
    created_by = models.ForeignKey(User, on_delete=models.CASCADE)
    created_at = models.DateTimeField(auto_now_add=True)
    # ManyToMany field for learning outcomes to link to program outcomes
    related_program_outcomes = models.ManyToManyField('self', symmetrical=False, blank=True, related_name='learning_outcomes')

    def __str__(self):
        return self.text

class Announcement(models.Model):
    ROLE_CHOICES = [
        ('instructor', 'Instructor'),
        ('faculty_head', 'Faculty Head'),
    ]
    
    sender = models.ForeignKey(User, on_delete=models.CASCADE, related_name='sent_announcements')
    receiver = models.ForeignKey(User, on_delete=models.CASCADE, null=True, blank=True, related_name='received_announcements')
    subject = models.CharField(max_length=200, default='No Topic')
    message = models.TextField()
    sender_role = models.CharField(max_length=20, choices=ROLE_CHOICES)
    receiver_role = models.CharField(max_length=20, choices=ROLE_CHOICES, null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        ordering = ['-created_at']
    
    def __str__(self):
        receiver_name = self.receiver.username if self.receiver else "Everyone"
        return f"{self.sender.username} -> {receiver_name}: {self.subject}"
