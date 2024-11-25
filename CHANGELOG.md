# Changelog

All notable changes to this project will be documented in this file.

## [1.2.0] - 2024-11-25

### Added

- Support the `timeout` argument to restrict the runtime of subprocesses.
- Support for text decoding using non-UTF8 encodings and non-strict error handling.

## [1.1.0] - 2024-09-19

### Added

- Support for `os.PathLike` arguments when not using shell mode, for parity with the standard library.
- Better static typing to disallow combining conflicting arguments (ie. `text=True, stdout=BytesIO`).

## [1.0.0] - 2023-11-29

### Added

- The ability to drop-in replace `subprocess.run` anywhere in your project with a `tee=True` alternative.
- Support for asynchronous environments.
- Support for arbitrary tee locations (stdout, file objects, etc.).
- Support for list-style direct execution in addition to string-style shell execution.
