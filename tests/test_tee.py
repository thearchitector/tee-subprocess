import asyncio
from io import BytesIO, StringIO
from subprocess import run

import pytest

from subprocess_tee import run as run_tee

CMD = ["python", "-c", "print('hi',end='')"]
CMD_S = " ".join(CMD)


@pytest.mark.parametrize("aio", (False, True), ids=["async", "sync"])
@pytest.mark.parametrize("shell", (False, True), ids=["direct", "in-shell"])
@pytest.mark.parametrize("cmd", (CMD, CMD_S), ids=["as-list", "as-str"])
@pytest.mark.parametrize(
    "kwargs,captured,teed",
    (
        # default behaviors are same as non-tee behaviors
        (dict(tee=False), None, ""),
        (dict(tee=False, capture_output=True), b"hi", ""),
        (dict(tee=False, text=True, capture_output=True), "hi", ""),
        # no capture, but tee (same as stdout as IO)
        (dict(), None, b"hi"),
        (dict(text=True), None, "hi"),
        # capture and tee
        (dict(capture_output=True), b"hi", b"hi"),
        (dict(text=True, capture_output=True), "hi", "hi"),
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

    assert tprocess.stdout == captured
    assert process.stdout == tprocess.stdout

    if tee:
        assert kwargs["stdout"].getvalue() == teed
        kwargs["stdout"].close()
