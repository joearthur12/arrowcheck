# Upstream ChRIMP Notes

Milestone 0 scope only: inspect upstream before writing any ArrowCheck implementation.

## Pinned upstream checkout

- Repository: `https://github.com/schwallergroup/ChRIMP.git`
- Checked-out commit SHA: `56dd595af0ce2ab8d594d2201c9906cc48489089`

## `MechSmiles` constructor signature

Defined in `upstream/ChRIMP/src/chrimp/world/mechsmiles.py`.

```python
def __init__(self, value: str, context: str | None = None)
```

Notes:

- The constructor immediately calls `self.init_everything_from_value(value, context=context)`.
- `init_everything_from_value()` splits `value` on `"|"`, stores the left side as `self.smiles`, builds `self.ms = MoleculeSet.from_smiles(self.smiles)`, and stores arrow text as `self.smiles_arrows`.
- `context` is optional and is used to derive `self.conds` by subtracting already-accounted species from the provided context string.

## `.prod` and `.ms_prod`

Both are lazy cached properties.

- `self._prod` starts as `None`.
- `self._ms_prod` starts as `None`.
- On first access, both properties call `self.check_validity()`.
- If that returns truthy, both properties compute the product via:

```python
self.ms.make_move(
    [self.process_smiles_arrow(a, self.ms.atom_map_dict) for a in self.smiles_arrows]
)
```

Observed behavior:

- `.prod` computes `self._ms_prod`, then sets `self._prod = self._ms_prod.can_smiles`, and returns the canonical product SMILES string.
- `.ms_prod` computes the same `MoleculeSet` object, also backfills `self._prod`, and returns the `MoleculeSet`.
- Once either property has been computed, the other reuses the cached value.
- Neither property standardizes the MechSMILES before computing the move.
- No upstream test directly asserts `.prod` or `.ms_prod` behavior.

## How atom mappings are stored

Relevant implementation is in `upstream/ChRIMP/src/chrimp/world/molecule_set.py`.

- `MoleculeSet.from_smiles()` reads RDKit atom map numbers with `a.GetAtomMapNum()`.
- It stores mappings in `atom_map_dict` as:

```python
{atom_map_number: rdkit_atom_idx}
```

- Example code path:
  - if `a.GetAtomMapNum() != 0`, then `atom_map_dict[a.GetAtomMapNum()] = a.GetIdx()`
- `MechSmiles.process_smiles_arrow()` uses `self.ms.atom_map_dict` to translate tuple numbers in the arrow text into internal atom indices.
- `MoleculeSet.mapped_smiles` reverses the dictionary and writes map numbers back onto an RDKit molecule for serialization.
- Important distinction:
  - `ChrimpAtom.idx` is a separate internal zero-based index assigned during `from_smiles()`.
  - Atom map numbers are not stored on `ChrimpAtom` instances; they live in `MoleculeSet.atom_map_dict`.

## Whether the upstream parser uses `eval()`

Yes.

Direct `eval()` calls appear in `upstream/ChRIMP/src/chrimp/world/mechsmiles.py`:

- `minimize_indices()` uses `eval(tup_str)` twice while remapping arrow tuples.
- `process_smiles_arrow()` does:

```python
arrow_smiles = re.sub(r"hv", r'"hv"', arrow_smiles)
tup = eval(arrow_smiles)
```

So the upstream arrow parser is not a safe parser today. ArrowCheck should avoid this pattern.

## Whether `check_validity()` is real validation or a placeholder

It is a placeholder.

Observed behavior in `check_validity()`:

- docstring says it is a placeholder for actual validation logic;
- it prints a one-time warning:
  - `"Careful, validity not implemented yet, this is a dummy test"`
- it always returns `True`.

There is no real structural, chemical, or parser-level validation in that method yet.

## Relevant upstream tests

### `upstream/ChRIMP/tests/test_mechsmiles.py`

This is the main relevant test file.

- `test_standardize_is_stable`
  - calls `standardize()` twice and expects the second result to match the first.
- `test_atoms_unchanged_after_standardize`
  - compares atom symbol counts before and after standardization.
- `test_hs_behavior_after_standardize`
  - checks that only specific explicit hydrogen species remain after standardization.
- `test_atoms_unchanged_after_hise_unhide_cond`
  - checks atom counts survive `hide_cond()` then `unhide_cond()`.

Coverage notes:

- The file includes a comment saying additional tests are needed.
- It does not directly test:
  - `process_smiles_arrow()`
  - malformed arrow strings
  - `.prod`
  - `.ms_prod`
  - actual validity checking

### `upstream/ChRIMP/tests/test_molecule_set.py`

- Contains one parameterized case:
  - `("O=[C-:1][Cl:2]", [("i", 1, 2)])`
- Verifies atom counts remain stable across:
  - `ms.can_smiles`
  - `ms.mapped_smiles`
  - `ms.make_move(move).can_smiles`
  - `ms.make_move(move).mapped_smiles`

This is useful for mapping/move stability, but it is very narrow.

