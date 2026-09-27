#!/bin/bash
# deploy_restore_server.sh — Deploy standalone restore server to Orange Pi
# Run from the project directory on Windows (needs SSH to Orange Pi)

set -e

ORANGE_PI="root@192.168.3.234"
REMOTE_DIR="/opt/lan-discovery"
SERVICE_FILE="restore-server.service"

echo "=== Deploying Restore Server ==="

# 1. Copy restore_server.py
echo "[1/3] Copying restore_server.py..."
scp restore_server.py "${ORANGE_PI}:${REMOTE_DIR}/restore_server.py"

# 2. Copy systemd service
echo "[2/3] Installing systemd service..."
scp "${SERVICE_FILE}" "${ORANGE_PI}:/etc/systemd/system/${SERVICE_FILE}"
ssh "${ORANGE_PI}" "systemctl daemon-reload && systemctl enable restore-server && systemctl restart restore-server"

# 3. Verify
echo "[3/3] Checking status..."
ssh "${ORANGE_PI}" "systemctl status restore-server --no-pager || true"

echo ""
echo "=== Done ==="
echo "Restore server: http://192.168.3.234:8081"
echo "Default creds: admin / restore2024"
echo ""
