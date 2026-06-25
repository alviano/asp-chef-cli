import json as json_module
import os
import re
import shutil
import subprocess
import tempfile
from collections import defaultdict
from typing import Optional, Dict, Final

import httpx
from dumbo_asp.primitives.models import Model
from dumbo_asp.primitives.rules import SymbolicRule
from dumbo_asp.primitives.templates import Template
from dumbo_asp.queries import explanation_graph, pack_xasp_navigator_url
from fastapi import APIRouter, Response
from fastapi.responses import StreamingResponse

from ..dependencies import *

router = APIRouter()


def strip_ansi_codes(text):
    # This regex matches standard ANSI escape sequences
    ansi_regex = re.compile(r'\x1b\[[0-9;]*[a-zA-Z]')
    return ansi_regex.sub('', text)


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
    minizinc = json["minizinc"]
    result = subprocess.check_output(
        ["./run.sh", "minizinc" if minizinc else "asp"],
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
    timeout_reached: Final = pyqasp_process[uuid].returncode == 124
    pyqasp_process[uuid] = None

    # report errors
    output = out.decode()
    lines = output.split('\n')
    if any(line.startswith("Error") for line in lines):
        raise ValueError(output)
    if timeout_reached:
        lines = [line for line in lines if not line.startswith("Sig term")]

    # return models
    models = [
        [lit for lit in json_module.loads(line)['literals'] if not lit.startswith('not ')]
        for line in lines if line
    ]
    return {"models": models}


casper_process: Final[Dict[str, Optional[subprocess.Popen]]] = defaultdict(lambda: None)
casper_path: Final[str | None] = shutil.which("casper")


def casper_terminate(uuid):
    if casper_process[uuid] is not None:
        casper_process[uuid].kill()


@endpoint(router, "/casper/")
async def _(json):
    global casper_process

    uuid = json["uuid"]
    program = json["program"]
    enumerate = json["enumerate"]
    timeout = json["timeout"]
    if type(timeout) is not int or timeout < 1 or timeout >= 24 * 60 * 60:
        timeout = 5

    casper_terminate(uuid)

    cmd = ["/bin/timeout", str(timeout), casper_path, "--problem", "/dev/stdin", "--json"]
    if enumerate:
        cmd.append("-n0")
    casper_process[uuid] = subprocess.Popen(cmd, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    out, err = casper_process[uuid].communicate(program.encode())
    timeout_reached: Final = casper_process[uuid].returncode == 124
    casper_process[uuid] = None
    
    # report errors
    output = out.decode()
    lines = output.split('\n')
    if any(line.startswith("Error") for line in lines):
        raise ValueError(output)
    if timeout_reached:
        lines = [line for line in lines if not line.startswith("Sig term")]

    # return models
    models = [
        [lit for lit in json_module.loads(line)['literals'] if not lit.startswith('not ')]
        for line in lines if line
    ]
    return {"models": models}    


pasta_process: Final[Dict[str, Optional[subprocess.Popen]]] = defaultdict(lambda: None)
pasta_path: Final[str | None] = shutil.which("pastasolver")


def pasta_terminate(uuid):
    if pasta_process[uuid] is not None:
        pasta_process[uuid].kill()


@endpoint(router, "/pasta/")
async def _(json):
    global pasta_process

    uuid = json["uuid"]
    program = json["program"]
    output_predicate = json["output_predicate"] or "__bounds__"
    bound_multiplier = 0
    try:
        bound_multiplier = int(json["bound_multiplier"])
        bound_multiplier = min(max(bound_multiplier, 0), 1_000_000)
    except ValueError:
        bound_multiplier = 0

    timeout = json["timeout"]
    if type(timeout) is not int or timeout < 1 or timeout >= 24 * 60 * 60:
        timeout = 5

    pasta_terminate(uuid)

    with tempfile.NamedTemporaryFile(mode='w', delete=True) as temp_file:
        temp_file.write(program)
        temp_file.flush()

        cmd = ["/bin/timeout", str(timeout), pasta_path, temp_file.name]
        pasta_process[uuid] = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        out, err = pasta_process[uuid].communicate()

    timeout_reached: Final = pasta_process[uuid].returncode == 124
    pasta_process[uuid] = None

    # report errors
    output = out.decode()
    lines = output.split('\n')
    lines = [strip_ansi_codes(line) for line in lines]
    if any(line.startswith("Error") for line in lines):
        raise ValueError('\n' + '\n'.join(lines))
    if timeout_reached:
        lines = [line for line in lines if not line.startswith("Sig term")]

    lines = [line for line in lines if line]
    lb, ub = None, None
    if len(lines) == 1:
        lb = ub = float(lines[0].split("Lower probability == upper probability for the query: ")[1])
    elif len(lines) == 2:
        lb = float(lines[0].split("Lower probability for the query: ")[1])
        ub = float(lines[1].split("Upper probability for the query: ")[1])

    if lb is None or ub is None:
        raise ValueError("Could not parse output from PASTA solver:\n" + '\n'.join(lines))

    if bound_multiplier:
        lb = round(lb * bound_multiplier)
        ub = round(ub * bound_multiplier)
    else:
        lb = f'real("{lb}")'
        ub = f'real("{ub}")'

    return {"models": [
        [f'{output_predicate}({lb},{ub})']
    ]}


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


@endpoint(router, "/template/parse-custom-template/")
async def _(json):
    source = json.get("program", "")
    if not source.strip():
        return {"error": "missing program source"}

    program = SymbolicProgram.parse(source)
    _, templates = Template.expand_program(program, return_templates=True)

    res = {}
    for key in templates.keys():
        res[key] = ({
            "name": str(templates[key].name),
            "documentation": str(templates[key].documentation),
            "predicates": sorted([f"{p.name}/{p.arity}" for p in templates[key].predicates()]),
            "program": str(templates[key].program)
        })

    return res


OLLAMA_URL = os.getenv("ASP_CHEF_CLI__OLLAMA_URL", "http://127.0.0.1:11434")


@router.api_route("/ollama/{path:path}", methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"])
async def ollama_proxy(path: str, request: Request):
    url = f"{OLLAMA_URL}/{path.lstrip('/')}"
    method = request.method
    params = request.query_params

    body = await request.body()
    headers = dict(request.headers)
    headers.pop("host", None)
    headers.pop("content-length", None)  # Let httpx recalculate it

    async def generate_stream():
        async with httpx.AsyncClient(timeout=None) as client:
            async with client.stream(
                    method=method,
                    url=url,
                    params=params,
                    headers=headers,
                    content=body,
            ) as rp_resp:
                async for chunk in rp_resp.aiter_bytes():
                    yield chunk

    try:
        return StreamingResponse(
            generate_stream(),
            media_type="application/octet-stream"
        )
    except httpx.ConnectError:
        return Response(content="Ollama not running", status_code=503)
