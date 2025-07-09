from generic_scpi_driver import get_controller_func

from repository.lib.devices.clock_glitch_filter import ClockGlitchFilter

main = get_controller_func("RelockerDriver", 8888, ClockGlitchFilter)


if __name__ == "__main__":
    main()