### `upstream/ChRIMP/tests/test_rdkit_sanitize.py`

- Not a normal pytest test.
- It is a script-like exploratory file that prints RDKit sanitization behavior for a few SMILES strings.

### `upstream/ChRIMP/tests/conftest.py`

- Dummy file only.
- No fixtures or test support logic.

## Dependencies likely needed for a minimal local linting path

Upstream packaging metadata is incomplete for the modules inspected.

Declared metadata:

- `setup.cfg` runtime dependency list only includes `importlib-metadata` for Python `<3.8`
- `setup.cfg` testing extra includes:
  - `setuptools`
  - `pytest`
  - `pytest-cov`
- `pyproject.toml` contains build metadata and a small Ruff config, but no full dependency list
- repo-level `requirements.txt` is broader and includes:
  - `transformers`
  - `datasets`
  - `cairosvg`
  - `svgutils`
  - `torch`
  - `accelerate`
  - `colorama`
  - `wandb`
  - `rdkit`
  - `pandas`
  - `matplotlib`
  - `seaborn`
  - `ipython`
  - `pre-commit`
  - `-e .`

Actual imports used by the relevant upstream path:

- `rdkit`
- `colorama`
- `numpy`
- `matplotlib`
- `Pillow` via `from PIL import Image`
- `cairosvg`
- `svgutils`

Practical takeaway:

- If we import `chrimp.world.mechsmiles` directly, we also pull in `MechSmilesVisualizer` at module import time, which in turn imports the visualization stack above.
- So a minimal environment for directly importing and exercising upstream `MechSmiles` is likely larger than the package metadata suggests.
- For local project tooling around ArrowCheck itself, we will probably also want:
  - `pytest`
  - `ruff`
  - `mypy`

## Milestone 0.5 environment facts

- Confirmed ArrowCheck Git repository root:
  - `C:\Users\joear\OneDrive\Documents\arrowcheck`
- `git init` was run in the ArrowCheck workspace.
- `git rev-parse --show-toplevel` returned:
  - `C:/Users/joear/OneDrive/Documents/arrowcheck`

## Exact package installation commands

Installed with the explicitly requested interpreter:

```powershell
C:\Users\joear\miniconda3\envs\arrowcheck\python.exe -m pip install rdkit colorama numpy matplotlib pillow cairosvg svgutils pytest
```

Recorded package snapshot command:

```powershell
C:\Users\joear\miniconda3\envs\arrowcheck\python.exe -m pip list --format=freeze
```

## Exact installed packages observed after the probe install

These package versions were present in the environment snapshot immediately after the install step:

```text
cairocffi==1.7.1
CairoSVG==2.9.0
cffi==2.0.0
colorama==0.4.6
contourpy==1.3.3
cssselect2==0.9.0
cycler==0.12.1
defusedxml==0.7.1
fonttools==4.63.0
iniconfig==2.3.0
kiwisolver==1.5.0
lxml==6.1.1
matplotlib==3.10.9
numpy==2.4.6
packaging==26.0
pillow==12.2.0
pip==26.1.1
pluggy==1.6.0
pycparser==3.0
Pygments==2.20.0
pyparsing==3.3.2
pytest==9.0.3
python-dateutil==2.9.0.post0
rdkit==2026.3.2
setuptools==82.0.1
six==1.17.0
svgutils==0.3.4
tinycss2==1.5.1
webencodings==0.5.1
wheel==0.46.3
```

## Minimal packages actually required for the live probe path

Observed minimum for the `.prod` / `.ms_prod` probe path, once the eager visualizer import was bypassed:

- `rdkit`
- `colorama`
- transitive runtime pieces used by installed `rdkit`, notably `numpy` and `pillow`

Packages installed from the requested command but not needed for the observed non-visual probe path:

- `matplotlib`
- `cairosvg`
- `svgutils`
- `pytest`
- their transitive dependencies

## Eager-import dependency problem

Direct import of `chrimp.world.mechsmiles` still failed after the package install because:

- `mechsmiles.py` eagerly imports `chrimp.visualization.mechsmiles_visualizer`
- that module eagerly imports `cairosvg`
- `cairosvg` imports `cairocffi`
- `cairocffi` then raised an `OSError` because no native Cairo library was available on this machine

Observed import failure summary:

- exception class: `OSError`
- message included:
  - `no library called "cairo-2" was found`
  - `cannot load library 'libcairo-2.dll': error 0x7e`

Probe decision:

- No extra Python package was installed beyond the requested set, because the failure was in an eager visualization import rather than the `.prod` / `.ms_prod` execution path itself.
- `scripts/probe_upstream.py` therefore injects a no-op `chrimp.visualization.mechsmiles_visualizer` module before importing the real upstream `MechSmiles` class.
- This keeps the probe trusted, local, and narrow while still exercising genuine upstream construction and move execution behavior.

## Observed behavior table

