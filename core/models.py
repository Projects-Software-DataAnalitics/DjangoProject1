from django.db import models

from django.db import models

class Student(models.Model):
    username = models.CharField(max_length=100, unique=True)
    student_id = models.CharField(max_length=20, unique=True)

    def __str__(self):
        return self.username

class Grade(models.Model):
    student = models.ForeignKey(Student, on_delete=models.CASCADE)
    course_name = models.CharField(max_length=100, default='Mathematics')
    midterm = models.FloatField()
    assignment = models.FloatField()
    final = models.FloatField()

    def __str__(self):
        return f"{self.student.username} - Mid: {self.midterm}, Assign: {self.assignment}, Final: {self.final}"

