import json as json_module
import subprocess
from base64 import b64decode, b64encode
from collections import defaultdict
from typing import Optional, Dict, Final, List

from dumbo_asp.primitives.atoms import SymbolicAtom, GroundAtom
from dumbo_asp.primitives.models import Model
from dumbo_asp.primitives.programs import SymbolicProgram
from dumbo_asp.primitives.rules import SymbolicRule
from dumbo_asp.queries import explanation_graph, pack_xasp_navigator_url
from dumbo_utils.validation import validate
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware

app = FastAPI()
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5188", "https://asp-chef.alviano.net"],
    allow_credentials=False,
    allow_methods=["POST"],
    allow_headers=["*"],
)

clingo_process: Final[Dict[str, Optional[subprocess.Popen]]] = defaultdict(lambda: None)
clingo_path: Final = subprocess.run(["which", "clingo"], capture_output=True).stdout.decode().strip()


def to_b64(string: str) -> str:
    return b64encode(string.encode()).decode()


def from_b64(encoded_content: str) -> str:
    return b64decode(encoded_content.encode()).decode()


def extract_b64(atom: str) -> str:
    return from_b64(SymbolicAtom.parse(atom).arguments[0].string_value())


def atoms_from_facts(program: SymbolicProgram, *, ground: bool = True) -> List[SymbolicAtom] | List[GroundAtom]:
    validate("only facts", all([rule.is_fact for rule in program]), equals=True)
    res = [rule.head_atom for rule in program]
    return [GroundAtom.parse(str(atom)) for atom in res] if ground else res


def endpoint(path):
    def wrapper(func):
        @app.post(path)
        async def wrapped(request: Request):
            json = await request.json()
            try:
                return await func(json)
            except Exception as e:
                return {
                    "error": str(e)
                }
        return wrapped
    return wrapper


def clingo_terminate(uuid):
    if clingo_process[uuid] is not None:
        clingo_process[uuid].kill()


@endpoint("/clingo-run/")
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
          f"--ro-bind /home/malvi/soft/miniconda3/lib /usr/lib --ro-bind /bin/timeout /bin/timeout".split(' ') +\
          ["--ro-bind", clingo_path, "/bin/clingo"] +\
          ["/bin/timeout", str(timeout), "/bin/clingo", "--outf=2", *options, str(number)]
    clingo_process[uuid] = subprocess.Popen(cmd, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    out, err = clingo_process[uuid].communicate(program.encode())
    clingo_process[uuid] = None

    return json_module.loads(out)


@endpoint("/clingo-terminate/")
async def _(json):
    uuid = json["uuid"]
    clingo_terminate(uuid)
    return json


@endpoint("/to-zero-simplification-version/")
async def _(json):
    program = SymbolicProgram.parse(json["program"])
    extra_atoms = [GroundAtom.parse(atom) for atom in json["extra_atoms"]]

    return {
        "program": str(program.to_zero_simplification_version(extra_atoms=extra_atoms, compact=True))
    }


@endpoint("/herbrand-base/")
async def _(json):
    program = SymbolicProgram.parse(json["program"])

    return {
        "herbrand_base": program.herbrand_base_without_false_predicate.as_facts
    }


@endpoint("/global-safe-variables/")
async def _(json):
    program = SymbolicProgram.parse(json["program"])

    return {
        "rules": [
            {
                "rule": str(rule),
                "variables": rule.global_safe_variables,
            }
            for rule in program
        ]
    }


@endpoint("/expand-global-safe-variables/")
async def _(json):
    program = SymbolicProgram.parse(json["program"])
    herbrand_base = None
    if json["herbrand_base"]:
        herbrand_base = Model.of_atoms(atoms_from_facts(SymbolicProgram.parse(json["herbrand_base"])))
    expand = {SymbolicRule.parse(key): value for key, value in json["expand"].items()}

    return {
        "program": str(program.expand_global_safe_variables_in_rules(expand, herbrand_base=herbrand_base))
    }


@endpoint("/expand-global-and-local-variables/")
async def _(json):
    program = SymbolicProgram.parse(json["program"])

    return {
        "program": str(program.expand_global_and_local_variables())
    }


@endpoint("/move-up/")
async def _(json):
    program = SymbolicProgram.parse(json["program"])
    atoms = atoms_from_facts(SymbolicProgram.parse(json["atoms"]), ground=False)

    return {
        "program": str(program.move_up(*atoms))
    }


@endpoint("/explanation-graph/")
async def _(json):
    program = SymbolicProgram.parse(json["program"])
    answer_set = Model.of_atoms(atom for atom in json["answer_set"])
    herbrand_base = atoms_from_facts(SymbolicProgram.parse(json["herbrand_base"]))
    query = Model.of_atoms(atom for atom in json["query"])

    validate("program", program, min_len=1, help_msg="Program cannot be empty")
    validate("herbrand base", herbrand_base, min_len=1, help_msg="Herbrand base cannot be empty")
    validate("query", query, min_len=1, help_msg="Query cannot be empty")

    graph = explanation_graph(
        program=program,
        answer_set=answer_set,
        herbrand_base=herbrand_base,
        query=query,
    )
    url = pack_xasp_navigator_url(
        graph,
        with_chopped_body=True,
        with_backward_search=True,
        backward_search_symbols=(';', ' :-'),
    )
    return {
        "url": url,
    }
