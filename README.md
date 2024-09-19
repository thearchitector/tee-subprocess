# tee-subprocess

![GitHub Workflow Status](https://img.shields.io/github/actions/workflow/status/thearchitector/tee-subprocess/ci.yaml?label=tests&style=flat-square)
![PyPI - Downloads](https://img.shields.io/pypi/dw/tee-subprocess?style=flat-square)

A subprocess replacement with tee support for both synchronous and asynchronous contexts.

Supports Python 3.8+.

## Example

Just import the `run` function and use it as you would use `subprocess.run`.

```python
from tee_subprocess import run

process = run(["python", "--version"], tee=True, text=True, capture_output=True)
# ==> Python 3.11.2
print(process.stdout)
# ==> Python 3.11.2
```

Changing `stdout` and `stderr` changes the location to which the `tee` occurs. You can supply any of the defined options in `subprocess` or `asyncio.subprocess` (`STDOUT`, `DEVNULL`, etc), as well as a writable text or binary file object; if providing a text file object, you must specify `text = True`.

### Async

Internally, `tee_subprocess` utilizes `asyncio` to concurrently output and capture the subprocess logs. If an event loop is already running, `run` will return an awaitable coroutine. Otherwise, it will call `asyncio.run` for you. Practically, this means you can just treat `run` as a coroutine if you're in an async context.

```python
async def main():
    process = await run(["python", "--version"], tee=True, text=True, capture_output=True)
    # ==> Python 3.11.2
    print(process.stdout)
    # ==> Python 3.11.2

asyncio.run(main())
```

### Static Typing

I do my best to provide a logical static function typing for any permitted invocation style. Mypy _should_ complain about missing or invalid overloads if you attempt to use a combination of arguments with undefined behavior (like supplying `text=True` while also providing a `BytesIO` as `stdout`, or supplying a `PathLike` argument while `shell=True`).

The one fairly large exception to this is `await run(...)` vs `run(...)`. For now, `run` returns a union between a complete process and a coroutine due to the runtime-check for an asyncio context. As a result, you'll have to `cast` the `run(...)` call to either an awaitable or a `CompletedProcess` depending on your specific use. The API may change in the future to avoid this problem.

## Alternatives

[subprocess-tee](https://github.com/pycontribs/subprocess-tee), the motivation for this library, has the same objective but fails to accommodate asynchronous applications and non-shell invocations. This library supports asynchronous contexts as well as direct, non-shell, program execution ("list-style" vs. "shell-style").

## License

MIT License
Copyright (c) 2023-2024 Elias Gabriel
