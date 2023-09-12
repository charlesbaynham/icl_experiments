from unittest.mock import MagicMock

from repository.lib.fragments.ad9910_ramper import AD9910Ramper


def test_correct_rate():
    desired_rate = 90e6
    clock_rate = 1e9

    freq_step_mu, delay_mu = AD9910Ramper.calculate_step_and_delay(
        desired_rate, clock_rate
    )

    assert freq_step_mu / delay_mu / clock_rate**2 == desired_rate
