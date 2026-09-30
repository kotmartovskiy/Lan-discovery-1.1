import os
import shlex
import sys

import paramiko


def main() -> None:
    host = os.environ.get("LAN_SSH_HOST", "")
    passwd = os.environ.get("LAN_SSH_PASS", "")
    tv = os.environ.get("LAN_TV_ADB", "")
    if not host or not passwd or not tv:
        sys.exit("нужен LAN_SSH_HOST, LAN_SSH_PASS и LAN_TV_ADB=<ip:port>")
    ssh = paramiko.SSHClient()
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    ssh.connect(host, username=os.environ.get("LAN_SSH_USER", "root"),
                password=passwd)

    shell_cmd = " ".join(sys.argv[1:])
    cmd = "adb -s " + tv + " shell " + shlex.quote(shell_cmd)
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
