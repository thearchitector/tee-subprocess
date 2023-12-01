# Changelog

All notable changes to this project will be documented in this file.

## [1.0.0] - 2023-11-29

### Added

- The ability to drop-in replace `subprocess.run` anywhere in your project with a `tee=True` alternative.
- Support for asynchronous environments.
- Support for arbitrary tee locations (stdout, file objects, etc.).
- Support for list-style direct execution in addition to string-style shell execution.
