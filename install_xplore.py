import os

import paramiko

REMOTE = "/root/xplore.apk"
LOCAL = os.path.join(os.environ["TEMP"], "xplore.apk")

ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
ssh.connect("192.168.3.234", username="root", password="1234")

sftp = ssh.open_sftp()
sftp.put(LOCAL, REMOTE)
sftp.close()
print("uploaded", REMOTE)

cmd = f"adb -s 192.168.3.24:5555 install -r {REMOTE}"
i, o, e = ssh.exec_command(cmd, timeout=180)
print(o.read().decode("utf-8", errors="replace"))
err = e.read().decode("utf-8", errors="replace")
if err:
    print("ERR:", err)

i, o, e = ssh.exec_command(
    "adb -s 192.168.3.24:5555 shell pm list packages | grep xplore; "
    "adb -s 192.168.3.24:5555 shell dumpsys package com.lonelycatgames.Xplore | grep -E 'versionName|nativeLibraryDir' | head -3"
)
print(o.read().decode("utf-8", errors="replace"))

ssh.close()
