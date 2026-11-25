"""Offline check of the installer's declared requirements, including requested extras."""

import re
import sys
from importlib import metadata
from pathlib import Path

from pip._vendor.packaging.requirements import Requirement


def unmet(spec):
    req = Requirement(spec)
    if req.marker and not req.marker.evaluate():
        return False
    try:
        dist = metadata.distribution(req.name)
    except metadata.PackageNotFoundError:
        return True
    if not req.specifier.contains(dist.version, prereleases=True):
        return True
    for extra in req.extras:
        for dependency in dist.requires or ():
            dep = Requirement(dependency)
            if dep.marker and dep.marker.evaluate({"extra": extra}):
                dep.marker = None
                if unmet(str(dep)):
                    return True
    return False


if __name__ == "__main__":
    missing = []
    for line in Path(sys.argv[1]).read_text(encoding="utf-8-sig").splitlines():
        spec = re.split(r"\s+#", line.strip(), maxsplit=1)[0]
        if spec and not spec.startswith("#") and unmet(spec):
            missing.append(spec)
    for spec in missing:
        print(spec)
    sys.exit(int(bool(missing)))
