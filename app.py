from flask import Flask, render_template, request, redirect, session, url_for, g, flash
import sqlite3
import os
import json
from datetime import datetime
from werkzeug.utils import secure_filename
import shutil
import math

app = Flask(__name__)
app.secret_key = 'your_secret_key'
AUTH_DATABASE = 'users.db'


# ---------- DB Helpers ----------
def get_auth_db():
    db = getattr(g, '_auth_db', None)
    if db is None:
        db = g._auth_db = sqlite3.connect(AUTH_DATABASE)
    return db


def get_app_db_path():
    # Use per-mode db path if set, else default to auth DB for legacy behavior
    return session.get('db_path', AUTH_DATABASE)


def get_app_db():
    db = getattr(g, '_app_db', None)
    if db is None:
        path = get_app_db_path()
        d = os.path.dirname(path)
        if d:
            os.makedirs(d, exist_ok=True)
        db = g._app_db = sqlite3.connect(path)
    return db


@app.teardown_appcontext
def close_connection(exception):
    adb = getattr(g, '_auth_db', None)
    if adb is not None:
        adb.close()
    appdb = getattr(g, '_app_db', None)
    if appdb is not None:
        appdb.close()


def create_user_table():
    with app.app_context():
        db = get_auth_db()
        db.execute('''
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                email TEXT UNIQUE NOT NULL,
                password TEXT NOT NULL
            )
        ''')
        db.commit()


# ---------- Routes ----------
@app.route('/')
def index():
    return render_template('index.html')


@app.route('/signup', methods=['GET', 'POST'])
def signup():
    if request.method == 'POST':
        name = request.form.get('name')
        email = request.form.get('email')
        password = request.form.get('password')

        if not name or not email or not password:
            return "Please fill all fields."

        db = get_auth_db()
        cursor = db.cursor()

        existing_user = cursor.execute("SELECT * FROM users WHERE email = ?", (email,)).fetchone()
        if existing_user:
            return "Email already registered."

        cursor.execute("INSERT INTO users (name, email, password) VALUES (?, ?, ?)", (name, email, password))
        db.commit()
        return redirect(url_for('login'))

    return render_template('signup.html')


@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email = request.form.get('email')
        password = request.form['password']
        db = get_auth_db()
        user = db.execute("SELECT * FROM users WHERE email = ? AND password = ?", (email, password)).fetchone()
        if user:
            session['user'] = user[1]  # name
            session['user_id'] = user[0]
            return redirect(url_for('mode_select'))
        else:
            return "Invalid credentials"
    return render_template('login.html')


@app.route('/mode_select')
def mode_select():
    if 'user' not in session:
        return redirect(url_for('login'))
    return render_template('mode_select.html', user=session.get('user'))


def init_sample_db(path):
    # Recreate sample DB with default schema/data
    if os.path.exists(path):
        os.remove(path)
    conn = sqlite3.connect(path)
    cur = conn.cursor()
    cur.execute("CREATE TABLE students (id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT, age INTEGER, grade TEXT)")
    cur.execute("CREATE TABLE courses (id INTEGER PRIMARY KEY AUTOINCREMENT, title TEXT, credits INTEGER)")
    cur.execute("CREATE TABLE enrollments (student_id INTEGER, course_id INTEGER, date_enrolled TEXT)")
    cur.executemany("INSERT INTO students (name, age, grade) VALUES (?, ?, ?)", [
        ("Alice", 20, "A"), ("Bob", 22, "B"), ("Charlie", 21, "A-")
    ])
    cur.executemany("INSERT INTO courses (title, credits) VALUES (?, ?)", [
        ("Math 101", 3), ("History 201", 4), ("CS 305", 3)
    ])
    cur.executemany("INSERT INTO enrollments (student_id, course_id, date_enrolled) VALUES (?, ?, ?)", [
        (1, 1, "2025-01-15"), (1, 3, "2025-02-01"), (2, 2, "2025-03-10")
    ])
    conn.commit()
    conn.close()


@app.route('/sample_mode')
def sample_mode():
    if 'user' not in session:
        return redirect(url_for('login'))
    session['mode'] = 'sample'
    db_dir = os.path.join('static', 'data')
    os.makedirs(db_dir, exist_ok=True)
    session['db_path'] = os.path.join(db_dir, 'sample.db')
    init_sample_db(session['db_path'])
    return redirect(url_for('dashboard'))


@app.route('/workspace_mode')
def workspace_mode():
    if 'user' not in session:
        return redirect(url_for('login'))
    session['mode'] = 'workspace'
    session.pop('db_path', None)
    return redirect(url_for('workspace_dashboard'))


def list_tables(db_path):
    try:
        conn = sqlite3.connect(db_path)
        cur = conn.cursor()
        cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name")
        tables = [r[0] for r in cur.fetchall()]
        conn.close()
        return tables
    except Exception:
        return []


