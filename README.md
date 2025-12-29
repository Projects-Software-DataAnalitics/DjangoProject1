# Smart School System

**Smart School System** is a comprehensive multi-role academic management system designed for students, instructors, and faculty heads. The system provides role-based authentication, course enrollment, and flexible grade management with CSV uploads, configurable assessments (midterm, final, project, assignment, quiz, absence), automatic weighted average and letter grade calculation, and manual grade entry capabilities. The assignment system enables instructors to create assignments with deadlines and file attachments, while students can submit PDF files with comprehensive tracking. The learning outcomes module allows users to define and link course learning outcomes to program outcomes with contribution percentages, connect assessments to learning outcomes, and generate visual progress graphs with automatic achievement score calculations. Communication features include role-based announcements with pinning functionality, email notifications via Gmail SMTP, SMS notifications via Twilio, and an in-app notification system. Additional features include academic calendar management for tracking important dates and deadlines, student progress tracking with visual graphs across courses and outcomes, and faculty head oversight tools for department-wide analytics and grade finalization. Built on Django with SQLite/PostgreSQL support, the system streamlines academic workflows with automated notifications and data import capabilities.

## Features

- **Multi-Role Authentication**: Student, Instructor, and Faculty Head roles with appropriate access controls
- **Course Management**: Course enrollment, scheduling, and instructor assignment
- **Grade Management**: 
  - CSV upload for bulk grade entry
  - Configurable assessment types (midterm, final, project, assignment, quiz, absence)
  - Customizable assessment weights and percentages
  - Automatic weighted average calculation
  - Letter grade assignment (AA-FF scale)
  - Manual grade entry and updates
- **Assignment System**: Create assignments, set deadlines, file attachments, and student PDF submissions
- **Learning Outcomes & Program Outcomes**: 
  - Define course learning outcomes
  - Link learning outcomes to program outcomes
  - Connect assessments to learning outcomes
  - Visual progress graphs
  - Automatic achievement score calculations
- **Communication**: 
  - Role-based announcements with pinning
  - Email notifications (Gmail SMTP)
  - SMS notifications (Twilio)
  - In-app notification system
- **Academic Calendar**: Upload and manage academic calendars with important dates
- **Student Progress Tracking**: View grades, learning outcomes, and program outcomes with visual graphs
- **Faculty Head Tools**: Department-wide analytics, grade finalization, and program outcome management

## Installation

### Prerequisites

- Python 3.8 or higher
- PostgreSQL (optional, SQLite is used by default)
- pip

### Setup

1. Clone the repository:
```bash
git clone <repository-url>
cd DjangoProject1
```

2. Create a virtual environment:
```bash
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
```

3. Install dependencies:
```bash
pip install -r requirements.txt
```

4. Create a `.env` file in the project root:
```env
# Database Configuration (Optional - defaults to SQLite)
DB_NAME=djangoproject2
DB_USER=postgres
DB_PASSWORD=your_password
DB_HOST=localhost
DB_PORT=5432

# Django Secret Key (generate a new one for production)
SECRET_KEY=your-secret-key-here

# Email Configuration (Optional)
EMAIL_HOST=smtp.gmail.com
EMAIL_PORT=587
EMAIL_USE_TLS=True
EMAIL_HOST_USER=your-email@gmail.com
EMAIL_HOST_PASSWORD=your-app-password
DEFAULT_FROM_EMAIL=noreply@university.edu

# SMS Configuration (Optional - Twilio)
SMS_BACKEND=twilio
TWILIO_ACCOUNT_SID=your_account_sid
TWILIO_AUTH_TOKEN=your_auth_token
TWILIO_PHONE_NUMBER=+1234567890

# Enable/Disable notifications
ENABLE_EMAIL_NOTIFICATIONS=True
ENABLE_SMS_NOTIFICATIONS=True
```

5. Run migrations:
```bash
python manage.py makemigrations
python manage.py migrate
```

6. Create a superuser:
```bash
python manage.py createsuperuser
```

7. Load initial data (optional):
```bash
python manage.py loaddata fixtures/initial_data.json
```

8. Run the development server:
```bash
python manage.py runserver
```

9. Access the application:
   - Main page: http://127.0.0.1:8000/
   - Admin panel: http://127.0.0.1:8000/admin/

## Configuration

### Database

The system supports both SQLite (default) and PostgreSQL. To use PostgreSQL, configure the database settings in `.env` and ensure PostgreSQL is installed and running.

### Email & SMS Notifications

For detailed setup instructions for email and SMS notifications, see [SETUP_INSTRUCTIONS.md](SETUP_INSTRUCTIONS.md).

### User Roles

- **Student**: Can view courses, submit assignments, view grades, track progress, and view announcements
- **Instructor**: Can manage courses, upload grades, create assignments, define learning outcomes, and send announcements
- **Faculty Head**: Has all instructor permissions plus department-wide oversight, grade finalization, and program outcome management

## Technologies Used

- **Backend**: Django 5.2.7
- **Database**: SQLite (default) / PostgreSQL
- **Frontend**: HTML, CSS, JavaScript
- **Email**: Gmail SMTP
- **SMS**: Twilio
- **Other**: python-dotenv for environment variables

## Project Structure

```
DjangoProject1/
├── DjangoProject2/          # Django project settings
│   ├── settings.py
│   ├── urls.py
│   └── wsgi.py
├── core/                    # Main application
│   ├── models.py           # Database models
│   ├── views.py            # View functions
│   ├── services/           # Email and SMS services
│   └── management/         # Custom management commands
├── templates/              # HTML templates
│   ├── student/           # Student templates
│   ├── instructor/        # Instructor templates
│   └── faculty/           # Faculty head templates
├── static/                # Static files (CSS, JS, JSON)
├── fixtures/              # Initial data
├── requirements.txt       # Python dependencies
└── README.md             # This file
```

## Usage

1. **Login**: Access the system through the main page and select your role (Student, Instructor, or Faculty Head)
2. **Students**: View courses, submit assignments, check grades, and track learning outcomes
3. **Instructors**: Manage courses, upload grades via CSV, create assignments, and define learning outcomes
4. **Faculty Heads**: Oversee all courses, finalize grades, manage program outcomes, and view department analytics

## Notes

- The system uses SQLite by default for easy setup. For production, consider using PostgreSQL.
- Email and SMS notifications are optional features that require additional configuration.
- CSV grade uploads must follow the format: `student_id, score`
- Assignment submissions are limited to PDF files.

## License

This project is for academic purposes.

## Support

For issues or questions, please refer to the [SETUP_INSTRUCTIONS.md](SETUP_INSTRUCTIONS.md) file or contact the development team.

