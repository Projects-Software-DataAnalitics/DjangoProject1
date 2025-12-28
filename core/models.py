from django.db import models
from django.contrib.auth.models import User
from django.core.validators import MinValueValidator, MaxValueValidator


class Faculty(models.Model):
    name = models.CharField(max_length=200)
    slug = models.SlugField(max_length=200, unique=True)

    def __str__(self):
        return self.name


class UserProfile(models.Model):
    """
    User profile with role and course associations.
    
    NOTE: Course-Instructor relationship is stored in multiple places:
    1. Course.instructor (ForeignKey) - PRIMARY source of truth
    2. UserProfile.courses (ManyToMany) - Secondary relationship for convenience
    3. User.instructor_courses (reverse ForeignKey) - Derived from Course.instructor
    
    This creates potential synchronization issues:
    - Course.instructor can differ from UserProfile.courses
    - Views must check both sources (see all_courses view)
    
    For academic purposes this is acceptable, but in production:
    - Choose ONE source of truth
    - Use signals or methods to keep them in sync
    """
    ROLE_CHOICES = [
        ('student', 'Student'),
        ('instructor', 'Instructor'),
        ('faculty_head', 'Faculty Head'),
    ]

    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='profile')
    role = models.CharField(max_length=20, choices=ROLE_CHOICES)
    faculty = models.ForeignKey(Faculty, null=True, blank=True, on_delete=models.SET_NULL)
    department = models.CharField(max_length=200, blank=True)
    # NOTE: Secondary course relationship - see docstring above
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
    """
    Course model.
    
    CRITICAL DESIGN ASSUMPTION: Course.name is assumed to be unique system-wide.
    This is used throughout the system for:
    - ProgramOutcome.course_name (string reference)
    - Course lookup by name in views
    - Announcement course markers
    
    If Course.name is not unique, the following will break:
    - ProgramOutcome relationships (orphaned data)
    - Course lookups (wrong course selected)
    - Grade associations (wrong grades shown)
    
    NOTE: Model-level uniqueness constraint is required to enforce this assumption.
    """
    name = models.CharField(max_length=100, unique=True)  # CRITICAL: Must be unique system-wide
    code = models.CharField(max_length=20, blank=True)
    # NOTE: Course-Instructor relationship is stored in multiple places:
    # 1. Course.instructor (ForeignKey) - Primary source of truth
    # 2. UserProfile.courses (ManyToMany) - Secondary relationship
    # 3. User.instructor_courses (reverse ForeignKey) - Derived from Course.instructor
    # This creates potential synchronization issues but is acceptable for academic purposes.
    instructor = models.ForeignKey(User, on_delete=models.CASCADE, related_name='instructor_courses')
    department = models.CharField(max_length=200, blank=True)
    credits = models.IntegerField(null=True, blank=True)

    def __str__(self):
        if self.code:
            return f"{self.code} - {self.name}"
        return self.name

class Assessment(models.Model):
    """
    Assessment configuration for a course.
    
    CRITICAL: OneToOneField with CASCADE means:
    - Deleting a Course will permanently delete its Assessment
    - This is intentional: Assessment has no meaning without Course
    - If you need to preserve assessment data, change to PROTECT or SET_NULL
    """
    course = models.OneToOneField(Course, on_delete=models.CASCADE, related_name='assessment')
    midterm = models.IntegerField(default=2)
    final = models.IntegerField(default=1)
    project = models.IntegerField(default=0)
    assignment = models.IntegerField(default=0)
    absence = models.IntegerField(default=0)
    quiz = models.IntegerField(default=0)
    assessment_count = models.IntegerField(default=3)  # midterm + final + project + assignment + absence + quiz
    
    # Percentages
    midterm_percentage = models.IntegerField(default=60)
    final_percentage = models.IntegerField(default=40)
    project_percentage = models.IntegerField(default=0)
    assignment_percentage = models.IntegerField(default=0)
    absence_percentage = models.IntegerField(default=0)
    quiz_percentage = models.IntegerField(default=0)
    
    # Many-to-Many relationship with Learning Outcomes (through AssessmentLORelation)
    learning_outcomes = models.ManyToManyField(
        'ProgramOutcome',
        through='AssessmentLORelation',
        related_name='assessments',
        blank=True,
        help_text="Learning Outcomes that this assessment contributes to"
    )

    def save(self, *args, **kwargs):
        # assessment_count'u quiz dahil hesapla
        self.assessment_count = self.midterm + self.final + self.project + self.assignment + self.absence + self.quiz
        super().save(*args, **kwargs)
    
    @property
    def percentage_count(self):
        # percentage_count'u hesapla (tabloya kaydedilmez, sadece property)
        return (self.midterm_percentage + self.final_percentage + self.project_percentage + 
                self.assignment_percentage + self.absence_percentage + self.quiz_percentage)

    def __str__(self):
        return f"Assessment for {self.course.name}"

