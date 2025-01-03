# Brewin Interpreter Test Cases

This repository contains:
- each version of the interpreter is in a `v*` folder
- the `tests` subdirectory contains source (`.br`) files for programs that should interpret and run without errors
- the `fails` subdirectory contains source (`.br`) files for programs that should interpret successfully, but error

## Usage

### Setup

1. **Make sure you're using Python 3.11**
2. Clone this repo and navigate to its root directory

Now, you're ready to test locally.

### Testing Locally

To test locally, you will additionally need a **working implementation** of the project version you're trying to test (your interpreter file and any additional files that you created that it relies on)

Place this in the same directory as `tester.py`. Then, to test Brewin-Interpreter-3 for example,

```sh
python3.11 tester.py 3 > output.txt
```

```sh
Running 6 tests...
Running v1/tests/test_add1.br...  PASSED
Running v1/tests/test_print_const.br...  PASSED
Running v1/tests/test_print_var.br...  PASSED
Running v1/fails/test_bad_var1.br...  PASSED
Running v1/fails/test_invalid_operands1.br...  PASSED
Running v1/fails/test_unknown_func_call.br...  PASSED
6/6 tests passed.
Total Score:    100.00%
```

Note: 
- the command records the terminal output directly into `output.txt`.
- it also automatically outputs the results of the terminal output to `results.json`.
