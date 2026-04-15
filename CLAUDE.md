# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Overview

Warehouse Manager is a self-hosted Flask + SQLite inventory app for automotive parts, packaged as a Docker image. The codebase is intentionally small: one Python file, one main template, one login template.

## Commands

```bash
# Dev run (SQLite DB + uploads created in repo root when WM_DATA_DIR is unset)
python3 app.py

# Production run (same as the container CMD)
gunicorn --bind 0.0.0.0:5000 --workers 3 --timeout 120 app:app

# Build + run locally via compose (image: viibeware/warehouse-manager)
sudo docker compose up -d --build

# Tail logs / restart after code changes
sudo docker compose logs -f
sudo docker compose restart
```

Env vars: `WM_DATA_DIR` (where `warehouse.db`, `uploads/`, `.secret_key` live — `/data` in the container), `SECRET_KEY` (optional; otherwise persisted to `.secret_key`), `WM_PORT` (host port).

There is no test suite, linter, or build step.

## Architecture

**Single-file backend (`app.py`, ~2k lines).** All routes, auth, migrations, image handling, label/QR generation, and import/export live here. Sections are delimited by banner comments (`MIGRATION SYSTEM`, `SEARCH COLS`, etc.). `APP_VERSION` at the top is bumped per release and must match the README changelog.

**Single-file frontend (`templates/index.html`, ~2.3k lines).** The app is an SPA: sidebar + table/card views + modals + all JS inline. Vanilla JS, no build step. `login.html` is separate.

**Data model is category-driven and dynamic.**
- `categories` + `category_fields` define the schema for each part category at runtime (added in migration v8).
- `parts` stores fixed columns (id, category slug, product_number, sold, flagged, image refs) plus a `custom_data` JSON column holding all category-specific fields. Since v10 there is no builtin-vs-custom distinction — Engine/Head/Transmission fields live in `custom_data` just like user-created categories.
- `part_images` (v5) holds multi-image metadata; files live in `UPLOAD_DIR`.
- Product numbers (`WM#####`, v9/v12/v13) are assigned by `assign_product_number()` and are independent of row IDs.

**Migration system.** Schema changes are append-only functions `migrate_vN(conn)` registered in the `MIGRATIONS` list near line 562. `init_db()` takes an fcntl lock on `.migration_lock` before applying anything — this is required because Gunicorn starts multiple workers that all call `init_db()` on boot. To add a schema change: write `migrate_vN`, append `(N, migrate_vN)` to `MIGRATIONS`, done. Never edit a past migration; add a new one. Current head is v14.

**Auth & roles.** Flask-Login with three roles: `admin`, `editor`, `viewer`. Decorators `@admin_required` and `@editor_required` gate routes; the `User` class exposes `is_admin` / `can_edit`. Default admin/admin is seeded in `migrate_v1`.

**Sorting.** The table uses natural alphanumeric sort via `_natural_sort_key` so `HD1, HD2, HD10` orders correctly. Preserve this behavior when touching sort logic.

**Labels & QR.** ReportLab generates 4"×1" PDFs (Zebra ZP500 layout) with a qrcode-generated PNG on the left and a two-column field layout on the right. Sold / Sold Date / Notes / Images are intentionally excluded from labels.

**Import flow.** 4 steps: upload → map columns → dry-run preview → commit. Accepts `.xlsx` (openpyxl) and `.csv`. Temp files go in `uploads/temp/`.

## Conventions

- Bump `APP_VERSION` in `app.py` and add a README changelog entry for user-visible changes.
- Adding a field to an existing category is a data operation (insert into `category_fields`), not a schema migration — unless you're changing the shape of `category_fields` itself.
- The `custom_data` JSON blob is the source of truth for per-category values; don't add new hardcoded columns to `parts` for category-specific data.
