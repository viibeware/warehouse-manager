# Changelog

## v1.5.3
- <strong>Centralized changelog</strong> — CHANGELOG.md is now the single source of truth, shipped with the Docker image. The About tab fetches it at runtime from <code>/api/changelog</code>, so updating one file keeps the About pane in sync with every build. README's "Changelog" section links here instead of duplicating entries.
- <strong>Per-part short description</strong> — Each part on the new + edit work-order forms has an optional full-width "Short description" input (color, condition, fitment note). The value persists in <code>parts_json.details</code>, surfaces on the card under the part line, and is included in the full-status update email and PDF export.

## v1.5.2
- <strong>Security hardening</strong> — Password minimum bumped to 8 characters. Constant-time login (dummy hash on missing/locked users) prevents user-enumeration via timing. Global security headers: <code>X-Content-Type-Options</code>, <code>X-Frame-Options: DENY</code>, <code>Referrer-Policy</code>, locked-down <code>Permissions-Policy</code>, HSTS when secure cookies are enabled. Secure session + remember cookies toggleable via <code>WM_SECURE_COOKIES=1</code> env var. Werkzeug debug mode disabled by default (opt-in via <code>FLASK_DEBUG=1</code>). <code>/uploads/&lt;filename&gt;</code> validates against a strict UUID-hex filename pattern. Email header injection hardened: CR/LF stripped from <code>to_email</code> and <code>subject</code>; recipient re-validated against the email regex before handing to Python's email module.
- <strong>Account lockout + admin unlock widget</strong> — Migration v28 adds <code>failed_login_count</code>, <code>locked_until</code>, <code>last_failed_login</code> to <code>users</code>. Five consecutive failed logins on an existing active account locks it for 15 minutes; unknown usernames are never locked out (prevents griefing). Expired locks auto-clear. Success resets counters. New admin <strong>Locked Accounts</strong> dashboard widget lists currently-locked users with their failed-count, expiry (UTC), and a one-click <strong>Unlock</strong> button. Endpoints: <code>GET /api/users/locked</code>, <code>POST /api/users/&lt;id&gt;/unlock</code>.
- <strong>SVG branding uploads (admin-only, sanitized)</strong> — PNG uploads are validated + re-encoded via Pillow (strips metadata/chunks). SVG uploads parse as XML and strip <code>&lt;script&gt;</code>, <code>&lt;foreignObject&gt;</code>, <code>&lt;iframe&gt;</code>, <code>&lt;use&gt;</code>, animation elements, every <code>on*</code> attribute, and <code>href</code>/<code>xlink:href</code> values that use <code>javascript:</code>, <code>data:</code>, <code>vbscript:</code>, or <code>file:</code> schemes. <code>/branding/logo</code> responses carry a restrictive <code>Content-Security-Policy</code> so even a smuggled script payload is neutered at the browser.
- <strong>Email notifications</strong> — Renamed the "Emails to the sales person" callout on the New Work Order form to "Email notifications".

## v1.5.1
- <strong>Always land on the dashboard after sign-in</strong> — Login redirect ignores any <code>?next=…</code> param and sends users to <code>/dashboard</code> for both AJAX and form-post flows; the already-authenticated guard matches.
- <strong>Softer login gradient</strong> — Hero sine-wave switched from triadic (120° apart) to an analogous pastel palette — three hues within ±25–40° of a random base hue, saturation 42–54%, lightness 76–82%. Less visually divergent, dreamier look. Reduced-motion static fallback matches.

