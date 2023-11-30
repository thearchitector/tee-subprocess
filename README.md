# tee-subprocess

![GitHub Workflow Status](https://img.shields.io/github/actions/workflow/status/thearchitector/tee-subprocess/ci.yaml?label=tests&style=flat-square)

A subprocess replacement with tee support for both synchronous and asynchronous contexts.

## Usage

Just import the `run` function and use it as you would use `subprocess.run`.

```python
from subprocess_tee import run

process = run(["python", "--version"], tee=True, text=True, capture_output=True)
# ==> Python 3.11.2
print(process.stdout)
# ==> Python 3.11.2
```

Changing `stdout` and `stderr` changes the location to which the `tee` occurs. You can supply any of the defined options in `subprocess` or `asyncio.subprocess`(`STDOUT`, `DEVNULL`, etc), as well as a writable text or binary file object.

### Async

Internally, `subprocess_tee` utilizes `asyncio` to concurrently output and capture the subprocess logs. If an event loop is already running, `run` will return an awaitable coroutine. Otherwise, it will call `asyncio.run` for you. Practically, this means you can just treat `run` as a coroutine if you're in an async content; if you're not, just call it synchronously.

```python
async def main():
    process = await run(["python", "--version"], tee=True, text=True, capture_output=True)
    # ==> Python 3.11.2
    print(process.stdout)
    # ==> Python 3.11.2

asyncio.run(main())
```

## License

MIT License
Copyright (c) 2023 Elias Gabriel
