from django.shortcuts import render


def index(request):
    return render(request, 'index.html')


def student_login(request):
    return render(request, 'student_login.html')


def instructor_login(request):
    return render(request, 'instructor_login.html')


def faculty_head_login(request):
    return render(request, 'faculty_head_login.html')


def student_dashboard(request):
    return render(request, 'student.html')


def instructor_dashboard(request):
    return render(request, 'instructor.html')


def faculty_head_dashboard(request):
    return render(request, 'faculty_head.html')
