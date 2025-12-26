from .models import Student

def student_info(request):
    if request.user.is_authenticated:
        try:
            student = Student.objects.get(user=request.user)
            return {
                'student_info': {
                    'username': student.username,
                    'name': f"{student.first_name} {student.last_name}".strip() or student.username,
                    'student_id': student.student_id,
                }
            }
        except Student.DoesNotExist:
            return {
                'student_info': {
                    'username': request.user.username,
                    'name': request.user.get_full_name() or request.user.username,
                    'student_id': '-',
                }
            }
    return {'student_info': None}

