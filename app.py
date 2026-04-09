import os
import re
import uuid
import secrets
from functools import wraps
from flask import Flask, render_template, request, jsonify, redirect, url_for, send_from_directory, session, Response
from flask_login import LoginManager, UserMixin, login_user, logout_user, login_required, current_user
from werkzeug.security import generate_password_hash, check_password_hash
import sqlite3

APP_VERSION = '0.1.29'

app = Flask(__name__)

# Data directory — configurable via env for Docker volume mounting
DATA_DIR = os.environ.get('WM_DATA_DIR', os.path.dirname(os.path.abspath(__file__)))
UPLOAD_DIR = os.path.join(DATA_DIR, 'uploads')
os.makedirs(UPLOAD_DIR, exist_ok=True)

app.config['UPLOAD_FOLDER'] = UPLOAD_DIR
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024

# Secret key: env var > file > auto-generate
if os.environ.get('SECRET_KEY'):
    app.config['SECRET_KEY'] = os.environ['SECRET_KEY']
else:
    SECRET_KEY_FILE = os.path.join(DATA_DIR, '.secret_key')
    if os.path.exists(SECRET_KEY_FILE):
        with open(SECRET_KEY_FILE, 'r') as f:
            app.config['SECRET_KEY'] = f.read().strip()
    else:
        key = secrets.token_hex(32)
        with open(SECRET_KEY_FILE, 'w') as f:
            f.write(key)
        os.chmod(SECRET_KEY_FILE, 0o600)
        app.config['SECRET_KEY'] = key

app.config['SESSION_COOKIE_HTTPONLY'] = True
app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'
app.config['PERMANENT_SESSION_LIFETIME'] = 86400  # 24 hours

ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'webp'}

DATABASE = os.path.join(DATA_DIR, 'warehouse.db')

# ══════════════════════════════════════════
#  LOGIN MANAGER
# ══════════════════════════════════════════

login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'
login_manager.login_message = ''


class User(UserMixin):
    def __init__(self, id, username, display_name, role, active):
        self.id = id
        self.username = username
        self.display_name = display_name
        self.role = role
        self.is_active_user = active

    def get_id(self):
        return str(self.id)

    @property
    def is_admin(self):
        return self.role == 'admin'

    @property
    def can_edit(self):
        return self.role in ('admin', 'editor')

    def is_active(self):
        return bool(self.is_active_user)


@login_manager.user_loader
def load_user(user_id):
    conn = get_db()
    row = conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
    conn.close()
    if row:
        return User(row['id'], row['username'], row['display_name'], row['role'], row['active'])
    return None


def admin_required(f):
    """Decorator: requires admin role."""
    @wraps(f)
    @login_required
    def decorated(*args, **kwargs):
        if not current_user.is_admin:
            return jsonify({'error': 'Admin access required'}), 403
        return f(*args, **kwargs)
    return decorated


def editor_required(f):
    """Decorator: requires admin or editor role."""
    @wraps(f)
    @login_required
    def decorated(*args, **kwargs):
        if not current_user.can_edit:
            return jsonify({'error': 'Editor access required'}), 403
        return f(*args, **kwargs)
    return decorated


# ══════════════════════════════════════════
#  DATABASE
# ══════════════════════════════════════════

def _natural_sort_key(s):
    """Return a sort key for natural alphanumeric sorting.
    Each chunk becomes a (type, value) tuple so ints and strings never compare directly."""
    if not s:
        return [(0, '')]
    parts = re.split(r'(\d+)', str(s))
    # (0, str) for text chunks, (1, int) for number chunks — type flag ensures same-type comparison
    return [(1, int(c)) if c.isdigit() else (0, c.lower()) for c in parts if c]


def get_db():
    conn = sqlite3.connect(DATABASE)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


# ──────────────────────────────────────────
#  MIGRATION SYSTEM
#
#  How it works:
#    - Each migration is a function that receives a db connection
#    - Migrations are registered in MIGRATIONS as (version, function) tuples
#    - On startup, only NEW migrations (version > current) are executed
#    - The schema_version table tracks what's been applied
#
#  To make a schema change in the future:
#    1. Write a new function, e.g. migrate_v3(conn)
#    2. Put your ALTER TABLE / CREATE INDEX / etc. inside it
#    3. Append it to MIGRATIONS: (3, migrate_v3)
#    4. That's it — existing data is preserved
#
#  Example future migration:
#
#    def migrate_v3(conn):
#        """Add a 'condition' column to parts."""
#        conn.execute("ALTER TABLE parts ADD COLUMN condition TEXT DEFAULT ''")
#
#    Then add to MIGRATIONS list:  (3, migrate_v3),
# ──────────────────────────────────────────

def migrate_v1(conn):
    """Initial schema: users table, parts table, indexes, default admin."""
    conn.executescript('''
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT NOT NULL UNIQUE COLLATE NOCASE,
            display_name TEXT DEFAULT '',
            password_hash TEXT NOT NULL,
            role TEXT NOT NULL DEFAULT 'user' CHECK(role IN ('admin', 'user')),
            active INTEGER NOT NULL DEFAULT 1,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS parts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            category TEXT NOT NULL CHECK(category IN ('engine', 'head', 'transmission')),
            sku TEXT DEFAULT '',
            location TEXT DEFAULT '',
            fitment_vehicle TEXT DEFAULT '',
            notes TEXT DEFAULT '',
            image_filename TEXT DEFAULT '',
            head_engine TEXT DEFAULT '',
            head_part TEXT DEFAULT '',
            foundry_number TEXT DEFAULT '',
            foundry TEXT DEFAULT '',
            head_number TEXT DEFAULT '',
            head_type TEXT DEFAULT '',
            engine_name TEXT DEFAULT '',
            engine_head TEXT DEFAULT '',
            engine_litre TEXT DEFAULT '',
            engine_date_stamp TEXT DEFAULT '',
            engine_turns INTEGER DEFAULT 0,
            trans_gear_condition TEXT DEFAULT '',
            trans_spins INTEGER DEFAULT 0,
            trans_shifts INTEGER DEFAULT 0,
            trans_date_code TEXT DEFAULT '',
            trans_stamped_numbers TEXT DEFAULT '',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );

        CREATE INDEX IF NOT EXISTS idx_parts_category ON parts(category);
        CREATE INDEX IF NOT EXISTS idx_parts_sku ON parts(sku);
        CREATE INDEX IF NOT EXISTS idx_parts_fitment ON parts(fitment_vehicle);
    ''')

    # Create default admin if no users exist
    count = conn.execute("SELECT COUNT(*) as n FROM users").fetchone()['n']
    if count == 0:
        pw_hash = generate_password_hash('admin', method='pbkdf2:sha256')
        conn.execute(
            "INSERT INTO users (username, display_name, password_hash, role, active) VALUES (?, ?, ?, ?, ?)",
            ('admin', 'Administrator', pw_hash, 'admin', 1)
        )
        print("\n  ╔══════════════════════════════════════════════╗")
        print("  ║  DEFAULT ADMIN ACCOUNT CREATED               ║")
        print("  ║  Username: admin                              ║")
        print("  ║  Password: admin                              ║")
        print("  ║  ⚠  CHANGE THIS PASSWORD IMMEDIATELY!        ║")
        print("  ╚══════════════════════════════════════════════╝\n")


def migrate_v2(conn):
    """Add location index for sort performance."""
    conn.execute("CREATE INDEX IF NOT EXISTS idx_parts_location ON parts(location)")


def migrate_v3(conn):
    """Add sold, sold_date, and head_old_number fields."""
    conn.execute("ALTER TABLE parts ADD COLUMN sold INTEGER DEFAULT 0")
    conn.execute("ALTER TABLE parts ADD COLUMN sold_date TEXT DEFAULT ''")
    conn.execute("ALTER TABLE parts ADD COLUMN head_old_number TEXT DEFAULT ''")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_parts_sold ON parts(sold)")


def migrate_v4(conn):
    """Add editor role, rename user role to viewer."""
    conn.executescript('''
        CREATE TABLE users_new (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT NOT NULL UNIQUE COLLATE NOCASE,
            display_name TEXT DEFAULT '',
            password_hash TEXT NOT NULL,
            role TEXT NOT NULL DEFAULT 'viewer' CHECK(role IN ('admin', 'editor', 'viewer')),
            active INTEGER NOT NULL DEFAULT 1,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        INSERT INTO users_new (id, username, display_name, password_hash, role, active, created_at)
            SELECT id, username, display_name, password_hash,
                   CASE WHEN role = 'user' THEN 'viewer' ELSE role END,
                   active, created_at
            FROM users;
        DROP TABLE users;
        ALTER TABLE users_new RENAME TO users;
    ''')


