from __future__ import annotations

import asyncio
import os
import shlex
import subprocess
import sys
import warnings
from asyncio import subprocess as aiosubprocess
from io import TextIOBase
from typing import TYPE_CHECKING, TextIO, cast

if TYPE_CHECKING:  # pragma: no cover
    from asyncio import StreamReader
    from asyncio.subprocess import Process
    from typing import (
        Any,
        BinaryIO,
        Coroutine,
        List,
        Literal,
        Optional,
        Tuple,
        TypeAlias,
        TypeVar,
        Union,
        overload,
    )

    SingleArg = TypeVar("SingleArg")
    Command: TypeAlias = Union[SingleArg, List[SingleArg], Tuple[SingleArg, ...]]
    ExecArg: TypeAlias = Union[str, bytes, os.PathLike[str], os.PathLike[bytes]]
    ShellArg: TypeAlias = Union[str, bytes]

    IOSink: TypeAlias = Optional[Union[BinaryIO, TextIO]]

    CompletedSubprocess: TypeAlias = Union[
        subprocess.CompletedProcess[str], subprocess.CompletedProcess[bytes]
    ]

    # @overload
    # async def _tee_stream(
    #     stream: StreamReader, text: Literal[True], should_capture: bool, sink: TextIO
    # ) -> Optional[bytes]: ...

    # @overload
    # async def _tee_stream(
    #     stream: StreamReader, text: Literal[False], should_capture: bool, sink: BinaryIO
    # ) -> Optional[bytes]: ...


