# Writing a procedure

A procedure is **one file** in [`procedures/`](procedures/), runnable
as a module, with a matching specification page in the IMG internal
documentation. This guide is enough to write one without that page in
front of you; [`read_detector_image.py`](procedures/read_detector_image.py)
and [`move_motor.py`](procedures/move_motor.py) are the two worked
examples to copy from.

## The two halves

| Half | Where it lives | What it is |
| --- | --- | --- |
| Implementation | this repo, `procedures/<cora-slug>.py` | the executable code |
| Specification | IMG internal docs, *19-BM Internal docs → Procedures* | preconditions, parameters, steps, postconditions, failure modes |

Both are named after the same cora `Procedure` slug, and each page
registers one-to-one with a cora `Method`. Keep the two in step: if
you add a parameter to the code, add it to the spec table.

## The code

Start from one of the two examples. The conventions they follow:

- **One file per procedure**, named for the cora slug, in `snake_case`.
- **A module docstring** that says what the procedure does, what it
  touches, how to run it, and why it is built the way it is. The
  examples explain their protocol choice; yours should explain
  whatever a reader would otherwise have to guess.
- **Runnable as a module** — `python -m procedures.<name>` — with a
  `main(argv=None) -> int` returning an exit code, and
  `raise SystemExit(main())` under `if __name__ == "__main__":`.
- **Operator parameters through `argparse`**, with defaults matching
  the spec page.
- **Import `epics` / `pvaccess` inside the function**, not at module
  scope, so `--help` works on a machine without them.
- **Anything that moves hardware** checks limits first, prompts unless
  `-y` / `--yes`, and offers `--dry-run`.

As the set grows, shared primitives go in `procedures/_shared/`,
following [2bm-procedures](https://github.com/xray-imaging/2bm-procedures).

## Which protocol

Both appear in the examples, and the difference is the point.

**PV Access** (`pvapy`) carries a whole structured object in one
request. An areaDetector `NTNDArray` arrives with its pixels *and* its
dimensions, so a frame cannot be reshaped wrongly — the shape came
with the data. Use it for images.

**Channel Access** (`pyepics`) carries one scalar or one flat array per
PV. That suits a motor record, where `.VAL`, `.RBV`, `.DMOV`, `.LLM`
and `.HLM` are each their own PV. Use it for control and status.

## The specification page

Copy the template at *19-BM Internal docs → Procedures → Procedure
template* as `<cora-slug>.rst`. Required sections, in order:

| Section | Contents | Maps to in cora |
| --- | --- | --- |
| **Name** | `snake_case` identifier | `Method.name` |
| **Devices** | every Asset read or written, linked to the Beamline components page | `Plan.wiring` targets |
| **Preconditions** | one assertion per bullet; "none" is allowed | guard clauses |
| **Parameters** | name, type, unit, description; "none" is allowed | `Method.parameters_schema` |
| **Steps** | one atomic action per row, with the PV or call | the Method body |
| **Postconditions** | what is true on success | asserted state |
| **Failure modes** | symptom and recovery; "none known" is allowed | `caution` entries |

*Operator walkthrough* and *Notes* are optional. Keep click-by-click
operator detail in the
[19-BM operations](https://docs19bm.readthedocs.io/en/latest/source/ops.html)
pages and link to them rather than duplicating.

## Before you run anything

Both examples need to reach the beamline IOCs. From a public-network
machine a plain broadcast does not work and you need the directory
service — see the *Troubleshooting* section of the 19-BM internal docs
for the `EPICS_CA_ADDR_LIST` that does.

Try `--dry-run` and `--help` first. `move_motor` drives real hardware.

## Submitting

This repository is a fork workflow: `origin` is a personal fork,
`upstream` is [xray-imaging/19bm-procedures](https://github.com/xray-imaging/19bm-procedures).
Push to your fork and open a pull request upstream.