def migrate_v5(conn):
    """Add part_images table for multi-image support, migrate existing images."""
    conn.execute('''
        CREATE TABLE IF NOT EXISTS part_images (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            part_id INTEGER NOT NULL,
            filename TEXT NOT NULL,
            sort_order INTEGER DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (part_id) REFERENCES parts(id) ON DELETE CASCADE
        )
    ''')
    conn.execute("CREATE INDEX IF NOT EXISTS idx_part_images_part ON part_images(part_id)")
    # Migrate existing image_filename values into the new table
    rows = conn.execute("SELECT id, image_filename FROM parts WHERE image_filename != '' AND image_filename IS NOT NULL").fetchall()
    for row in rows:
        conn.execute("INSERT INTO part_images (part_id, filename, sort_order) VALUES (?, ?, 0)",
                     (row['id'], row['image_filename']))


def migrate_v6(conn):
    """Convert engine_turns, trans_spins, trans_shifts from integer toggles to text radio values."""
    # engine_turns: 1 -> 'yes', 0 -> 'untested'
    conn.execute("UPDATE parts SET engine_turns = CASE WHEN engine_turns = 1 THEN 'yes' WHEN engine_turns = 0 THEN 'untested' ELSE 'untested' END WHERE category = 'engine'")
    # trans_spins: 0 -> 'untested', 1 -> 'yes'
    conn.execute("UPDATE parts SET trans_spins = CASE WHEN trans_spins = 1 THEN 'yes' WHEN trans_spins = 0 THEN 'untested' ELSE 'untested' END WHERE category = 'transmission'")
    # trans_shifts: 0 -> 'untested', 1 -> 'yes'
    conn.execute("UPDATE parts SET trans_shifts = CASE WHEN trans_shifts = 1 THEN 'yes' WHEN trans_shifts = 0 THEN 'untested' ELSE 'untested' END WHERE category = 'transmission'")


def migrate_v7(conn):
    """Normalize engine_turns values to yes/no/untested."""
    conn.execute("UPDATE parts SET engine_turns = 'yes' WHERE engine_turns = 'turns'")
    conn.execute("UPDATE parts SET engine_turns = 'no' WHERE engine_turns = 'does_not_turn'")


def migrate_v8(conn):
    """Add custom categories and category_fields tables, custom_data column on parts."""
    conn.executescript('''
        CREATE TABLE IF NOT EXISTS categories (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            slug TEXT NOT NULL UNIQUE,
            name TEXT NOT NULL,
            icon TEXT DEFAULT '',
            color TEXT DEFAULT '#4a8eff',
            sort_order INTEGER DEFAULT 0,
            is_builtin INTEGER DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS category_fields (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            category_slug TEXT NOT NULL,
            field_key TEXT NOT NULL,
            field_label TEXT NOT NULL,
            field_type TEXT NOT NULL DEFAULT 'text',
            radio_options TEXT DEFAULT '',
            show_on_card INTEGER DEFAULT 0,
            show_in_table INTEGER DEFAULT 0,
            sort_order INTEGER DEFAULT 0,
            FOREIGN KEY (category_slug) REFERENCES categories(slug) ON DELETE CASCADE
        );

        CREATE INDEX IF NOT EXISTS idx_cf_slug ON category_fields(category_slug);
    ''')
    # Add custom_data column for flexible JSON storage
    try:
        conn.execute("ALTER TABLE parts ADD COLUMN custom_data TEXT DEFAULT '{}'")
    except Exception:
        pass  # column may already exist

    # Register built-in categories
    for slug, name, color, order in [
        ('engine', 'Engine', '#f59e0b', 1),
        ('head', 'Cylinder Head', '#10b981', 2),
        ('transmission', 'Transmission', '#a78bfa', 3),
    ]:
        existing = conn.execute("SELECT id FROM categories WHERE slug = ?", (slug,)).fetchone()
        if not existing:
            conn.execute("INSERT INTO categories (slug, name, color, sort_order, is_builtin) VALUES (?, ?, ?, ?, 1)",
                         (slug, name, color, order))

    # Remove the CHECK constraint on category column by rebuilding parts table
    # This allows custom category slugs
    cols_info = conn.execute("PRAGMA table_info(parts)").fetchall()
    col_names = [c['name'] for c in cols_info]
    cols_str = ', '.join(col_names)

    # Create new table without CHECK constraint on category
    create_cols = []
    for c in cols_info:
        col_def = f"{c['name']} {c['type']}"
        if c['name'] == 'category':
            col_def = "category TEXT NOT NULL"
        elif c['notnull'] and c['dflt_value'] is not None:
            col_def += f" NOT NULL DEFAULT {c['dflt_value']}"
        elif c['notnull']:
            col_def += " NOT NULL"
        elif c['dflt_value'] is not None:
            col_def += f" DEFAULT {c['dflt_value']}"
        if c['pk']:
            col_def += " PRIMARY KEY AUTOINCREMENT"
        create_cols.append(col_def)

    conn.execute(f"CREATE TABLE parts_new ({', '.join(create_cols)})")
    conn.execute(f"INSERT INTO parts_new ({cols_str}) SELECT {cols_str} FROM parts")
    conn.execute("DROP TABLE parts")
    conn.execute("ALTER TABLE parts_new RENAME TO parts")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_parts_category ON parts(category)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_parts_sku ON parts(sku)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_parts_fitment ON parts(fitment_vehicle)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_parts_location ON parts(location)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_parts_sold ON parts(sold)")


def migrate_v9(conn):
    """Add product_number column and assign retroactively starting at WM-1000000."""
    try:
        conn.execute("ALTER TABLE parts ADD COLUMN product_number TEXT DEFAULT ''")
    except Exception:
        pass
    conn.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_parts_product_number ON parts(product_number) WHERE product_number != ''")
    # Assign numbers to existing parts ordered by id
    rows = conn.execute("SELECT id FROM parts WHERE product_number = '' OR product_number IS NULL ORDER BY id").fetchall()
    # Find the next available number
    max_row = conn.execute("SELECT product_number FROM parts WHERE product_number LIKE 'WM-%' ORDER BY product_number DESC LIMIT 1").fetchone()
    if max_row and max_row['product_number']:
        try:
            next_num = int(max_row['product_number'].replace('WM-', '')) + 1
        except ValueError:
            next_num = 1000000
    else:
        next_num = 1000000
    for row in rows:
        conn.execute("UPDATE parts SET product_number = ? WHERE id = ?", (f"WM-{next_num}", row['id']))
        next_num += 1


