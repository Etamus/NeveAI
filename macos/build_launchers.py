"""Build native Finder applets with Apple's built-in tools (no Xcode needed)."""

import plistlib
import shutil
import subprocess
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent


def build():
    for name, mode in (("Instalar Neve", "install"), ("Iniciar Neve", "start")):
        stage = HERE / ".runtime" / f"launchers-{time.time_ns()}"
        stage.mkdir(parents=True)
        target = stage / (name + ".app")
        script = f'''
on run
    set appPath to POSIX path of (path to me)
    set folderPath to do shell script "/usr/bin/dirname " & quoted form of appPath
    try
        do shell script "/bin/test -f " & quoted form of (folderPath & "/launch.sh")
    on error
        set folderPath to POSIX path of (choose folder with prompt "Selecione a pasta macos do projeto Neve")
    end try
    do shell script "NEVE_MACOS_NO_TERMINAL=1 /bin/bash " & quoted form of (folderPath & "/launch.sh") & " {mode} >/dev/null 2>&1 &"
end run
'''
        subprocess.run(["/usr/bin/osacompile", "-o", str(target), "-e", script], check=True)
        plist = target / "Contents/Info.plist"
        data = plistlib.loads(plist.read_bytes())
        data.update(
            CFBundleIdentifier=f"local.neve.{mode}",
            LSMinimumSystemVersion="14.0",
            LSArchitecturePriority=["arm64", "x86_64"],
            LSRequiresNativeExecution=True,
            NSHighResolutionCapable=True,
        )
        plist.write_bytes(plistlib.dumps(data))
        subprocess.run(
            ["/usr/bin/codesign", "--force", "--sign", "-", str(target)], check=True
        )
        app = HERE / target.name
        if app.exists():
            backup = HERE / ".runtime/original-launchers" / str(time.time_ns())
            backup.mkdir(parents=True)
            app.rename(backup / app.name)
        target.rename(app)
        shutil.rmtree(stage)
        print(app)


if __name__ == "__main__":
    build()
