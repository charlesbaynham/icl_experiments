from toptica.lasersdk.dlcpro.v1_9_0 import DLCpro
from toptica.lasersdk.dlcpro.v1_9_0 import NetworkConnection


class TopticaDLCPro:
    """
    Thin wrapper for the Toptica SDK, to match the format that ARTIQ expects for initialisation
    """

    def __init__(self, *args, ip, laser, simulation=False):

        if simulation:
            raise ValueError("Simulation mode is not supported for the Toptica SDK")

        self.dlcpro = DLCpro(NetworkConnection(ip))

        assert laser in ["laser1", "laser2"], ValueError(
            f"Laser must be laser1 or laser2: got {laser}"
        )
        self.laser = laser

    def get_dlcpro(self) -> DLCpro:
        """Access the raw DLC Pro driver object

        Users should prefer to use the get_laser() function, so the details of
        which laser you're accessing can be stored in device_db"""
        return self.dlcpro

    def get_laser(self):
        """Access the laser driver

        Returns either self.get_dlcpro().laser1 or self.get_dlcpro().laser2
        depending on which is stored in device_db
        """
        return getattr(self.dlcpro, self.laser)

    # Pass on __enter__ and __exit__ so that users can use `with TopticaDLCPro`
    # to start a network connection
    def __enter__(self, *args, **kwargs):
        return self.dlcpro.__enter__(*args, **kwargs)

    def __exit__(self, *args, **kwargs):
        return self.dlcpro.__exit__(*args, **kwargs)
