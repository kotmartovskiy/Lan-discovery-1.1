import os
import sys

import paramiko

REMOTE = "/root/xplore.apk"
LOCAL = os.path.join(os.environ["TEMP"], "xplore.apk")

HOST = os.environ.get("LAN_SSH_HOST", "")
PASS = os.environ.get("LAN_SSH_PASS", "")
TV = os.environ.get("LAN_TV_ADB", "")
if not HOST or not PASS or not TV:
    sys.exit("нужен LAN_SSH_HOST, LAN_SSH_PASS и LAN_TV_ADB=<ip:port>")

ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
ssh.connect(HOST, username=os.environ.get("LAN_SSH_USER", "root"), password=PASS)

sftp = ssh.open_sftp()
sftp.put(LOCAL, REMOTE)
sftp.close()
print("uploaded", REMOTE)

cmd = f"adb -s {TV} install -r {REMOTE}"
i, o, e = ssh.exec_command(cmd, timeout=180)
print(o.read().decode("utf-8", errors="replace"))
err = e.read().decode("utf-8", errors="replace")
if err:
    print("ERR:", err)

i, o, e = ssh.exec_command(
    f"adb -s {TV} shell pm list packages | grep xplore; "
    f"adb -s {TV} shell dumpsys package com.lonelycatgames.Xplore | grep -E 'versionName|nativeLibraryDir' | head -3"
)
print(o.read().decode("utf-8", errors="replace"))

ssh.close()
