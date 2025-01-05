"""Script to show SQLite database schema."""
import sqlite3

def show_schema(sqlite_path: str):
    """Show the schema of all tables in the SQLite database."""
    print(f"Reading schema from: {sqlite_path}")
    
    conn = sqlite3.connect(sqlite_path)
    cursor = conn.cursor()
    
    # Get all table names
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
    tables = cursor.fetchall()
    
    print("\nDatabase Schema:")
    print("================")
    
    for table in tables:
        table_name = table[0]
        print(f"\nTable: {table_name}")
        print("-" * (len(table_name) + 7))
        
        # Get table schema
        cursor.execute(f"SELECT sql FROM sqlite_master WHERE type='table' AND name='{table_name}';")
        schema = cursor.fetchone()[0]
        print(schema)
        
        # Get column info
        cursor.execute(f"PRAGMA table_info({table_name});")
        columns = cursor.fetchall()
        
        print("\nColumns:")
        for col in columns:
            cid, name, type_, notnull, dflt_value, pk = col
            print(f"  {name}: {type_}", end="")
            if pk: print(" (PRIMARY KEY)", end="")
            if notnull: print(" NOT NULL", end="")
            if dflt_value is not None: print(f" DEFAULT {dflt_value}", end="")
            print()
        
        # Get sample data (first row)
        cursor.execute(f"SELECT * FROM {table_name} LIMIT 1;")
        sample = cursor.fetchone()
        if sample:
            print("\nSample Data (first row):")
            for col, val in zip(columns, sample):
                print(f"  {col[1]}: {val}")
    
    conn.close()

if __name__ == "__main__":
    # Specify the path to your SQLite database
    SQLITE_PATH = "path/to/your/sqlite.db"  # Ändern Sie dies zu Ihrem Datenbankpfad
    show_schema(SQLITE_PATH) 