@app.route('/dashboard')
def dashboard():
    if 'user' not in session:
        return redirect(url_for('login'))
    mode = session.get('mode', 'legacy')
    db_path = get_app_db_path()
    tables = list_tables(db_path) if os.path.exists(db_path) else []
    return render_template('dashboard.html', user=session['user'], mode=mode, tables=tables)


@app.route('/create_table', methods=['POST'])
def create_table():
    table_name = request.form['table_name']
    columns = request.form['columns']
    conn = get_app_db()
    cursor = conn.cursor()
    try:
        query = f"CREATE TABLE IF NOT EXISTS {table_name} ({columns})"
        cursor.execute(query)
        conn.commit()
    except Exception as e:
        flash(f"Error: {str(e)}")
    finally:
        cursor.close()
    return redirect(url_for('dashboard'))


@app.route('/insert_data', methods=['POST'])
def insert_data():
    table_name = request.form['table_name']
    columns = request.form['columns']
    values = request.form['values']
    conn = get_app_db()
    cursor = conn.cursor()
    try:
        query = f"INSERT INTO {table_name} ({columns}) VALUES ({values})"
        cursor.execute(query)
        conn.commit()
    except Exception as e:
        flash(f"Error: {str(e)}")
    finally:
        cursor.close()
    return redirect(url_for('dashboard'))


@app.route('/run-query', methods=['POST'])
def run_query():
    if 'user' not in session:
        return redirect(url_for('login'))

    table = request.form.get('table')
    columns = request.form.get('columns', '*')
    where = request.form.get('where', '')
    order_by = request.form.get('order_by', '')
    limit = request.form.get('limit', '')
    group_by = request.form.get('group_by', '')
    having = request.form.get('having', '')
    join = request.form.get('join', '')

    query = f"SELECT {columns} FROM {table}"
    explanation = f"Selecting {columns} from {table}"

    if join:
        query += f" {join}"
        explanation += f" joined with condition: {join}"

    if where:
        query += f" WHERE {where}"
        explanation += f" where {where}"

    if group_by:
        query += f" GROUP BY {group_by}"
        explanation += f", grouped by {group_by}"

    if having:
        query += f" HAVING {having}"
        explanation += f", having condition {having}"

    if order_by:
        query += f" ORDER BY {order_by}"
        explanation += f", ordered by {order_by}"

    if limit:
        query += f" LIMIT {limit}"
        explanation += f", limited to {limit} results"

    db = get_app_db()
    try:
        cursor = db.execute(query)
        rows = cursor.fetchall()
        headers = [description[0] for description in cursor.description]
    except Exception as e:
        return f"Error in SQL query: {str(e)}"

    db_path = get_app_db_path()
    tables = list_tables(db_path) if os.path.exists(db_path) else []
    return render_template('dashboard.html', user=session['user'], mode=session.get('mode','legacy'), tables=tables, query=query, explanation=explanation, result=rows, headers=headers)


@app.route('/reset_sample', methods=['POST'])
def reset_sample():
    if session.get('mode') != 'sample':
        return redirect(url_for('dashboard'))
    path = session.get('db_path')
    if path:
        init_sample_db(path)
        flash('Sample data reset.')
    return redirect(url_for('dashboard'))


# ---------- Workspace Mode ----------
def user_projects_root():
    user_id = session.get('user_id', 'anon')
    root = os.path.join('user_data', str(user_id), 'projects')
    os.makedirs(root, exist_ok=True)
    return root


def project_path(name):
    return os.path.join(user_projects_root(), secure_filename(name))


def project_db_path(name):
    return os.path.join(project_path(name), f"{secure_filename(name)}.db")


def project_meta_path(name):
    return os.path.join(project_path(name), 'project.json')


def load_projects():
    projects = []
    root = user_projects_root()
    for entry in os.listdir(root):
        pdir = os.path.join(root, entry)
        if os.path.isdir(pdir):
            meta_file = os.path.join(pdir, 'project.json')
            if os.path.exists(meta_file):
                try:
                    with open(meta_file, 'r') as f:
                        meta = json.load(f)
                    projects.append(meta)
                except Exception:
                    pass
    projects.sort(key=lambda m: m.get('last_opened', ''), reverse=True)
    return projects


@app.route('/workspace')
def workspace_dashboard():
    if session.get('mode') != 'workspace':
        return redirect(url_for('mode_select'))
    projects = load_projects()
    current_project = session.get('current_project')
    tables = list_tables(get_app_db_path()) if session.get('db_path') else []
    return render_template('workspace_dashboard.html', user=session['user'], projects=projects, current_project=current_project, tables=tables)


