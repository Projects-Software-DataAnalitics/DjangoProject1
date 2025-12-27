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

def instructor_info(request):
    if request.user.is_authenticated:
        try:
            profile = request.user.profile
            if profile and profile.role == 'instructor':
                return {
                    'instructor_info': {
                        'username': request.user.username,
                        'name': f"{request.user.first_name} {request.user.last_name}".strip() or request.user.username,
                        'faculty': profile.faculty.name if profile.faculty else '-',
                        'department': profile.department if profile else '-',
                    }
                }
        except AttributeError:
            pass
    return {'instructor_info': None}

def faculty_head_info(request):
    if request.user.is_authenticated:
        try:
            profile = request.user.profile
            if profile and profile.role == 'faculty_head':
                return {
                    'faculty_head_info': {
                        'username': request.user.username,
                        'name': f"{request.user.first_name} {request.user.last_name}".strip() or request.user.username,
                        'faculty': profile.faculty.name if profile.faculty else '-',
                        'department': profile.department if profile else '-',
                    }
                }
        except AttributeError:
            pass
    return {'faculty_head_info': None}

