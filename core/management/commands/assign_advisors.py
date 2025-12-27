from django.core.management.base import BaseCommand
from django.contrib.auth.models import User
from core.models import Student


class Command(BaseCommand):
    help = 'Assign advisors to students based on their department'

    def handle(self, *args, **options):
        self.stdout.write('Assigning advisors to students...')
        
        # Get advisors from database
        try:
            #Burdan emin değilim, bir bakın.
            # Computer Engineering advisor: Ahmet Bulut (faculty_head)
            computer_eng_advisor = User.objects.get(username='ahmet.bulut')
            
            # Electrical/Electronical Engineering advisor: Kadir Uslu (instructor)
            electrical_eng_advisor = User.objects.get(username='kadir.uslu')
        except User.DoesNotExist as e:
            self.stdout.write(self.style.ERROR(f'Advisor not found: {e}'))
            return
        
        computer_eng_students = Student.objects.filter(
            department__icontains='Computer Engineering'
        )
        
        count_computer = 0
        for student in computer_eng_students:
            student.advisor = computer_eng_advisor
            student.save()
            count_computer += 1
            self.stdout.write(f'Assigned {computer_eng_advisor.username} to {student.username}')
        
        # Electrical Engineering and Electronical Engineering
        electrical_eng_students = Student.objects.filter(
            department__icontains='Electrical Engineering'
        ) | Student.objects.filter(
            department__icontains='Electronical Engineering'
        )
        
        count_electrical = 0
        for student in electrical_eng_students:
            student.advisor = electrical_eng_advisor
            student.save()
            count_electrical += 1
            self.stdout.write(f'Assigned {electrical_eng_advisor.username} to {student.username}')
        
        self.stdout.write(self.style.SUCCESS(
            f'Successfully assigned advisors:\n'
            f'  Computer Engineering: {count_computer} students -> {computer_eng_advisor.username}\n'
            f'  Electrical/Electronical Engineering: {count_electrical} students -> {electrical_eng_advisor.username}'
        ))

