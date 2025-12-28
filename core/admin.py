from django.contrib import admin
from .models import Assignment, Notification, AssignmentSubmission

admin.site.register(Assignment)
admin.site.register(Notification)
admin.site.register(AssignmentSubmission)