async def _tee_stream(
    stream: StreamReader, should_capture: bool, sink: IOSink
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
            if isinstance(sink, (TextIOBase, TextIO)):
                sink.write(lineb.decode())
            else:
                sink.write(lineb)

    if should_capture:
        return b"".join(stdio)

    return None


if TYPE_CHECKING:  # pragma: no cover

    @overload
    def _coerce_stdio(
        stdio: Optional[Union[IOSink, int]], default: TextIO, text: Literal[True]
    ) -> TextIO: ...

    @overload
    def _coerce_stdio(
        stdio: Optional[Union[IOSink, int]], default: BinaryIO, text: Literal[False]
    ) -> BinaryIO: ...


def _coerce_stdio(
    stdio: Optional[Union[IOSink, int]], default: IOSink, text: bool
) -> IOSink:
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
    elif stdio is None:
        return default

    if text and not isinstance(stdio, (TextIOBase, TextIO)):
        raise TypeError("You must use an instance of TextIO if text mode is enabled.")
    elif not text and isinstance(stdio, (TextIOBase, TextIO)):
        raise TypeError(
            "You must use an instance of BinaryIO if text mode is disabled."
        )

    return stdio


async def _target(
    cmd: Union[Command[ExecArg], Command[ShellArg]],
    shell: bool = False,
    tee: bool = True,
    capture_output: bool = False,
    stdout: Optional[Union[IOSink, int]] = None,
    stderr: Optional[Union[IOSink, int]] = None,
    text: bool = False,
    check: bool = False,
    **kwargs: Any,
) -> CompletedSubprocess:
    """
    Convert the given command to the expected format depending on the shell parameter,
    then run the command in the provided subprocess while tee-ing the output into the
    configured stdout and stderr sink.
    """
    out_sink: Optional[IOSink] = None
    err_sink: Optional[IOSink] = None
    if tee:
        # if tee (default), we need to coerce the tee destinations to proper writables
        if text:
            out_sink = _coerce_stdio(stdout, sys.stdout, True)
            err_sink = _coerce_stdio(stderr, sys.stderr, True)
        else:
            out_sink = _coerce_stdio(stdout, sys.stdout.buffer, False)
            err_sink = _coerce_stdio(stderr, sys.stderr.buffer, False)

    process: Process
    if not shell:
        # if not shell, convert the command into a program + args
        _tcmd: Tuple[ExecArg, ...]
        if isinstance(cmd, (str, bytes)):
            warnings.warn(
                "Due to platform variance, single string commands may not work as"
                " intended. It is recommended to instead explicitly wrap your command"
                " in list/tuple, or enable shell mode with `shell=True`.",
                stacklevel=2,
            )
            posix: bool = os.name == "posix"
            _tcmd = tuple(shlex.split(os.fsdecode(cmd), posix=posix))
        elif isinstance(cmd, os.PathLike):
            _tcmd = (cmd,)
        else:
            _tcmd = tuple(cmd)

        program: ExecArg = _tcmd[0]
        args: Tuple[ExecArg, ...] = _tcmd[1:]
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
        _scmd: ShellArg
        if isinstance(cmd, os.PathLike) or (
            isinstance(cmd, (list, tuple))
            and any((isinstance(arg, os.PathLike) for arg in cmd))
        ):
            raise TypeError("You cannot use path-like arguments in shell mode.")
        elif isinstance(cmd, (list, tuple)):
            warnings.warn(
                "Due to platform variance, list/tuple-based commands may not work as"
                " intended. It is recommended to instead explicitly pass your command"
                " as a string, or disable shell mode with `shell=False`.",
                stacklevel=2,
            )
            _scmd = shlex.join((os.fsdecode(arg) for arg in cmd))
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
            _tee_stream(cast("StreamReader", process.stdout), capture_output, out_sink),
            _tee_stream(cast("StreamReader", process.stderr), capture_output, err_sink),
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

    return subprocess.CompletedProcess(cmd, returncode=retcode, stdout=out, stderr=err)


if TYPE_CHECKING:  # pragma: no cover

    @overload
    def run(
        args: Command[ShellArg],
        shell: Literal[True],
        text: Literal[True],
        stdout: Optional[Union[int, TextIO]] = None,
        stderr: Optional[Union[int, TextIO]] = None,
        **kwargs: Any,
    ) -> Union[
        subprocess.CompletedProcess[str],
        Coroutine[None, None, subprocess.CompletedProcess[str]],
    ]: ...

    @overload
    def run(
        args: Command[ShellArg],
        shell: Literal[True],
        text: Literal[False] = False,
        stdout: Optional[Union[int, BinaryIO]] = None,
        stderr: Optional[Union[int, BinaryIO]] = None,
        **kwargs: Any,
    ) -> Union[
        subprocess.CompletedProcess[bytes],
        Coroutine[None, None, subprocess.CompletedProcess[bytes]],
    ]: ...

    @overload
    def run(
        args: Command[ExecArg],
        shell: Literal[False],
        text: Literal[True],
        stdout: Optional[Union[int, TextIO]] = None,
        stderr: Optional[Union[int, TextIO]] = None,
        **kwargs: Any,
    ) -> Union[
        subprocess.CompletedProcess[str],
        Coroutine[None, None, subprocess.CompletedProcess[str]],
    ]: ...

    @overload
    def run(
        args: Command[ExecArg],
        shell: Literal[False] = False,
        text: Literal[False] = False,
        stdout: Optional[Union[int, BinaryIO]] = None,
        stderr: Optional[Union[int, BinaryIO]] = None,
        **kwargs: Any,
    ) -> Union[
        subprocess.CompletedProcess[bytes],
        Coroutine[None, None, subprocess.CompletedProcess[bytes]],
    ]: ...


def run(
    args: Union[Command[ExecArg], Command[ShellArg]],
    shell: bool = False,
    text: bool = False,
    stdout: Optional[Union[IOSink, int]] = None,
    stderr: Optional[Union[IOSink, int]] = None,
    **kwargs: Any,
) -> Union[CompletedSubprocess, Coroutine[None, None, CompletedSubprocess]]:
    """
    Run the command described by args. Wait for command to complete, then return
    a CompletedProcess instance. If tee is True (the default), the command output will
    be captured in addition to printing to stdout and stderr.

    Also by default, runs not in shell, with no capture (tee only), and in binary mode.

    If run within an async context, returns a coroutine instead that must be awaited.
    """
    prog: Coroutine[None, None, CompletedSubprocess] = _target(
        args, shell=shell, text=text, stdout=stdout, stderr=stderr, **kwargs
    )
    try:
        # check if there is an event loop running, if there is return a coroutine to run
        asyncio.get_running_loop()
        return prog
    except RuntimeError:
        # otherwise, just run in this one directly
        return asyncio.run(prog)
