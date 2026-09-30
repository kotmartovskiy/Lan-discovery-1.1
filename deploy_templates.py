import paramiko
import sys
import io
import os
import time

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

BASE = r"C:\Users\Lenovo\Documents\Default Project"
REMOTE = "/opt/lan-discovery"

HOST = os.environ.get("LAN_SSH_HOST", "")
PASS = os.environ.get("LAN_SSH_PASS", "")
if not HOST or not PASS:
    sys.exit("укажите LAN_SSH_HOST и LAN_SSH_PASS в окружении")

ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
ssh.connect(HOST, username=os.environ.get("LAN_SSH_USER", "root"), password=PASS, timeout=10)
print('Connected.')

# 1. Backup
ts = time.strftime("%Y%m%d-%H%M%S")
ssh.exec_command(f"cp {REMOTE}/app.py {REMOTE}/app.py.backup-{ts}")
time.sleep(1)
print(f"Backup: app.py.backup-{ts}")

# 2. Upload app.py
sftp = ssh.open_sftp()
with open(os.path.join(BASE, "app.py"), "r", encoding="utf-8") as f:
    content = f.read()
with sftp.open(f"{REMOTE}/app.py", "w") as f:
    f.write(content.encode("utf-8"))
print(f"Uploaded app.py ({len(content)} bytes)")

# 3. Create templates dir and upload templates
ssh.exec_command(f"mkdir -p {REMOTE}/templates {REMOTE}/static")
time.sleep(1)

templates_dir = os.path.join(BASE, "templates")
for fname in os.listdir(templates_dir):
    fpath = os.path.join(templates_dir, fname)
    with open(fpath, "r", encoding="utf-8") as f:
        data = f.read()
    with sftp.open(f"{REMOTE}/templates/{fname}", "w") as f:
        f.write(data.encode("utf-8"))
    print(f"  templates/{fname} ({len(data)} bytes)")

# 4. Upload static/style.css
static_dir = os.path.join(BASE, "static")
for fname in os.listdir(static_dir):
    fpath = os.path.join(static_dir, fname)
    with open(fpath, "r", encoding="utf-8") as f:
        data = f.read()
    with sftp.open(f"{REMOTE}/static/{fname}", "w") as f:
        f.write(data.encode("utf-8"))
    print(f"  static/{fname} ({len(data)} bytes)")

sftp.close()

# 5. Syntax check
stdin, stdout, stderr = ssh.exec_command(f"python3 -c \"import py_compile; py_compile.compile('{REMOTE}/app.py', doraise=True); print('SYNTAX OK')\"")
out = stdout.read().decode('utf-8', errors='replace').strip()
print(f"Syntax: {out}")

# 6. Restart
ssh.exec_command("systemctl restart lan-discovery")
time.sleep(2)
stdin, stdout, stderr = ssh.exec_command("systemctl is-active lan-discovery")
status = stdout.read().decode('utf-8', errors='replace').strip()
print(f"Service: {status}")

ssh.close()