## v1.5.0
- <strong>Two-panel login screen</strong> — New split layout with a left hero panel that always renders a full-canvas animated sine-wave gradient. Each reload picks a fresh triadic palette (random rotation, random wave frequencies/phases); reduced-motion falls back to a static gradient. The hero shows the Warehouse Manager SVG + name at 100 px. The right form panel displays just the version number (Inter). The login chrome respects the last signed-in user's saved light/dark theme by reading <code>wm-theme</code> from localStorage before first paint.
- <strong>Custom branding</strong> — New admin-only Branding tab in Settings. Upload a PNG or SVG logo to appear at the bottom of the login hero; logo width is adjustable via a range slider + numeric input with a WYSIWYG preview rendered at the actual render width; changes persist via a Save button. <code>GET /branding/logo</code> serves the asset publicly so the login page can fetch it pre-auth.
- <strong>Sales people from users</strong> — Migration v25 adds <code>users.is_sales_person</code>. The work-order Sales Person dropdown is now derived from users flagged as sales people (their username = email); the Sales People tab in Work Order Lists is gone. Usernames are validated as emails and used as the recipient for every automatic work-order email.
- <strong>Threaded notes with replies + activity</strong> — Migration v26 adds <code>parent_id</code> + <code>author_user_id</code> to <code>work_order_notes</code>. Adding a note emails the salesperson; replies email every prior participant + the salesperson. Each note shows author, timestamp, body, and a Reply button; flag notes and unflag events appear in the same thread (flags in red, unflag neutral). The thread caps at ~5 notes of height with internal scrolling; newest thread at the top. The Add Note / Reply modal carries an inline disclaimer warning an email will be sent. Part flag descriptions are required and land in the thread so teammates can reply to them.
- <strong>Global + per-user email toggles</strong> — Migration v27 adds <code>smtp_notifications_enabled</code> setting and <code>users.email_notifications_enabled</code>. Admin toggle kills all alerts; user toggle opts individuals out. Banner on the Work Orders page when global alerts are off.
- <strong>Photo emails to salesperson</strong> — Uploading a photo to a WO part now emails the salesperson with the image attached (JPEG resized to 2048 px, quality 80). Comment text is included in the body.
- <strong>Per-part camera icon</strong> — Add Photo icon sits next to the flag icon on each part line; the bottom "+ Add Photo" button is gone in favor of the per-row icon. Thumbnails with edit-comment and delete controls still appear under each part.
- <strong>Collapsible cards + cleaner layout</strong> — Every WO card has a chevron accordion. Delivered (pending + archived) default to collapsed, requested/flagged default expanded. Status and priority badges cluster to the right of the header next to the chevron; customer name anchors the left. Action row sits at the bottom of the card with a divider, left-aligned, Mark Delivered pushed far-right. Tooltips on every action button.
- <strong>Sort parts by Audit, Posted to Web, and any sortable column header</strong> — Parts table column headers become click-to-sort with inline arrows; new sort options for audit flag and the per-category <code>posted_to_web</code> toggle (via SQLite <code>json_extract</code>). Audit surfaces on the card view for every category (not just heads) with an orange ⚠ AUDIT badge and card outline.
- <strong>Detail modal retired</strong> — The work-order detail modal is gone; the list view renders every action button, the full parts grid, the notes thread, and the photo UI inline.
- <strong>Derived flag status + sidebar badge</strong> — Work-order status is derived from per-part flags (no more WO-level Flag button). The sidebar Work Orders nav shows a red badge with the count of active flagged WOs.
- <strong>? help tooltip on the Work Orders heading</strong> — Explains flagged → requested transitions, 23:00 auto-archive, and the notes/reply email flow. 600 px wide on desktop, capped to viewport.
- <strong>Misc</strong> — "Username (email address)" label on the user-edit form; email validation on save.

## v1.4.1
- <strong>Collapsible work-order cards</strong> — Every card in the list view now has a chevron toggle that expands/collapses the request details and parts grid. Delivered work orders (both pending and archived) default to collapsed so the active list stays compact; requested/flagged cards default to expanded.
- <strong>Header reshuffle</strong> — Status and priority badges moved to a right-aligned cluster sitting to the left of the collapse chevron; WO number and customer anchor the left side.
- <strong>View button + action row</strong> — Row sits at the bottom of each card with a divider; Mark Delivered pushed to the far right.
- <strong>Per-part photo icon in the row</strong> — Camera icon next to the flag icon on each part line.
- <strong>Button tooltips</strong> — Descriptive <code>title</code> attributes on every work-order action button.
- <strong>Edit user modal</strong> — Username field reads "Username (email address)".

