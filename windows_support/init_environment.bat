@REM Set up a minimal python environment on Windows only for running the dashboard
@REM Python must already be installed and in PATH and at least version 3.10

python -c "import sys; assert sys.version_info >= (3,10), 'Python 3.10 or higher is required'" || (
    echo Python 3.10 or higher is required
    exit /b 1
)

python -m venv .venv
.venv\Scripts\python -m pip install --no-deps --ignore-requires-python -r windows_support\requirements.txt
