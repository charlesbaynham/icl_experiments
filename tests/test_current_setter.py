import pytest

from device_db_config.configuration import VoltageControlledCurrentSupply
from repository.lib.fragments.current_supply_setter import SetAnalogCurrentSupplies


def test_current_to_volts_conversion_host(fragment_factory):
    current_config_a = VoltageControlledCurrentSupply("zotino_plant_room", 0, -2.0)
    current_config_b = VoltageControlledCurrentSupply("zotino_plant_room", 0, -10.0)

    current_configs = [
        current_config_a,
        current_config_b,
    ]

    exp: SetAnalogCurrentSupplies = fragment_factory(
        SetAnalogCurrentSupplies, current_configs=current_configs
    )

    voltages = [0.0] * 2
    exp._currents_to_volts([1.0, 1.0], voltages)
    assert voltages == [-0.5, -0.1]


def test_current_to_volts_conversion_wrong_number_of_currents(fragment_factory):

    current_config_a = VoltageControlledCurrentSupply("zotino_plant_room", 0, -2.0)
    current_config_b = VoltageControlledCurrentSupply("zotino_plant_room", 0, -10.0)

    current_configs = [
        current_config_a,
        current_config_b,
    ]

    exp: SetAnalogCurrentSupplies = fragment_factory(
        SetAnalogCurrentSupplies, current_configs=current_configs
    )

    voltages = [0.0] * 3
    with pytest.raises(ValueError):
        exp._currents_to_volts([1.0, 1.0], voltages)


def test_current_to_volts_conversion_core_compiles(fragment_factory):

    current_config_a = VoltageControlledCurrentSupply("zotino_plant_room", 0, -2.0)
    current_config_b = VoltageControlledCurrentSupply("zotino_plant_room", 0, -10.0)

    current_configs = [
        current_config_a,
        current_config_b,
    ]

    def precompile(self):
        precompiled_convert = self.core.precompile(
            self._currents_to_volts, [1.0, 1.0], [0.0, 0.0]
        )

        print("Experiment was precompiled:")
        print(precompiled_convert)

    setattr(SetAnalogCurrentSupplies, "precompile", precompile)

    exp: SetAnalogCurrentSupplies = fragment_factory(
        SetAnalogCurrentSupplies, current_configs=current_configs
    )

    exp.host_setup()

    exp.precompile()
