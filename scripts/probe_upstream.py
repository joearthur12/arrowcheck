from __future__ import annotations

import os
import sys
import types
from dataclasses import dataclass
from pathlib import Path

import colorama

ROOT = Path(__file__).resolve().parents[1]
UPSTREAM_SRC = ROOT / "upstream" / "ChRIMP" / "src"


@dataclass(frozen=True)
class ProbeCase:
    name: str
    value: str
    context: str | None = None


def install_probe_environment() -> None:
    os.environ.setdefault("MPLCONFIGDIR", str(ROOT / ".mplconfig"))
    colorama.init(strip=True)
    sys.path.insert(0, str(UPSTREAM_SRC))

    # Upstream MechSmiles eagerly imports its visualizer, which pulls in Cairo-
    # backed rendering code that is not needed for .prod / .ms_prod probing.
    stub = types.ModuleType("chrimp.visualization.mechsmiles_visualizer")

    class MechSmilesVisualizer:
        pass

    stub.MechSmilesVisualizer = MechSmilesVisualizer
    sys.modules["chrimp.visualization.mechsmiles_visualizer"] = stub


def fresh_mechsmiles(case: ProbeCase):
    from chrimp.world.mechsmiles import MechSmiles

    return MechSmiles(case.value, context=case.context)


def emit_result(label: str, ok: bool, detail: str) -> None:
    status = "OK" if ok else "ERR"
    print(f"{label}: {status}: {detail}")


def main() -> None:
    install_probe_environment()

    cases = [
        ProbeCase(
            "valid_elementary_step",
            "C[C:2](=[O:3])C.[NH3:1]|(1,2);((2,3), 3)",
        ),
        ProbeCase(
            "malformed_harmless_extra_tuple",
            "[OH-:1].[H+:2]|(1,2,3)",
        ),
        ProbeCase(
            "unknown_atom_map_identifier",
            "C[C:2](=[O:3])C.[NH3:1]|(9,2)",
        ),
        ProbeCase(
            "duplicate_atom_map_identifier",
            "[CH3:1][OH:1].[H+:2]|(1,2)",
        ),
        ProbeCase(
            "nonexistent_bond_reference",
            "[CH3:1].[OH-:2]|((1,2),2)",
        ),
        ProbeCase(
            "possible_invalid_valence_move",
            "C[C:2](=[O:3])C.[F-:1]|(1,2)",
        ),
        ProbeCase(
            "invalid_reactant_smiles",
            "notasmiles|(1,2)",
        ),
        ProbeCase(
            "context_mismatch",
            "C[C:2](=[O:3])C.[NH3:1]|(1,2)",
            context="CCO",
        ),
        ProbeCase(
            "radical_input",
            "[CH3:1]|",
        ),
    ]

    for case in cases:
        print(f"CASE: {case.name}")
        print(f"INPUT: {case.value}")
        print(f"CONTEXT: {case.context!r}")
        try:
            constructed = fresh_mechsmiles(case)
            emit_result("CONSTRUCTION", True, constructed.value)
        except Exception as exc:
            emit_result("CONSTRUCTION", False, f"{type(exc).__name__}: {exc}")
            print("PROD: NOT_RUN")
            print("MS_PROD: NOT_RUN")
            print()
            continue

        try:
            prod_instance = fresh_mechsmiles(case)
            emit_result("PROD", True, prod_instance.prod)
        except Exception as exc:
            emit_result("PROD", False, f"{type(exc).__name__}: {exc}")

        try:
            ms_prod_instance = fresh_mechsmiles(case)
            ms_prod = ms_prod_instance.ms_prod
            emit_result(
                "MS_PROD",
                True,
                f"{type(ms_prod).__name__}: {ms_prod.can_smiles}",
            )
        except Exception as exc:
            emit_result("MS_PROD", False, f"{type(exc).__name__}: {exc}")

        print()


if __name__ == "__main__":
    main()
