# Materialized View Implementation

## Overview
A materialized view `student_grade_statistics` has been created to improve query performance for student grade statistics. This pre-computes and stores grade data, making queries faster.

## Files Created

1. **Migration**: `core/migrations/0037_create_student_grade_statistics_view.py`
   - Creates the materialized view and indexes
   - Note: Due to migration history issues, you may need to run the SQL script manually

2. **SQL Script**: `create_materialized_view.sql`
   - Standalone SQL script to create the materialized view
   - Can be run directly in PostgreSQL

3. **Management Command**: `core/management/commands/refresh_grade_statistics.py`
   - Command to refresh the materialized view
   - Usage: `python manage.py refresh_grade_statistics`

4. **Helper Function**: `get_student_grade_statistics_from_materialized_view()` in `core/views.py`
   - Function to query the materialized view
   - Returns empty list if view doesn't exist (safe fallback)

## Setup Instructions

### Option 1: Run SQL Script (Recommended)
```bash
psql -d djangoproject2 -U postgres -f create_materialized_view.sql
```

### Option 2: Run via Django Shell
```python
python manage.py shell
>>> from django.db import connection
>>> with open('create_materialized_view.sql', 'r') as f:
...     sql = f.read()
...     with connection.cursor() as cursor:
...         cursor.execute(sql)
```

### Option 3: Manual Migration (if migration history is fixed)
```bash
python manage.py migrate core 0037
```

## Usage

### Refresh Materialized View
After grade updates, refresh the view:
```bash
python manage.py refresh_grade_statistics
```

### Use in Views
```python
from core.views import get_student_grade_statistics_from_materialized_view

# Get statistics for a department
stats = get_student_grade_statistics_from_materialized_view(department="Computer Engineering")

# Get statistics for a specific course
stats = get_student_grade_statistics_from_materialized_view(course_id=1)
```

## Benefits

1. **Performance**: Pre-computed data reduces query time
2. **Scalability**: Handles large datasets efficiently
3. **Safe**: If view doesn't exist, function returns empty list (no errors)
4. **Flexible**: Can be refreshed on-demand or scheduled

## Notes

- The materialized view needs to be refreshed periodically to stay current
- Consider setting up a cron job to refresh daily or after grade updates
- The view only includes grades with `overall_score IS NOT NULL`