def migrate_v10(conn):
    """Register field definitions for original categories and mark all categories as non-builtin."""
    import json as json_mod

    # Define field sets for the three original categories
    head_fields = [
        ('sku', 'SKU', 'text', '', 0, 1),
        ('head_old_number', 'Old SKU', 'text', '', 0, 1),
        ('location', 'Location', 'text', '', 1, 1),
        ('head_engine', 'Engine', 'text', '', 1, 1),
        ('head_part', 'Part', 'text', '', 0, 0),
        ('foundry_number', 'Foundry Number', 'text', '', 0, 0),
        ('foundry', 'Foundry', 'text', '', 0, 1),
        ('head_number', 'Head Number', 'text', '', 1, 1),
        ('head_type', 'Type', 'text', '', 0, 0),
        ('fitment_vehicle', 'Fitment Vehicle', 'text', '', 1, 1),
        ('sold', 'Sold', 'toggle', '', 0, 1),
        ('sold_date', 'Sold Date', 'text', '', 0, 0),
        ('notes', 'Notes', 'textarea', '', 0, 0),
    ]

    engine_fields = [
        ('sku', 'SKU', 'text', '', 0, 1),
        ('location', 'Location', 'text', '', 1, 1),
        ('engine_turns', 'Turns', 'radio', 'Yes,No,Untested', 0, 1),
        ('engine_name', 'Engine', 'text', '', 1, 1),
        ('engine_head', 'Head', 'text', '', 0, 0),
        ('engine_litre', 'Litre', 'text', '', 1, 1),
        ('engine_date_stamp', 'Date Stamp', 'text', '', 0, 1),
        ('fitment_vehicle', 'Fitment Vehicle', 'text', '', 1, 1),
        ('sold', 'Sold', 'toggle', '', 0, 1),
        ('sold_date', 'Sold Date', 'text', '', 0, 0),
        ('notes', 'Notes', 'textarea', '', 0, 0),
    ]

    trans_fields = [
        ('sku', 'SKU', 'text', '', 0, 1),
        ('location', 'Location', 'text', '', 1, 1),
        ('trans_spins', 'Spins', 'radio', 'Yes,No,Untested', 0, 1),
        ('trans_shifts', 'Shifts', 'radio', 'Yes,No,Untested', 0, 1),
        ('trans_date_code', 'Date Code', 'text', '', 0, 1),
        ('trans_stamped_numbers', 'Stamped Numbers', 'text', '', 0, 1),
        ('fitment_vehicle', 'Fitment Vehicle', 'text', '', 1, 1),
        ('sold', 'Sold', 'toggle', '', 0, 1),
        ('sold_date', 'Sold Date', 'text', '', 0, 0),
        ('notes', 'Notes', 'textarea', '', 0, 0),
    ]

    cat_field_map = {
        'head': head_fields,
        'engine': engine_fields,
        'transmission': trans_fields,
    }

    for slug, fields_def in cat_field_map.items():
        # Only insert fields if none exist yet for this category
        existing = conn.execute("SELECT COUNT(*) as n FROM category_fields WHERE category_slug = ?", (slug,)).fetchone()['n']
        if existing == 0:
            for i, (key, label, ftype, radio_opts, show_card, show_table) in enumerate(fields_def):
                conn.execute(
                    "INSERT INTO category_fields (category_slug, field_key, field_label, field_type, radio_options, show_on_card, show_in_table, sort_order) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                    (slug, key, label, ftype, radio_opts, show_card, show_table, i)
                )

    # Mark all categories as non-builtin (deletable)
    conn.execute("UPDATE categories SET is_builtin = 0")

    # Migrate existing hardcoded column data into custom_data JSON for all parts
    rows = conn.execute("SELECT * FROM parts").fetchall()
    hardcoded_keys = {
        'head': ['sku', 'location', 'head_engine', 'head_part', 'foundry_number', 'foundry',
                 'head_number', 'head_type', 'head_old_number', 'fitment_vehicle', 'sold', 'sold_date', 'notes'],
        'engine': ['sku', 'location', 'engine_turns', 'engine_name', 'engine_head', 'engine_litre',
                   'engine_date_stamp', 'fitment_vehicle', 'sold', 'sold_date', 'notes'],
        'transmission': ['sku', 'location', 'trans_spins', 'trans_shifts', 'trans_date_code',
                         'trans_stamped_numbers', 'fitment_vehicle', 'sold', 'sold_date', 'notes'],
    }
    # Shared fields that stay in their own columns (not moved to custom_data)
    shared_keys = {'sku', 'location', 'fitment_vehicle', 'sold', 'sold_date', 'notes',
                   'category', 'id', 'image_filename', 'created_at', 'updated_at', 'product_number', 'custom_data'}

    for row in rows:
        r = dict(row)
        cat = r.get('category', '')
        if cat not in hardcoded_keys:
            continue
        existing_cd = {}
        try:
            existing_cd = json_mod.loads(r.get('custom_data', '{}') or '{}')
        except Exception:
            pass
        # Move category-specific hardcoded columns into custom_data
        for key in hardcoded_keys[cat]:
            if key in shared_keys:
                continue
            val = r.get(key, '')
            if val and key not in existing_cd:
                existing_cd[key] = str(val) if val else ''
        if existing_cd:
            conn.execute("UPDATE parts SET custom_data = ? WHERE id = ?",
                         (json_mod.dumps(existing_cd), r['id']))


def migrate_v11(conn):
    """Deduplicate category_fields created by v10 race condition across Gunicorn workers."""
    # For each category, keep only the first set of fields (lowest IDs)
    cats = conn.execute("SELECT DISTINCT category_slug FROM category_fields").fetchall()
    for cat in cats:
        slug = cat['category_slug']
        # Get all fields grouped by field_key, keeping the one with lowest id
        rows = conn.execute(
            "SELECT field_key, MIN(id) as keep_id FROM category_fields WHERE category_slug = ? GROUP BY field_key",
            (slug,)
        ).fetchall()
        keep_ids = [r['keep_id'] for r in rows]
        if keep_ids:
            placeholders = ','.join(['?'] * len(keep_ids))
            conn.execute(
                f"DELETE FROM category_fields WHERE category_slug = ? AND id NOT IN ({placeholders})",
                [slug] + keep_ids
            )


# ┌──────────────────────────────────────────────┐
# │  MIGRATIONS REGISTRY — append new ones here  │
# └──────────────────────────────────────────────┘
MIGRATIONS = [
    (1, migrate_v1),
    (2, migrate_v2),
    (3, migrate_v3),
    (4, migrate_v4),
    (5, migrate_v5),
    (6, migrate_v6),
    (7, migrate_v7),
    (8, migrate_v8),
    (9, migrate_v9),
    (10, migrate_v10),
    (11, migrate_v11),
    # (12, migrate_v12),  ← your next change goes here
]


def init_db():
    """Run all pending migrations (with file lock to prevent Gunicorn worker races)."""
    import fcntl
    lock_path = os.path.join(DATA_DIR, '.migration_lock')
    lock_file = open(lock_path, 'w')
    try:
        fcntl.flock(lock_file, fcntl.LOCK_EX)

        conn = get_db()
        conn.execute('''
            CREATE TABLE IF NOT EXISTS schema_version (
                version INTEGER NOT NULL
            )
        ''')

        row = conn.execute("SELECT MAX(version) as v FROM schema_version").fetchone()
        current_version = row['v'] if row['v'] is not None else 0

        applied = 0
        for version, migrate_fn in MIGRATIONS:
            if version > current_version:
                print(f"  → Applying migration v{version}: {migrate_fn.__doc__.strip()}")
                migrate_fn(conn)
                conn.execute("INSERT INTO schema_version (version) VALUES (?)", (version,))
                conn.commit()
                applied += 1

        if applied:
            print(f"  ✓ {applied} migration(s) applied (now at v{MIGRATIONS[-1][0]})")
        else:
            print(f"  ✓ Database up to date (v{current_version})")

        conn.close()
    finally:
        fcntl.flock(lock_file, fcntl.LOCK_UN)
        lock_file.close()


# ══════════════════════════════════════════
#  SEARCH COLS
# ══════════════════════════════════════════

SEARCH_COLS = {
    'head': ['sku','location','head_engine','head_part','foundry_number','foundry','head_number','head_type','head_old_number','fitment_vehicle','sold_date','notes'],
    'engine': ['sku','location','engine_name','engine_head','engine_litre','engine_date_stamp','fitment_vehicle','sold_date','notes'],
    'transmission': ['sku','location','trans_date_code','trans_stamped_numbers','fitment_vehicle','sold_date','notes'],
}
ALL_SEARCH_COLS = list(set(col for cols in SEARCH_COLS.values() for col in cols))

ALL_FIELDS = [
    'category','sku','location','fitment_vehicle','notes','image_filename',
    'sold','sold_date',
    'head_engine','head_part','foundry_number','foundry','head_number','head_type','head_old_number',
    'engine_name','engine_head','engine_litre','engine_date_stamp','engine_turns',
    'trans_gear_condition','trans_spins','trans_shifts','trans_date_code','trans_stamped_numbers',
]
INT_FIELDS = {'sold'}
RADIO_FIELDS = {'engine_turns', 'trans_spins', 'trans_shifts'}

# Importable fields per category (used by import system)
IMPORT_FIELDS = {
    'head': [
        ('sku', 'SKU'), ('head_old_number', 'Old SKU'), ('location', 'Location'), ('head_engine', 'Engine'),
        ('head_part', 'Part'), ('foundry_number', 'Foundry Number'), ('foundry', 'Foundry'),
        ('head_number', 'Head Number'), ('head_type', 'Type'),
        ('fitment_vehicle', 'Fitment Vehicle'), ('sold', 'Sold'), ('sold_date', 'Sold Date'),
        ('notes', 'Notes'),
    ],
    'engine': [
        ('sku', 'SKU'), ('location', 'Location'), ('engine_turns', 'Turns'),
        ('engine_name', 'Engine'), ('engine_head', 'Head'), ('engine_litre', 'Litre'),
        ('engine_date_stamp', 'Date Stamp'), ('fitment_vehicle', 'Fitment Vehicle'),
        ('sold', 'Sold'), ('sold_date', 'Sold Date'), ('notes', 'Notes'),
    ],
    'transmission': [
        ('sku', 'SKU'), ('location', 'Location'), ('trans_spins', 'Spins'),
        ('trans_shifts', 'Shifts'), ('trans_date_code', 'Date Code'),
        ('trans_stamped_numbers', 'Stamped Numbers'), ('fitment_vehicle', 'Fitment Vehicle'),
        ('sold', 'Sold'), ('sold_date', 'Sold Date'), ('notes', 'Notes'),
    ],
}

UPLOAD_TEMP = os.path.join(UPLOAD_DIR, 'temp')
os.makedirs(UPLOAD_TEMP, exist_ok=True)


