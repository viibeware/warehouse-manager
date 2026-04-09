# Warehouse Manager

A self-hosted web-based inventory management system built for automotive parts — engines, cylinder heads, transmissions, and any custom category you define. Built with Flask + SQLite, deployed via Docker.

![Dark Mode](https://img.shields.io/badge/theme-dark%20%2F%20light-blue) ![Docker](https://img.shields.io/badge/docker-ready-blue) ![License](https://img.shields.io/badge/license-MIT-green)

## Features

- **Dynamic categories** — Engines, Cylinder Heads, and Transmissions included out of the box. Create unlimited custom categories with your own field sets, field types, colors, and ordering
- **Drag-to-reorder fields** — Define fields per category (text, textarea, toggle, radio) and drag them into the order you want
- **Multi-image gallery** — Upload multiple photos per part with thumbnail strip and full-screen lightbox viewer
- **Product numbers** — Every part gets a unique `WM-XXXXXXX` number assigned automatically, starting at WM-1000000
- **QR codes** — Auto-generated QR code per part, displayed in the detail view and embedded on printed labels
- **Label printing** — Generate 4" × 1" PDF labels (Zebra ZP500 compatible) with QR code, product number, SKU, and all category fields in a two-column layout. Print single labels or batch-select from the table
- **Table & card views** — Default table view with natural alphanumeric sorting (HD1, HD2, HD10 — not HD1, HD10, HD2), or a visual card grid with category badges and sold ribbons
- **Import / Export** — Import from Excel (.xlsx) or CSV with a 4-step wizard (upload → map columns → dry run preview → import). Export entire inventory to CSV
- **Role-based access** — Admin, Editor, and Viewer roles with granular permissions
- **Sold tracking** — Mark parts as sold with date; sold items highlighted with red row backgrounds and diagonal ribbon badges
- **Light / dark mode** — Toggle in Settings, persists across sessions
- **Sidebar layout** — Fixed sidebar with dynamic category navigation, part counts, and user profile
- **Live search** — Real-time AJAX search across all fields including custom data

## Screenshots

| Table View | Detail + QR | Label PDF |
|---|---|---|
| Dark sidebar with category counts, sortable table with WM# column | Product number with QR code, fields, actions, image gallery | 4"×1" label with QR, product number, SKU, and two-column field layout |

## Quick Start

### Docker Compose (recommended)

Create a `docker-compose.yml`:

```yaml
services:
  warehouse-manager:
    image: viibeware/warehouse-manager:latest
    container_name: warehouse-manager
    restart: unless-stopped
    ports:
      - "5059:5000"
    volumes:
      - wm-data:/data
    environment:
      - WM_DATA_DIR=/data

volumes:
  wm-data:
```

Start it:

```bash
sudo docker compose up -d
```

Open `http://<your-server-ip>:5059` and sign in:

- **Username:** `admin`
- **Password:** `admin`

**Change this password immediately** in Settings → Change Password.

### Build from Source

```bash
git clone https://github.com/viibeware/warehouse-manager.git
cd warehouse-manager
sudo docker compose up -d --build
```

## Configuration

Create a `.env` file alongside your `docker-compose.yml`:

```env
# Port to expose on the host (default: 5059)
WM_PORT=5059

# Secret key for session encryption (leave blank to auto-generate)
# Generate one with: python3 -c "import secrets; print(secrets.token_hex(32))"
SECRET_KEY=
```

If using a custom port via `.env`, update your compose ports:

```yaml
    ports:
      - "${WM_PORT:-5059}:5000"
```

## User Roles

| Role | Browse & Search | Add / Edit / Delete | Import / Export | Manage Users & Categories |
|------|----------------|--------------------|-----------------|-----------------------------|
| **Admin** | ✓ | ✓ | ✓ | ✓ |
| **Editor** | ✓ | ✓ | ✓ | ✗ |
| **Viewer** | ✓ | ✗ | ✗ | ✗ |

All roles can view parts, search, and print labels. Editors and Admins can add, edit, delete, import, and export. Only Admins can manage users and categories.

## Categories & Custom Fields

The app ships with three categories — **Engine**, **Cylinder Head**, and **Transmission** — each with pre-configured field sets. All categories are fully editable:

- **Rename, recolor, or delete** any category (requires removing parts from the category first)
- **Add custom categories** with any name and color
- **Define fields** per category: Text, Textarea, Toggle (yes/no), or Radio (multiple choice with custom options)
- **Control visibility**: Check "Card" to show on card view, "Table" to show as a table column
- **Drag to reorder** fields — the order in the category editor is the order in forms, detail views, and labels

Shared fields (SKU, Location, Fitment Vehicle, Sold, Sold Date, Notes, Images) are available on all categories automatically.

## Product Numbers & Labels

Every part is assigned a unique product number in the format `WM-XXXXXXX` (starting at WM-1000000). Numbers are assigned:

- Automatically when adding a part through the UI
- Automatically during Excel/CSV import
- Retroactively to all existing parts during the initial migration

### Label Printing

Labels are formatted for **4" × 1" thermal labels** (Zebra ZP500 or compatible):

- **QR code** on the left encoding the product number
- **Product number** and **SKU** in bold at the top right
- **Category fields** in a two-column layout below (excludes Sold, Sold Date, Notes, and Images)

Generate labels from:
- **Detail modal** → "Print Label" button (single label PDF)
- **Table view** → Select parts with checkboxes → "Print Labels" in the bulk action bar (multi-label PDF)

## Data Persistence

All data is stored in the `wm-data` Docker volume at `/data`:

| File | Purpose |
|------|---------|
| `warehouse.db` | SQLite database (parts, users, categories, images metadata) |
| `uploads/` | Uploaded part images |
| `.secret_key` | Auto-generated session encryption key |

### Backup

```bash
sudo docker cp warehouse-manager:/data/warehouse.db ./backup-warehouse.db
sudo docker cp warehouse-manager:/data/uploads ./backup-uploads
```

### Restore

```bash
sudo docker cp ./backup-warehouse.db warehouse-manager:/data/warehouse.db
sudo docker cp ./backup-uploads/. warehouse-manager:/data/uploads/
sudo docker compose restart
```

## Database Migrations

The app uses an automatic versioned migration system. Migrations run on startup and are tracked in a `schema_version` table. A file lock prevents race conditions when running under Gunicorn with multiple workers.

Current migration history:

| Version | Description |
|---------|-------------|
| v1 | Initial schema — users and parts tables |
| v2 | Location index |
| v3 | Sold, sold_date, head_old_number columns |
| v4 | Editor role, viewer rename |
| v5 | Multi-image support (part_images table) |
| v6 | Radio fields for turns/spins/shifts |
| v7 | Normalize engine_turns values |
| v8 | Custom categories system (categories + category_fields tables, custom_data JSON column) |
| v9 | Product numbers (WM-1000000+), retroactive assignment |
| v10 | Register field definitions for original categories, migrate data to custom_data JSON |
| v11 | Deduplicate category_fields (fix for Gunicorn worker race) |

## Tech Stack

- **Backend:** Python 3.12, Flask, Flask-Login, Gunicorn
- **Database:** SQLite (WAL mode) with versioned migrations
- **Frontend:** Vanilla JS, DM Sans + Inter + JetBrains Mono fonts, CSS custom properties for theming
- **PDF Labels:** ReportLab
- **QR Codes:** qrcode + Pillow
- **Import:** openpyxl (Excel) + csv (CSV)
- **Container:** Docker with named volumes for persistence

## Manual Setup (without Docker)

```bash
sudo apt update && sudo apt install python3 python3-pip python3-venv sqlite3
python3 -m venv venv && source venv/bin/activate
pip install flask flask-login gunicorn openpyxl qrcode[pil] reportlab

# Development
python3 app.py

# Production
gunicorn --bind 0.0.0.0:5000 --workers 3 --timeout 120 app:app
```

## Project Structure

```
warehouse-manager/
├── app.py                 # Flask application (routes, migrations, auth, API)
├── Dockerfile             # Container image definition
├── docker-compose.yml     # Docker Compose for development (build: .)
├── requirements.txt       # Python dependencies
├── .env                   # Environment configuration
├── .dockerignore          # Docker build exclusions
├── setup.sh               # Legacy Ubuntu systemd installer
├── static/
│   ├── favicon.png        # Browser tab icon
│   └── logo.svg           # Sidebar logo
└── templates/
    ├── index.html          # Main SPA (sidebar, table, cards, modals, all JS)
    └── login.html          # Login page
```

## License

MIT

## Credits

Built by [viibeware Corp.](https://viibeware.com)
