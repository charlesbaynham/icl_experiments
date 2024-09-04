@REM Launch an ARTIQ dashboard on Windows
@REM You must have manually set up a poetry environment and have kept it up to date using "poetry install"

poetry run artiq_dashboard -v -p ndscan.dashboard_plugin -s 10.137.1.252
