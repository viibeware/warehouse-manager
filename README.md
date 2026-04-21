# Warehouse Manager

A self-hosted web-based inventory management system built for automotive parts — engines, cylinder heads, transmissions, and any custom category you define. Built with Flask + SQLite, deployed via Docker.

![Dark Mode](https://img.shields.io/badge/theme-dark%20%2F%20light-blue) ![Docker](https://img.shields.io/badge/docker-ready-blue) ![License](https://img.shields.io/badge/license-AGPLv3-green)

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

The app ships with three categories — **Engine**, **Cylinder Head**, and **Transmission** — each with pre-configured field sets. All categories are fully editable and deletable.

- **Rename, recolor, or delete** any category (requires removing parts from it first)
- **Add custom categories** with any name and color — new categories come pre-populated with default fields (SKU, Location, Fitment Vehicle, Sold, Sold Date, Notes) that you can rearrange or remove
- **Define fields** per category: Text, Textarea, Toggle (yes/no), or Radio (multiple choice with custom options)
- **Control visibility**: Check "Card" to show on card view, "Table" to show as a table column
- **Drag to reorder** any field — the order in the category editor is the order in forms, detail views, and labels. This includes the default fields — put SKU at the bottom if you want, or move Notes to the middle
- **Images** are always available on every category and don't need to be added as a field

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

## Changelog

### v1.5.1
- **Always land on the dashboard after sign-in.** Login redirect ignores any `?next=…` param and sends users to `/dashboard` for both AJAX and form-post flows; the already-authenticated guard matches.
- **Softer login gradient.** Hero sine-wave switched from triadic (120° apart) to an analogous pastel palette — three hues within ±25–40° of a random base hue, saturation 42–54%, lightness 76–82%. Less visually divergent, dreamier look. Reduced-motion static fallback matches.

### v1.5.0
- **Two-panel login screen** — New split layout with a left hero panel that always renders a full-canvas animated sine-wave gradient. Each reload picks a fresh triadic palette (3 complementary hues 120° apart, random rotation, random wave frequencies/phases); reduced-motion falls back to a static gradient. The hero shows the Warehouse Manager SVG + name at 100 px; no Viibeware branding. The right form panel displays just the version number (Inter, not mono). The login chrome respects the last signed-in user's saved light/dark theme by reading `wm-theme` from localStorage before first paint.
- **Custom branding** — New admin-only Branding tab in Settings. Upload a PNG or SVG logo to appear at the bottom of the login hero; logo width is adjustable via a range slider + numeric input with a WYSIWYG preview rendered at the actual render width; changes persist via a Save button. `GET /branding/logo` serves the asset publicly so the login page can fetch it pre-auth.
- **Sales people from users** — Migration v25 adds `users.is_sales_person`. The work-order Sales Person dropdown is now derived from users flagged as sales people (their username = email); the Sales People tab in Work Order Lists is gone. Usernames are validated as emails and used as the recipient for every automatic work-order email.
- **Threaded notes with replies + activity** — Migration v26 adds `parent_id` + `author_user_id` to `work_order_notes`. Adding a note emails the salesperson; replies email every prior participant + the salesperson. Each note shows author, timestamp, body, and a Reply button; flag notes and unflag events appear in the same thread (flags in red, unflag neutral). The thread caps at ~5 notes of height with internal scrolling; newest thread at the top. The Add Note / Reply modal carries an inline disclaimer warning an email will be sent. Part flag descriptions are required and land in the thread so teammates can reply to them.
- **Photo emails to salesperson** — Uploading a photo to a WO part now emails the salesperson with the image attached (JPEG resized to 2048 px, quality 80). Comment text is included in the body.
- **Per-part camera icon** — Add Photo icon sits next to the flag icon on each part line; the bottom "+ Add Photo" button is gone in favor of the per-row icon. Thumbnails with edit-comment and delete controls still appear under each part.
- **Collapsible cards + cleaner layout** — Every WO card has a chevron accordion. Delivered (pending + archived) default to collapsed, requested/flagged default expanded. Status and priority badges cluster to the right of the header next to the chevron; customer name anchors the left. Action row sits at the bottom of the card with a divider, left-aligned, Mark Delivered pushed far-right. Tooltips on every action button.
- **Sort parts by Audit, Posted to Web, and any sortable column header** — Parts table column headers become click-to-sort with inline arrows; new sort options for audit flag and the per-category `posted_to_web` toggle (via SQLite `json_extract`). Audit surfaces on the card view for every category (not just heads) with an orange ⚠ AUDIT badge and card outline.
- **Detail modal retired** — The work-order detail modal is gone; the list view renders every action button, the full parts grid, the notes thread, and the photo UI inline. Opening a WO only takes a click to expand the accordion.
- **Derived flag status + sidebar badge** — Work-order status is derived from per-part flags (no more WO-level Flag button). The sidebar Work Orders nav shows a red badge with the count of active flagged WOs.
- **? help tooltip on the Work Orders heading** — Explains flagged → requested transitions, 23:00 auto-archive, and the notes/reply email flow. 600 px wide on desktop, capped to viewport.
- **Misc** — "Username (email address)" label on the user-edit form; email validation on save.

### v1.4.1
- **Collapsible work-order cards** — Every card in the list view now has a chevron toggle that expands/collapses the request details and parts grid. Delivered work orders (both pending and archived) default to collapsed so the active list stays compact; requested/flagged cards default to expanded.
- **Header reshuffle** — Card header bar is now `WO-##### · Customer · #invoice  …  STATUS · PRIORITY · ▾`: the status and priority badges moved to a right-aligned cluster sitting to the left of the collapse chevron. WO number and customer anchor the left side; the right side gives the status its own visual lane.
- **View button + button header** — Action row sits at the bottom of each card with a divider, and a new **View** button (editor + viewer) opens the work-order detail modal. "Mark Delivered" is pushed to the far right of the row.
- **Per-part photo icon in the row** — Camera icon sits next to the flag icon on each part line so uploads don't require drilling into the detail modal.
- **Button tooltips** — Descriptive `title` attributes on every work-order action button (View, Edit, Add Note, Archive Now, Reopen, Email Update, Download PDF, Duplicate, Audit Trail, Mark Delivered, Re-Archive, Delete).
- **Edit user modal** — Username field now reads "Username (email address)".

### v1.4.0
- **Flag status is now per-part** — Removed the work-order–level Flag / Unflag / Update Flag Note buttons. A work order is automatically marked "flagged" as soon as any part is flagged, and returns to "requested" the moment the last part flag is cleared. Delivered work orders are unaffected.
- **Edit part flag notes** — Clicking a flagged part's flag icon now opens an editor modal prefilled with the existing note, with Save and Unflag buttons. Creating a flag works as before.
- **Sidebar flagged badge** — Work Orders nav item now shows a red pill with the count of flagged work orders, refreshed whenever a flag is added/removed or the counts are re-fetched.
- **API changes** — `POST /api/work-orders/<id>/status` no longer accepts `flagged` (derived); `POST /api/work-orders/<id>/parts/<idx>/flag` now also handles note-only updates for an already-flagged part.

### v1.3.1
- **Auto-email salesperson on photo upload** — Uploading a photo to a work-order part now sends the salesperson an update email with the image(s) attached. Subject is `[Photo] Work Order WO-XXXXX`; body includes customer, vehicle, part description, uploader, and the optional comment. Send success/failure is logged to the audit trail and surfaced in the toast. `_send_email` now takes an optional `attachments` list of `{filename, content, mime_type}`.

### v1.3.0
- **Per-part photos on work orders** — Editors can attach photos directly to individual parts within a work order, each with an optional comment. Uploads are resized to a 2048 px long edge and re-encoded as JPEG quality 80 to keep disk usage small. Thumbnails show under each part in the detail modal (click to open the lightbox), with inline edit-comment + delete buttons; card summaries surface up to four mini-thumbs so list readers know photos exist. Photo actions are mirrored into the Notes & Activity feed and the audit trail. Migration v24 adds `work_order_part_photos`; parts gain a stable UUID `key` so photos stay anchored across edits. Orphaned photos are cleaned up automatically when a part is removed during an edit or when the whole work order is deleted.

### v1.2.11
- **"Mark Delivered" button restyled** — yellow pale fill / dark-yellow text at rest, transitions to pale green + green text on hover (previews the delivered state). Applies to both the inline card button and the detail-modal footer button.
- **"Deliver" → "Mark Delivered"** on the list card (was already named that way in the detail modal).

### v1.2.8
- **Sub-modals return to Settings** — Closing any settings-reached modal (Work Order Lists, SMTP, Turnstile, User Management, Category Manager, Import, Change Password) via save, cancel, or X returns you to the main Settings modal on the appropriate tab instead of dumping you back to the dashboard.
- **Role permissions matrix** — The User form modal now shows a 12-row permission grid for all four roles (Viewer / Editor / Supervisor / Admin) so admins can see what each role can and can't do at a glance.
- **Re-Archive button + three-tier delete gating** — Migration v23 tracks `was_archived`. Editors can no longer delete a work order that's been archived and reopened — they see a **Re-Archive** button instead (marks delivered + archives immediately, skipping the 23:00 grace). Admins and supervisors retain delete on previously-archived reopened WOs. Delivered / currently-archived orders remain admin-only to delete.
- **Delayed archival + Archive Now** — Migration v22: delivered WOs stay in the Active list until 23:00 local time of the delivery day, then an on-demand sweep (triggered by any list/count query) sets `archived_at`. New `POST /api/work-orders/<id>/archive-now` + button lets an editor archive immediately. New `POST /api/work-orders/<id>/re-archive` skips the grace period for the re-archive flow.
- **Delivered-pending visual state** — Work orders in that post-delivery / pre-archive window get a persistent pale green card background (`color-mix(--bg-card 75% / #86efac 25%)`), with the Mark-Delivered flash animation settling onto that exact color and Archive Now / Re-Archive using a fade-out animation on top of it.
- **Duplicate work order** — `POST /api/work-orders/<id>/duplicate` copies fields + parts (pulled / flagged reset) into a fresh `WO-#####`, logs an audit entry, and posts a "Duplicated from WO-XXXXX" note. Button appears on every card and in the detail modal footer (active + archive).
- **Audit Trail button on list cards** — Admins and supervisors see an Audit Trail button directly on each work order card in both the active and archive views.
- **Invoice number click-to-copy** — Invoice / quote # shown next to customer name on the card and in the detail modal. Clicking copies the bare number (stripping any `#` prefix) with a pill hover highlight so it reads as interactive.
- **"Needs Audited" from anywhere** — Part detail modal's orange banner is now clickable for editors (edit / clear the flag), a "Mark for Audit" button appears on parts that aren't flagged, and the Audit column in the parts table is fully actionable. New `POST /api/parts/<id>/audit` endpoint.
- **Configurable priority colors** — Priorities in Settings → Admin → Work Order Lists now carry an optional color (color-picker input + clear button). Card tints use that color via `color-mix(--bg-card 82% / configured 18%)`. Stored as `{name, color}` with legacy-string normalization. Next Day Air default bumped from pale yellow to `#fff3e5` with a forward-migrate for records still on the old default.
- **Six themes** — Light, Dark, Neobrutal Light, Neobrutal Dark, Solarpunk, Cyberpunk — picker in Settings → General; sidebar sun/moon button toggles Light ↔ Dark.
- **AGPLv3 license** — Switched from MIT; About pane links to the canonical GNU text.
- **Dashboard landing page + URL routing** — `/dashboard` with WO summary + active list + recent part updates. Flask serves `/dashboard`, `/workorders`, `/workorders/archive`, `/parts`, `/parts/<slug>`; frontend uses `pushState` + `popstate` so every view has its own URL.
- **Next Day Air card tint** — Priority-colored card background with paler (18%) color-mix, skipped on the archive list.
- **Settings modal** — 900 px wide, fixed 640 px height so tabs don't jump, mixed-case labels, About tab is admin-only.
- **Pulled flash + audit logging** — Checking a part's pulled box pulses a pale green 1 s flash on the work-order block and adds an entry to the Notes & Activity feed. Pulled timestamp captured and displayed under the part description.
- **Send / Email Update** — Renamed "Send Update" → **Email Update**; added to the card action row.
- **WO detail modal** — Widened to 768 px with two-row footer (Edit/Add Note/Flag/Download PDF/Email Update/Duplicate on row 1; Mark Delivered, Audit Trail, …, Delete on row 2) and sticky footer so action buttons stay visible while body scrolls.
- **90-day login sessions** — `PERMANENT_SESSION_LIFETIME` + `REMEMBER_COOKIE_DURATION` = 90 days.
- **Cloudflare Turnstile** — Optional login challenge, admin-configurable site key + secret.
- **Supervisor role** — Editor permissions + audit-trail view.
- **Promoted to 1.0 in this line** — feature-complete working release.

### v1.1.1
- **Activate audit from view modal** — The orange "Needs Audited" banner in the part detail modal is now clickable for editors: it opens a Part Audit modal prefilled with the current note, where you can edit the details or clear the audit flag entirely. A **Mark for Audit** button appears in place of the banner when the part isn't currently flagged.
- **Trigger audit from the list view** — The Audit column in the parts table is now actionable: rows with `needs_audit = true` show a clickable orange **⚠ AUDIT** badge (opens the modal for editing/clearing); editors see a subtle dashed **+ Audit** button on rows that aren't flagged, so they can mark a part for audit directly from the table without opening the part.
- **Backend** — New `POST /api/parts/<id>/audit` endpoint (editor required) accepts `{needs_audit, audit_note}`; clearing the flag also clears the stored note.

### v1.1.0
- **Needs Audited flag on parts** — New universal toggle on every part. When enabled, a textarea appears to capture audit details (reason / what to look for). Migration v21 adds `needs_audit` and `audit_note` columns on `parts`.
- **Audit column in the parts table** — Rows with `needs_audit = true` show an orange ⚠ AUDIT marker in the new rightmost column; hovering the cell shows the audit note as a tooltip. The detail modal also surfaces a prominent orange Needs-Audited banner with the notes.
- **Download PDF from the WO list** — The inline actions row on each work order card now has a Download PDF button alongside Send Update / Edit / etc.

### v1.0.0
- **Version → 1.0** — Promoted from `0.6.x` to `1.0.0` to mark feature completeness of the work order system, dashboard, audit trail, roles, Turnstile, and SMTP notifications.
- **License → AGPLv3** — Switched from MIT to the GNU Affero General Public License v3.0. `LICENSE` replaced, README badge and bottom section updated, About pane now links to the canonical `gnu.org/licenses/agpl-3.0.html` page.

### v0.6.6
- **About pane redesigned** — Mirrors the tspro About layout: a hero card with the app logo, name, version, tagline, Built-by-VIIBEWARE credit, and MIT license on the left; a "Built With" tech-stack grid on the right (Python / Flask / Jinja / Gunicorn / SQLite / JavaScript / Docker) with masked-SVG icons that recolor on hover.

### v0.6.5
- **90-day sessions** — `PERMANENT_SESSION_LIFETIME` and `REMEMBER_COOKIE_DURATION` bumped to 90 days. Users stay signed in for 90 days between logins.
- **Footer icon alignment** — Sidebar footer bottom row now has matching horizontal padding (0.6 rem) so the theme toggle aligns on the same vertical axis as the gear icon above it.

### v0.6.4
- **Pull events logged to activity** — Toggling a part's pulled checkbox now adds a "Part pulled" / "Part unmarked pulled" entry to the work order's Notes & Activity list (blue Note badge).

### v0.6.3
- **Pull flash duration** — Bumped from 500 ms to 1000 ms for a slower, more visible fade.

### v0.6.2
- **Dashboard Work Orders widget merged** — Active work order list now lives inside the Work Orders widget under an "Active" sub-header, below the summary counts. The standalone Active Work Orders widget was removed.
- **Pulled flash tuned** — Animation lengthened to 500 ms and now lights the whole work-order block a pale green instead of just the row, then fades. Uses `box-shadow: inset` so it overlays any card/detail container without replacing its background.

### v0.6.1
- **Pulled flash effect** — Checking a part's pulled box briefly lights up the row in bright green and fades to transparent over 300 ms (in both the list view and the detail modal).

### v0.6.0
- **Dashboard** — New landing view at `/dashboard` with three widgets: a Work Orders summary (Requested / Flagged / Delivered counts), Recent Part Updates (last 6 touched), and an Active Work Orders list. Every row in the widgets is a deep link to the record.
- **URL routing** — Flask now serves the SPA at `/`, `/dashboard`, `/workorders`, `/workorders/archive`, `/parts`, and `/parts/<slug>`. Clicking a nav item updates the URL via `history.pushState`; browser back/forward is wired to `popstate`, and opening any URL directly lands on the right view. After login, users land on the dashboard.

### v0.5.4
- **Send Update on list view** — The work order card now includes a Send Update button alongside Edit/Add Note/Flag/Deliver.
- **Confirmation rewritten** — Both list-card and detail-modal Send Update buttons now prompt: "Do you want to send an email update to the sales person?"
- **Theme button moved** — Light/dark toggle now sits at the bottom-right of the sidebar footer, across from the Sign Out link.

### v0.5.3
- **Theme toggle moved to sidebar** — Light/dark mode is now a one-click icon button in the sidebar footer (sun when light / moon when dark), removed from the Settings → General tab.
- **Cloudflare Turnstile on login** — Admins can configure a Turnstile site key/secret key from the Settings → Admin tab. When enabled, the login page renders the Turnstile widget and the backend verifies the token via `https://challenges.cloudflare.com/turnstile/v0/siteverify` before checking credentials. Public `/api/auth/turnstile-config` endpoint exposes just the site key so the login page can load the widget.

### v0.5.2
- **Supervisor role** — New user role with the same permissions as Editor, plus the ability to view work order audit trails. Migration v20 extends the users CHECK constraint to accept `supervisor`; the User Management form exposes it and role badges now include a distinct color for supervisors. The Audit Trail button is visible to admins and supervisors; Delete remains admin-only.

### v0.5.1
- **Request Details background removed** — the field no longer renders as a gray block; just flows as plain text.
- **Part list column spacing** — widened the first two columns so "Pulled" and "Qty" headers no longer run together.
- **Notes & Activity ordering** — latest note now appears at the top; older entries below.
- **Sticky detail footer** — On the work order detail modal, the action buttons are now pinned at the bottom and always visible; the body content above them scrolls independently.

### v0.5.0
- **"Notes" → "Request Details"** — The original work-order notes field (captured at create/edit time) is renamed everywhere: form, card, detail modal, PDF, email.
- **Running notes** — New "Add Note" action on the list card and on the work order detail modal. Notes can be added without entering edit mode; each note captures the author and timestamp.
- **Notes & Activity log** — The detail modal's history section now shows all entries (flag notes + general notes) in chronological order, each tagged with a Flag/Note badge. Flag entries still drive email notifications; general notes never email.

### v0.4.6
- **Send Update button** — On the work order detail modal, a new Send Update button emails the full current-state work order details to the sales person on demand (independent of the automatic flag/deliver emails). The email includes status, customer/vehicle/VIN, notes, every part with its pulled/flagged state, and the flag notes history. Audit-logged.

### v0.4.5
- **Notes in list view** — Notes now appear on each work order card in the active and archive lists as a light gray block; clamped to 3 lines so cards stay compact.
- **Notes moved above parts in the detail modal** — Notes block is now rendered between the field grid and the parts table (above the parts) and styled as the same gray block so it stands out from surrounding fields.

### v0.4.4
- **VIN on work order cards** — VIN is now shown in the active and archive list cards alongside vehicle, location, and salesperson.

### v0.4.3
- **WO number format** — Work order numbers now include a hyphen: `WO-00001`, `WO-00002`, …. Migration v18 rewrites existing numbers; future assignments use the new format. The lookup that determines the next number tolerates both old and new formats.

### v0.4.2
- **Part rows align cleanly** — A "Pulled" column header now labels the checkbox column; rows use consistent padding so the checkmarks stay in the same column whether a part is flagged or not, and there's always a 22 px slot for the flag button (even for viewers).
- **Pulled timestamp** — Checking a part records the date/time it was pulled (UTC) and displays it under the part description. Unchecking clears the timestamp. The audit trail captures the exact pull time.
- **No more strikethrough** — Pulled items no longer cross out the part description.
- **Part flag notes in history** — Per-part flag (and unflag) events now appear in the Flag Notes History section of the work order detail modal alongside work-order-level notes.

### v0.4.1
- **Unflag** — Remove the flag from a work order and return it to Requested status via an Unflag button in both the detail modal and the list card. Clears the stale flag note so a future re-flag starts clean. Mark Delivered from a flagged state also still works.

### v0.4.0
- **Work order search** — Live-search the active and archive views by WO #, customer, vehicle, VIN, notes, or parts description
- **Work order sort** — Sort by Requested Date (default, newest first), Customer, Priority, WO #, or Status, with a direction toggle
- **Inline Edit button** — Each work order card now has an Edit button in the active list so you can edit without opening the detail modal first
- **Parts on the list view** — Parts with quantities appear on each card; click the checkbox to mark a part as pulled (strikethrough)
- **Per-part flagging** — Flag an individual part with its own reason note; the salesperson gets a dedicated email. Flagged parts highlight red with the note visible inline

### v0.3.0
- **Edit work orders** — Editors/admins can now edit any field on an existing work order via an Edit button in the detail modal. The form pre-fills with current values (including parts list), and the detail modal re-opens with the updated record after save.
- **Audit trail** — Every create/edit/status-change/note/delete is logged with timestamp + actor + description. Admins see an Audit Trail button in the detail modal that opens a popup listing the full history. Field-level edits show before → after for each changed field.

### v0.2.2
- **Save returns to Settings** — Clicking Save Changes on Work Order Lists or SMTP Settings now closes that sub-modal and re-opens the main Settings modal on the Admin tab (instead of leaving the sub-modal open).

### v0.2.1
- **Repeatable parts list** — Each work order now supports a list of requested parts with quantity and description. Parts appear in the detail view, email notifications, and PDF.
- **Work Order Lists: tabs** — Locations, Sales People, and Priorities are now separate tabs inside the Work Order Lists modal (cleaner than the old stacked layout).
- **Save keeps modals open** — Clicking Save on SMTP or Work Order Lists no longer closes the modal; use the X to close. Avoids re-opening after a minor edit.
- **SMTP modal overflow fix** — Form inputs now use `width:100%` + `min-width:0` globally; SMTP modal widened slightly and the test-email row uses a grid so the Send button no longer crowds the input.

### v0.2.0
- **Work orders** — New end-to-end workflow for requesting parts. Each work order gets a unique `WO#####` number and initial request date. Fields: warehouse location, customer name, quote/invoice #, sales person, vehicle, VIN, priority, notes
- **Status workflow** — Requested → Flagged (with a required reason note) → Delivered/Complete. Reopen from archive if needed
- **SMTP email notifications** — Admins configure SMTP host/port/credentials. App emails the sales person automatically when a work order is flagged, when a new note is added to a flagged order, or when it's marked delivered
- **Admin settings** — Manage warehouse locations, sales people (name + email), and priorities from the Admin tab of the Settings modal
- **Printable PDFs** — Download a letter-size PDF of any work order (fields + flag-note history)
- **Archive** — Completed work orders are archived in a dedicated sidebar view for future reference

### v0.1.40
- **Modals only close via the X button** — Clicking the backdrop or pressing Escape no longer dismisses any modal app-wide. Fixes the edit modal closing when text-selection drags end on the backdrop.

### v0.1.38
- **Table column order** — SKU column now appears first, followed by WM # and the rest of the category fields

### v0.1.37
- **Flag toggle re-sorts when sorting by Flagged** — Clicking a flag in the list while sorted by Flagged now immediately re-orders the row into the correct group instead of waiting for a page refresh. Scroll position is preserved.

### v0.1.36
- **Edit preserves scroll position** — Saving a part from the edit modal no longer jumps the list back to the top; the page stays where you were so you don't have to scroll to find the part again

### v0.1.35
- **Settings moved to sidebar footer** — Replaced the full-width Settings nav item with a compact gear icon beside the user profile
- **Bulk delete progress** — Deleting many rows now shows a blocking spinner with live "Deleting X of Y…" progress; requests run 8-at-a-time for faster completion

### v0.1.34
- **Fixed import dropping non-shared fields** — Imports were silently ignoring every mapped field except SKU, Location, Fitment, Sold, Sold Date, and Notes. Server now strips the `custom_` UI prefix before validating the mapping, so Engine/Head/Transmission-specific fields (including `[HC]` headChart values) actually land in the database

### v0.1.33
- **headChart import parser** — Import flow auto-detects the `headChart` HTML block in Welsh product exports and offers a toggle to extract Engine #, Head #, Block Part #, Litre, Vehicle, Date Stamp, and Mileage as virtual columns (`[HC] …`) in the column-mapping step
- **Clean Description** — A `[HC] Clean Description` virtual column strips the headChart div, makeoffer block, and `<img>` tags so it maps cleanly to Notes
- **Smarter auto-match** — Engine category imports pre-select the HC virtual columns for the corresponding DB fields

### v0.1.32
- **WM numbers reformatted** — 5-digit format: WM00001 through WM99999, then WM100000+ on overflow. All existing parts renumbered sequentially
- **Card view flags** — Flag icon in the top-right corner of each card, click to toggle
- **Detail view flags** — Flag toggle button in the product detail modal next to the WM number
- **Flag sync** — Toggling a flag in any view (table, card, detail modal) instantly updates all other views without a page reload

### v0.1.31
- **Flagging** — Click the flag icon in the table to mark/unmark parts instantly (auto-saves). Sort by flagged to see all flagged items first
- **Posted to Web** — New toggle field added to all categories, visible in the table view
- **Sort by Sold** — Sort the table by sold status to group sold/unsold parts
- **Sort by Flagged** — Sort by flag status to surface flagged items
- **Head category cleanup** — Removed Old SKU and Head Number from the default table columns for cleaner display
- **Icon picker** — Choose from 24 icons when creating or editing categories (engine, wrench, gear, truck, battery, etc.)
- **Flagged in export** — CSV export includes a Flagged column

### v0.1.30
- **WM numbers reformatted** — Removed dash: `WM-1000000` → `WM1000000`
- **Sort by WM#** — New sort option in the toolbar dropdown
- **QR codes updated** — Reflect the new dashless product number format

### v0.1.29
- **Default fields on new categories** — Creating a category pre-populates SKU, Location, Fitment Vehicle, Sold, Sold Date, Notes as editable/reorderable fields
- **Category editor shows all fields** — Including shared fields, fully draggable

### v0.1.28
- **Custom categories** — Admin-defined categories with drag-to-reorder custom fields
- **Product numbers** — Auto-assigned WM numbers starting at WM1000000
- **QR codes** — Per-part QR code displayed in detail view
- **Label printing** — 4"×1" Zebra-compatible PDF labels with QR code and two-column field layout
- **Batch labels** — Select multiple parts and print all labels at once
- **Docker deployment** — Full Dockerfile, docker-compose.yml, and .env configuration
- **Categories fully editable** — Engines, Heads, and Transmissions are no longer hardcoded; all categories can be renamed, edited, or deleted
- **Dynamic sidebar** — Category navigation built from the database with custom icons and part counts
- **Unified data model** — All category fields stored in `custom_data` JSON; no more builtin vs custom distinction
- **File-locked migrations** — Prevents race conditions under Gunicorn multi-worker

## License

GNU Affero General Public License v3.0 — see [LICENSE](./LICENSE).

## Credits

Built by [viibeware Corp.](https://viibeware.com)