# ══════════════════════════════════════════
#  HELPERS
# ══════════════════════════════════════════

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def save_image(file_field):
    if file_field and file_field.filename and allowed_file(file_field.filename):
        ext = file_field.filename.rsplit('.', 1)[1].lower()
        fname = f"{uuid.uuid4().hex}.{ext}"
        file_field.save(os.path.join(app.config['UPLOAD_FOLDER'], fname))
        return fname
    return ''

def delete_image(filename):
    if filename:
        path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        if os.path.exists(path):
            os.remove(path)


def get_part_images(conn, part_id):
    """Get all images for a part, ordered by sort_order."""
    rows = conn.execute(
        "SELECT id, filename, sort_order FROM part_images WHERE part_id = ? ORDER BY sort_order, id",
        (part_id,)
    ).fetchall()
    return [dict(r) for r in rows]


def save_part_images(conn, part_id, files):
    """Save multiple uploaded images for a part."""
    max_order = conn.execute(
        "SELECT COALESCE(MAX(sort_order), -1) FROM part_images WHERE part_id = ?", (part_id,)
    ).fetchone()[0]
    saved = []
    for f in files:
        fname = save_image(f)
        if fname:
            max_order += 1
            conn.execute(
                "INSERT INTO part_images (part_id, filename, sort_order) VALUES (?, ?, ?)",
                (part_id, fname, max_order)
            )
            saved.append(fname)
    return saved


def enrich_part_with_images(conn, part_dict):
    """Add images list and primary image_filename to a part dict."""
    images = get_part_images(conn, part_dict['id'])
    part_dict['images'] = images
    part_dict['image_filename'] = images[0]['filename'] if images else ''
    return part_dict


def assign_product_number(conn):
    """Get the next available product number and return it."""
    row = conn.execute("SELECT product_number FROM parts WHERE product_number LIKE 'WM-%' ORDER BY CAST(SUBSTR(product_number, 4) AS INTEGER) DESC LIMIT 1").fetchone()
    if row and row['product_number']:
        try:
            next_num = int(row['product_number'].replace('WM-', '')) + 1
        except ValueError:
            next_num = 1000000
    else:
        next_num = 1000000
    return f"WM-{next_num}"

def form_val(key, default=''):
    val = request.form.get(key, default)
    if key in INT_FIELDS:
        try: return int(val)
        except (ValueError, TypeError): return 0
    return val


# ══════════════════════════════════════════
#  AUTH ROUTES
# ══════════════════════════════════════════

@app.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('index'))

    if request.method == 'POST':
        # Try JSON first, fall back to form data
        username = ''
        password = ''
        is_ajax = False
        try:
            data = request.get_json(force=True, silent=True)
            if data and isinstance(data, dict) and 'username' in data:
                username = data.get('username', '').strip()
                password = data.get('password', '')
                is_ajax = True
        except Exception:
            pass

        if not is_ajax:
            username = request.form.get('username', '').strip()
            password = request.form.get('password', '')
            # Check if this was an AJAX request by header
            is_ajax = request.headers.get('X-Requested-With') == 'XMLHttpRequest'

        conn = get_db()
        row = conn.execute("SELECT * FROM users WHERE username = ?", (username,)).fetchone()
        conn.close()

        if row and row['active'] and check_password_hash(row['password_hash'], password):
            user = User(row['id'], row['username'], row['display_name'], row['role'], row['active'])
            login_user(user, remember=True)
            session.permanent = True

            if is_ajax:
                return jsonify({'success': True, 'redirect': url_for('index')})
            return redirect(request.args.get('next') or url_for('index'))

        if is_ajax:
            return jsonify({'error': 'Invalid username or password'}), 401
        return render_template('login.html', error='Invalid username or password')

    return render_template('login.html', error=None)


@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('login'))


@app.route('/api/auth/me')
@login_required
def auth_me():
    return jsonify({
        'id': current_user.id,
        'username': current_user.username,
        'display_name': current_user.display_name,
        'role': current_user.role,
        'can_edit': current_user.can_edit,
        'version': APP_VERSION,
    })


@app.route('/api/auth/change-password', methods=['POST'])
@login_required
def change_own_password():
    data = request.get_json()
    current_pw = data.get('current_password', '')
    new_pw = data.get('new_password', '')

    if not new_pw or len(new_pw) < 4:
        return jsonify({'error': 'New password must be at least 4 characters'}), 400

    conn = get_db()
    row = conn.execute("SELECT password_hash FROM users WHERE id = ?", (current_user.id,)).fetchone()
    if not check_password_hash(row['password_hash'], current_pw):
        conn.close()
        return jsonify({'error': 'Current password is incorrect'}), 400

    conn.execute("UPDATE users SET password_hash = ? WHERE id = ?",
                 (generate_password_hash(new_pw, method='pbkdf2:sha256'), current_user.id))
    conn.commit()
    conn.close()
    return jsonify({'success': True})


# ══════════════════════════════════════════
#  ADMIN — USER MANAGEMENT
# ══════════════════════════════════════════

@app.route('/api/users', methods=['GET'])
@admin_required
def list_users():
    conn = get_db()
    rows = conn.execute("SELECT id, username, display_name, role, active, created_at FROM users ORDER BY created_at").fetchall()
    conn.close()
    return jsonify([dict(r) for r in rows])


@app.route('/api/users', methods=['POST'])
@admin_required
def create_user():
    data = request.get_json()
    username = data.get('username', '').strip()
    display_name = data.get('display_name', '').strip()
    password = data.get('password', '')
    role = data.get('role', 'viewer')

    if not username or not password:
        return jsonify({'error': 'Username and password are required'}), 400
    if len(password) < 4:
        return jsonify({'error': 'Password must be at least 4 characters'}), 400
    if role not in ('admin', 'editor', 'viewer'):
        return jsonify({'error': 'Invalid role'}), 400

    conn = get_db()
    existing = conn.execute("SELECT id FROM users WHERE username = ?", (username,)).fetchone()
    if existing:
        conn.close()
        return jsonify({'error': 'Username already exists'}), 409

    pw_hash = generate_password_hash(password, method='pbkdf2:sha256')
    cur = conn.execute(
        "INSERT INTO users (username, display_name, password_hash, role, active) VALUES (?, ?, ?, ?, 1)",
        (username, display_name or username, pw_hash, role)
    )
    conn.commit()
    row = conn.execute("SELECT id, username, display_name, role, active, created_at FROM users WHERE id = ?",
                       (cur.lastrowid,)).fetchone()
    conn.close()
    return jsonify(dict(row)), 201


@app.route('/api/users/<int:uid>', methods=['PUT'])
@admin_required
def update_user(uid):
    data = request.get_json()
    conn = get_db()
    existing = conn.execute("SELECT * FROM users WHERE id = ?", (uid,)).fetchone()
    if not existing:
        conn.close()
        return jsonify({'error': 'User not found'}), 404

    # Prevent demoting yourself or deactivating yourself
    if uid == current_user.id:
        if data.get('role') and data['role'] != 'admin':
            conn.close()
            return jsonify({'error': 'Cannot remove your own admin role'}), 400
        if 'active' in data and not data['active']:
            conn.close()
            return jsonify({'error': 'Cannot deactivate your own account'}), 400

    username = data.get('username', existing['username']).strip()
    display_name = data.get('display_name', existing['display_name']).strip()
    role = data.get('role', existing['role'])
    active = int(data.get('active', existing['active']))

    if role not in ('admin', 'editor', 'viewer'):
        conn.close()
        return jsonify({'error': 'Invalid role'}), 400

    # Check username conflict
    conflict = conn.execute("SELECT id FROM users WHERE username = ? AND id != ?", (username, uid)).fetchone()
    if conflict:
        conn.close()
        return jsonify({'error': 'Username already taken'}), 409

    conn.execute("UPDATE users SET username=?, display_name=?, role=?, active=? WHERE id=?",
                 (username, display_name, role, active, uid))

    # Optional password reset
    new_pw = data.get('password', '')
    if new_pw:
        if len(new_pw) < 4:
            conn.close()
            return jsonify({'error': 'Password must be at least 4 characters'}), 400
        conn.execute("UPDATE users SET password_hash = ? WHERE id = ?",
                     (generate_password_hash(new_pw, method='pbkdf2:sha256'), uid))

    conn.commit()
    row = conn.execute("SELECT id, username, display_name, role, active, created_at FROM users WHERE id = ?",
                       (uid,)).fetchone()
    conn.close()
    return jsonify(dict(row))


