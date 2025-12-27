from django.db import models
from django.contrib.auth.models import User
from django.core.validators import MinValueValidator, MaxValueValidator


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
    advisor = models.ForeignKey(User, null=True, blank=True, on_delete=models.SET_NULL, related_name='advised_students', limit_choices_to={'profile__role__in': ['instructor', 'faculty_head']})
    courses = models.ManyToManyField('Course', blank=True, related_name='students')

    def __str__(self):
        return self.username

class Course(models.Model):
    name = models.CharField(max_length=100)
    code = models.CharField(max_length=20, blank=True)
    instructor = models.ForeignKey(User, on_delete=models.CASCADE, related_name='instructor_courses')
    department = models.CharField(max_length=200, blank=True)
    credits = models.IntegerField(null=True, blank=True)

    def __str__(self):
        if self.code:
            return f"{self.code} - {self.name}"
        return self.name

class Assessment(models.Model):
    course = models.OneToOneField(Course, on_delete=models.CASCADE, related_name='assessment')
    midterm = models.IntegerField(default=2)
    final = models.IntegerField(default=1)
    proje = models.IntegerField(default=0)
    homework = models.IntegerField(default=0)
    absence = models.IntegerField(default=0)
    quiz = models.IntegerField(default=0)
    assessment_count = models.IntegerField(default=3)  # midterm + final + proje + homework + absence + quiz
    
    # Percentages
    midterm_percentage = models.IntegerField(default=60)
    final_percentage = models.IntegerField(default=40)
    proje_percentage = models.IntegerField(default=0)
    homework_percentage = models.IntegerField(default=0)
    absence_percentage = models.IntegerField(default=0)
    quiz_percentage = models.IntegerField(default=0)

    def save(self, *args, **kwargs):
        # assessment_count'u quiz dahil hesapla
        self.assessment_count = self.midterm + self.final + self.proje + self.homework + self.absence + self.quiz
        super().save(*args, **kwargs)
    
    @property
    def percentage_count(self):
        # percentage_count'u hesapla (tabloya kaydedilmez, sadece property)
        return (self.midterm_percentage + self.final_percentage + self.proje_percentage + 
                self.homework_percentage + self.absence_percentage + self.quiz_percentage)

    def __str__(self):
        return f"Assessment for {self.course.name}"

class Grade(models.Model):
    student = models.ForeignKey(Student, on_delete=models.CASCADE)
    course = models.ForeignKey(Course, on_delete=models.CASCADE)
    
    # Grade fields - stored as average scores (float) for each assessment type
    # If multiple assessments exist (e.g., 2 midterms), the average is calculated and stored
    # Example: midterm_1=60, midterm_2=50 -> midterm = 55.0 (average)
    # If assessment count is 0, the field remains empty (None)
    midterm = models.JSONField(default=None, blank=True, null=True)  # Average midterm score
    final = models.JSONField(default=None, blank=True, null=True)  # Average final score
    proje = models.JSONField(default=None, blank=True, null=True)  # Average project score
    homework = models.JSONField(default=None, blank=True, null=True)  # Average homework score
    absence = models.JSONField(default=None, blank=True, null=True)  # Average absence score
    quiz = models.JSONField(default=None, blank=True, null=True)  # Average quiz score
    
    # Store individual assessment scores for tracking uploaded files
    # Format: {"midterm_1": {score: 60, uploaded_at: "..."}, "midterm_2": {...}}
    assessment_scores = models.JSONField(default=dict, blank=True)  # Individual scores for each assessment file
    
    # Track when grades were last modified
    last_changes_at = models.DateTimeField(null=True, blank=True)  # Last time grades were modified

    class Meta:
        unique_together = ['student', 'course']

    def __str__(self):
        return f"{self.student.username} - {self.course.name}"
    
    def get_assessment_score(self, assessment_type):
        """Get average score for a specific assessment type"""
        score = getattr(self, assessment_type, None)
        # Handle both float and None values
        if score is None:
            return None
        try:
            return float(score)
        except (TypeError, ValueError):
            return None
    
    def set_assessment_score(self, assessment_type, score):
        """Set average score for a specific assessment type"""
        if score is not None:
            try:
                setattr(self, assessment_type, float(score))
            except (TypeError, ValueError):
                setattr(self, assessment_type, None)
        else:
            setattr(self, assessment_type, None)
    
    def set_individual_score(self, assessment_key, score, file_name=None):
        """Set individual score for a specific assessment file (e.g., midterm_1)"""
        if not self.assessment_scores:
            self.assessment_scores = {}
        from django.utils import timezone
        self.assessment_scores[assessment_key] = {
            'score': float(score) if score is not None else None,
            'uploaded_at': timezone.now().isoformat(),
            'file_name': file_name or ''
        }
    
    def get_uploaded_file_info(self, assessment_key):
        """Get uploaded file name and time for a specific assessment file"""
        if not self.assessment_scores:
            return None, None
        data = self.assessment_scores.get(assessment_key)
        if data:
            return data.get('file_name'), data.get('uploaded_at')
        return None, None
    
    def get_individual_score(self, assessment_key):
        """Get individual score for a specific assessment file"""
        if not self.assessment_scores:
            return None
        data = self.assessment_scores.get(assessment_key)
        return data.get('score') if data else None
    
    def remove_individual_score(self, assessment_key):
        """Remove individual score for a specific assessment file"""
        if not self.assessment_scores:
            return
        if assessment_key in self.assessment_scores:
            del self.assessment_scores[assessment_key]
    
    def calculate_average_for_type(self, assessment_type, expected_count):
        """Calculate average for an assessment type if all files are uploaded"""
        if not self.assessment_scores:
            return None
        
        scores = []
        for i in range(1, expected_count + 1):
            key = f"{assessment_type}_{i}"
            score_data = self.assessment_scores.get(key)
            if score_data and score_data.get('score') is not None:
                scores.append(score_data['score'])
        
        # Only calculate average if ALL expected files are uploaded
        if len(scores) == expected_count and expected_count > 0:
            return sum(scores) / len(scores)
        return None

class ProgramOutcome(models.Model):
    text = models.CharField(max_length=255)
    course_name = models.CharField(max_length=255, blank=True, default="")
    faculty = models.ForeignKey(Faculty, null=True, blank=True, on_delete=models.CASCADE, related_name='program_outcomes')
    created_by = models.ForeignKey(User, on_delete=models.CASCADE)
    created_at = models.DateTimeField(auto_now_add=True)
    # ManyToMany field for learning outcomes to link to program outcomes
    related_program_outcomes = models.ManyToManyField('self', symmetrical=False, blank=True, related_name='learning_outcomes', through='LearningOutcomeProgramOutcome')

    def __str__(self):
        return self.text

class LearningOutcomeProgramOutcome(models.Model):
    learning_outcome = models.ForeignKey('ProgramOutcome', on_delete=models.CASCADE, related_name='lo_po_relationships')
    program_outcome = models.ForeignKey('ProgramOutcome', on_delete=models.CASCADE, related_name='po_lo_relationships')
    percentage = models.IntegerField(default=0, validators=[MinValueValidator(0), MaxValueValidator(100)])

    class Meta:
        unique_together = [['learning_outcome', 'program_outcome']]

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
    read_by = models.ManyToManyField(User, related_name='read_announcements', blank=True)
    is_pinned = models.BooleanField(default=False)
    
    class Meta:
        ordering = ['-created_at']
    
    def __str__(self):
        receiver_name = self.receiver.username if self.receiver else "Everyone"
        return f"{self.sender.username} -> {receiver_name}: {self.subject}"