| Case | Input summary | Construction result | `.prod` result | Observed exception class | Observed exception message | Reliable ArrowCheck classification? | Notes |
| --- | --- | --- | --- | --- | --- | --- | --- |
| valid elementary step | `C[C:2](=[O:3])C.[NH3:1]|(1,2);((2,3), 3)` | OK | OK: `CC(C)([NH3+])[O-]` |  |  | Yes | `.ms_prod` also succeeded and returned `MoleculeSet: CC(C)([NH3+])[O-]`. |
| `.prod` / `.ms_prod` product generation | Same input as above | OK | OK |  |  | Yes | Same trusted case verifies both lazy properties on fresh instances. |
| invalid reactant-side SMILES | `notasmiles|(1,2)` | ERR | NOT_RUN | `MechSmilesInitError` | `Invalid smiles notasmiles` | Yes | Failure occurs during `MoleculeSet.from_smiles()` inside construction. |
| malformed but harmless arrow tuple | `[OH-:1].[H+:2]|(1,2,3)` | OK | OK: `O` |  |  | Yes | Extra tuple element was silently ignored by upstream attack parsing; `.ms_prod` returned `MoleculeSet: O`. |
| unknown atom-map identifier | `C[C:2](=[O:3])C.[NH3:1]|(9,2)` | OK | ERR | `KeyError` | `9` | Yes | Missing map is not validated at construction time. |
| duplicated atom-map identifier | `[CH3:1][OH:1].[H+:2]|(1,2)` | OK | OK: `C[OH2+]` |  |  | Partly | Upstream did not reject duplicate map labels; exploratory inspection showed `atom_map_dict` kept the last `:1` occurrence, so the behavior is ambiguous / last-write-wins. `.ms_prod` also succeeded with `MoleculeSet: C[OH2+]`. |
| nonexistent bond reference | `[CH3:1].[OH-:2]|((1,2),2)` | OK | ERR | `BondNotFoundError` | `Could not find a bond between 0 and 1 in molecule [CH3].[OH-]` | Yes | Exception leaks internal zero-based atom indices rather than original atom-map numbers. |
| move that may produce invalid valence | `C[C:2](=[O:3])C.[F-:1]|(1,2)` | OK | ERR | `ReusedVirtualTSException` | `Virtual TS already used for C- (idx: 1)` | Partly | Upstream did not raise a clean valence-validation error; it failed later in virtual-TS handling. |
| context mismatch | value `C[C:2](=[O:3])C.[NH3:1]|(1,2)` with context `CCO` | ERR | NOT_RUN | `MechSmilesContextError` | `Context incorrect, doesn't contain the reacting species`<br>`already_acounted_species_value=Counter({'CC(C)=O': 1, 'N': 1})`<br>`all_context=Counter({'CCO': 1})` | Yes | Context is checked during construction if the optional `context` argument is supplied. |
| radical input | `[CH3:1]|` | OK | OK: `[CH3]` |  |  | Yes | Radical input is accepted in this minimal case; `.ms_prod` returned `MoleculeSet: [CH3]`. |
| direct import without visualizer workaround | Import `chrimp.world.mechsmiles` after installing Python packages only | ERR | NOT_RUN | `OSError` | `no library called "cairo-2" was found` ... `cannot load library 'libcairo-2.dll': error 0x7e` | Yes | Environment-specific eager-import failure, not a MechSmiles parsing error. |

## Unsafe or brittle upstream behavior observed

- Arrow parsing uses `eval()` on arrow strings.
- `check_validity()` is still a placeholder and always returns `True`.
- Direct import of `MechSmiles` is coupled to optional visualization dependencies through eager imports.
- Duplicate atom-map identifiers are not rejected during construction.
- Malformed tuple shapes can be accepted if the consumed prefix happens to fit an expected branch.
- Some exceptions report internal zero-based indices instead of the original mapped identifiers.
- The failure mode for chemically suspect moves can surface as virtual-transition-state bookkeeping errors rather than clean validation errors.

## Uncertainties to test before coding

- Whether ArrowCheck should match upstream acceptance of arrow strings exactly, or intentionally reject malformed / ambiguous forms that upstream currently accepts via `eval()`.
- Whether we need compatibility with the special `hv` arrow handling.
- Whether ArrowCheck should preserve upstream map-number semantics exactly, including the distinction between atom map numbers and internal zero-based atom indices.
- Whether future product checks must reproduce upstream `.prod` output byte-for-byte, or only match chemically equivalent canonical output.
- Whether `hide_cond()` / `unhide_cond()` behavior matters for the ArrowCheck scope, since upstream tests cover it but the validation milestone may not need it.
- Whether importing upstream `MechSmiles` in the target development environment is acceptable, given the eager visualization imports.
- Whether we need additional local golden tests for malformed arrow tuples, unsafe input strings, and direct `.prod` / `.ms_prod` behavior, because upstream coverage is currently thin in those areas.
- Whether duplicate atom-map identifiers should be a hard ArrowCheck error even though upstream currently accepts them.
- Whether `ReusedVirtualTSException` should map to a user-facing ArrowCheck category like invalid-valence / unsupported-intermediate, or remain a more specific upstream-compatibility bucket.
