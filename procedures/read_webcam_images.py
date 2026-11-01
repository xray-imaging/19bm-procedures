"""Read the three 19-BM hutch web cameras into a numpy array
(cora slug: ``read_webcam_images``).

Grabs one still frame from each of the three IP cameras in the 19-BM-D
hutch and returns them stacked as a single ``(3, 1080, 1920, 3)`` uint8
array, ready to hand to an image-processing agent. Nothing is moved and
nothing is configured; this only reads.

The cameras are the same model as the one at 2-BM, and the grab follows
the 32-ID-C implementation in ``tomoscan_32idc.py`` rather than the
older 2-BM one. The reasons, in order of how much they matter:

* **OpenCV is not used.** The 2-BM version calls
  ``cv2.VideoCapture``. OpenCV is not installed in the beamline python
  environments and cannot do Digest authentication anyway, so it would
  be a new dependency that still might not work. ``urllib`` and Pillow
  are already present.
* **The password never enters the URL.** 2-BM splices credentials into
  the URL string, which only works for Basic auth and leaks the
  password into anything that logs a URL. Registering a
  ``HTTPDigestAuthHandler`` alongside a ``HTTPBasicAuthHandler`` covers
  either scheme and keeps the password out of the request line.
* **A still, not a stream.** ``/cgi-bin/camera`` returns one JPEG and
  closes. The ``/cgi-bin/mjpeg?stream=1`` endpoint these cameras also
  expose returns ``multipart/x-mixed-replace``, which never ends on its
  own and has to be parsed frame by frame. For a snapshot the still
  endpoint is simpler and cannot hang.
* **Everything has a timeout.** An unreachable camera fails in
  ``TIMEOUT`` seconds instead of blocking.

Endpoints and resolution were confirmed against the live cameras on
2026-11-01: all three answer ``/cgi-bin/camera`` with a 1920x1080 RGB
JPEG of roughly 235 KB. ``/cgi-bin/jpeg`` returns 403 and the Axis-style
paths return 404, so the path is not guesswork, but it is still exposed
as ``--path`` in case the firmware changes.

Credentials live in ``~/.webcam_credentials`` as a single
``username|password`` line, the same file tomoscan uses. It must not be
world-readable; the procedure refuses to run if it is.

Run it::

    python -m procedures.read_webcam_images
    python -m procedures.read_webcam_images --camera 2
    python -m procedures.read_webcam_images --save hutch.npy
    python -m procedures.read_webcam_images --save-dir /tmp/hutch --skip-failed

The operator-facing spec is in the IMG internal documentation under
*19-BM Internal docs -> Procedures*.
"""

from __future__ import annotations

import argparse
import os
import pathlib
import stat
import sys

import numpy as np

#: The three hutch cameras, in the order they appear on ``mct_main.adl``.
DEFAULT_CAMERAS: dict[str, str] = {
    "1": "10.54.129.31",
    "2": "10.54.129.32",
    "3": "10.54.129.33",
}

#: Still-image endpoint. The cameras also serve an MJPEG stream at
#: ``/cgi-bin/mjpeg?stream=1``, which is deliberately not used.
DEFAULT_PATH = "/cgi-bin/camera"

#: Seconds to wait for one camera before giving up.
TIMEOUT = 10.0

#: Credentials file, shared with tomoscan. One ``username|password`` line.
CREDENTIALS_FILE = pathlib.Path.home() / ".webcam_credentials"


def read_webcam_credentials(path: os.PathLike | str = CREDENTIALS_FILE
                            ) -> tuple[str, str]:
    """Return ``(username, password)`` from the credentials file.

    Raises
    ------
    FileNotFoundError
        If the file does not exist.
    PermissionError
        If the file is readable by group or other. This is a refusal,
        not a warning: the file holds a live password, and a procedure
        that quietly used a world-readable one would hide the problem
        rather than surface it. Fix with ``chmod 600``.
    ValueError
        If the contents are not a single ``username|password`` line.
    """
    path = pathlib.Path(path)
    if not path.exists():
        raise FileNotFoundError(
            f"{path} not found; create it with one 'username|password' line "
            "and chmod 600 it"
        )

    mode = path.stat().st_mode
    if mode & (stat.S_IRWXG | stat.S_IRWXO):
        raise PermissionError(
            f"{path} is mode {oct(mode & 0o777)[2:]}, readable beyond its "
            "owner; run: chmod 600 " + str(path)
        )

    text = path.read_text().strip()
    if text.count("|") != 1:
        raise ValueError(
            f"{path} should hold exactly one 'username|password' line"
        )
    username, password = text.split("|")
    return username, password


def _opener(url: str, username: str, password: str):
    """Build a urllib opener that can satisfy Digest or Basic auth."""
    import urllib.request

    manager = urllib.request.HTTPPasswordMgrWithDefaultRealm()
    manager.add_password(None, url, username, password)
    return urllib.request.build_opener(
        urllib.request.HTTPDigestAuthHandler(manager),
        urllib.request.HTTPBasicAuthHandler(manager),
    )


