from dumbo_asp.primitives.models import Model
from dumbo_asp.primitives.rules import SymbolicRule
from dumbo_asp.queries import explanation_graph, pack_xasp_navigator_url
from fastapi import APIRouter

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
        "herbrand_base": program.herbrand_base_without_false_predicate.as_facts
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
        herbrand_base = Model.of_atoms(atoms_from_facts(SymbolicProgram.parse(json["herbrand_base"])))
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
    answer_set = Model.of_atoms(atom for atom in json["answer_set"])
    herbrand_base = atoms_from_facts(SymbolicProgram.parse(json["herbrand_base"]))
    query = Model.of_atoms(atom for atom in json["query"])
    as_forest = json["as_forest"]

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
        as_forest_with_roots=query if as_forest else None,
        with_chopped_body=True,
        with_backward_search=True,
        backward_search_symbols=(';', ' :-'),
    )
    return {
        "url": url,
    }
