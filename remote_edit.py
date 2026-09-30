import paramiko
import os
import sys
import time

HOST = os.environ.get("LAN_SSH_HOST", "")
USER = os.environ.get("LAN_SSH_USER", "root")
PASS = os.environ.get("LAN_SSH_PASS", "")
if not HOST or not PASS:
    sys.exit("укажите LAN_SSH_HOST и LAN_SSH_PASS в окружении")
FILE = "/opt/lan-discovery/app.py"

ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
ssh.connect(HOST, username=USER, password=PASS, timeout=10)
print("Connected.")

# Read current file
sftp = ssh.open_sftp()
with sftp.open(FILE, "r") as f:
    content = f.read().decode("utf-8")
sftp.close()
print(f"Read {len(content)} bytes from {FILE}")

# Find run_scan function boundaries
lines = content.split("\n")
start_idx = None
end_idx = None
for i, line in enumerate(lines):
    if line.strip().startswith("def run_scan("):
        start_idx = i
    elif start_idx is not None and (line.strip().startswith("def ") and i > start_idx):
        end_idx = i
        break

if start_idx is None:
    print("ERROR: Could not find def run_scan")
    ssh.close()
    exit(1)
if end_idx is None:
    print("ERROR: Could not find next def after run_scan")
    ssh.close()
    exit(1)

print(f"Found run_scan at lines {start_idx+1}-{end_idx} (1-indexed)")

new_func = '''def run_scan():
    import subprocess

    devices = {}

    for iface in ["end0", "wlan1"]:
        try:
            r = subprocess.run(
                ["nmap", "-sn", "-PR", "-e", iface, "--host-timeout", "3s", NETWORK],
                capture_output=True, text=True, timeout=45
            )
            if r.returncode == 0:
                ip = None
                for line in r.stdout.splitlines():
                    m = re.search(r"Nmap scan report for (.+)", line)
                    if m:
                        v = m.group(1).strip()
                        ip_m = re.search(r"\\(([\d.]+)\\)", v)
                        ip = ip_m.group(1) if ip_m else v.strip()
                    elif "MAC Address:" in line and ip:
                        mp = line.split("MAC Address:")[1].strip().split("(")
                        devices[ip] = mp[0].strip()
                        ip = None
        except Exception:
            pass

    for self_ip in ["192.168.3.234", "192.168.3.235"]:
        if self_ip not in devices:
            devices[self_ip] = ""

    if not devices:
        print("SCAN ERROR: no hosts found", flush=True)
        return None

    output = ""
    for ip, mac in devices.items():
        output += f"\\nNmap scan report for {ip}\\n"
        output += "Host is up.\\n"
        if mac:
            output += f"MAC Address: {mac} (Unknown)\\n"
    return output.strip()
'''

# Rebuild file: everything before run_scan + new function + everything from end_idx onward
new_content = "\n".join(lines[:start_idx]) + new_func + "\n".join(lines[end_idx:])
# Fix double newlines at boundary
new_content = new_content.replace("\n\n\n", "\n\n")

# Write updated file
sftp = ssh.open_sftp()
with sftp.open(FILE, "w") as f:
    f.write(new_content.encode("utf-8"))
sftp.close()
print("File written successfully.")

# Verify syntax
print("\n--- Syntax check ---")
stdin, stdout, stderr = ssh.exec_command(f'python3 -c "import py_compile; py_compile.compile(\'{FILE}\', doraise=True); print(\'OK\')"')
out = stdout.read().decode()
err = stderr.read().decode()
print(f"stdout: {out}")
print(f"stderr: {err}")

# Restart service
print("\n--- Restarting service ---")
stdin, stdout, stderr = ssh.exec_command("systemctl daemon-reload && systemctl restart lan-discovery")
out = stdout.read().decode()
err = stderr.read().decode()
print(f"stdout: {out}")
print(f"stderr: {err}")

# Wait 45 seconds
print("\nWaiting 45 seconds for scan to run...")
time.sleep(45)

# Check logs
print("\n--- journalctl SCAN ---")
stdin, stdout, stderr = ssh.exec_command("journalctl -u lan-discovery --since '2 min ago' --no-pager | grep SCAN")
out = stdout.read().decode()
err = stderr.read().decode()
print(out if out else "(no output)")
if err.strip():
    print(f"stderr: {err}")

# Check specific IPs
for ip in ["192.168.3.51", "192.168.3.55", "192.168.3.220"]:
    print(f"\n--- DB query for {ip} ---")
    cmd = f"sqlite3 /opt/lan-discovery/devices.db \"SELECT ip, online, last_seen FROM devices WHERE ip='{ip}'\""
    stdin, stdout, stderr = ssh.exec_command(cmd)
    out = stdout.read().decode()
    err = stderr.read().decode()
    print(f"stdout: {out}" if out.strip() else f"stdout: (no rows)")
    if err.strip():
        print(f"stderr: {err}")

# Count online devices
print("\n--- Online device count ---")
stdin, stdout, stderr = ssh.exec_command("sqlite3 /opt/lan-discovery/devices.db \"SELECT COUNT(*) FROM devices WHERE online=1\"")
out = stdout.read().decode()
err = stderr.read().decode()
print(f"stdout: {out}")
if err.strip():
    print(f"stderr: {err}")

ssh.close()
print("\nDone.")