@app.route('/api/users/<int:uid>', methods=['DELETE'])
@admin_required
def delete_user(uid):
    if uid == current_user.id:
        return jsonify({'error': 'Cannot delete your own account'}), 400

    conn = get_db()
    existing = conn.execute("SELECT id FROM users WHERE id = ?", (uid,)).fetchone()
    if not existing:
        conn.close()
        return jsonify({'error': 'User not found'}), 404

    conn.execute("DELETE FROM users WHERE id = ?", (uid,))
    conn.commit()
    conn.close()
    return jsonify({'success': True})


# ══════════════════════════════════════════
#  PAGE ROUTES
# ══════════════════════════════════════════

@app.route('/')
@login_required
def index():
    return render_template('index.html')


@app.route('/uploads/<filename>')
@login_required
def uploaded_file(filename):
    return send_from_directory(app.config['UPLOAD_FOLDER'], filename)


# ══════════════════════════════════════════
#  PARTS API (all @login_required)
# ══════════════════════════════════════════

@app.route('/api/parts', methods=['GET'])
@login_required
def get_parts():
    category = request.args.get('category', '')
    search = request.args.get('search', '').strip()
    page = int(request.args.get('page', 1))
    per_page = int(request.args.get('per_page', 24))

    conn = get_db()
    conds, params = [], []
    if category:
        conds.append("category = ?")
        params.append(category)
    if search:
        term = f"%{search}%"
        cols = ['sku', 'location', 'fitment_vehicle', 'notes', 'sold_date', 'custom_data']
        conds.append("(" + " OR ".join(f"{c} LIKE ?" for c in cols) + ")")
        params.extend([term] * len(cols))

    where = "WHERE " + " AND ".join(conds) if conds else ""

    # Sorting
    SORT_ALLOWED = {'sku', 'location', 'fitment_vehicle', 'updated_at'}
    sort_by = request.args.get('sort_by', 'updated_at')
    sort_dir = request.args.get('sort_dir', 'desc').lower()
    if sort_by not in SORT_ALLOWED:
        sort_by = 'updated_at'
    if sort_dir not in ('asc', 'desc'):
        sort_dir = 'desc'
    reverse = sort_dir == 'desc'

    if sort_by in ('sku', 'location', 'fitment_vehicle'):
        rows = conn.execute(f"SELECT * FROM parts {where}", params).fetchall()
        parts = [dict(r) for r in rows]
        parts.sort(key=lambda p: _natural_sort_key(p.get(sort_by, '')), reverse=reverse)
        total = len(parts)
        offset = (page - 1) * per_page
        page_parts = parts[offset:offset + per_page]
    else:
        total = conn.execute(f"SELECT COUNT(*) as n FROM parts {where}", params).fetchone()['n']
        offset = (page - 1) * per_page
        rows = conn.execute(
            f"SELECT * FROM parts {where} ORDER BY {sort_by} {sort_dir.upper()} LIMIT ? OFFSET ?",
            params + [per_page, offset]
        ).fetchall()
        page_parts = [dict(r) for r in rows]

    # Batch-fetch first image for each part
    if page_parts:
        pids = [p['id'] for p in page_parts]
        placeholders = ','.join(['?'] * len(pids))
        img_rows = conn.execute(
            f"SELECT part_id, filename FROM part_images WHERE part_id IN ({placeholders}) ORDER BY sort_order, id",
            pids
        ).fetchall()
        # Build map: part_id -> first filename
        first_img = {}
        for r in img_rows:
            if r['part_id'] not in first_img:
                first_img[r['part_id']] = r['filename']
        for p in page_parts:
            p['image_filename'] = first_img.get(p['id'], '')

    conn.close()
    return jsonify({
        'parts': page_parts, 'total': total, 'page': page,
        'per_page': per_page, 'pages': max(1, (total + per_page - 1) // per_page)
    })


def _valid_category(conn, slug):
    """Check if a category slug exists (built-in or custom)."""
    return conn.execute("SELECT id FROM categories WHERE slug = ?", (slug,)).fetchone() is not None



@app.route('/api/parts', methods=['POST'])
@editor_required
def create_part():
    f = request.form
    category = f.get('category', '')

    conn = get_db()
    if not _valid_category(conn, category):
        conn.close()
        return jsonify({'error': 'Invalid category'}), 400

    import json as json_mod

    # Shared fields go in SQL columns; category-specific fields go in custom_data
    shared_keys = {'category', 'sku', 'location', 'fitment_vehicle', 'sold', 'sold_date', 'notes'}
    fields = [fld for fld in ALL_FIELDS if fld != 'image_filename']
    vals = [form_val(fld) for fld in fields] + ['']

    # Build custom_data from category fields
    cat_fields = conn.execute(
        "SELECT field_key FROM category_fields WHERE category_slug = ? ORDER BY sort_order", (category,)
    ).fetchall()
    custom_data = {}
    for cf in cat_fields:
        k = cf['field_key']
        if k in shared_keys:
            continue  # these are already in SQL columns via form_val
        # Check both custom_ prefixed and direct form keys
        if f"custom_{k}" in f:
            custom_data[k] = f.get(f"custom_{k}", '')
        elif k in f:
            custom_data[k] = f.get(k, '')

    fields_with_cd = fields + ['image_filename', 'custom_data']
    vals_with_cd = vals[:-1] + ['', json_mod.dumps(custom_data)]
    placeholders = ','.join(['?'] * len(fields_with_cd))
    col_names = ','.join(fields_with_cd)
    cur = conn.execute(f"INSERT INTO parts ({col_names}) VALUES ({placeholders})", vals_with_cd)

    part_id = cur.lastrowid

    # Assign product number
    pn = assign_product_number(conn)
    conn.execute("UPDATE parts SET product_number = ? WHERE id = ?", (pn, part_id))

    images = request.files.getlist('images')
    if not images or not images[0].filename:
        images = request.files.getlist('image')
    save_part_images(conn, part_id, images)

    conn.commit()
    row = conn.execute("SELECT * FROM parts WHERE id = ?", (part_id,)).fetchone()
    part = enrich_part_with_images(conn, dict(row))
    conn.close()
    return jsonify(part), 201


@app.route('/api/parts/<int:pid>', methods=['GET'])
@login_required
def get_part(pid):
    conn = get_db()
    row = conn.execute("SELECT * FROM parts WHERE id = ?", (pid,)).fetchone()
    if not row:
        conn.close()
        return jsonify({'error': 'Not found'}), 404
    part = enrich_part_with_images(conn, dict(row))
    conn.close()
    return jsonify(part)


@app.route('/api/parts/<int:pid>', methods=['PUT'])
@editor_required
def update_part(pid):
    conn = get_db()
    existing = conn.execute("SELECT * FROM parts WHERE id = ?", (pid,)).fetchone()
    if not existing:
        conn.close()
        return jsonify({'error': 'Not found'}), 404
    f = request.form
    category = f.get('category', existing['category'])
    if not _valid_category(conn, category):
        conn.close()
        return jsonify({'error': 'Invalid category'}), 400

    fields = [fld for fld in ALL_FIELDS if fld != 'image_filename']
    sets = ','.join(f"{fld}=?" for fld in fields)
    vals = []
    for fld in fields:
        vals.append(form_val(fld) if fld in request.form else existing[fld])

    # Handle custom_data - all categories use it now
    import json as json_mod
    shared_keys = {'category', 'sku', 'location', 'fitment_vehicle', 'sold', 'sold_date', 'notes'}
    cat_fields = conn.execute(
        "SELECT field_key FROM category_fields WHERE category_slug = ? ORDER BY sort_order", (category,)
    ).fetchall()
    existing_cd = {}
    try:
        existing_cd = json_mod.loads(existing['custom_data'] or '{}')
    except Exception:
        pass
    for cf in cat_fields:
        k = cf['field_key']
        if k in shared_keys:
            continue
        if f"custom_{k}" in f:
            existing_cd[k] = f.get(f"custom_{k}", '')
        elif k in f:
            existing_cd[k] = f.get(k, '')
    sets += ",custom_data=?"
    vals.append(json_mod.dumps(existing_cd))

    sets += ",updated_at=CURRENT_TIMESTAMP"
    vals.append(pid)
    conn.execute(f"UPDATE parts SET {sets} WHERE id=?", vals)

    # Handle new image uploads (add to gallery)
    images = request.files.getlist('images')
    if not images or not images[0].filename:
        images = request.files.getlist('image')
    if images and images[0].filename:
        save_part_images(conn, pid, images)

    conn.commit()
    row = conn.execute("SELECT * FROM parts WHERE id = ?", (pid,)).fetchone()
    part = enrich_part_with_images(conn, dict(row))
    conn.close()
    return jsonify(part)


@app.route('/api/parts/<int:pid>/images/<int:img_id>', methods=['DELETE'])
@editor_required
def delete_part_image(pid, img_id):
    conn = get_db()
    row = conn.execute("SELECT * FROM part_images WHERE id = ? AND part_id = ?", (img_id, pid)).fetchone()
    if not row:
        conn.close()
        return jsonify({'error': 'Image not found'}), 404
    delete_image(row['filename'])
    conn.execute("DELETE FROM part_images WHERE id = ?", (img_id,))
    conn.commit()
    conn.close()
    return jsonify({'success': True})


@app.route('/api/parts/<int:pid>', methods=['DELETE'])
@editor_required
def delete_part(pid):
    conn = get_db()
    existing = conn.execute("SELECT * FROM parts WHERE id = ?", (pid,)).fetchone()
    if not existing:
        conn.close()
        return jsonify({'error': 'Not found'}), 404
    # Delete all images
    imgs = conn.execute("SELECT filename FROM part_images WHERE part_id = ?", (pid,)).fetchall()
    for img in imgs:
        delete_image(img['filename'])
    conn.execute("DELETE FROM part_images WHERE part_id = ?", (pid,))
    delete_image(existing['image_filename'])  # legacy field
    conn.execute("DELETE FROM parts WHERE id = ?", (pid,))
    conn.commit()
    conn.close()
    return jsonify({'success': True})


@app.route('/api/stats', methods=['GET'])
@login_required
def get_stats():
    conn = get_db()
    cats = conn.execute("SELECT slug, name FROM categories ORDER BY sort_order").fetchall()
    stats = {}
    total = 0
    for cat in cats:
        n = conn.execute("SELECT COUNT(*) as n FROM parts WHERE category = ?", (cat['slug'],)).fetchone()['n']
        stats[cat['slug']] = n
        total += n
    stats['total'] = total
    conn.close()
    return jsonify(stats)


# ══════════════════════════════════════════
#  CATEGORIES API
# ══════════════════════════════════════════

@app.route('/api/categories', methods=['GET'])
@login_required
def get_categories():
    conn = get_db()
    cats = conn.execute("SELECT * FROM categories ORDER BY sort_order, id").fetchall()
    result = []
    for cat in cats:
        c = dict(cat)
        fields = conn.execute(
            "SELECT * FROM category_fields WHERE category_slug = ? ORDER BY sort_order, id",
            (c['slug'],)
        ).fetchall()
        c['fields'] = [dict(f) for f in fields]
        result.append(c)
    conn.close()
    return jsonify(result)


@app.route('/api/categories', methods=['POST'])
@admin_required
def create_category():
    data = request.get_json()
    name = data.get('name', '').strip()
    if not name:
        return jsonify({'error': 'Name is required'}), 400

    # Generate slug
    slug = re.sub(r'[^a-z0-9]+', '_', name.lower()).strip('_')
    if not slug:
        return jsonify({'error': 'Invalid name'}), 400

    color = data.get('color', '#4a8eff')
    icon = data.get('icon', '')
    fields_data = data.get('fields', [])

    conn = get_db()
    existing = conn.execute("SELECT id FROM categories WHERE slug = ?", (slug,)).fetchone()
    if existing:
        conn.close()
        return jsonify({'error': 'A category with this name already exists'}), 409

    max_order = conn.execute("SELECT COALESCE(MAX(sort_order), 0) FROM categories").fetchone()[0]
    conn.execute(
        "INSERT INTO categories (slug, name, icon, color, sort_order, is_builtin) VALUES (?, ?, ?, ?, ?, 0)",
        (slug, name, icon, color, max_order + 1)
    )

    for i, f in enumerate(fields_data):
        conn.execute(
            "INSERT INTO category_fields (category_slug, field_key, field_label, field_type, radio_options, show_on_card, show_in_table, sort_order) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (slug, f.get('field_key', '').strip(), f.get('field_label', '').strip(),
             f.get('field_type', 'text'), f.get('radio_options', ''),
             int(f.get('show_on_card', 0)), int(f.get('show_in_table', 0)), i)
        )

    conn.commit()
    conn.close()
    return jsonify({'success': True, 'slug': slug}), 201


