# PostgreSQL Database Schema Documentation

This documentation describes the structure and relationships of all PostgreSQL tables in the DjangoProject3 project.

## Table of Contents

1. [core_faculty](#1-core_faculty)
2. [core_userprofile](#2-core_userprofile)
3. [core_student](#3-core_student)
4. [core_course](#4-core_course)
5. [core_grade](#5-core_grade)
6. [core_assessment](#6-core_assessment)
7. [core_programoutcome](#7-core_programoutcome)
8. [core_learningoutcomeprogramoutcome](#8-core_learningoutcomeprogramoutcome)
9. [core_announcement](#9-core_announcement)
10. [Many-to-Many Relationship Tables](#10-many-to-many-relationship-tables)

---

## 1. core_faculty

Stores faculty information.

### Table Structure

```sql
CREATE TABLE core_faculty (
    id INTEGER PRIMARY KEY,
    name VARCHAR(200) NOT NULL,
    slug VARCHAR(200) NOT NULL UNIQUE
);
```

### Field Descriptions

| Field Name | Data Type | NULL | Unique | Description |
|------------|-----------|------|--------|-------------|
| `id` | INTEGER | NO | YES | Primary key (auto-increment) |
| `name` | VARCHAR(200) | NO | NO | Faculty name |
| `slug` | VARCHAR(200) | NO | YES | URL-friendly faculty name (unique) |

### Relationships

- **One-to-Many**: `core_userprofile.faculty_id` → `core_faculty.id`
- **One-to-Many**: `core_programoutcome.faculty_id` → `core_faculty.id`

---

## 2. core_userprofile

Stores user profiles. Contains each user's role (student, instructor, faculty head) and faculty information.

### Table Structure

```sql
CREATE TABLE core_userprofile (
    id BIGSERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL UNIQUE,
    role VARCHAR(20) NOT NULL,
    faculty_id INTEGER NULL,
    department VARCHAR(200) DEFAULT '' NOT NULL,
    CONSTRAINT core_userprofile_user_id_5141ad90_fk_auth_user_id 
        FOREIGN KEY (user_id) REFERENCES auth_user(id) 
        DEFERRABLE INITIALLY DEFERRED,
    CONSTRAINT core_userprofile_faculty_id_fk_core_faculty_id 
        FOREIGN KEY (faculty_id) REFERENCES core_faculty(id) 
        ON DELETE SET NULL
);
```

### Field Descriptions

| Field Name | Data Type | NULL | Unique | Default | Description |
|------------|-----------|------|--------|---------|-------------|
| `id` | BIGSERIAL | NO | YES | AUTO | Primary key |
| `user_id` | INTEGER | NO | YES | - | Reference to Django User table |
| `role` | VARCHAR(20) | NO | NO | - | User role: 'student', 'instructor', 'faculty_head' |
| `faculty_id` | INTEGER | YES | NO | NULL | Faculty ID (Foreign Key) |
| `department` | VARCHAR(200) | NO | NO | '' | Department name |

### Relationships

- **One-to-One**: `user_id` → `auth_user.id`
- **Many-to-One**: `faculty_id` → `core_faculty.id` (SET NULL on delete)
- **Many-to-Many**: Related to `core_course` via `core_userprofile_courses` table

### Indexes

- `core_userprofile_user_id_5141ad90`: Index on `user_id`

---

## 3. core_student

Stores student information.

### Table Structure

```sql
CREATE TABLE core_student (
    id BIGSERIAL PRIMARY KEY,
    username VARCHAR(100) NOT NULL UNIQUE,
    student_id VARCHAR(20) NOT NULL UNIQUE,
    first_name VARCHAR(100) DEFAULT '' NOT NULL,
    last_name VARCHAR(100) DEFAULT '' NOT NULL,
    department VARCHAR(200) DEFAULT '' NOT NULL,
    year INTEGER NULL,
    user_id INTEGER NULL UNIQUE,
    CONSTRAINT core_student_user_id_fk_auth_user_id 
        FOREIGN KEY (user_id) REFERENCES auth_user(id) 
        ON DELETE SET NULL
);
```

### Field Descriptions

| Field Name | Data Type | NULL | Unique | Default | Description |
|------------|-----------|------|--------|---------|-------------|
| `id` | BIGSERIAL | NO | YES | AUTO | Primary key |
| `username` | VARCHAR(100) | NO | YES | - | Student username (unique) |
| `student_id` | VARCHAR(20) | NO | YES | - | Student number (unique) |
| `first_name` | VARCHAR(100) | NO | NO | '' | Student first name |
| `last_name` | VARCHAR(100) | NO | NO | '' | Student last name |
| `department` | VARCHAR(200) | NO | NO | '' | Department name |
| `year` | INTEGER | YES | NO | NULL | Academic year |
| `user_id` | INTEGER | YES | YES | NULL | Reference to Django User table (SET NULL on delete) |

### Relationships

- **One-to-One**: `user_id` → `auth_user.id` (SET NULL on delete)
- **One-to-Many**: `core_grade.student_id` → `core_student.id`
- **Many-to-Many**: Related to `core_course` via `core_student_courses` table

### Indexes

- `core_student_username_8c980dcc_like`: Pattern index on `username`
- `core_student_student_id_4b8cfd3a_like`: Pattern index on `student_id`

---

## 4. core_course

Stores course information.

### Table Structure

```sql
CREATE TABLE core_course (
    id BIGSERIAL PRIMARY KEY,
    name VARCHAR(100) NOT NULL,
    code VARCHAR(20) DEFAULT '' NOT NULL,
    instructor_id INTEGER NOT NULL,
    department VARCHAR(200) DEFAULT '' NOT NULL,
    credits INTEGER NULL,
    CONSTRAINT core_course_instructor_id_8dd6ea2e_fk_auth_user_id 
        FOREIGN KEY (instructor_id) REFERENCES auth_user(id) 
        DEFERRABLE INITIALLY DEFERRED
);
```

### Field Descriptions

| Field Name | Data Type | NULL | Unique | Default | Description |
|------------|-----------|------|--------|---------|-------------|
| `id` | BIGSERIAL | NO | YES | AUTO | Primary key |
| `name` | VARCHAR(100) | NO | NO | - | Course name |
| `code` | VARCHAR(20) | NO | NO | '' | Course code |
| `instructor_id` | INTEGER | NO | NO | - | Instructor ID (Foreign Key → auth_user) |
| `department` | VARCHAR(200) | NO | NO | '' | Department name |
| `credits` | INTEGER | YES | NO | NULL | Course credits |

### Relationships

- **Many-to-One**: `instructor_id` → `auth_user.id`
- **One-to-One**: `core_assessment.course_id` → `core_course.id`
- **One-to-Many**: `core_grade.course_id` → `core_course.id`
- **Many-to-Many**: Related to `core_student` via `core_student_courses` table
- **Many-to-Many**: Related to `core_userprofile` via `core_userprofile_courses` table

### Indexes

- `core_course_instructor_id_8dd6ea2e`: Index on `instructor_id`

---

## 5. core_grade

Stores student grades. Supports both the old (midterm, assignment, final) and new dynamic (JSONB) grade systems.

### Table Structure

```sql
CREATE TABLE core_grade (
    id BIGSERIAL PRIMARY KEY,
    student_id BIGINT NOT NULL,
    course_id BIGINT NOT NULL,
    
    -- Old Grade Fields (Backward Compatibility)
    midterm DOUBLE PRECISION NULL,
    assignment DOUBLE PRECISION NULL,
    final DOUBLE PRECISION NULL,
    
    -- New Dynamic Grade System
    grades JSONB DEFAULT '{}' NOT NULL,
    
    -- Finalization Fields
    is_finalized BOOLEAN DEFAULT FALSE NOT NULL,
    finalized_at TIMESTAMP WITH TIME ZONE NULL,
    
    -- CSV Upload Information
    uploaded_file_name VARCHAR(255) DEFAULT '' NOT NULL,
    uploaded_at TIMESTAMP WITH TIME ZONE NULL,
    
    -- Constraints
    CONSTRAINT core_grade_student_id_course_id_90282ccb_uniq 
        UNIQUE (student_id, course_id),
    CONSTRAINT core_grade_course_id_290db5e6_fk_core_course_id 
        FOREIGN KEY (course_id) REFERENCES core_course(id) 
        DEFERRABLE INITIALLY DEFERRED,
    CONSTRAINT core_grade_student_id_7a78bbfb_fk_core_student_id 
        FOREIGN KEY (student_id) REFERENCES core_student(id) 
        DEFERRABLE INITIALLY DEFERRED
);
```

### Field Descriptions

| Field Name | Data Type | NULL | Unique | Default | Description |
|------------|-----------|------|--------|---------|-------------|
| `id` | BIGSERIAL | NO | YES | AUTO | Primary key |
| `student_id` | BIGINT | NO | NO | - | Student ID (Foreign Key) |
| `course_id` | BIGINT | NO | NO | - | Course ID (Foreign Key) |
| `midterm` | DOUBLE PRECISION | YES | NO | NULL | Midterm grade (old system) |
| `assignment` | DOUBLE PRECISION | YES | NO | NULL | Assignment grade (old system) |
| `final` | DOUBLE PRECISION | YES | NO | NULL | Final grade (old system) |
| `grades` | JSONB | NO | NO | `{}` | Dynamic grades (in JSON format) |
| `is_finalized` | BOOLEAN | NO | NO | `FALSE` | Whether grades are finalized |
| `finalized_at` | TIMESTAMP WITH TIME ZONE | YES | NO | NULL | Finalization timestamp |
| `uploaded_file_name` | VARCHAR(255) | NO | NO | '' | Uploaded CSV file name |
| `uploaded_at` | TIMESTAMP WITH TIME ZONE | YES | NO | NULL | CSV upload timestamp |

### Relationships

- **Many-to-One**: `student_id` → `core_student.id`
- **Many-to-One**: `course_id` → `core_course.id`

### Constraints

- **Unique**: `(student_id, course_id)` - Only one grade record per student-course pair

### Indexes

- `core_grade_course_id_290db5e6`: Index on `course_id`
- `core_grade_student_id_7a78bbfb`: Index on `student_id`

### JSONB `grades` Field Example

```json
{
    "1. Midterm": 85.5,
    "2. Midterm": 90.0,
    "Final": 88.5,
    "Project": 95.0,
    "Quiz": 80.0,
    "Assignment": 92.0
}
```

---

## 6. core_assessment

Stores course assessment criteria. Defines assessment types (midterm, final, project, assignment, absence, quiz) and their percentages for each course.

### Table Structure

```sql
CREATE TABLE core_assessment (
    id BIGSERIAL PRIMARY KEY,
    course_id BIGINT NOT NULL UNIQUE,
    
    -- Assessment Counts
    midterm INTEGER DEFAULT 2 NOT NULL,
    final INTEGER DEFAULT 1 NOT NULL,
    project INTEGER DEFAULT 0 NOT NULL,
    assignment INTEGER DEFAULT 0 NOT NULL,
    absence INTEGER DEFAULT 0 NOT NULL,
    quiz INTEGER DEFAULT 0 NOT NULL,
    assessment_count INTEGER DEFAULT 3 NOT NULL,
    
    -- Percentages
    midterm_percentage INTEGER DEFAULT 60 NOT NULL,
    final_percentage INTEGER DEFAULT 40 NOT NULL,
    project_percentage INTEGER DEFAULT 0 NOT NULL,
    assignment_percentage INTEGER DEFAULT 0 NOT NULL,
    absence_percentage INTEGER DEFAULT 0 NOT NULL,
    quiz_percentage INTEGER DEFAULT 0 NOT NULL,
    
    CONSTRAINT core_assessment_course_id_fk_core_course_id 
        FOREIGN KEY (course_id) REFERENCES core_course(id) 
        ON DELETE CASCADE
);
```

### Field Descriptions

| Field Name | Data Type | NULL | Unique | Default | Description |
|------------|-----------|------|--------|---------|-------------|
| `id` | BIGSERIAL | NO | YES | AUTO | Primary key |
| `course_id` | BIGINT | NO | YES | - | Course ID (Foreign Key, Unique) |
| `midterm` | INTEGER | NO | NO | 2 | Number of midterms |
| `final` | INTEGER | NO | NO | 1 | Number of finals |
| `project` | INTEGER | NO | NO | 0 | Number of projects |
| `assignment` | INTEGER | NO | NO | 0 | Number of assignments |
| `absence` | INTEGER | NO | NO | 0 | Number of absence records |
| `quiz` | INTEGER | NO | NO | 0 | Number of quizzes |
| `assessment_count` | INTEGER | NO | NO | 3 | Total assessment count (auto-calculated) |
| `midterm_percentage` | INTEGER | NO | NO | 60 | Midterm percentage |
| `final_percentage` | INTEGER | NO | NO | 40 | Final percentage |
| `project_percentage` | INTEGER | NO | NO | 0 | Project percentage |
| `assignment_percentage` | INTEGER | NO | NO | 0 | Assignment percentage |
| `absence_percentage` | INTEGER | NO | NO | 0 | Absence percentage |
| `quiz_percentage` | INTEGER | NO | NO | 0 | Quiz percentage |

### Relationships

- **One-to-One**: `course_id` → `core_course.id` (CASCADE on delete)

### Notes

- The `assessment_count` field is automatically calculated: `midterm + final + project + assignment + absence + quiz`
- Only one assessment record per course (unique constraint)

---

## 7. core_programoutcome

Stores program outcomes (learning outcomes). Each program outcome is linked to a faculty and the user who created it.

### Table Structure

```sql
CREATE TABLE core_programoutcome (
    id BIGSERIAL PRIMARY KEY,
    text VARCHAR(255) NOT NULL,
    course_name VARCHAR(255) DEFAULT '' NOT NULL,
    faculty_id INTEGER NULL,
    created_by_id INTEGER NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW() NOT NULL,
    CONSTRAINT core_programoutcome_faculty_id_fk_core_faculty_id 
        FOREIGN KEY (faculty_id) REFERENCES core_faculty(id) 
        ON DELETE CASCADE,
    CONSTRAINT core_programoutcome_created_by_id_fk_auth_user_id 
        FOREIGN KEY (created_by_id) REFERENCES auth_user(id) 
        ON DELETE CASCADE
);
```

### Field Descriptions

| Field Name | Data Type | NULL | Unique | Default | Description |
|------------|-----------|------|--------|---------|-------------|
| `id` | BIGSERIAL | NO | YES | AUTO | Primary key |
| `text` | VARCHAR(255) | NO | NO | - | Program outcome text |
| `course_name` | VARCHAR(255) | NO | NO | '' | Related course name |
| `faculty_id` | INTEGER | YES | NO | NULL | Faculty ID (Foreign Key) |
| `created_by_id` | INTEGER | NO | NO | - | Creator user ID (Foreign Key) |
| `created_at` | TIMESTAMP WITH TIME ZONE | NO | NO | NOW() | Creation timestamp |

### Relationships

- **Many-to-One**: `faculty_id` → `core_faculty.id` (CASCADE on delete)
- **Many-to-One**: `created_by_id` → `auth_user.id` (CASCADE on delete)
- **Many-to-Many**: Self-referential relationship via `core_learningoutcomeprogramoutcome` table (learning outcome ↔ program outcome)

### Indexes

- `core_programoutcome_created_by_id_408df781`: Index on `created_by_id`
- `core_programoutcome_faculty_id_*`: Index on `faculty_id` (if exists)

---

## 8. core_learningoutcomeprogramoutcome

Stores relationships and percentages between learning outcomes and program outcomes.

### Table Structure

```sql
CREATE TABLE core_learningoutcomeprogramoutcome (
    id BIGSERIAL PRIMARY KEY,
    learning_outcome_id BIGINT NOT NULL,
    program_outcome_id BIGINT NOT NULL,
    percentage INTEGER DEFAULT 0 NOT NULL,
    CONSTRAINT core_lo_po_learning_outcome_id_fk_core_programoutcome_id 
        FOREIGN KEY (learning_outcome_id) REFERENCES core_programoutcome(id) 
        ON DELETE CASCADE,
    CONSTRAINT core_lo_po_program_outcome_id_fk_core_programoutcome_id 
        FOREIGN KEY (program_outcome_id) REFERENCES core_programoutcome(id) 
        ON DELETE CASCADE,
    CONSTRAINT core_lo_po_learning_outcome_program_outcome_uniq 
        UNIQUE (learning_outcome_id, program_outcome_id),
    CONSTRAINT core_lo_po_percentage_check 
        CHECK (percentage >= 0 AND percentage <= 100)
);
```

### Field Descriptions

| Field Name | Data Type | NULL | Unique | Default | Description |
|------------|-----------|------|--------|---------|-------------|
| `id` | BIGSERIAL | NO | YES | AUTO | Primary key |
| `learning_outcome_id` | BIGINT | NO | NO | - | Learning Outcome ID (Foreign Key → core_programoutcome) |
| `program_outcome_id` | BIGINT | NO | NO | - | Program Outcome ID (Foreign Key → core_programoutcome) |
| `percentage` | INTEGER | NO | NO | 0 | Relationship percentage (0-100) |

### Relationships

- **Many-to-One**: `learning_outcome_id` → `core_programoutcome.id` (CASCADE on delete)
- **Many-to-One**: `program_outcome_id` → `core_programoutcome.id` (CASCADE on delete)

### Constraints

- **Unique**: `(learning_outcome_id, program_outcome_id)` - Only one record per learning outcome and program outcome pair
- **Check**: `percentage >= 0 AND percentage <= 100` - Percentage value must be between 0 and 100

---

## 9. core_announcement

Stores announcements. Used for messaging between instructors and faculty heads.

### Table Structure

```sql
CREATE TABLE core_announcement (
    id BIGSERIAL PRIMARY KEY,
    sender_id INTEGER NOT NULL,
    receiver_id INTEGER NULL,
    subject VARCHAR(200) DEFAULT 'No Topic' NOT NULL,
    message TEXT NOT NULL,
    sender_role VARCHAR(20) NOT NULL,
    receiver_role VARCHAR(20) NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW() NOT NULL,
    CONSTRAINT core_announcement_sender_id_fk_auth_user_id 
        FOREIGN KEY (sender_id) REFERENCES auth_user(id) 
        ON DELETE CASCADE,
    CONSTRAINT core_announcement_receiver_id_fk_auth_user_id 
        FOREIGN KEY (receiver_id) REFERENCES auth_user(id) 
        ON DELETE CASCADE
);
```

### Field Descriptions

| Field Name | Data Type | NULL | Unique | Default | Description |
|------------|-----------|------|--------|---------|-------------|
| `id` | BIGSERIAL | NO | YES | AUTO | Primary key |
| `sender_id` | INTEGER | NO | NO | - | Sender user ID (Foreign Key) |
| `receiver_id` | INTEGER | YES | NO | NULL | Receiver user ID (Foreign Key, NULL means sent to everyone) |
| `subject` | VARCHAR(200) | NO | NO | 'No Topic' | Announcement subject |
| `message` | TEXT | NO | NO | - | Announcement message |
| `sender_role` | VARCHAR(20) | NO | NO | - | Sender role: 'instructor', 'faculty_head' |
| `receiver_role` | VARCHAR(20) | YES | NO | NULL | Receiver role: 'instructor', 'faculty_head' |
| `created_at` | TIMESTAMP WITH TIME ZONE | NO | NO | NOW() | Creation timestamp |

### Relationships

- **Many-to-One**: `sender_id` → `auth_user.id` (CASCADE on delete)
- **Many-to-One**: `receiver_id` → `auth_user.id` (CASCADE on delete, can be NULL)

### Indexes

- `core_announcement_created_at_*`: Index on `created_at` (for ordering)

### Notes

- If `receiver_id` is NULL, the announcement was sent to all users
- Table is ordered by `created_at` in descending order (newest first)

---

## 10. Many-to-Many Relationship Tables

### 10.1. core_student_courses

Stores the many-to-many relationship between students and courses.

```sql
CREATE TABLE core_student_courses (
    id BIGSERIAL PRIMARY KEY,
    student_id BIGINT NOT NULL,
    course_id BIGINT NOT NULL,
    CONSTRAINT core_student_courses_student_id_fk_core_student_id 
        FOREIGN KEY (student_id) REFERENCES core_student(id) 
        ON DELETE CASCADE,
    CONSTRAINT core_student_courses_course_id_fk_core_course_id 
        FOREIGN KEY (course_id) REFERENCES core_course(id) 
        ON DELETE CASCADE,
    CONSTRAINT core_student_courses_student_course_uniq 
        UNIQUE (student_id, course_id)
);
```

**Fields:**
- `student_id`: Student ID (Foreign Key → core_student)
- `course_id`: Course ID (Foreign Key → core_course)
- **Unique Constraint**: `(student_id, course_id)` - Only one record per student-course pair

### 10.2. core_userprofile_courses

Stores the many-to-many relationship between user profiles and courses.

```sql
CREATE TABLE core_userprofile_courses (
    id BIGSERIAL PRIMARY KEY,
    userprofile_id BIGINT NOT NULL,
    course_id BIGINT NOT NULL,
    CONSTRAINT core_userprofile_courses_userprofile_id_fk_core_userprofile_id 
        FOREIGN KEY (userprofile_id) REFERENCES core_userprofile(id) 
        ON DELETE CASCADE,
    CONSTRAINT core_userprofile_courses_course_id_fk_core_course_id 
        FOREIGN KEY (course_id) REFERENCES core_course(id) 
        ON DELETE CASCADE,
    CONSTRAINT core_userprofile_courses_userprofile_course_uniq 
        UNIQUE (userprofile_id, course_id)
);
```

**Fields:**
- `userprofile_id`: User profile ID (Foreign Key → core_userprofile)
- `course_id`: Course ID (Foreign Key → core_course)
- **Unique Constraint**: `(userprofile_id, course_id)` - Only one record per profile-course pair

---

## Database Relationship Diagram

```
auth_user (Django)
    ├── core_userprofile (One-to-One)
    │   ├── core_faculty (Many-to-One)
    │   └── core_course (Many-to-Many via core_userprofile_courses)
    │
    ├── core_student (One-to-One, nullable)
    │   ├── core_grade (One-to-Many)
    │   └── core_course (Many-to-Many via core_student_courses)
    │
    ├── core_course (Many-to-One via instructor_id)
    │   ├── core_assessment (One-to-One)
    │   └── core_grade (One-to-Many)
    │
    ├── core_programoutcome (Many-to-One via created_by_id)
    │   └── core_learningoutcomeprogramoutcome (Many-to-Many, self-referential)
    │
    └── core_announcement (Many-to-One via sender_id, receiver_id)

core_faculty
    ├── core_userprofile (One-to-Many)
    └── core_programoutcome (One-to-Many)
```

---

## Important Notes

1. **JSONB Usage**: The `core_grade.grades` field stores dynamic grade types in JSONB format.

2. **Backward Compatibility**: The `core_grade` table supports both old (`midterm`, `assignment`, `final`) and new (`grades` JSONB) grade systems.

3. **Unique Constraints**: 
   - `core_grade`: `(student_id, course_id)` - Single grade per student-course pair
   - `core_learningoutcomeprogramoutcome`: `(learning_outcome_id, program_outcome_id)` - No duplicate relationships
   - Many-to-Many tables: Single record per pair

4. **CASCADE Delete**: Most foreign key relationships use CASCADE delete, but some use SET NULL (e.g., `core_student.user_id`).

5. **Indexes**: Indexes exist on foreign key fields and frequently queried fields.

---

## Last Update

This documentation is based on migration files and model definitions.
Last migration: `0019_assessment_absence_percentage_and_more`
