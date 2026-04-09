#!/bin/bash
# ─────────────────────────────────────────────────────────────
# Warehouse Manager — Ubuntu 24.04 Setup Script
# Run as: sudo bash setup.sh
# ─────────────────────────────────────────────────────────────

set -e

APP_DIR="/opt/warehouse-manager"
APP_USER="parts"

echo "══════════════════════════════════════════════"
echo "  Warehouse Manager — Automated Setup"
echo "══════════════════════════════════════════════"
echo

# ── 1. System packages ──
echo "[1/6] Installing system packages..."
apt update -qq
apt install -y -qq python3 python3-pip python3-venv sqlite3 > /dev/null

# ── 2. Create app user ──
echo "[2/6] Creating application user..."
if ! id -u "$APP_USER" &>/dev/null; then
    useradd --system --create-home --shell /bin/bash "$APP_USER"
fi

# ── 3. Copy app files ──
echo "[3/6] Setting up application directory..."
mkdir -p "$APP_DIR"
cp -r "$(dirname "$0")"/* "$APP_DIR/"
mkdir -p "$APP_DIR/uploads"
chown -R "$APP_USER:$APP_USER" "$APP_DIR"

# ── 4. Python virtual environment & dependencies ──
echo "[4/6] Creating Python virtual environment..."
sudo -u "$APP_USER" python3 -m venv "$APP_DIR/venv"
sudo -u "$APP_USER" "$APP_DIR/venv/bin/pip" install --quiet flask flask-login gunicorn openpyxl

# ── 5. Initialize database ──
echo "[5/6] Initializing database..."
cd "$APP_DIR"
sudo -u "$APP_USER" "$APP_DIR/venv/bin/python" -c "
import sys
sys.path.insert(0, '.')
from app import init_db
init_db()
print('Database initialized.')
"

# ── 6. Create systemd service ──
echo "[6/6] Creating systemd service..."
cat > /etc/systemd/system/warehouse-manager.service <<EOF
[Unit]
Description=Warehouse Manager Web Application
After=network.target

[Service]
Type=exec
User=$APP_USER
Group=$APP_USER
WorkingDirectory=$APP_DIR
ExecStart=$APP_DIR/venv/bin/gunicorn --bind 0.0.0.0:5000 --workers 3 --timeout 120 app:app
Restart=always
RestartSec=5
Environment=PYTHONUNBUFFERED=1

[Install]
WantedBy=multi-user.target
EOF

systemctl daemon-reload
systemctl enable warehouse-manager
systemctl start warehouse-manager

echo
echo "══════════════════════════════════════════════"
echo "  ✓ Setup complete!"
echo ""
echo "  The app is running at:"
echo "    http://$(hostname -I | awk '{print $1}'):5000"
echo ""
echo "  Manage the service with:"
echo "    sudo systemctl status warehouse-manager"
echo "    sudo systemctl restart warehouse-manager"
echo "    sudo journalctl -u warehouse-manager -f"
echo ""
echo "  Database: $APP_DIR/warehouse.db"
echo "  Uploads:  $APP_DIR/uploads/"
echo "══════════════════════════════════════════════"
