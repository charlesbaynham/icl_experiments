@REM Launch an ARTIQ dashboard on Windows
@REM You must have manually set up a python environment and have kept it up to date


.venv\Scripts\python -m artiq.frontend.artiq_dashboard -v -p ndscan.dashboard_plugin -s 10.137.1.252
