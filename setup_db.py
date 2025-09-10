import sqlite3

conn = sqlite3.connect('users.db')
c = conn.cursor()

# Sample tables
c.execute("CREATE TABLE IF NOT EXISTS students (id INTEGER PRIMARY KEY, name TEXT, age INTEGER)")
c.execute("CREATE TABLE IF NOT EXISTS courses (id INTEGER PRIMARY KEY, title TEXT, credits INTEGER)")
c.execute("CREATE TABLE IF NOT EXISTS enrollments (id INTEGER PRIMARY KEY, student_id INTEGER, course_id INTEGER)")

# Sample data
c.execute("INSERT INTO students (name, age) VALUES ('Alice', 20), ('Zia', 21), ('John', 19)")
c.execute("INSERT INTO courses (title, credits) VALUES ('Math', 3), ('CS', 4)")
c.execute("INSERT INTO enrollments (student_id, course_id) VALUES (1,1), (2,2)")

conn.commit()
conn.close()
