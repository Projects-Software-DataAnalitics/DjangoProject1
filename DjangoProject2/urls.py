"""
URL configuration for DjangoProject2 project.

The urlpatterns list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/5.2/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""
from django.contrib import admin
from django.urls import path
from django.conf import settings
from django.conf.urls.static import static
from core import views as core_views

urlpatterns = [
    path('', core_views.index, name='home'),
    path('admin/', admin.site.urls),
    path('grades/upload/', core_views.upload_grades, name='upload_grades'),
    path('student-login/', core_views.student_login, name='student-login'),
    path('instructor-login/', core_views.instructor_login, name='instructor-login'),
    path('faculty-head-login/', core_views.faculty_head_login, name='faculty-head-login'),
    path('student/', core_views.student_dashboard, name='student'),
    path('student/profile/', core_views.student_profile, name='student_profile'),
    path('student/courses/', core_views.student_courses, name='student_courses'),
    path('student/assignments/<int:assignment_id>/submit/', core_views.submit_assignment, name='submit_assignment'),
    path('student/assignments/<int:assignment_id>/delete-submission/', core_views.delete_submission, name='delete_submission'),
    path('student/courses/<int:course_id>/learning-outcomes/', core_views.student_course_learning_outcomes, name='student_course_learning_outcomes'),
    path('student/courses/<int:course_id>/learning-outcomes/<int:outcome_id>/', core_views.student_learning_outcome_detail, name='student_learning_outcome_detail'),
    path('student/courses/<int:course_id>/learning-outcomes/<int:outcome_id>/graph/', core_views.student_learning_outcome_graph, name='student_learning_outcome_graph'),
    path('student/grades/', core_views.student_grades, name='student_grades'),
    path('student/announcements/', core_views.student_announcements, name='student_announcements'),
    path('student/announcements/<int:announcement_id>/mark-read/', core_views.mark_announcement_as_read, name='mark_announcement_read'),
    path('student/announcements/<int:announcement_id>/toggle-pin/', core_views.toggle_announcement_pin, name='toggle_announcement_pin'),
    path('student/program-outcomes/', core_views.student_program_outcomes, name='student_program_outcomes'),
    path('student/advisor/<str:username>/', core_views.advisor_profile, name='advisor_profile'),
    path('student/logout/', core_views.logout_view, name='logout'),
    path('instructor/', core_views.instructor_dashboard, name='instructor'),
    path('instructor/profile/', core_views.instructor_profile, name='instructor_profile'),
    path('instructor/my-courses/', core_views.instructor_my_courses, name='instructor_my_courses'),
    path('instructor/grades/', core_views.instructor_grades, name='instructor_grades'),
    path('instructor/grades/<str:course_name>/', core_views.instructor_course_grades, name='instructor_course_grades'),
    path('instructor/grades/<str:course_name>/upload-<str:assessment_type>-<int:assessment_index>/', core_views.upload_assessment_grades, name='upload_assessment_grades'),
    path('instructor/grades/<str:course_name>/delete-<str:assessment_type>-<int:assessment_index>/', core_views.delete_assessment_file, name='delete_assessment_file'),
    path('instructor/grades/<str:course_name>/update-individual-grade/', core_views.update_individual_grade, name='update_individual_grade'),
    path('instructor/grades/<str:course_name>/update-assessment/', core_views.update_assessment, name='update_assessment'),
    path('instructor/grades/<str:course_name>/update-assessment-percentages/', core_views.update_assessment_percentages, name='update_assessment_percentages'),
    path('instructor/learning-outcomes/<str:course_name>/', core_views.course_learning_outcomes, name='course_learning_outcomes'),
    path('instructor/learning-outcomes/create/', core_views.create_learning_outcome, name='create_learning_outcome'),
    path('instructor/learning-outcomes/update/<int:outcome_id>/', core_views.update_learning_outcome, name='update_learning_outcome'),
    path('instructor/learning-outcomes/delete/<int:outcome_id>/', core_views.delete_learning_outcome, name='delete_learning_outcome'),
    path('instructor/learning-outcomes/<int:course_id>/<int:outcome_id>/', core_views.learning_outcome_detail, name='learning_outcome_detail'),
    path('instructor/program-outcomes/', core_views.instructor_program_outcomes, name='instructor_program_outcomes'),
    path('instructor/announcements/', core_views.instructor_announcements, name='instructor_announcements'),
]

# Faculty Head URLs
urlpatterns += [
    path('faculty-head/', core_views.faculty_head_dashboard, name='faculty-head'),
    path('faculty-head/profile/', core_views.faculty_head_profile, name='faculty_head_profile'),
    path('faculty-head/grades/', core_views.faculty_head_grades, name='faculty-head-grades'),
    path('faculty-head/grades/<str:course_name>/', core_views.faculty_head_grades, name='faculty-head-course-grades'),
    path('faculty-head/grades/<str:course_name>/upload-<str:assessment_type>-<int:assessment_index>/', core_views.upload_assessment_grades, name='faculty-head-upload-assessment-grades'),
    path('faculty-head/grades/<str:course_name>/delete-<str:assessment_type>-<int:assessment_index>/', core_views.delete_assessment_file, name='faculty-head-delete-assessment-file'),
    path('faculty-head/grades/<str:course_name>/update-individual-grade/', core_views.update_individual_grade, name='faculty-head-update-individual-grade'),
    path('faculty-head/grades/<str:course_name>/update-assessment/', core_views.update_assessment, name='faculty-head-update-assessment'),
    path('faculty-head/grades/<str:course_name>/update-assessment-percentages/', core_views.update_assessment_percentages, name='faculty-head-update-assessment-percentages'),
    path('faculty-head/grades/<str:course_name>/update/', core_views.faculty_head_update_manual_grades, name='faculty-head-update-grades'),
    path('faculty-head/grades/<str:course_name>/finalize/', core_views.faculty_head_finalize_grades, name='faculty-head-finalize-grades'),
    path('faculty-head/grades/<str:course_name>/delete-csv/', core_views.faculty_head_delete_uploaded_csv, name='faculty-head-delete-csv'),
    path('faculty-head/learning-outcomes/', core_views.faculty_head_learning_outcomes, name='faculty_head_learning_outcomes'),
    path('faculty-head/learning-outcomes/<str:course_name>/', core_views.faculty_head_course_learning_outcomes, name='faculty_head_course_learning_outcomes'),
    path('faculty-head/courses/<int:course_id>/learning-outcomes/<int:outcome_id>/', core_views.faculty_head_learning_outcome_detail, name='faculty_head_learning_outcome_detail'),
    path('faculty-head/courses/<int:course_id>/learning-outcomes/<int:outcome_id>/graph/', core_views.faculty_head_learning_outcome_graph, name='faculty_head_learning_outcome_graph'),
    path('faculty-head/learning-outcomes/<int:outcome_id>/update/', core_views.faculty_head_update_learning_outcome, name='faculty_head_update_learning_outcome'),
    path('faculty-head/learning-outcomes/<int:outcome_id>/delete/', core_views.faculty_head_delete_learning_outcome, name='faculty_head_delete_learning_outcome'),
    path('faculty-head/learning-outcomes/<int:outcome_id>/link-program-outcomes/', core_views.faculty_head_link_program_outcomes, name='faculty_head_link_program_outcomes'),
    path('faculty-head/learning-outcomes/<int:outcome_id>/unlink-program-outcome/<int:program_outcome_id>/', core_views.faculty_head_unlink_program_outcome, name='faculty_head_unlink_program_outcome'),
    path('faculty-head/learning-outcomes/<int:outcome_id>/update-percentage/<int:program_outcome_id>/', core_views.faculty_head_update_percentage, name='faculty_head_update_percentage'),
    path('faculty-head/announcements/', core_views.faculty_head_announcements, name='faculty-head-announcements'),
    path('faculty-head/announcements/<int:announcement_id>/mark-read/', core_views.mark_announcement_as_read, name='faculty_head_mark_announcement_read'),
    path('faculty-head/announcements/<int:announcement_id>/toggle-pin/', core_views.toggle_announcement_pin, name='faculty_head_toggle_announcement_pin'),
    path('faculty-head/logout/', core_views.faculty_head_logout, name='faculty-head-logout'),
    path('faculty-head/all-courses/', core_views.all_courses, name='all_courses'),
    path('faculty-head/department-graph/', core_views.faculty_head_department_graph, name='faculty_head_department_graph'),
    path('faculty-head/my-courses/', core_views.my_courses, name='my_courses'),
    path('faculty-head/add-assignment/', core_views.faculty_head_add_assignment, name='faculty_head_add_assignment'),
    path('faculty-head/assignments/<int:assignment_id>/update/', core_views.faculty_head_update_assignment, name='faculty_head_update_assignment'),
    path('faculty-head/submissions/<int:submission_id>/delete/', core_views.delete_student_submission, name='faculty_head_delete_student_submission'),
    path('faculty-head/program-outcomes/', core_views.program_outcomes, name='program_outcomes'),
    path('faculty-head/program-outcomes/<int:outcome_id>/', core_views.program_outcome_detail, name='program_outcome_detail'),
    path('faculty-head/program-outcomes/<int:outcome_id>/update/', core_views.update_program_outcome, name='update_program_outcome'),
    path('faculty-head/program-outcomes/<int:outcome_id>/delete/', core_views.delete_program_outcome, name='delete_program_outcome'),
    path('faculty-head/program-outcomes/create/', core_views.create_program_outcome, name='create_program_outcome'),
    path('faculty-head/course/<int:course_id>/grade/', core_views.give_grade, name='give_grade'),
    path('instructor/learning-outcomes/<str:course_name>/', core_views.course_learning_outcomes, name='course_learning_outcomes'),
    path('instructor/learning-outcomes/create/', core_views.create_learning_outcome, name='create_learning_outcome'),
    path('instructor/courses/<int:course_id>/learning-outcomes/<int:outcome_id>/', core_views.learning_outcome_detail, name='learning_outcome_detail'),
    path('instructor/courses/<int:course_id>/learning-outcomes/<int:outcome_id>/graph/', core_views.learning_outcome_graph, name='learning_outcome_graph'),
    path('instructor/learning-outcomes/<int:outcome_id>/update/', core_views.update_learning_outcome, name='update_learning_outcome'),
    path('instructor/learning-outcomes/<int:outcome_id>/delete/', core_views.delete_learning_outcome, name='delete_learning_outcome'),
    path('instructor/learning-outcomes/<int:outcome_id>/link-program-outcomes/', core_views.link_program_outcomes, name='link_program_outcomes'),
    path('instructor/learning-outcomes/<int:outcome_id>/unlink-program-outcome/<int:program_outcome_id>/', core_views.unlink_program_outcome, name='unlink_program_outcome'),
    path('instructor/learning-outcomes/<int:outcome_id>/update-percentage/<int:program_outcome_id>/', core_views.update_percentage, name='update_percentage'),
    path('instructor/profile/', core_views.instructor_profile, name='instructor_profile'),
    path('instructor/announcements/', core_views.instructor_announcements, name='instructor_announcements'),
    path('instructor/announcements/<int:announcement_id>/mark-read/', core_views.mark_announcement_as_read, name='instructor_mark_announcement_read'),
    path('instructor/announcements/<int:announcement_id>/toggle-pin/', core_views.toggle_announcement_pin, name='instructor_toggle_announcement_pin'),
    path('instructor/my-courses/', core_views.instructor_my_courses, name='instructor_my_courses'),
    path('instructor/add-assignment/', core_views.add_assignment, name='add_assignment'),
    path('instructor/assignments/<int:assignment_id>/update/', core_views.update_assignment, name='update_assignment'),
    path('instructor/submissions/<int:submission_id>/delete/', core_views.delete_student_submission, name='delete_student_submission'),
    path('instructor/grades/', core_views.instructor_grades, name='instructor_grades'),
    path('instructor/grades/<str:course_name>/', core_views.instructor_course_grades, name='instructor_course_grades'),
    path('instructor/program-outcomes/', core_views.instructor_program_outcomes, name='instructor_program_outcomes'),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
