# Generated manually for Materialized View implementation
# This creates a materialized view for student grade statistics to improve query performance

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0038_add_missing_assessment_columns'),
    ]

    operations = [
        migrations.RunSQL(
            # Create materialized view for student grade statistics
            sql="""
            CREATE MATERIALIZED VIEW IF NOT EXISTS student_grade_statistics AS
            SELECT 
                s.id AS student_id,
                s.username,
                s.student_id AS student_number,
                s.department,
                c.id AS course_id,
                c.name AS course_name,
                c.department AS course_department,
                g.overall_score,
                g.letter_grade,
                c.credits,
                g.last_changes_at,
                CASE 
                    WHEN g.overall_score >= 90 THEN 'AA'
                    WHEN g.overall_score >= 85 THEN 'AB'
                    WHEN g.overall_score >= 80 THEN 'BB'
                    WHEN g.overall_score >= 75 THEN 'BC'
                    WHEN g.overall_score >= 70 THEN 'CC'
                    WHEN g.overall_score >= 65 THEN 'CD'
                    WHEN g.overall_score >= 60 THEN 'DD'
                    WHEN g.overall_score >= 50 THEN 'FD'
                    ELSE 'FF'
                END AS calculated_letter_grade
            FROM core_student s
            INNER JOIN core_grade g ON s.id = g.student_id
            INNER JOIN core_course c ON g.course_id = c.id
            WHERE g.overall_score IS NOT NULL;
            """,
            # Drop materialized view if migration is reversed
            reverse_sql="DROP MATERIALIZED VIEW IF EXISTS student_grade_statistics;"
        ),
        migrations.RunSQL(
            # Create unique index for CONCURRENT refresh support
            sql="""
            CREATE UNIQUE INDEX IF NOT EXISTS idx_student_grade_stats_unique 
            ON student_grade_statistics(student_id, course_id);
            
            CREATE INDEX IF NOT EXISTS idx_student_grade_stats_student_id 
            ON student_grade_statistics(student_id);
            
            CREATE INDEX IF NOT EXISTS idx_student_grade_stats_course_id 
            ON student_grade_statistics(course_id);
            
            CREATE INDEX IF NOT EXISTS idx_student_grade_stats_department 
            ON student_grade_statistics(department);
            """,
            reverse_sql="""
            DROP INDEX IF EXISTS idx_student_grade_stats_department;
            DROP INDEX IF EXISTS idx_student_grade_stats_course_id;
            DROP INDEX IF EXISTS idx_student_grade_stats_student_id;
            DROP INDEX IF EXISTS idx_student_grade_stats_unique;
            """
        ),
    ]

