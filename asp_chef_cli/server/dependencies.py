from base64 import b64decode, b64encode
from typing import List

from dumbo_asp.primitives.atoms import SymbolicAtom, GroundAtom
from dumbo_asp.primitives.programs import SymbolicProgram
from dumbo_utils.validation import validate
from fastapi import Request


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


def endpoint(router, path):
    def wrapper(func):
        @router.post(path)
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
