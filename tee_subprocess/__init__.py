from __future__ import annotations

import asyncio
import os
import shlex
import subprocess
import sys
import warnings
from asyncio import subprocess as aiosubprocess
from typing import TYPE_CHECKING, Coroutine, cast

if TYPE_CHECKING:
    from asyncio import StreamReader
    from asyncio.subprocess import Process
    from typing import (
        Any,
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
    Read the stream line by line, outputting to the sink if provided while appending to
    the capture buffer. Once EOF is found (the process has terminated), return the final
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
    tee: bool = True,
    shell: bool = False,
    capture_output: bool = False,
    text: bool = False,
    check: bool = False,
    **kwargs: Any,
) -> CompletedSubprocess:
    """
    Convert the given command to the expected format depending on the shell parameter,
    then run the command in the provided subprocess while tee-ing the output into the
    configured stdout and stderr sink.
    """
    out_sink: IOSink = None
    err_sink: IOSink = None
    if tee:
        # if tee (default), we need to coerce the tee destinations to proper writables
        stdout = sys.stdout if text else sys.stdout.buffer
        stderr = sys.stderr if text else sys.stderr.buffer
        out_sink = _coerce_stdio(kwargs.pop("stdout", stdout), text)
        err_sink = _coerce_stdio(kwargs.pop("stderr", stderr), text)

    process: Process
    if not shell:
        # if not shell, convert the command into a program + args
        _tcmd: Tuple[str, ...]
        if isinstance(cmd, str):
            warnings.warn(
                "Due to platform variance, single string commands may not work as"
                " intended. It is recommended to instead explicitly wrap your command"
                " in list/tuple, or enable shell mode with `shell=True`.",
                stacklevel=2,
            )
            posix: bool = os.name == "posix"
            _tcmd = tuple(shlex.split(cmd, posix=posix))
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
            warnings.warn(
                "Due to platform variance, list/tuple-based commands may not work as"
                " intended. It is recommended to instead explicitly pass your command"
                " as a string, or disable shell mode with `shell=False`.",
                stacklevel=2,
            )
            _scmd = shlex.join(cmd)
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
        output: Optional[str] = out.decode() if out else None
        error: Optional[str] = err.decode() if err else None

        if check and retcode != 0:
            raise subprocess.CalledProcessError(
                retcode, cmd, output=output, stderr=error
            )

        return subprocess.CompletedProcess(
            cmd,
            returncode=retcode,
            stdout=out.decode() if out else None,
            stderr=err.decode() if err else None,
        )

    if check and retcode != 0:
        raise subprocess.CalledProcessError(retcode, cmd, output=out, stderr=err)

    return subprocess.CompletedProcess(
        cmd,
        returncode=retcode,
        stdout=out,
        stderr=err,
    )


def run(
    args: Command,
    **kwargs: Any,
) -> Union[CompletedSubprocess, Coroutine[None, None, CompletedSubprocess]]:
    """
    Run the command described by args. Wait for command to complete, then return
    a CompletedProcess instance. If tee is True (the default), the command output will
    be captured in addition to printing to stdout and stderr.

    Also by default, runs not in shell, with no capture (tee only), and in binary mode.

    If run within an async context, returns a coroutine instead that must be awaited.
    """
    prog: Coroutine[None, None, CompletedSubprocess] = _target(args, **kwargs)
    try:
        # check if there is an event loop running. if there is, run in another thread
        asyncio.get_running_loop()
        return prog
    except RuntimeError:
        # otherwise, just run in this one directly
        return asyncio.run(prog)
