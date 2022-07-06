from generic_scpi_driver import get_controller_func

from .driver import TTIPowerSupply

main = get_controller_func("TTIPowerSupply", 3301, TTIPowerSupply)


if __name__ == "__main__":
    main()