@app.route('/api/categories/<slug>', methods=['PUT'])
@admin_required
def update_category(slug):
    conn = get_db()
    existing = conn.execute("SELECT * FROM categories WHERE slug = ?", (slug,)).fetchone()
    if not existing:
        conn.close()
        return jsonify({'error': 'Category not found'}), 404

    data = request.get_json()
    name = data.get('name', existing['name']).strip()
    color = data.get('color', existing['color'])
    icon = data.get('icon', existing['icon'])

    conn.execute("UPDATE categories SET name=?, color=?, icon=? WHERE slug=?",
                 (name, color, icon, slug))

    # Replace fields if provided
    if 'fields' in data:
        conn.execute("DELETE FROM category_fields WHERE category_slug = ?", (slug,))
        for i, f in enumerate(data['fields']):
            conn.execute(
                "INSERT INTO category_fields (category_slug, field_key, field_label, field_type, radio_options, show_on_card, show_in_table, sort_order) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (slug, f.get('field_key', '').strip(), f.get('field_label', '').strip(),
                 f.get('field_type', 'text'), f.get('radio_options', ''),
                 int(f.get('show_on_card', 0)), int(f.get('show_in_table', 0)), i)
            )

    conn.commit()
    conn.close()
    return jsonify({'success': True})


@app.route('/api/categories/<slug>', methods=['DELETE'])
@admin_required
def delete_category(slug):
    conn = get_db()
    existing = conn.execute("SELECT * FROM categories WHERE slug = ?", (slug,)).fetchone()
    if not existing:
        conn.close()
        return jsonify({'error': 'Category not found'}), 404
    # Check for parts using this category
    count = conn.execute("SELECT COUNT(*) as n FROM parts WHERE category = ?", (slug,)).fetchone()['n']
    if count > 0:
        conn.close()
        return jsonify({'error': f'Cannot delete: {count} parts use this category. Remove or reassign them first.'}), 400

    conn.execute("DELETE FROM category_fields WHERE category_slug = ?", (slug,))
    conn.execute("DELETE FROM categories WHERE slug = ?", (slug,))
    conn.commit()
    conn.close()
    return jsonify({'success': True})


# ══════════════════════════════════════════
#  IMPORT API
# ══════════════════════════════════════════

def _read_file_rows(temp_path, sheet_name=None):
    """Read all rows from a CSV or Excel file. Returns list of string lists."""
    import csv as csv_module
    ext = temp_path.rsplit('.', 1)[-1].lower()
    all_rows = []
    if ext == 'csv':
        with open(temp_path, 'r', encoding='utf-8-sig', errors='replace') as f:
            for row in csv_module.reader(f):
                all_rows.append([str(c).strip() for c in row])
    else:
        from openpyxl import load_workbook
        wb = load_workbook(temp_path, read_only=True, data_only=True)
        ws = wb[sheet_name] if sheet_name else wb.active
        for row in ws.iter_rows(values_only=True):
            all_rows.append([str(c) if c is not None else '' for c in row])
        wb.close()
    return all_rows

@app.route('/api/import/fields', methods=['GET'])
@login_required
def import_fields():
    """Return importable field definitions per category."""
    return jsonify({cat: [{'key': k, 'label': l} for k, l in fields]
                    for cat, fields in IMPORT_FIELDS.items()})


@app.route('/api/import/upload', methods=['POST'])
@editor_required
def import_upload():
    """Upload an Excel or CSV file, return sheet names, column headers, and sample rows."""
    import csv as csv_module
    from io import StringIO

    if 'file' not in request.files:
        return jsonify({'error': 'No file uploaded'}), 400
    file = request.files['file']
    if not file.filename:
        return jsonify({'error': 'No file selected'}), 400

    ext = file.filename.rsplit('.', 1)[-1].lower() if '.' in file.filename else ''
    if ext not in ('xlsx', 'xls', 'xlsm', 'csv'):
        return jsonify({'error': 'File must be .xlsx, .xls, .xlsm, or .csv'}), 400

    # Save temp file
    temp_name = f"{uuid.uuid4().hex}.{ext}"
    temp_path = os.path.join(UPLOAD_TEMP, temp_name)
    file.save(temp_path)

    try:
        result = {'temp_file': temp_name, 'sheets': []}

        if ext == 'csv':
            with open(temp_path, 'r', encoding='utf-8-sig', errors='replace') as f:
                reader = csv_module.reader(f)
                rows_data = []
                for row in reader:
                    rows_data.append([str(c).strip() for c in row])
                    if len(rows_data) > 25:
                        break
            if rows_data:
                result['sheets'].append({
                    'name': 'CSV',
                    'headers': rows_data[0],
                    'sample_rows': rows_data[1:],
                    'col_count': len(rows_data[0]),
                })
        else:
            from openpyxl import load_workbook
            wb = load_workbook(temp_path, read_only=True, data_only=True)
            for sheet_name in wb.sheetnames:
                ws = wb[sheet_name]
                rows_data = []
                for row in ws.iter_rows(values_only=True):
                    rows_data.append([str(c) if c is not None else '' for c in row])
                    if len(rows_data) > 25:
                        break
                if not rows_data:
                    continue
                result['sheets'].append({
                    'name': sheet_name,
                    'headers': rows_data[0],
                    'sample_rows': rows_data[1:],
                    'col_count': len(rows_data[0]),
                })
            wb.close()

        return jsonify(result)
    except Exception as e:
        if os.path.exists(temp_path):
            os.remove(temp_path)
        return jsonify({'error': f'Failed to read file: {str(e)}'}), 400


