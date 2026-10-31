"""Move an EPICS motor and report the readback (cora slug:
``move_motor``).

A basic training procedure. It reads where a motor is, checks the
target against the soft limits, moves there over Channel Access and
reports where it ended up.

The motor record fields used here are the standard ones every record
has, and are worth knowing before anything else at a beamline:

==========  =======================================================
``.VAL``    desired position; writing it starts a move
``.RBV``    readback, where the motor actually is
``.DMOV``   0 while moving, 1 when done
``.LLM``    low user limit
``.HLM``    high user limit
==========  =======================================================

Run it::

    python -m procedures.move_motor --relative 0.1
    python -m procedures.move_motor --motor 19bmSoft:m22 --position 1.5
    python -m procedures.move_motor --relative 0.1 --dry-run

It asks for confirmation before moving unless ``--yes`` is given, and
``--dry-run`` checks the limits and prints the intended move without
sending anything.

.. warning::

   This moves real hardware. The default motor is the sample centering
   stage; pass ``--motor`` deliberately rather than relying on it, and
   prefer small ``--relative`` steps when learning.

The operator-facing spec is in the IMG internal documentation under
*19-BM Internal docs -> Procedures*.
"""

from __future__ import annotations

import argparse
import sys

#: Sample centering stage, SampleTop X. A short-travel stage, so a
#: small mistake here is cheap.
DEFAULT_MOTOR = "19bmSoft:m21"


def move_motor(motor: str = DEFAULT_MOTOR, *, target: float,
               timeout: float = 60.0, dry_run: bool = False) -> float:
    """Move ``motor`` to ``target`` and return the final readback.

    Parameters
    ----------
    motor
        Motor record name with no field suffix, e.g. ``19bmSoft:m21``.
    target
        Absolute position in the record's engineering units.
    timeout
        Seconds to wait for the move to complete.
    dry_run
        Check and report, but send nothing.

    Raises
    ------
    RuntimeError
        If the record does not respond.
    ValueError
        If ``target`` lies outside the soft limits.
    """
    from epics import caget, caput  # imported late so --help works without pyepics

    start = caget(f"{motor}.RBV")
    if start is None:
        raise RuntimeError(
            f"no response from {motor}.RBV -- check the IOC is running and "
            "that EPICS_CA_ADDR_LIST reaches it"
        )

    # Check the soft limits before writing. The record would refuse the
    # move anyway, but it refuses silently: .VAL is ignored and the
    # motor simply never moves, which is baffling the first time.
    low = caget(f"{motor}.LLM")
    high = caget(f"{motor}.HLM")
    if low is not None and high is not None and low != high:
        if not low <= target <= high:
            raise ValueError(
                f"target {target:g} is outside the limits of {motor} "
                f"[{low:g}, {high:g}]"
            )

    print(f"{motor}: at {start:.4f}, target {target:.4f}")
    if dry_run:
        print("dry run -- nothing sent")
        return start

    # wait=True blocks until the record reports the move finished, so
    # there is no need to poll .DMOV by hand. On timeout it returns
    # rather than raising, so the state is checked explicitly below.
    caput(f"{motor}.VAL", target, wait=True, timeout=timeout)

    final = caget(f"{motor}.RBV")
    if not caget(f"{motor}.DMOV"):
        print(f"warning: {motor} still moving after {timeout:g} s",
              file=sys.stderr)

    print(f"{motor}: now at {final:.4f} (moved {final - start:+.4f})")
    return final


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Move an EPICS motor and report the readback.",
    )
    parser.add_argument("--motor", default=DEFAULT_MOTOR,
                        help="motor record, no field suffix (default: %(default)s)")
    target = parser.add_mutually_exclusive_group(required=True)
    target.add_argument("--position", type=float, help="absolute target")
    target.add_argument("--relative", type=float,
                        help="offset from the current readback")
    parser.add_argument("--timeout", type=float, default=60.0,
                        help="seconds to wait for the move (default: %(default)s)")
    parser.add_argument("--dry-run", action="store_true",
                        help="check limits and print, but do not move")
    parser.add_argument("-y", "--yes", action="store_true",
                        help="skip the confirmation prompt")
    args = parser.parse_args(argv)

    from epics import caget

    if args.relative is not None:
        here = caget(f"{args.motor}.RBV")
        if here is None:
            print(f"no response from {args.motor}.RBV", file=sys.stderr)
            return 1
        goal = here + args.relative
    else:
        goal = args.position

    if not args.yes and not args.dry_run:
        if input(f"move {args.motor} to {goal:.4f}? [y/N] ").strip().lower() \
                not in ("y", "yes"):
            print("cancelled")
            return 1

    try:
        move_motor(args.motor, target=goal, timeout=args.timeout,
                   dry_run=args.dry_run)
    except (RuntimeError, ValueError) as exc:
        print(str(exc), file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        print("\ninterrupted -- the motor may still be moving; check .DMOV",
              file=sys.stderr)
        return 130

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
