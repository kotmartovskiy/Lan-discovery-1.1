import paramiko

ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
ssh.connect('192.168.3.234', username='root', password='1234')

q = (
    "SELECT ip, mac, hostname, name, vendor, device_type, online, first_seen, last_seen "
    "FROM devices WHERE ip='192.168.3.24';"
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
