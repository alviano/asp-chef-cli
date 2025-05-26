import json as json_module
import shutil
import subprocess
from collections import defaultdict
from typing import Optional, Dict, Final

from fastapi import APIRouter

from ..dependencies import *

router = APIRouter()

clingo_process: Final[Dict[str, Optional[subprocess.Popen]]] = defaultdict(lambda: None)
clingo_path: Final[str | None] = shutil.which("clingo")


def clingo_terminate(uuid):
    if clingo_process[uuid] is not None:
        clingo_process[uuid].kill()


@endpoint(router, "/run")
async def _(json):
    global clingo_process

    uuid = json["uuid"]
    program = json["program"]
    number = json["number"]
    options = json["options"]
    timeout = json["timeout"]
    if type(timeout) is not int or timeout < 1 or timeout >= 24 * 60 * 60:
        timeout = 5

    clingo_terminate(uuid)

    cmd = f"bwrap --ro-bind /usr/lib /usr/lib --ro-bind /lib /lib --ro-bind /lib64 /lib64 " \
          f"--ro-bind /bin/timeout /bin/timeout".split(' ') +\
          ["--ro-bind", clingo_path, "/bin/clingo"] +\
          ["/bin/timeout", str(timeout), "/bin/clingo", "--outf=2", *options, str(number)]
    clingo_process[uuid] = subprocess.Popen(cmd, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    out, err = clingo_process[uuid].communicate(program.encode())
    clingo_process[uuid] = None

    return json_module.loads(out)


@endpoint(router, "/terminate")
async def _(json):
    uuid = json["uuid"]
    clingo_terminate(uuid)
    return json
