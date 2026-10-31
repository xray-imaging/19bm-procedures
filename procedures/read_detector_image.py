"""Read one areaDetector frame into a numpy array over PV Access
(cora slug: ``read_detector_image``).

A basic training procedure. It connects to the PVA plugin of the 19-BM
Vieworks camera, fetches the current frame as an ``NTNDArray``, converts
it to a 2-D numpy array and prints a short summary. Optionally writes
the array to a ``.npy`` file.

Nothing is moved and nothing is configured. The camera must already be
acquiring -- this reads whatever frame is current rather than
triggering one -- and the areaDetector PVA plugin must be enabled for
the channel to exist at all.

**Why PV Access rather than Channel Access.** A PVA ``NTNDArray``
carries the pixels and their dimensions together in one structured
object, so the frame cannot be reshaped wrongly: the shape arrived with
the data. Fetching the same image over Channel Access means reading a
flat ``image1:ArrayData`` and then reading width and height from two
further PVs, which can disagree with the array if the camera was
reconfigured between the reads.

Run it::

    python -m procedures.read_detector_image
    python -m procedures.read_detector_image --channel 19bmVieworks:Pva1:Image
    python -m procedures.read_detector_image --save frame.npy

The operator-facing spec is in the IMG internal documentation under
*19-BM Internal docs -> Procedures*.
"""

from __future__ import annotations

import argparse
import sys

import numpy as np

#: PVA plugin channel of the 19-BM Vieworks camera.
DEFAULT_CHANNEL = "19bmVieworks:Pva1:Image"


def read_detector_image(channel: str = DEFAULT_CHANNEL) -> np.ndarray:
    """Return the current frame on ``channel`` as a 2-D numpy array.

    Parameters
    ----------
    channel
        PVA channel name. For an areaDetector IOC this is the camera
        prefix followed by ``Pva1:Image``.

    Raises
    ------
    NotImplementedError
        If the frame is not two-dimensional, i.e. colour or stacked.
    """
    import pvaccess as pva  # imported late so --help works without pvapy

    frame = pva.Channel(channel).get("")

    # The pixel data sits in a union whose key names the pixel type the
    # camera is currently sending -- ubyteValue for Mono8, ushortValue
    # for Mono12 or Mono16, and so on. Read whichever field is
    # populated rather than hard-coding one, so the procedure keeps
    # working when the camera's PixelFormat changes.
    value = frame["value"][0]
    (pixel_type,) = value.keys()
    flat = np.asarray(value[pixel_type])

    # Dimensions travel with the pixels, fastest-varying axis first:
    # dimension[0] is x (width), dimension[1] is y (height).
    dims = frame["dimension"]
    if len(dims) != 2:
        raise NotImplementedError(
            f"{channel} delivered a {len(dims)}-dimensional frame; this "
            "procedure handles mono images only"
        )
    width = dims[0]["size"]
    height = dims[1]["size"]

    return flat.reshape(height, width)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Read one areaDetector frame into a numpy array over PVA.",
    )
    parser.add_argument("--channel", default=DEFAULT_CHANNEL,
                        help="PVA channel name (default: %(default)s)")
    parser.add_argument("--save", metavar="FILE.npy",
                        help="also write the array to a .npy file")
    args = parser.parse_args(argv)

    try:
        image = read_detector_image(args.channel)
    except Exception as exc:  # noqa: BLE001 - a training script should explain
        print(f"could not read {args.channel}: {exc}", file=sys.stderr)
        print("check that the IOC is up, the PVA plugin is enabled, and "
              "EPICS_PVA_ADDR_LIST reaches the beamline subnet",
              file=sys.stderr)
        return 1

    print(f"channel : {args.channel}")
    print(f"shape   : {image.shape}  (height, width)")
    print(f"dtype   : {image.dtype}")
    print(f"min/max : {image.min()} / {image.max()}")
    print(f"mean    : {image.mean():.1f}")

    if args.save:
        np.save(args.save, image)
        print(f"saved   : {args.save}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
