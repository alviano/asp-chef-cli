import json as json_module
import shutil
import subprocess
from collections import defaultdict
from dumbo_asp.primitives.models import Model
from dumbo_asp.primitives.rules import SymbolicRule
from dumbo_asp.primitives.templates import Template
from dumbo_asp.queries import explanation_graph, pack_xasp_navigator_url
from fastapi import APIRouter
from typing import Optional, Dict, Final

from ..dependencies import *

router = APIRouter()


@endpoint(router, "/to-zero-simplification-version/")
async def _(json):
    program = SymbolicProgram.parse(json["program"])
    extra_atoms = [GroundAtom.parse(atom) for atom in json["extra_atoms"]]

    return {
        "program": str(program.to_zero_simplification_version(extra_atoms=extra_atoms, compact=True))
    }


@endpoint(router, "/herbrand-base/")
async def _(json):
    program = SymbolicProgram.parse(json["program"])

    return {
        "herbrand_base": program.herbrand_base.as_facts
    }

@endpoint(router, "/global-safe-variables/")
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


@endpoint(router, "/expand-global-safe-variables/")
async def _(json):
    program = SymbolicProgram.parse(json["program"])
    herbrand_base = None
    if json["herbrand_base"]:
        herbrand_base = Model.of_atoms(atoms_from_facts(SymbolicProgram.parse(json["herbrand_base"])), sort=False)
    expand = {SymbolicRule.parse(key): value for key, value in json["expand"].items()}

    return {
        "program": str(program.expand_global_safe_variables_in_rules(expand, herbrand_base=herbrand_base))
    }


@endpoint(router, "/expand-global-and-local-variables/")
async def _(json):
    program = SymbolicProgram.parse(json["program"])

    return {
        "program": str(program.expand_global_and_local_variables())
    }


@endpoint(router, "/move-before/")
async def _(json):
    program = SymbolicProgram.parse(json["program"])
    atoms = atoms_from_facts(SymbolicProgram.parse(json["atoms"]), ground=False)

    return {
        "program": str(program.move_before(*atoms))
    }


@endpoint(router, "/explanation-graph/")
async def _(json):
    program = SymbolicProgram.parse(json["program"])
    answer_set = Model.of_atoms(*(atom for atom in json["answer_set"]), sort=False)
    herbrand_base = atoms_from_facts(SymbolicProgram.parse(json["herbrand_base"]))
    query = Model.of_atoms(*(atom for atom in json["query"]), sort=False)
    as_forest = json["as_forest"]
    collect_pus_program = json["collect_pus_program"]

    validate("program", program, min_len=1, help_msg="Program cannot be empty")
    validate("herbrand base", herbrand_base, min_len=1, help_msg="Herbrand base cannot be empty")
    validate("query", query, min_len=1, help_msg="Query cannot be empty")

    pus_program = []
    graph = explanation_graph(
        program=program,
        answer_set=answer_set,
        herbrand_base=herbrand_base,
        query=query,
        collect_pus_program=pus_program if collect_pus_program else None
    )
    url = pack_xasp_navigator_url(
        graph,
        as_forest_with_roots=query if as_forest else None,
        with_chopped_body=True,
        with_backward_search=True,
        backward_search_symbols=(';', ' :-'),
    )
    return {
        "url": url,
        "pus_program": [str(program) for program in pus_program],
    }


@endpoint(router, "/sdl/")
async def _(json):
    program = json["program"]
    result = subprocess.check_output(
        ["./run.sh"],
        input=program.encode(),
        cwd="../SDL",
    )
    return {
        "program": result,
    }


pyqasp_process: Final[Dict[str, Optional[subprocess.Popen]]] = defaultdict(lambda: None)
pyqasp_path: Final[str | None] = shutil.which("pyqasp")


def pyqasp_terminate(uuid):
    if pyqasp_process[uuid] is not None:
        pyqasp_process[uuid].kill()


@endpoint(router, "/pyqasp/")
async def _(json):
    global pyqasp_process

    uuid = json["uuid"]
    program = json["program"]
    enumerate = json["enumerate"]
    timeout = json["timeout"]
    if type(timeout) is not int or timeout < 1 or timeout >= 24 * 60 * 60:
        timeout = 5

    pyqasp_terminate(uuid)

    # cmd = f"bwrap --ro-bind /usr/lib /usr/lib --ro-bind /lib /lib --ro-bind /lib64 /lib64 " \
    #       f"--ro-bind /bin/timeout /bin/timeout".split(' ') +\
    #       ["--ro-bind", pyqasp_path, "/bin/pyqasp"] +\
    #       ["--bind", "/", "/"] +\
    #       ["/bin/timeout", str(timeout), "/bin/pyqasp", "/dev/stdin", *options]
    cmd = ["/bin/timeout", str(timeout), pyqasp_path, "/dev/stdin"]
    if enumerate:
        cmd.append("--enumerate")
    pyqasp_process[uuid] = subprocess.Popen(cmd, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    out, err = pyqasp_process[uuid].communicate(program.encode())
    pyqasp_process[uuid] = None

    # report errors
    output = out.decode()
    lines = output.split('\n')
    if any(line.startswith("Error") for line in lines):
        raise ValueError(output)

    # return models
    models = [
        [lit for lit in json_module.loads(line)['literals'] if not lit.startswith('not ')]
        for line in lines if line
    ]
    return {"models": models}


@endpoint(router, "/template/core-template/")
async def _(json):
    if not json:
        return sorted(Template.core_template_names())
    name = json["name"]
    template = Template.core_template(name)
    return {
        "name": name,
        "documentation": template.documentation,
        "predicates": sorted([f"{predicate.name}/{predicate.arity}" for predicate in template.predicates()]),
        "program": str(template.program),
    }


@endpoint(router, "/template/expand-program/")
async def _(json):
    program = json["program"]
    result = Template.expand_program(SymbolicProgram.parse(program))
    return {
        "program": str(result),
    }
