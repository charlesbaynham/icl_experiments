import pytest


def test_current_to_volts_conversion_host(fragment_factory):
    from repository.lib.fragments.current_supply_setter import SetAnalogCurrentSupplies
    from device_db_config.configuration import VoltageControlledCurrentSupply

    current_config_a = VoltageControlledCurrentSupply("zotino_plant_room", 0, -2.0)
    current_config_b = VoltageControlledCurrentSupply("zotino_plant_room", 0, -10.0)

    current_configs = [
        current_config_a,
        current_config_b,
    ]

    exp: SetAnalogCurrentSupplies = fragment_factory(
        SetAnalogCurrentSupplies, current_configs=current_configs
    )

    assert exp._currents_to_volts([1.0, 1.0]) == [-0.5, -0.1]


def test_current_to_volts_conversion_wrong_number_of_currents(fragment_factory):
    from repository.lib.fragments.current_supply_setter import SetAnalogCurrentSupplies
    from device_db_config.configuration import VoltageControlledCurrentSupply

    current_config_a = VoltageControlledCurrentSupply("zotino_plant_room", 0, -2.0)
    current_config_b = VoltageControlledCurrentSupply("zotino_plant_room", 0, -10.0)

    current_configs = [
        current_config_a,
        current_config_b,
    ]

    exp: SetAnalogCurrentSupplies = fragment_factory(
        SetAnalogCurrentSupplies, current_configs=current_configs
    )

    with pytest.raises(ValueError):
        exp._currents_to_volts([1.0, 1.0, 1.0])


def test_current_to_volts_conversion_core_compiles(fragment_factory):
    from repository.lib.fragments.current_supply_setter import SetAnalogCurrentSupplies
    from device_db_config.configuration import VoltageControlledCurrentSupply

    current_config_a = VoltageControlledCurrentSupply("zotino_plant_room", 0, -2.0)
    current_config_b = VoltageControlledCurrentSupply("zotino_plant_room", 0, -10.0)

    current_configs = [
        current_config_a,
        current_config_b,
    ]

    def precompile(self):
        precompiled_convert = self.core.precompile(self._currents_to_volts, [1.0, 1.0])

        print("Experiment was precompiled:")
        print(precompiled_convert)

    setattr(SetAnalogCurrentSupplies, "precompile", precompile)

    exp: SetAnalogCurrentSupplies = fragment_factory(
        SetAnalogCurrentSupplies, current_configs=current_configs
    )

    exp.host_setup()

    exp.precompile()