@app.route('/api/import/preview', methods=['POST'])
@editor_required
def import_preview():
    """Dry run: apply column mapping and return preview of what would be imported."""
    data = request.get_json()
    temp_file = data.get('temp_file', '')
    sheet_name = data.get('sheet', '')
    category = data.get('category', '')
    mapping = data.get('mapping', {})
    header_row = data.get('header_row', 0)

    if category not in IMPORT_FIELDS:
        return jsonify({'error': 'Invalid category'}), 400

    temp_path = os.path.join(UPLOAD_TEMP, temp_file)
    if not os.path.exists(temp_path):
        return jsonify({'error': 'Uploaded file not found. Please re-upload.'}), 404

    try:
        all_rows = _read_file_rows(temp_path, sheet_name)
    except Exception as e:
        return jsonify({'error': f'Failed to read file: {str(e)}'}), 400

    # Data rows start after header
    data_rows = all_rows[header_row + 1:]

    # Build preview
    field_labels = {k: l for k, l in IMPORT_FIELDS[category]}
    preview_rows = []
    errors = []

    for row_idx, row in enumerate(data_rows):
        # Skip completely empty rows
        if all(c.strip() == '' for c in row):
            continue

        mapped = {}
        for db_field, col_idx_str in mapping.items():
            col_idx = int(col_idx_str)
            if col_idx < 0:
                continue
            value = row[col_idx] if col_idx < len(row) else ''
            # Handle toggle fields (sold)
            if db_field in INT_FIELDS:
                value_lower = value.strip().lower()
                if value_lower in ('yes', 'y', '1', 'true'):
                    mapped[db_field] = 1
                elif value_lower in ('no', 'n', '0', 'false', ''):
                    mapped[db_field] = 0
                else:
                    mapped[db_field] = 0
                    errors.append(f"Row {row_idx + 1}: '{db_field}' value '{value}' not recognized, defaulting to No")
            elif db_field in RADIO_FIELDS:
                mapped[db_field] = value.strip().lower() if value.strip() else 'untested'
            else:
                mapped[db_field] = value.strip()

        # Check if row has any meaningful data
        text_vals = [v for k, v in mapped.items() if k not in INT_FIELDS and k not in RADIO_FIELDS and v]
        if not text_vals:
            continue

        mapped['_row_num'] = row_idx + header_row + 2  # Excel row number (1-based + header)
        preview_rows.append(mapped)

    return jsonify({
        'category': category,
        'field_labels': field_labels,
        'fields': [k for k, l in IMPORT_FIELDS[category]],
        'preview': preview_rows,
        'total': len(preview_rows),
        'warnings': errors,
    })


@app.route('/api/import/execute', methods=['POST'])
@editor_required
def import_execute():
    """Execute the import: insert all mapped rows into the database."""
    data = request.get_json()
    temp_file = data.get('temp_file', '')
    sheet_name = data.get('sheet', '')
    category = data.get('category', '')
    mapping = data.get('mapping', {})
    header_row = data.get('header_row', 0)

    if category not in IMPORT_FIELDS:
        return jsonify({'error': 'Invalid category'}), 400

    temp_path = os.path.join(UPLOAD_TEMP, temp_file)
    if not os.path.exists(temp_path):
        return jsonify({'error': 'Uploaded file not found. Please re-upload.'}), 404

    try:
        all_rows = _read_file_rows(temp_path, sheet_name)
    except Exception as e:
        return jsonify({'error': f'Failed to read file: {str(e)}'}), 400

    data_rows = all_rows[header_row + 1:]

    # Determine all db columns to insert
    valid_fields = {k for k, l in IMPORT_FIELDS[category]}
    mapped_fields = [f for f in mapping.keys() if f in valid_fields and int(mapping[f]) >= 0]

    conn = get_db()
    inserted = 0
    errors = []

    for row_idx, row in enumerate(data_rows):
        if all((c.strip() == '' if isinstance(c, str) else c == '') for c in row):
            continue

        vals = {'category': category}
        has_data = False

        for db_field in mapped_fields:
            col_idx = int(mapping[db_field])
            value = row[col_idx] if col_idx < len(row) else ''
            value = value.strip() if isinstance(value, str) else value

            if db_field in INT_FIELDS:
                value_lower = str(value).strip().lower()
                vals[db_field] = 1 if value_lower in ('yes', 'y', '1', 'true') else 0
            elif db_field in RADIO_FIELDS:
                vals[db_field] = str(value).strip().lower() if str(value).strip() else 'untested'
            else:
                vals[db_field] = value
                if value:
                    has_data = True

        if not has_data:
            continue

        # Build insert
        all_cols = ['category'] + mapped_fields
        placeholders = ','.join(['?'] * len(all_cols))
        col_names = ','.join(all_cols)
        col_vals = [vals.get(c, '') for c in all_cols]

        try:
            cur = conn.execute(f"INSERT INTO parts ({col_names}) VALUES ({placeholders})", col_vals)
            pn = assign_product_number(conn)
            conn.execute("UPDATE parts SET product_number = ? WHERE id = ?", (pn, cur.lastrowid))
            inserted += 1
        except Exception as e:
            errors.append(f"Row {row_idx + header_row + 2}: {str(e)}")

    conn.commit()
    conn.close()

    # Cleanup temp file
    try:
        os.remove(temp_path)
    except OSError:
        pass

    return jsonify({
        'success': True,
        'inserted': inserted,
        'errors': errors,
    })


# ══════════════════════════════════════════
#  EXPORT API
# ══════════════════════════════════════════

@app.route('/api/export/csv', methods=['GET'])
@editor_required
def export_csv():
    """Export entire inventory as CSV."""
    import csv as csv_module
    from io import StringIO

    conn = get_db()
    rows = conn.execute("SELECT * FROM parts ORDER BY category, sku").fetchall()

    # Get all categories and their fields for headers
    all_cats = conn.execute("SELECT slug FROM categories ORDER BY sort_order").fetchall()
    all_cat_fields = {}
    all_custom_keys = []  # ordered unique custom field keys
    for cat in all_cats:
        cfs = conn.execute(
            "SELECT field_key, field_label FROM category_fields WHERE category_slug = ? ORDER BY sort_order",
            (cat['slug'],)
        ).fetchall()
        all_cat_fields[cat['slug']] = cfs
        for cf in cfs:
            if cf['field_key'] not in ('sku', 'location', 'fitment_vehicle', 'sold', 'sold_date', 'notes') and cf['field_key'] not in [k for k, _ in all_custom_keys]:
                all_custom_keys.append((cf['field_key'], cf['field_label']))
    conn.close()

    import json as json_mod
    shared_cols = [
        ('product_number', 'Product Number'),
        ('category', 'Category'),
        ('sku', 'SKU'),
        ('location', 'Location'),
        ('fitment_vehicle', 'Fitment Vehicle'),
        ('sold', 'Sold'),
        ('sold_date', 'Sold Date'),
        ('notes', 'Notes'),
    ]
    all_cols = shared_cols + all_custom_keys

    output = StringIO()
    writer = csv_module.writer(output)
    writer.writerow([label for _, label in all_cols])

    for row in rows:
        r = dict(row)
        cd = {}
        try:
            cd = json_mod.loads(r.get('custom_data', '{}') or '{}')
        except Exception:
            pass
        csv_row = []
        for key, _ in all_cols:
            if key in ('product_number', 'category', 'sku', 'location', 'fitment_vehicle', 'sold_date', 'notes'):
                csv_row.append(r.get(key, '') or '')
            elif key == 'sold':
                csv_row.append('Yes' if r.get('sold') else 'No')
            else:
                # Custom data field — check custom_data first, then legacy SQL column
                val = cd.get(key, '') or r.get(key, '') or ''
                csv_row.append(str(val))
        writer.writerow(csv_row)

    csv_data = output.getvalue()
    output.close()

    return Response(
        csv_data,
        mimetype='text/csv',
        headers={'Content-Disposition': 'attachment; filename=warehouse-export.csv'}
    )


