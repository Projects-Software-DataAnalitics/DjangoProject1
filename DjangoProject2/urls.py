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
from core import views as core_views

urlpatterns = [
    path('', core_views.index, name='home'),
    path('admin/', admin.site.urls),
    path('grades/upload/', core_views.upload_grades, name='upload_grades'),

    # login
    path('student-login/', core_views.student_login, name='student-login'),
    path('instructor-login/', core_views.instructor_login, name='instructor-login'),
    path('faculty-head-login/', core_views.faculty_head_login, name='faculty-head-login'),

    # Dashboards
    path('student/', core_views.student_dashboard, name='student'),
    path('instructor/', core_views.instructor_dashboard, name='instructor'),
    path('instructor/profile/', core_views.instructor_profile, name='instructor_profile'),
    path('instructor/my-courses/', core_views.instructor_my_courses, name='instructor_my_courses'),
    path('instructor/grades/', core_views.instructor_grades, name='instructor_grades'),
    path('instructor/grades/<str:course_name>/', core_views.instructor_course_grades, name='instructor_course_grades'),
    path('instructor/grades/<str:course_name>/delete-csv/', core_views.delete_uploaded_csv, name='delete_uploaded_csv'),
    path('instructor/grades/<str:course_name>/update-manual/', core_views.update_manual_grades, name='update_manual_grades'),
    path('instructor/grades/<str:course_name>/finalize/', core_views.finalize_grades, name='finalize_grades'),
    path('instructor/announcements/', core_views.instructor_announcements, name='instructor_announcements'),
    path('instructor/set-session/', core_views.set_instructor_session, name='set_instructor_session'),
    path('faculty-head/', core_views.faculty_head_dashboard, name='faculty-head'),
    path('faculty-head/logout/', core_views.faculty_head_logout, name='faculty-head-logout'),
    path('faculty-head/grades/', core_views.faculty_head_grades, name='faculty-head-grades'),
    path('faculty-head/announcements/', core_views.faculty_head_announcements, name='faculty-head-announcements'),
    path('faculty-head/profile/', core_views.faculty_head_profile, name='faculty_head_profile'),

    # Faculty head pages

    path('faculty-head/all-courses/', core_views.all_courses, name='all_courses'),
    path('faculty-head/my-courses/', core_views.my_courses, name='my_courses'),
    path('faculty-head/learning-outcomes/', core_views.faculty_head_learning_outcomes, name='faculty_head_learning_outcomes'),
    path('faculty-head/course/<str:course_name>/learning-outcomes/', core_views.faculty_head_course_learning_outcomes, name='faculty_head_course_learning_outcomes'),
    path('faculty-head/courses/<int:course_id>/learning-outcomes/<int:outcome_id>/', core_views.faculty_head_learning_outcome_detail, name='faculty_head_learning_outcome_detail'),
    path('faculty-head/courses/<int:course_id>/learning-outcomes/<int:outcome_id>/graph/', core_views.faculty_head_learning_outcome_graph, name='faculty_head_learning_outcome_graph'),
    path('faculty-head/learning-outcomes/detail/<int:outcome_id>/unlink/<int:program_outcome_id>/', core_views.faculty_head_unlink_program_outcome, name='faculty_head_unlink_program_outcome'),
    path('faculty-head/learning-outcomes/detail/<int:outcome_id>/link/', core_views.faculty_head_link_program_outcomes, name='faculty_head_link_program_outcomes'),
    path('faculty-head/learning-outcomes/update/<int:outcome_id>/', core_views.faculty_head_update_learning_outcome, name='faculty_head_update_learning_outcome'),
    path('faculty-head/program-outcomes/', core_views.program_outcomes, name='program_outcomes'),
    path('faculty-head/program-outcomes/detail/<int:outcome_id>/', core_views.program_outcome_detail, name='program_outcome_detail'),
    path('faculty-head/program-outcomes/update/<int:outcome_id>/', core_views.update_program_outcome, name='update_program_outcome'),
    path('faculty-head/program-outcomes/delete/<int:outcome_id>/', core_views.delete_program_outcome, name='delete_program_outcome'),
    path('faculty-head/program-outcomes/create/', core_views.create_program_outcome, name='create_program_outcome'),
    path('faculty-head/course/<int:course_id>/grade/', core_views.give_grade, name='give_grade'),

    # Instructor pages
    path('instructor/learning-outcomes/', core_views.learning_outcomes, name='learning_outcomes'),
    path('instructor/learning-outcomes/<str:course_name>/', core_views.course_learning_outcomes, name='course_learning_outcomes'),
    path('instructor/courses/<int:course_id>/learning-outcomes/<int:outcome_id>/', core_views.learning_outcome_detail, name='learning_outcome_detail'),
    path('instructor/courses/<int:course_id>/learning-outcomes/<int:outcome_id>/graph/', core_views.learning_outcome_graph, name='learning_outcome_graph'),
    path('instructor/learning-outcomes/detail/<int:outcome_id>/unlink/<int:program_outcome_id>/', core_views.unlink_program_outcome, name='unlink_program_outcome'),
    path('instructor/learning-outcomes/detail/<int:outcome_id>/link/', core_views.link_program_outcomes, name='link_program_outcomes'),
    path('instructor/learning-outcomes/create/', core_views.create_learning_outcome, name='create_learning_outcome'),
    path('instructor/learning-outcomes/update/<int:outcome_id>/', core_views.update_learning_outcome, name='update_learning_outcome'),
    path('instructor/learning-outcomes/delete/<int:outcome_id>/', core_views.delete_learning_outcome, name='delete_learning_outcome'),

    # Student pages
    path("student/profile/", core_views.student_profile, name="student_profile"),
    path("student/courses/", core_views.student_courses, name="student_courses"),
    path("student/courses/<int:course_id>/learning-outcomes/", core_views.student_course_learning_outcomes, name="student_course_learning_outcomes"),
    path("student/grades/", core_views.student_grades, name="student_grades"),
    path("student/announcements/", core_views.student_announcements, name="student_announcements"),
    path("student/program-outcomes/", core_views.student_program_outcomes, name="student_program_outcomes"),
    path("student/logout/", core_views.logout_view, name="logout"),
    
    # Instructor program outcomes
    path("instructor/program-outcomes/", core_views.instructor_program_outcomes, name="instructor_program_outcomes"),

]