class Grade(models.Model):
    student = models.ForeignKey(Student, on_delete=models.CASCADE)
    course = models.ForeignKey(Course, on_delete=models.CASCADE)
    
    # Grade fields - stored as average scores (float) for each assessment type
    # NOTE: These fields are JSONField but store float values (not JSON objects)
    # This is a design inconsistency - consider using FloatField(null=True, blank=True) instead
    # Current implementation: JSONField stores float as JSON number
    # Usage: get_assessment_score() returns float, set_assessment_score() accepts float
    # If multiple assessments exist (e.g., 2 midterms), the average is calculated and stored
    # Example: midterm_1=60, midterm_2=50 -> midterm = 55.0 (average)
    # If assessment count is 0, the field remains empty (None)
    midterm = models.JSONField(default=None, blank=True, null=True)  # Average midterm score
    final = models.JSONField(default=None, blank=True, null=True)  # Average final score
    project = models.JSONField(default=None, blank=True, null=True)  # Average project score
    assignment = models.JSONField(default=None, blank=True, null=True)  # Average assignment score
    absence = models.JSONField(default=None, blank=True, null=True)  # Average absence score
    quiz = models.JSONField(default=None, blank=True, null=True)  # Average quiz score
    
    # Store individual assessment scores for tracking uploaded files
    # Format: {"midterm_1": {score: 60, uploaded_at: "..."}, "midterm_2": {...}}
    assessment_scores = models.JSONField(default=dict, blank=True)  # Individual scores for each assessment file
    
    # Track when grades were last modified
    last_changes_at = models.DateTimeField(null=True, blank=True)  # Last time grades were modified
    
    # Overall score calculated from assessment percentages
    overall_score = models.FloatField(null=True, blank=True)  # Weighted average based on assessment percentages
    
    # Letter grade based on overall score
    letter_grade = models.CharField(max_length=2, null=True, blank=True)  # Letter grade (AA, AB, BB, etc.)

    class Meta:
        # Modern Django: Use constraints instead of deprecated unique_together
        constraints = [
            models.UniqueConstraint(fields=['student', 'course'], name='unique_student_course')
        ]

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
    
    def calculate_overall_score(self):
        """Calculate overall score based on assessment percentages.
        Only calculates if ALL required assessments have been entered."""
        try:
            assessment = Assessment.objects.get(course=self.course)
        except Assessment.DoesNotExist:
            self.overall_score = None
            return None
        
        total_score = 0.0
        total_percentage = 0
        
        # Assessment types to check
        assessment_types = ['midterm', 'final', 'project', 'assignment', 'absence', 'quiz']
        
        # First, check if ALL required assessments are entered
        all_assessments_entered = True
        
        for assessment_type in assessment_types:
            # Get assessment count and percentage
            assessment_count = getattr(assessment, assessment_type, 0)
            percentage = getattr(assessment, f'{assessment_type}_percentage', 0)
            
            # Only check if assessment count > 0 and percentage > 0
            if assessment_count > 0 and percentage > 0:
                # Check if all individual scores for this assessment type are entered
                all_scores_entered = True
                for i in range(1, assessment_count + 1):
                    key = f"{assessment_type}_{i}"
                    individual_score = self.get_individual_score(key)
                    if individual_score is None:
                        all_scores_entered = False
                        break
                
                # If not all scores are entered, we can't calculate overall score
                if not all_scores_entered:
                    all_assessments_entered = False
                    break
                
                # Get the average score for this assessment type
                score = self.get_assessment_score(assessment_type)
                
                # If average score is None, it means not all files are uploaded yet
                if score is None:
                    all_assessments_entered = False
                    break
        
        # Only calculate if ALL assessments are entered
        if not all_assessments_entered:
            self.overall_score = None
            return None
        
        # Now calculate the weighted average
        for assessment_type in assessment_types:
            assessment_count = getattr(assessment, assessment_type, 0)
            percentage = getattr(assessment, f'{assessment_type}_percentage', 0)
            
            if assessment_count > 0 and percentage > 0:
                score = self.get_assessment_score(assessment_type)
                if score is not None:
                    # Add weighted score: score × percentage
                    total_score += score * percentage
                    total_percentage += percentage
        
        # Calculate overall score: total_score / total_percentage
        if total_percentage > 0:
            self.overall_score = total_score / total_percentage
            # Calculate letter grade based on overall score
            self.letter_grade = self.calculate_letter_grade(self.overall_score)
        else:
            self.overall_score = None
            self.letter_grade = None
        
        return self.overall_score
    
    def calculate_letter_grade(self, overall_score):
        """Calculate letter grade based on overall score"""
        if overall_score is None:
            return None
        
        score = float(overall_score)
        
        if score >= 90:
            return 'AA'
        elif score >= 85:
            return 'AB'
        elif score >= 80:
            return 'BB'
        elif score >= 75:
            return 'BC'
        elif score >= 70:
            return 'CC'
        elif score >= 65:
            return 'CD'
        elif score >= 60:
            return 'DD'
        elif score >= 50:
            return 'FD'
        else:
            return 'FF'

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
    
    def calculate_student_score(self, student):
        from .models import AssessmentLORelation, Grade
        
        if not self.course_name:
            return None
        
        assessment_relations = AssessmentLORelation.objects.filter(
            learning_outcome=self
        ).select_related('assessment', 'assessment__course')
        
        if not assessment_relations.exists():
            return None
        
        total_score = 0.0
        total_contribution = 0
        
        for rel in assessment_relations:
            assessment = rel.assessment
            course = assessment.course
            contribution_percentage = rel.contribution_percentage
            assessment_type = rel.assessment_type  # Use the specific assessment type from relation
            
            if contribution_percentage <= 0:
                continue
            
            try:
                grade = Grade.objects.get(student=student, course=course)
            except Grade.DoesNotExist:
                continue
            
            # Get score for the specific assessment type
            assessment_score = grade.get_assessment_score(assessment_type)
            
            if assessment_score is not None:
                total_score += assessment_score * contribution_percentage
                total_contribution += contribution_percentage
        
        # Calculate final score: total_score / total_contribution
        # Total contribution can be any value (100, 150, etc.) - we normalize by dividing by it
        if total_contribution > 0:
            return total_score / total_contribution
        return None
    
    def calculate_program_outcome_score(self, student):
        """
        Calculate a student's achievement score for this Program Outcome.
        
        Formula: PO_Başarısı = Σ(LO_Notu × LO_PO_Etki_Yüzdesi) / Total_Contribution
        
        For each learning outcome linked to this PO:
        - Get the student's LO score
        - Multiply by the LO->PO percentage
        - Sum all contributions
        - Divide by total contribution (can be > 100, no need to be exactly 100)
        
        Args:
            student: Student instance
            
        Returns:
            float: Achievement score (0-100) or None if no learning outcomes linked
        """
        from .models import LearningOutcomeProgramOutcome
        
        # Only calculate for Program Outcomes (course_name == '')
        if self.course_name:
            return None
        
        # Get all learning outcomes linked to this PO
        lo_po_relations = LearningOutcomeProgramOutcome.objects.filter(
            program_outcome=self
        ).select_related('learning_outcome')
        
        if not lo_po_relations.exists():
            return None
        
        total_score = 0.0
        total_contribution = 0
        
        for rel in lo_po_relations:
            learning_outcome = rel.learning_outcome
            percentage = rel.percentage
            
            if percentage <= 0:
                continue
            
            # Get student's score for this learning outcome
            lo_score = learning_outcome.calculate_student_score(student)
            
            if lo_score is not None:
                # Add weighted contribution: LO_score × percentage
                total_score += lo_score * percentage
                total_contribution += percentage
        
        # Calculate final score: total_score / total_contribution
        # Total contribution can be any value (100, 150, etc.) - we normalize by dividing by it
        if total_contribution > 0:
            return total_score / total_contribution
        return None