# ══════════════════════════════════════════
#  LABEL & QR CODE API
# ══════════════════════════════════════════

def _generate_qr_png(data_str):
    """Generate a QR code as PNG bytes."""
    import qrcode
    from io import BytesIO
    qr = qrcode.QRCode(version=1, error_correction=qrcode.constants.ERROR_CORRECT_M, box_size=10, border=1)
    qr.add_data(data_str)
    qr.make(fit=True)
    img = qr.make_image(fill_color="black", back_color="white")
    buf = BytesIO()
    img.save(buf, format='PNG')
    buf.seek(0)
    return buf.getvalue()


def _get_label_fields(conn, part):
    """Get printable fields for a part (excluding sold, sold_date, notes, images)."""
    import json as json_mod
    cat = part['category']
    exclude_keys = {'sold', 'sold_date', 'notes'}

    fields = []
    fields.append(('Product #', part.get('product_number', '')))
    fields.append(('Category', getCatName(conn, cat)))

    cat_field_rows = conn.execute(
        "SELECT field_key, field_label, field_type FROM category_fields WHERE category_slug = ? ORDER BY sort_order",
        (cat,)
    ).fetchall()

    cd = {}
    try:
        cd = json_mod.loads(part.get('custom_data', '{}') or '{}')
    except Exception:
        pass

    for cf in cat_field_rows:
        k, label, ftype = cf['field_key'], cf['field_label'], cf['field_type']
        if k in exclude_keys:
            continue
        # Get value from custom_data first, then SQL column fallback
        val = cd.get(k, '') or part.get(k, '') or ''
        if ftype == 'toggle':
            val = 'Yes' if val and val not in ('0', 'No', 'false') else ''
        elif ftype == 'radio' and val:
            val = val.capitalize()
        if val:
            fields.append((label, str(val)))

    return fields


def getCatName(conn, slug):
    row = conn.execute("SELECT name FROM categories WHERE slug = ?", (slug,)).fetchone()
    return row['name'] if row else slug


@app.route('/api/parts/<int:pid>/qr.png')
@login_required
def part_qr_code(pid):
    conn = get_db()
    row = conn.execute("SELECT product_number FROM parts WHERE id = ?", (pid,)).fetchone()
    conn.close()
    if not row:
        return 'Not found', 404
    png = _generate_qr_png(row['product_number'])
    return Response(png, mimetype='image/png')


@app.route('/api/parts/<int:pid>/label.pdf')
@login_required
def part_label_pdf(pid):
    from reportlab.lib.pagesizes import inch
    from reportlab.lib.units import mm
    from reportlab.pdfgen import canvas as pdf_canvas
    from reportlab.lib.utils import ImageReader
    from io import BytesIO

    conn = get_db()
    row = conn.execute("SELECT * FROM parts WHERE id = ?", (pid,)).fetchone()
    if not row:
        conn.close()
        return jsonify({'error': 'Not found'}), 404
    part = dict(row)
    label_fields = _get_label_fields(conn, part)
    conn.close()

    # 4" x 1" label
    w, h = 4 * inch, 1 * inch
    buf = BytesIO()
    c = pdf_canvas.Canvas(buf, pagesize=(w, h))

    # QR code on the left
    qr_png = _generate_qr_png(part.get('product_number', ''))
    qr_img = ImageReader(BytesIO(qr_png))
    qr_size = 0.82 * inch
    c.drawImage(qr_img, 4, (h - qr_size) / 2, qr_size, qr_size)

    # Text fields on the right
    x_start = qr_size + 10
    text_area_w = w - x_start - 6
    y = h - 13

    # Product number bold
    c.setFont("Helvetica-Bold", 9)
    pn = part.get('product_number', '')
    c.drawString(x_start, y, pn)
    y -= 10

    # SKU bold same size
    sku = part.get('sku', '')
    if sku:
        c.setFont("Helvetica-Bold", 9)
        c.drawString(x_start, y, sku)
        y -= 10

    # Remaining fields in two columns
    remaining = [(lbl, val) for lbl, val in label_fields if lbl not in ('Product #', 'SKU')]
    col_width = text_area_w / 2 - 2
    font_size = 7
    line_h = 7
    c.setFont("Helvetica", font_size)

    col1_x = x_start
    col2_x = x_start + text_area_w / 2
    mid = (len(remaining) + 1) // 2
    col1_items = remaining[:mid]
    col2_items = remaining[mid:]

    col_y = y
    for item in col1_items:
        text = f"{item[0]}: {item[1]}"
        while c.stringWidth(text, "Helvetica", font_size) > col_width and len(text) > 8:
            text = text[:-4] + '…'
        c.drawString(col1_x, col_y, text)
        col_y -= line_h
        if col_y < 3:
            break

    col_y = y
    for item in col2_items:
        text = f"{item[0]}: {item[1]}"
        while c.stringWidth(text, "Helvetica", font_size) > col_width and len(text) > 8:
            text = text[:-4] + '…'
        c.drawString(col2_x, col_y, text)
        col_y -= line_h
        if col_y < 3:
            break

    c.save()
    buf.seek(0)

    return Response(
        buf.getvalue(),
        mimetype='application/pdf',
        headers={'Content-Disposition': f'inline; filename=label-{pn}.pdf'}
    )


@app.route('/api/labels/batch', methods=['POST'])
@login_required
def batch_labels_pdf():
    """Generate a multi-label PDF for multiple parts."""
    from reportlab.lib.pagesizes import inch, letter
    from reportlab.pdfgen import canvas as pdf_canvas
    from reportlab.lib.utils import ImageReader
    from io import BytesIO

    data = request.get_json()
    part_ids = data.get('ids', [])
    if not part_ids:
        return jsonify({'error': 'No parts specified'}), 400

    conn = get_db()

    # Label dimensions
    lw, lh = 4 * inch, 1 * inch
    buf = BytesIO()
    c = pdf_canvas.Canvas(buf, pagesize=(lw, lh))

    for i, pid in enumerate(part_ids):
        row = conn.execute("SELECT * FROM parts WHERE id = ?", (pid,)).fetchone()
        if not row:
            continue
        part = dict(row)
        label_fields = _get_label_fields(conn, part)

        if i > 0:
            c.showPage()

        # QR code
        qr_png = _generate_qr_png(part.get('product_number', ''))
        qr_img = ImageReader(BytesIO(qr_png))
        qr_size = 0.82 * inch
        c.drawImage(qr_img, 4, (lh - qr_size) / 2, qr_size, qr_size)

        # Text
        x_start = qr_size + 10
        text_area_w = lw - x_start - 6
        y = lh - 13

        c.setFont("Helvetica-Bold", 9)
        pn = part.get('product_number', '')
        c.drawString(x_start, y, pn)
        y -= 10

        sku = part.get('sku', '')
        if sku:
            c.setFont("Helvetica-Bold", 9)
            c.drawString(x_start, y, sku)
            y -= 10

        # Remaining fields in two columns
        remaining = [(lbl, val) for lbl, val in label_fields if lbl not in ('Product #', 'SKU')]
        col_width = text_area_w / 2 - 2
        font_size = 7
        line_h = 7
        c.setFont("Helvetica", font_size)

        col1_x = x_start
        col2_x = x_start + text_area_w / 2
        mid = (len(remaining) + 1) // 2
        col1_items = remaining[:mid]
        col2_items = remaining[mid:]

        col_y = y
        for item in col1_items:
            text = f"{item[0]}: {item[1]}"
            while c.stringWidth(text, "Helvetica", font_size) > col_width and len(text) > 8:
                text = text[:-4] + '…'
            c.drawString(col1_x, col_y, text)
            col_y -= line_h
            if col_y < 3:
                break

        col_y = y
        for item in col2_items:
            text = f"{item[0]}: {item[1]}"
            while c.stringWidth(text, "Helvetica", font_size) > col_width and len(text) > 8:
                text = text[:-4] + '…'
            c.drawString(col2_x, col_y, text)
            col_y -= line_h
            if col_y < 3:
                break

    c.save()
    conn.close()
    buf.seek(0)

    return Response(
        buf.getvalue(),
        mimetype='application/pdf',
        headers={'Content-Disposition': 'inline; filename=labels-batch.pdf'}
    )


# ══════════════════════════════════════════
#  HANDLE 401 FOR AJAX
# ══════════════════════════════════════════

@login_manager.unauthorized_handler
def unauthorized():
    if request.headers.get('X-Requested-With') == 'XMLHttpRequest' or request.is_json or request.path.startswith('/api/'):
        return jsonify({'error': 'Authentication required'}), 401
    return redirect(url_for('login', next=request.url))


init_db()

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)
