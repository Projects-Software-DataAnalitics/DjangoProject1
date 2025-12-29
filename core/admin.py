from django.contrib import admin
from django.utils.html import format_html
from .models import (
    Faculty, UserProfile, Student, Course, Assessment, Grade,
    ProgramOutcome, LearningOutcomeProgramOutcome, AssessmentLORelation,
    Announcement, Assignment, AssignmentSubmission,
    AcademicCalendar, AcademicCalendarEvent, Notification
)


@admin.register(Faculty)
class FacultyAdmin(admin.ModelAdmin):
    list_display = ('name', 'slug')
    search_fields = ('name', 'slug')
    prepopulated_fields = {'slug': ('name',)}


@admin.register(UserProfile)
class UserProfileAdmin(admin.ModelAdmin):
    list_display = ('user', 'role', 'faculty', 'department', 'get_courses_count')
    list_filter = ('role', 'faculty', 'department')
    search_fields = ('user__username', 'user__email', 'department')
    filter_horizontal = ('courses',)
    raw_id_fields = ('user', 'faculty')
    
    def get_courses_count(self, obj):
        return obj.courses.count()
    get_courses_count.short_description = 'Courses Count'


@admin.register(Student)
class StudentAdmin(admin.ModelAdmin):
    list_display = ('username', 'student_id', 'first_name', 'last_name', 'department', 'year', 'advisor', 'get_courses_count')
    list_filter = ('department', 'year', 'advisor')
    search_fields = ('username', 'student_id', 'first_name', 'last_name', 'department')
    filter_horizontal = ('courses',)
    raw_id_fields = ('user', 'advisor')
    
    def get_courses_count(self, obj):
        return obj.courses.count()
    get_courses_count.short_description = 'Courses Count'


@admin.register(Course)
class CourseAdmin(admin.ModelAdmin):
    list_display = ('name', 'code', 'instructor', 'department', 'credits', 'day', 'time', 'room', 'get_students_count')
    list_filter = ('department', 'instructor', 'day')
    search_fields = ('name', 'code', 'instructor__username', 'department')
    raw_id_fields = ('instructor',)
    
    def get_students_count(self, obj):
        return obj.students.count()
    get_students_count.short_description = 'Students Count'


@admin.register(Assessment)
class AssessmentAdmin(admin.ModelAdmin):
    list_display = (
        'course', 'midterm', 'final', 'project', 'assignment', 'absence', 'quiz',
        'midterm_percentage', 'final_percentage', 'project_percentage',
        'assignment_percentage', 'absence_percentage', 'quiz_percentage'
    )
    list_filter = ('course__department', 'course__instructor')
    search_fields = ('course__name', 'course__code')
    raw_id_fields = ('course',)
    
    fieldsets = (
        ('Course', {
            'fields': ('course',)
        }),
        ('Assessment Counts', {
            'fields': ('midterm', 'final', 'project', 'assignment', 'absence', 'quiz')
        }),
        ('Assessment Percentages', {
            'fields': (
                'midterm_percentage', 'final_percentage', 'project_percentage',
                'assignment_percentage', 'absence_percentage', 'quiz_percentage'
            ),
            'description': 'Total must equal 100%'
        }),
    )


@admin.register(Grade)
class GradeAdmin(admin.ModelAdmin):
    list_display = ('student', 'course', 'overall_score', 'letter_grade', 'last_changes_at')
    list_filter = ('course', 'letter_grade', 'course__instructor', 'last_changes_at')
    search_fields = ('student__username', 'student__student_id', 'course__name')
    raw_id_fields = ('student', 'course')
    readonly_fields = ('overall_score', 'letter_grade', 'last_changes_at')
    
    fieldsets = (
        ('Basic Info', {
            'fields': ('student', 'course', 'last_changes_at')
        }),
        ('Assessment Scores', {
            'fields': ('midterm', 'final', 'project', 'assignment', 'absence', 'quiz')
        }),
        ('Calculated Fields', {
            'fields': ('overall_score', 'letter_grade', 'assessment_scores'),
            'classes': ('collapse',)
        }),
    )


@admin.register(ProgramOutcome)
class ProgramOutcomeAdmin(admin.ModelAdmin):
    list_display = ('text_preview', 'course_name', 'faculty', 'created_by', 'created_at', 'is_learning_outcome')
    list_filter = ('faculty', 'created_by', 'created_at', 'course_name')
    search_fields = ('text', 'course_name', 'created_by__username')
    raw_id_fields = ('created_by', 'faculty')
    # Note: related_program_outcomes uses through model, so filter_horizontal cannot be used
    readonly_fields = ('created_at',)
    
    def text_preview(self, obj):
        return obj.text[:100] + '...' if len(obj.text) > 100 else obj.text
    text_preview.short_description = 'Text'
    
    def is_learning_outcome(self, obj):
        return bool(obj.course_name)
    is_learning_outcome.boolean = True
    is_learning_outcome.short_description = 'Is Learning Outcome'


