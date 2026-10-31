# 19bm-procedures

Executable Python procedures for the APS 19-BM FACT imaging beamline.

Each procedure is **one file** in [`procedures/`](procedures/), named to
match the corresponding cora `Procedure` slug. The human specification
for each one lives in the IMG internal documentation under
**19-BM Internal docs → Procedures**; this repo carries the executable
implementation.

Structured after the 2-BM equivalent,
[`2bm-procedures`](https://github.com/xray-imaging/2bm-procedures), so a
procedure written for one beamline reads the same way at the other.

## Layout

```
19bm-procedures/
├── procedures/
│   ├── __init__.py
│   ├── read_detector_image.py   # PVA -> numpy, basic training
│   └── move_motor.py            # pyepics motor move, basic training
├── pyproject.toml
└── LICENSE
```

As the set grows, cross-procedure primitives belong in
`procedures/_shared/`, following 2-BM.

## Invocation

Each procedure file is runnable as a module:

```bash
python -m procedures.read_detector_image --save frame.npy
python -m procedures.move_motor --relative 0.1 --dry-run
```

Operator-facing parameters are surfaced via `argparse`; defaults match
the values documented on the corresponding procedure page.

## The two training procedures

These exist to be read before they are used. Between them they cover
the two protocols you need at a beamline and when each applies.

`read_detector_image` uses **PV Access** (`pvapy`). A PVA `NTNDArray`
carries its pixels and its dimensions together, so the frame cannot be
reshaped wrongly — the shape arrived with the data.

`move_motor` uses **Channel Access** (`pyepics`). CA carries one scalar
or one flat array per PV, which suits a motor record, where `.VAL`,
`.RBV` and `.DMOV` are each their own PV.

`move_motor` drives real hardware. It checks soft limits, asks for
confirmation unless `--yes` is given, and supports `--dry-run`.

## Install

```bash
pip install -e .          # pyepics + numpy
pip install -e '.[pva]'   # adds pvapy, needed by read_detector_image
```

`pvapy` is optional so that `move_motor` stays usable on a machine
without it. Both procedures import their EPICS library inside the
function rather than at module scope, so `--help` works regardless.

## Environment

Both need to reach the beamline IOCs. From a public-network machine
that means the directory service, not a plain broadcast — see the
*Troubleshooting* section of the 19-BM internal docs for why, and for
the `EPICS_CA_ADDR_LIST` that works.

## License

Apache-2.0; see [`LICENSE`](LICENSE).
