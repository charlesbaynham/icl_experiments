@REM Launch an ARTIQ dashboard on Windows
@REM You must have manually set up a poetry environment and have kept it up to date using "poetry install"

set WAND_CONFIG_PATH=C:\working_dirs\icl_experiments\scripts\icl_aion_gui_config.pyon
poetry run wand_gui -n icl_aion
