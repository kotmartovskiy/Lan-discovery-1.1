import os
import sys

import paramiko

HOST = os.environ.get("LAN_SSH_HOST", "")
PASS = os.environ.get("LAN_SSH_PASS", "")
TV_IP = sys.argv[1] if len(sys.argv) > 1 else os.environ.get("LAN_TV_IP", "")
if not HOST or not PASS or not TV_IP:
    sys.exit("нужен LAN_SSH_HOST, LAN_SSH_PASS и TV IP (argv[1] или LAN_TV_IP)")

ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
ssh.connect(HOST, username=os.environ.get("LAN_SSH_USER", "root"), password=PASS)

q = (
    "SELECT ip, mac, hostname, name, vendor, device_type, online, first_seen, last_seen "
    f"FROM devices WHERE ip='{TV_IP}';"
)

stdin, stdout, stderr = ssh.exec_command(
    "sqlite3 -header -column /opt/lan-discovery/devices.db", timeout=30
)
stdin.write(q + "\n")
stdin.channel.shutdown_write()
out = stdout.read().decode('utf-8', errors='replace')
err = stderr.read().decode('utf-8', errors='replace')
print(out)
if err:
    print("ERR:", err)

ssh.close()