@app.route('/workspace/create', methods=['POST'])
def workspace_create():
    if session.get('mode') != 'workspace':
        return redirect(url_for('mode_select'))
    name = request.form.get('name', '').strip()
    desc = request.form.get('description', '').strip()
    if not name:
        flash('Project name required.')
        return redirect(url_for('workspace_dashboard'))
    pdir = project_path(name)
    os.makedirs(pdir, exist_ok=True)
    dbp = project_db_path(name)
    # create empty db file
    conn = sqlite3.connect(dbp)
    conn.close()
    meta = {
        'name': name,
        'created': datetime.utcnow().strftime('%Y-%m-%d'),
        'last_opened': datetime.utcnow().strftime('%Y-%m-%d'),
        'description': desc
    }
    with open(project_meta_path(name), 'w') as f:
        json.dump(meta, f)
    flash('Project created.')
    return redirect(url_for('workspace_open', name=name))


@app.route('/workspace/open/<name>')
def workspace_open(name):
    if session.get('mode') != 'workspace':
        return redirect(url_for('mode_select'))
    name = secure_filename(name)
    dbp = project_db_path(name)
    if not os.path.exists(dbp):
        flash('Project not found.')
        return redirect(url_for('workspace_dashboard'))
    session['db_path'] = dbp
    session['current_project'] = name
    # update last_opened
    meta_file = project_meta_path(name)
    try:
        with open(meta_file, 'r') as f:
            meta = json.load(f)
        meta['last_opened'] = datetime.utcnow().strftime('%Y-%m-%d')
        with open(meta_file, 'w') as f:
            json.dump(meta, f)
    except Exception:
        pass
    return redirect(url_for('workspace_dashboard'))


@app.route('/workspace/delete/<name>', methods=['POST'])
def workspace_delete(name):
    if session.get('mode') != 'workspace':
        return redirect(url_for('mode_select'))
    name = secure_filename(name)
    pdir = project_path(name)
    if os.path.isdir(pdir):
        shutil.rmtree(pdir)
    if session.get('current_project') == name:
        session.pop('current_project', None)
        session.pop('db_path', None)
    flash('Project deleted.')
    return redirect(url_for('workspace_dashboard'))


@app.route('/workspace/import', methods=['POST'])
def workspace_import():
    if session.get('mode') != 'workspace':
        return redirect(url_for('mode_select'))
    file = request.files.get('dbfile')
    name = request.form.get('name') or (file.filename.rsplit('.', 1)[0] if file else None)
    if not file or not name:
        flash('File and project name required.')
        return redirect(url_for('workspace_dashboard'))
    name = secure_filename(name)
    pdir = project_path(name)
    os.makedirs(pdir, exist_ok=True)
    target = project_db_path(name)
    file.save(target)
    meta = {
        'name': name,
        'created': datetime.utcnow().strftime('%Y-%m-%d'),
        'last_opened': datetime.utcnow().strftime('%Y-%m-%d'),
        'description': 'Imported database'
    }
    with open(project_meta_path(name), 'w') as f:
        json.dump(meta, f)
    flash('Project imported.')
    return redirect(url_for('workspace_open', name=name))


def quote_ident(name: str) -> str:
    # Safely quote an SQLite identifier
    return '"' + name.replace('"', '""') + '"'


@app.route('/workspace/table/<table_name>')
def workspace_table(table_name):
    if session.get('mode') != 'workspace':
        return redirect(url_for('mode_select'))
    if not session.get('db_path'):
        flash('Open a project first.')
        return redirect(url_for('workspace_dashboard'))

    # Pagination params
    try:
        page = max(1, int(request.args.get('page', 1)))
    except Exception:
        page = 1
    try:
        page_size = max(1, min(200, int(request.args.get('page_size', 50))))
    except Exception:
        page_size = 50
    offset = (page - 1) * page_size

    db_path = get_app_db_path()
    tables = list_tables(db_path)
    if table_name not in tables:
        flash('Table not found in current project.')
        return redirect(url_for('workspace_dashboard'))

    qname = quote_ident(table_name)
    conn = get_app_db()
    cur = conn.cursor()
    # total rows
    cur.execute(f'SELECT COUNT(*) FROM {qname}')
    total_rows = cur.fetchone()[0]
    # fetch page rows
    cur.execute(f'SELECT * FROM {qname} LIMIT ? OFFSET ?', (page_size, offset))
    rows = cur.fetchall()
    headers = [d[0] for d in cur.description] if cur.description else []
    cur.close()

    last_page = max(1, math.ceil(total_rows / page_size))
    page = min(page, last_page)
    has_prev = page > 1
    has_next = page < last_page

    projects = load_projects()
    current_project = session.get('current_project')
    return render_template(
        'workspace_dashboard.html',
        user=session['user'],
        projects=projects,
        current_project=current_project,
        tables=tables,
        viewer_headers=headers,
        viewer_rows=rows,
        viewer_table=table_name,
        page=page,
        page_size=page_size,
        total_rows=total_rows,
        has_prev=has_prev,
        has_next=has_next,
        last_page=last_page,
    )


@app.route('/logout')
def logout():
    session.pop('user', None)
    session.pop('user_id', None)
    session.pop('mode', None)
    session.pop('db_path', None)
    session.pop('current_project', None)
    return redirect(url_for('index'))


if __name__ == '__main__':
    create_user_table()
    app.run(debug=True)