class LearningOutcomeProgramOutcome(models.Model):
    learning_outcome = models.ForeignKey('ProgramOutcome', on_delete=models.CASCADE, related_name='lo_po_relationships')
    program_outcome = models.ForeignKey('ProgramOutcome', on_delete=models.CASCADE, related_name='po_lo_relationships')
    percentage = models.IntegerField(default=0, validators=[MinValueValidator(0), MaxValueValidator(100)])

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=['learning_outcome', 'program_outcome'], name='unique_lo_po')
        ]

class AssessmentLORelation(models.Model):
    """
    NOTE: Learning Outcomes are stored in ProgramOutcome model with course_name != ''.
    """
    ASSESSMENT_TYPE_CHOICES = [
        ('midterm', 'Midterm'),
        ('final', 'Final'),
        ('project', 'Project'),
        ('assignment', 'Assignment'),
        ('absence', 'Absence'),
        ('quiz', 'Quiz'),
    ]
    
    assessment = models.ForeignKey(Assessment, on_delete=models.CASCADE, related_name='lo_relations')
    learning_outcome = models.ForeignKey('ProgramOutcome', on_delete=models.CASCADE, related_name='assessment_relations')
    assessment_type = models.CharField(
        max_length=20,
        choices=ASSESSMENT_TYPE_CHOICES,
        default='midterm',
        help_text="Type of assessment (midterm, final, project, etc.)"
    )
    contribution_percentage = models.IntegerField(
        default=0, 
        validators=[MinValueValidator(0), MaxValueValidator(100)],
        help_text="Percentage contribution of this assessment to the learning outcome (0-100)"
    )

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=['assessment', 'learning_outcome', 'assessment_type'], name='unique_assessment_lo_type')
        ]
    
    def __str__(self):
        return f"{self.assessment.course.name} - {self.get_assessment_type_display()} to {self.learning_outcome.text[:50]} ({self.contribution_percentage}%)"

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

class Assignment(models.Model):
    course = models.ForeignKey(Course, on_delete=models.CASCADE, related_name='assignments')
    title = models.CharField(max_length=200)
    details = models.TextField()
    deadline = models.DateTimeField()
    file = models.FileField(upload_to='assignments/', blank=True, null=True)
    created_by = models.ForeignKey(User, on_delete=models.CASCADE, related_name='created_assignments')
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        ordering = ['-created_at']
    
    def __str__(self):
        return f"{self.course.name} - {self.title}"

class AssignmentSubmission(models.Model):
    assignment = models.ForeignKey(Assignment, on_delete=models.CASCADE, related_name='submissions')
    student = models.ForeignKey(Student, on_delete=models.CASCADE, related_name='assignment_submissions')
    file = models.FileField(upload_to='assignment_submissions/', blank=True, null=True)
    submitted_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        unique_together = ['assignment', 'student']
        ordering = ['-submitted_at']
    
    def __str__(self):
        return f"{self.student.username} - {self.assignment.title}"