## v1.4.0
- <strong>Flag status is now per-part</strong> — Removed the work-order–level Flag / Unflag / Update Flag Note buttons. A work order is automatically marked "flagged" as soon as any part is flagged, and returns to "requested" the moment the last part flag is cleared. Delivered work orders are unaffected.
- <strong>Edit part flag notes</strong> — Clicking a flagged part's flag icon opens an editor modal prefilled with the existing note, with Save and Unflag buttons.
- <strong>Sidebar flagged badge</strong> — Work Orders nav item shows a red pill with the count of flagged work orders, refreshed whenever a flag is added/removed.
- <strong>API changes</strong> — <code>POST /api/work-orders/&lt;id&gt;/status</code> no longer accepts <code>flagged</code> (derived); <code>POST /api/work-orders/&lt;id&gt;/parts/&lt;idx&gt;/flag</code> handles note-only updates for an already-flagged part.

## v1.3.1
- <strong>Auto-email salesperson on photo upload</strong> — Uploading a photo to a work-order part sends the salesperson an update email with the image(s) attached. Subject is <code>[Photo] Work Order WO-XXXXX</code>; body includes customer, vehicle, part description, uploader, and the optional comment.

## v1.3.0
- <strong>Per-part photos on work orders</strong> — Editors can attach photos directly to individual parts within a work order, each with an optional comment. Uploads are resized to 2048 px / JPEG 80 to keep disk usage small. Thumbnails show under each part (click to open the lightbox), with inline edit-comment + delete buttons. Migration v24 adds <code>work_order_part_photos</code>; parts gain a stable UUID <code>key</code> so photos stay anchored across edits. Orphaned photos are cleaned up automatically on part removal or WO delete.

## v1.2.11
- <strong>"Mark Delivered" button restyled</strong> — Yellow pale fill / dark-yellow text at rest, transitions to pale green + green text on hover (previews the delivered state).
- <strong>"Deliver" → "Mark Delivered"</strong> on the list card (was already named that way in the detail modal).

## v1.2.8
- <strong>Sub-modals return to Settings</strong> — Closing any settings-reached modal returns to the main Settings modal on the appropriate tab.
- <strong>Role permissions matrix</strong> — The User form modal shows a 12-row permission grid for all four roles.
- <strong>Re-Archive + three-tier delete gating</strong> — Editors can't delete a previously-archived reopened WO — they see a Re-Archive button instead. Admins and supervisors retain delete on those; delivered/currently-archived remain admin-only.
- <strong>Delayed archival + Archive Now</strong> — Migration v22: delivered WOs stay Active until 23:00 local time of the delivery day, then an on-demand sweep archives them.
- <strong>Duplicate work order</strong> — Copies fields + parts (pulled / flagged reset) into a fresh WO-#####.
- <strong>Audit Trail button on list cards</strong> — Admins and supervisors see an Audit Trail button directly on each card.
- <strong>Invoice number click-to-copy</strong> — Invoice/quote # next to customer name, clicking copies the bare number.
- <strong>"Needs Audited" from anywhere</strong> — Banner, list cell, and "Mark for Audit" button all wired up.
- <strong>Configurable priority colors</strong> — Priorities in Settings carry an optional color; card tints use it via <code>color-mix</code>.
- <strong>Six themes</strong> — Light, Dark, Neobrutal Light, Neobrutal Dark, Solarpunk, Cyberpunk.
- <strong>AGPLv3 license</strong> — Switched from MIT.
- <strong>Dashboard landing page + URL routing</strong> — <code>/dashboard</code> with WO summary + active list + recent part updates.
</content>
</invoke>