@admin.register(LearningOutcomeProgramOutcome)
class LearningOutcomeProgramOutcomeAdmin(admin.ModelAdmin):
    list_display = ('learning_outcome', 'program_outcome', 'percentage')
    list_filter = ('program_outcome__faculty', 'percentage')
    search_fields = ('learning_outcome__text', 'program_outcome__text')
    raw_id_fields = ('learning_outcome', 'program_outcome')


@admin.register(AssessmentLORelation)
class AssessmentLORelationAdmin(admin.ModelAdmin):
    list_display = ('assessment', 'learning_outcome', 'assessment_type', 'assessment_index', 'contribution_percentage')
    list_filter = ('assessment_type', 'assessment__course', 'learning_outcome__course_name')
    search_fields = ('assessment__course__name', 'learning_outcome__text')
    raw_id_fields = ('assessment', 'learning_outcome')


@admin.register(Announcement)
class AnnouncementAdmin(admin.ModelAdmin):
    list_display = ('subject_preview', 'sender', 'receiver', 'receiver_role', 'is_pinned', 'created_at')
    list_filter = ('receiver_role', 'is_pinned', 'created_at', 'sender')
    search_fields = ('subject', 'message', 'sender__username', 'receiver__username')
    raw_id_fields = ('sender', 'receiver')
    filter_horizontal = ('read_by',)
    readonly_fields = ('created_at',)
    
    def subject_preview(self, obj):
        return obj.subject[:50] + '...' if len(obj.subject) > 50 else obj.subject
    subject_preview.short_description = 'Subject'


@admin.register(Assignment)
class AssignmentAdmin(admin.ModelAdmin):
    list_display = ('title', 'course', 'created_by', 'deadline', 'created_at', 'has_file')
    list_filter = ('course', 'created_by', 'deadline', 'created_at')
    search_fields = ('title', 'details', 'course__name', 'created_by__username')
    raw_id_fields = ('course', 'created_by')
    readonly_fields = ('created_at',)
    
    def has_file(self, obj):
        return bool(obj.file)
    has_file.boolean = True
    has_file.short_description = 'Has File'


@admin.register(AssignmentSubmission)
class AssignmentSubmissionAdmin(admin.ModelAdmin):
    list_display = ('assignment', 'student', 'submitted_at', 'has_file')
    list_filter = ('assignment__course', 'submitted_at', 'assignment__created_by')
    search_fields = ('assignment__title', 'student__username', 'student__student_id')
    raw_id_fields = ('assignment', 'student')
    readonly_fields = ('submitted_at',)
    
    def has_file(self, obj):
        return bool(obj.file)
    has_file.boolean = True
    has_file.short_description = 'Has File'


@admin.register(AcademicCalendar)
class AcademicCalendarAdmin(admin.ModelAdmin):
    list_display = ('__str__', 'academic_year', 'semester', 'uploaded_by', 'uploaded_at', 'has_file')
    list_filter = ('academic_year', 'semester', 'uploaded_at')
    search_fields = ('academic_year', 'semester', 'uploaded_by__username')
    raw_id_fields = ('uploaded_by',)
    readonly_fields = ('uploaded_at',)
    
    def has_file(self, obj):
        return bool(obj.file)
    has_file.boolean = True
    has_file.short_description = 'Has File'


@admin.register(AcademicCalendarEvent)
class AcademicCalendarEventAdmin(admin.ModelAdmin):
    list_display = ('calendar', 'event_name', 'start_date', 'end_date')
    list_filter = ('calendar', 'start_date')
    search_fields = ('event_name', 'calendar__academic_year', 'calendar__semester')
    raw_id_fields = ('calendar',)
    date_hierarchy = 'start_date'


@admin.register(Notification)
class NotificationAdmin(admin.ModelAdmin):
    list_display = ('user', 'announcement', 'assignment', 'is_read', 'created_at')
    list_filter = ('is_read', 'created_at', 'announcement', 'assignment')
    search_fields = ('user__username', 'announcement__subject', 'assignment__title')
    raw_id_fields = ('user', 'announcement', 'assignment')
    readonly_fields = ('created_at',)
