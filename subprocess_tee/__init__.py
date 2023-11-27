from __future__ import annotations

import asyncio
import subprocess
import sys
from asyncio import subprocess as aiosubprocess
from concurrent.futures import ThreadPoolExecutor
from typing import TYPE_CHECKING, cast

if TYPE_CHECKING:
    from asyncio import StreamReader
    from asyncio.subprocess import Process
    from typing import (
        Any,
        Awaitable,
        BinaryIO,
        List,
        Optional,
        TextIO,
        Tuple,
        TypeAlias,
        TypeVar,
        Union,
    )

    T = TypeVar("T", str, bytes)
    Command: TypeAlias = Union[str, List[str], Tuple[str, ...]]
    IOSink: TypeAlias = Optional[Union[BinaryIO, TextIO]]
    CompletedSubprocess: TypeAlias = Union[
        subprocess.CompletedProcess[str], subprocess.CompletedProcess[bytes]
    ]


async def _tee_stream(
    stream: StreamReader, text: bool, should_capture: bool, sink: IOSink
) -> Optional[bytes]:
    """
    Read the stream line by line, outputting to the sink if provided while appending to the tee buffer. Once EOF is found (the process has terminated), return the final
    coalesced buffer.
    """
    stdio: List[bytes] = []

    # while the stream is available (not closed / EOF by subprocess)
    while not stream.at_eof():
        lineb: bytes = await stream.readline()

        if should_capture:
            # if we want to capture to pass back as the process stdout, we need
            # to manually keep track of what we read since reading for tee consumes
            # the buffer
            stdio.append(lineb)
        if sink:
            if text:
                sink.write(lineb.decode())  # type: ignore
            else:
                sink.write(lineb)  # type: ignore

    if should_capture:
        return b"".join(stdio)

    return None


def _coerce_stdio(stdio: Union[IOSink, int], text: bool) -> IOSink:
    """
    If the input is a STDOUT or PIPE, return stdout. If DEVNULL, return None.
    Otherwise, just return what is provided.
    """
    if isinstance(stdio, int):
        if stdio in (
            subprocess.STDOUT,
            subprocess.PIPE,
            aiosubprocess.STDOUT,
            aiosubprocess.PIPE,
        ):
            return sys.stdout if text else sys.stdout.buffer

        return None  # DEVNULL

    return stdio


async def _target(
    cmd: Command,
    shell: bool = False,
    capture_output: bool = False,
    text: bool = False,
    **kwargs: Any,
) -> CompletedSubprocess:
    """
    Convert the given command to the expected format depending on the shell parameter,
    then run the command in the provided subprocess while tee-ing the output into the
    configured stdout and stderr sink.
    """
    stdout: IOSink = sys.stdout if text else sys.stdout.buffer
    stderr: IOSink = sys.stderr if text else sys.stderr.buffer
    out_sink: IOSink = _coerce_stdio(kwargs.pop("stdout", stdout), text)
    err_sink: IOSink = _coerce_stdio(kwargs.pop("stderr", stderr), text)

    process: Process
    if not shell:
        # if not shell, convert the command into a program + args
        _tcmd: Tuple[str, ...]
        if isinstance(cmd, str):
            _tcmd = tuple(cmd.split(" "))
        else:
            _tcmd = tuple(cmd)

        program: str = _tcmd[0]
        args: Tuple[str, ...] = _tcmd[1:]
        # exec the program and args
        process = await aiosubprocess.create_subprocess_exec(
            program,
            *args,
            stdout=aiosubprocess.PIPE,
            stderr=aiosubprocess.PIPE,
            **kwargs,
        )
    else:
        # if in a shell, combine the args into a single command string
        _scmd: str
        if not isinstance(cmd, str):
            _scmd = " ".join(cmd)
        else:
            _scmd = cmd

        # run the program in system shell
        process = await aiosubprocess.create_subprocess_shell(
            _scmd,
            stdout=aiosubprocess.PIPE,
            stderr=aiosubprocess.PIPE,
            **kwargs,
        )

    out, err = await asyncio.gather(
        *(
            _tee_stream(process.stdout, text, capture_output, out_sink),  # type: ignore
            _tee_stream(process.stderr, text, capture_output, err_sink),  # type: ignore
        )
    )
    await process.communicate()
    retcode: int = cast(int, process.returncode)

    if text:
        return subprocess.CompletedProcess(
            cmd,
            returncode=retcode,
            stdout=out.decode() if out else None,
            stderr=err.decode() if err else None,
        )

    return subprocess.CompletedProcess(
        cmd,
        returncode=retcode,
        stdout=out,
        stderr=err,
    )


def run(
    args: Command,
    tee: bool = True,
    **popen_kwargs: Any,
) -> CompletedSubprocess:
    """
    Run the command described by args. Wait for command to complete, then return
    a CompletedProcess instance. If tee is True (the default), the command output will
    be captured in addition to printing to stdout and stderr.

    Also by default, runs not in shell, with no capture (tee only), and in binary mode.
    """
    if not tee:
        return subprocess.run(args, **popen_kwargs)  # type: ignore

    prog: Awaitable[CompletedSubprocess] = _target(args, **popen_kwargs)

    try:
        # check if there is an event loop running. if there is, run in another thread
        asyncio.get_running_loop()
        with ThreadPoolExecutor(max_workers=1) as executor:
            return executor.submit(asyncio.run, prog).result()
    except RuntimeError:
        # otherwise, just run in this one directly
        return asyncio.run(prog)
