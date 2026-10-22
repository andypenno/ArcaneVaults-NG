# Tests

Run `python3 tests/run.py --suite unit` from the repository root with Python 3. Reports and logs go under ignored `results/`; existing report directories are rejected.

The shared inventory boundary types support production-code fixtures. Policy unit tests reject excessive work, timing regressions and incomplete scenario matrices. These checks do not execute Skyrim.
