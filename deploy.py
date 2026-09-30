import paramiko
import sys
import io
import os
import time

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

HOST = os.environ.get("LAN_SSH_HOST", "")
PASS = os.environ.get("LAN_SSH_PASS", "")
if not HOST or not PASS:
    sys.exit("укажите LAN_SSH_HOST и LAN_SSH_PASS в окружении")

ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
ssh.connect(HOST, username=os.environ.get("LAN_SSH_USER", "root"), password=PASS, timeout=10)

FILE = "/opt/lan-discovery/app.py"
LOCAL = r"C:\Users\Lenovo\Documents\Default Project\app.py"

# Backup
ts = time.strftime("%Y%m%d-%H%M%S")
ssh.exec_command(f"cp {FILE} {FILE}.backup-{ts}")
time.sleep(1)
print(f"Backup: {FILE}.backup-{ts}")

# Upload
sftp = ssh.open_sftp()
with open(LOCAL, "r", encoding="utf-8") as f:
    content = f.read()
with sftp.open(FILE, "w") as f:
    f.write(content.encode("utf-8"))
sftp.close()
print(f"Uploaded {len(content)} bytes.")

# Syntax check
stdin, stdout, stderr = ssh.exec_command(f"python3 -c \"import py_compile; py_compile.compile('{FILE}', doraise=True); print('SYNTAX OK')\"")
print(f"Syntax: {stdout.read().decode('utf-8', errors='replace').strip()}")

# Restart
ssh.exec_command("systemctl restart lan-discovery")
time.sleep(2)
stdin, stdout, stderr = ssh.exec_command("systemctl is-active lan-discovery")
print(f"Service: {stdout.read().decode('utf-8', errors='replace').strip()}")

ssh.close()
