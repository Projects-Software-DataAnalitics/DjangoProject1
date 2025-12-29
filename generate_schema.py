"""
Generate complete database schema from PostgreSQL
"""
import os
import sys
import django

# Setup Django
sys.path.append(os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'DjangoProject2.settings')
django.setup()

from django.db import connection

def generate_schema():
    """Generate complete database schema"""
    schema = []
    schema.append("=" * 80)
    schema.append("DATABASE SCHEMA - djangoproject2")
    schema.append("=" * 80)
    schema.append("")
    
    with connection.cursor() as cursor:
        # Get all tables
        cursor.execute("""
            SELECT table_name 
            FROM information_schema.tables 
            WHERE table_schema = 'public' 
            AND table_type = 'BASE TABLE'
            ORDER BY table_name;
        """)
        tables = [row[0] for row in cursor.fetchall()]
        
        for table in tables:
            schema.append(f"\n{'=' * 80}")
            schema.append(f"TABLE: {table}")
            schema.append(f"{'=' * 80}\n")
            
            # Get columns
            cursor.execute("""
                SELECT 
                    column_name,
                    data_type,
                    character_maximum_length,
                    numeric_precision,
                    numeric_scale,
                    is_nullable,
                    column_default
                FROM information_schema.columns
                WHERE table_schema = 'public' 
                AND table_name = %s
                ORDER BY ordinal_position;
            """, [table])
            
            columns = cursor.fetchall()
            schema.append("Columns:")
            schema.append("-" * 80)
            for col in columns:
                col_name, data_type, max_len, num_prec, num_scale, nullable, default = col
                
                type_str = data_type.upper()
                if max_len:
                    type_str += f"({max_len})"
                elif num_prec:
                    if num_scale:
                        type_str += f"({num_prec},{num_scale})"
                    else:
                        type_str += f"({num_prec})"
                
                nullable_str = "NULL" if nullable == "YES" else "NOT NULL"
                default_str = f" DEFAULT {default}" if default else ""
                
                schema.append(f"  {col_name:30} {type_str:20} {nullable_str}{default_str}")
            
            # Get indexes
            cursor.execute("""
                SELECT indexname, indexdef
                FROM pg_indexes
                WHERE schemaname = 'public' 
                AND tablename = %s
                ORDER BY indexname;
            """, [table])
            
            indexes = cursor.fetchall()
            if indexes:
                schema.append("\nIndexes:")
                schema.append("-" * 80)
                for idx_name, idx_def in indexes:
                    schema.append(f"  {idx_name}")
                    schema.append(f"    {idx_def}")
            
            # Get foreign keys
            cursor.execute("""
                SELECT 
                    tc.constraint_name,
                    kcu.column_name,
                    ccu.table_name AS foreign_table_name,
                    ccu.column_name AS foreign_column_name
                FROM information_schema.table_constraints AS tc
                JOIN information_schema.key_column_usage AS kcu
                    ON tc.constraint_name = kcu.constraint_name
                JOIN information_schema.constraint_column_usage AS ccu
                    ON ccu.constraint_name = tc.constraint_name
                WHERE tc.constraint_type = 'FOREIGN KEY'
                AND tc.table_schema = 'public'
                AND tc.table_name = %s
                ORDER BY tc.constraint_name;
            """, [table])
            
            fks = cursor.fetchall()
            if fks:
                schema.append("\nForeign Keys:")
                schema.append("-" * 80)
                for fk_name, col_name, fk_table, fk_col in fks:
                    schema.append(f"  {fk_name}")
                    schema.append(f"    {table}.{col_name} -> {fk_table}.{fk_col}")
            
            schema.append("")
    
    return "\n".join(schema)

if __name__ == "__main__":
    schema = generate_schema()
    output_file = "database_schema.txt"
    with open(output_file, "w", encoding="utf-8") as f:
        f.write(schema)
    print(f"Schema saved to {output_file}")

