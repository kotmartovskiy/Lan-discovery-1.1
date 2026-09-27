import shlex
import sys

import paramiko

TV = "192.168.3.24:5555"


def main() -> None:
    ssh = paramiko.SSHClient()
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    ssh.connect("192.168.3.234", username="root", password="1234")

    shell_cmd = " ".join(sys.argv[1:])
    cmd = "adb -s " + TV + " shell " + shlex.quote(shell_cmd)
    stdin, stdout, stderr = ssh.exec_command(cmd, timeout=60)
    out = stdout.read().decode("utf-8", errors="replace").replace("\r", "")
    err = stderr.read().decode("utf-8", errors="replace").replace("\r", "")
    if out:
        print(out, end="")
    if err:
        print("ERR:", err, end="")
    ssh.close()


if __name__ == "__main__":
    main()
