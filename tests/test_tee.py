import asyncio
import platform
import sys
from io import BytesIO, StringIO
from pathlib import Path
from subprocess import run

import pytest

from tee_subprocess import run as run_tee

OUTPUT = f"Python {platform.python_version()}"
OUTPUTB = OUTPUT.encode()


@pytest.mark.parametrize("aio", (False, True), ids=["sync", "async"])
@pytest.mark.parametrize(
    "cmd,shell",
    (
        (["python", "--version"], False),
        ([b"python", b"--version"], False),
        ([b"python", "--version"], False),
        ([Path(sys.executable).resolve(), "--version"], False),
        ("python --version", True),
        pytest.param(
            b"python --version",
            True,
            marks=pytest.mark.xfail(
                condition=platform.system() == "Windows",
                reason="Plain byte arguments are not supported on Windows",
            ),
        ),
    ),
    ids=["str-list", "bytes-list", "mixed-list", "list-with-pathlike", "str", "bytes"],
)
@pytest.mark.parametrize(
    "kwargs,captured,teed",
    (
        # default behaviors are same as non-tee behaviors
        (dict(tee=False), None, ""),
        (dict(tee=False, capture_output=True), OUTPUTB, ""),
        (dict(tee=False, text=True, capture_output=True), OUTPUT, ""),
        # no capture, but tee (same as stdout as IO)
        (dict(), None, OUTPUTB),
        (dict(text=True), None, OUTPUT),
        # capture and tee
        (dict(capture_output=True), OUTPUTB, OUTPUTB),
        (dict(text=True, capture_output=True), OUTPUT, OUTPUT),
    ),
    ids=(
        "no-tee",
        "no-tee-capture",
        "no-tee-capture-text",
        "tee-no-capture",
        "tee-text-no-capture",
        "tee-capture",
        "tee-capture-text",
    ),
)
def test_run(tmp_path, aio, shell, cmd, kwargs, captured, teed):
    kwargs = dict(**kwargs, shell=shell)
    tee = kwargs.pop("tee", True)
    process = run(cmd, **kwargs)

    if tee:
        kwargs["stdout"] = StringIO() if kwargs.get("text") else BytesIO()

    if aio:

        async def _():
            return await run_tee(cmd, tee=tee, **kwargs)

        tprocess = asyncio.run(_())
    else:
        tprocess = run_tee(cmd, tee=tee, **kwargs)

    pout = process.stdout.strip() if process.stdout else None
    tout = tprocess.stdout.strip() if tprocess.stdout else None
    assert tout == captured
    assert pout == tout

    if tee:
        assert kwargs["stdout"].getvalue().strip() == teed
        kwargs["stdout"].close()
