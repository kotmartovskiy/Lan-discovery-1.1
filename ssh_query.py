import paramiko
import sys
import os

os.environ['PYTHONIOENCODING'] = 'utf-8'

HOST = os.environ.get("LAN_SSH_HOST", "")
PASS = os.environ.get("LAN_SSH_PASS", "")
if not HOST or not PASS:
    sys.exit("укажите LAN_SSH_HOST и LAN_SSH_PASS в окружении")

ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
ssh.connect(HOST, username=os.environ.get("LAN_SSH_USER", "root"), password=PASS)

def run_cmd(cmd):
    stdin, stdout, stderr = ssh.exec_command(cmd)
    out = stdout.read().decode('utf-8', errors='replace')
    err = stderr.read().decode('utf-8', errors='replace')
    return out, err

if len(sys.argv) > 1:
    cmd = ' '.join(sys.argv[1:])
    out, err = run_cmd(cmd)
    if out:
        sys.stdout.buffer.write(out.encode('utf-8', errors='replace'))
    if err:
        sys.stderr.buffer.write(err.encode('utf-8', errors='replace'))
else:
    print("No command specified")

ssh.close()