def read_webcam_image(host: str,
                      username: str,
                      password: str,
                      path: str = DEFAULT_PATH,
                      timeout: float = TIMEOUT) -> np.ndarray:
    """Return one frame from ``host`` as an ``(H, W, 3)`` uint8 array.

    Parameters
    ----------
    host
        Camera address, e.g. ``10.54.129.31``.
    path
        Still-image endpoint on the camera.
    timeout
        Seconds to wait for the response.
    """
    from PIL import Image  # imported late so --help works without Pillow
    import io

    url = f"http://{host}{path}"
    with _opener(url, username, password).open(url, timeout=timeout) as response:
        payload = response.read()

    # convert('RGB') normalises away greyscale or palette JPEGs, so the
    # caller always gets three channels and the stack below cannot fail
    # on a camera that happens to be configured differently.
    return np.asarray(Image.open(io.BytesIO(payload)).convert("RGB"))


def read_webcam_images(cameras: dict[str, str] | None = None,
                       path: str = DEFAULT_PATH,
                       timeout: float = TIMEOUT,
                       skip_failed: bool = False
                       ) -> tuple[np.ndarray, list[str]]:
    """Read every camera and return the frames stacked, with their names.

    Returns
    -------
    images
        ``(N, H, W, 3)`` uint8 array, one frame per camera that
        responded, in ``cameras`` order.
    names
        The camera keys corresponding to ``images`` along axis 0. With
        ``skip_failed`` this is how the caller knows which cameras are
        actually in the stack.

    Parameters
    ----------
    skip_failed
        If true, a camera that cannot be read is logged to stderr and
        omitted rather than raising. The default is to raise, because a
        silently short stack is worse than a clear failure when the
        result is being handed to something that will process it
        automatically.

    Raises
    ------
    RuntimeError
        If a camera fails and ``skip_failed`` is false, if every camera
        fails, or if the frames differ in shape and so cannot be
        stacked.
    """
    cameras = DEFAULT_CAMERAS if cameras is None else cameras
    username, password = read_webcam_credentials()

    frames: list[np.ndarray] = []
    names: list[str] = []
    for name, host in cameras.items():
        try:
            frames.append(read_webcam_image(host, username, password,
                                            path=path, timeout=timeout))
            names.append(name)
        except Exception as exc:  # noqa: BLE001 - the host is the useful part
            message = f"camera {name} ({host}): {type(exc).__name__}: {exc}"
            if not skip_failed:
                raise RuntimeError(message) from exc
            print(f"skipping {message}", file=sys.stderr)

    if not frames:
        raise RuntimeError("no camera could be read")

    shapes = {frame.shape for frame in frames}
    if len(shapes) != 1:
        raise RuntimeError(
            "cameras returned different frame shapes and cannot be stacked: "
            + ", ".join(f"{n}={f.shape}" for n, f in zip(names, frames))
            + "; read them individually with read_webcam_image()"
        )

    return np.stack(frames), names


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Read the 19-BM hutch web cameras into a numpy array.",
    )
    parser.add_argument("--camera", choices=sorted(DEFAULT_CAMERAS) + ["all"],
                        default="all",
                        help="which camera to read (default: %(default)s)")
    parser.add_argument("--path", default=DEFAULT_PATH,
                        help="still-image endpoint (default: %(default)s)")
    parser.add_argument("--timeout", type=float, default=TIMEOUT,
                        help="seconds per camera (default: %(default)s)")
    parser.add_argument("--skip-failed", action="store_true",
                        help="omit cameras that cannot be read instead of failing")
    parser.add_argument("--save", metavar="FILE.npy",
                        help="write the stacked array to a .npy file")
    parser.add_argument("--save-dir", metavar="DIR",
                        help="also write camera_<name>.png per camera")
    args = parser.parse_args(argv)

    cameras = (DEFAULT_CAMERAS if args.camera == "all"
               else {args.camera: DEFAULT_CAMERAS[args.camera]})

    try:
        images, names = read_webcam_images(cameras, path=args.path,
                                           timeout=args.timeout,
                                           skip_failed=args.skip_failed)
    except Exception as exc:  # noqa: BLE001 - a training script should explain
        print(f"could not read the web cameras: {exc}", file=sys.stderr)
        print("check that the cameras answer on the beamline subnet and that "
              f"{CREDENTIALS_FILE} holds a valid 'username|password' line",
              file=sys.stderr)
        return 1

    print(f"cameras : {', '.join(names)}")
    print(f"shape   : {images.shape}  (n, height, width, rgb)")
    print(f"dtype   : {images.dtype}")
    for name, frame in zip(names, images):
        print(f"  camera {name}: min/max {frame.min()}/{frame.max()}  "
              f"mean {frame.mean():.1f}")

    if args.save:
        np.save(args.save, images)
        print(f"saved   : {args.save}")

    if args.save_dir:
        from PIL import Image
        directory = pathlib.Path(args.save_dir)
        directory.mkdir(parents=True, exist_ok=True)
        for name, frame in zip(names, images):
            out = directory / f"camera_{name}.png"
            Image.fromarray(frame).save(out)
            print(f"saved   : {out}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
