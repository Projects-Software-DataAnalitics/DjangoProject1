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
    path('student-login/', core_views.student_login, name='student-login'),
    path('instructor-login/', core_views.instructor_login, name='instructor-login'),
    path('faculty-head-login/', core_views.faculty_head_login, name='faculty-head-login'),
    path('student/', core_views.student_dashboard, name='student'),
    path('instructor/', core_views.instructor_dashboard, name='instructor'),
    path('faculty-head/', core_views.faculty_head_dashboard, name='faculty-head'),
    path('student/<str:username>/', core_views.student_grades, name='student_grades'),
    path('api/student/<str:username>/grades/', core_views.get_student_grades_api, name='get_student_grades_api'),
    path('api/course/<str:course_name>/students/', core_views.get_course_students, name='get_course_students'),
    path('api/grades/manual/', core_views.save_manual_grades, name='save_manual_grades'),
    path('api/instructor/<str:course_name>/grades/', core_views.get_instructor_grades, name='get_instructor_grades'),
    path('api/students/courses/', core_views.get_all_students_courses, name='get_all_students_courses'),
    path('api/courses/enrollment/', core_views.get_course_enrollment, name='get_course_enrollment'),

]
