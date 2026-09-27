import paramiko
import sys
import os

os.environ['PYTHONIOENCODING'] = 'utf-8'

ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
ssh.connect('192.168.3.234', username='root', password='1234')

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
