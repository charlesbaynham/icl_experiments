from artiq.experiment import EnvExperiment
import numpy as np
from time import sleep


class MakeImages(EnvExperiment):

    def build(self):
        self.setattr_device("ccb")

        import numpy as np

        # Parameters for the 2D Gaussian
        mean = 0  # Mean of the Gaussian
        sigma = 1  # Standard deviation of the Gaussian
        size = 100  # Size of the array (100x100)

        # Create a 2D grid of coordinates (x, y)
        x = np.linspace(-3, 3, size)
        y = np.linspace(-3, 3, size)
        x, y = np.meshgrid(x, y)

        # Create the 2D Gaussian array
        self.gaussian_2d = (1 / (2 * np.pi * sigma**2)) * np.exp(
            -((x - mean) ** 2 + (y - mean) ** 2) / (2 * sigma**2)
        )

    def run(self):
        cmd_1 = "${python} 'repository/lib/applets/simple_img_applet.py' test_image"
        cmd_2 = "${python} 'repository/lib/applets/img_applet_slices.py' test_image"
        self.ccb.issue("create_applet", "simple", cmd_1)
        self.ccb.issue("create_applet", "slices", cmd_2)
        noise_mean = 0  # Mean of the noise
        noise_std = 0.01  # Standard deviation of the noise
        for i in range(10):

            noise = np.random.normal(noise_mean, noise_std, self.gaussian_2d.shape)
            img = self.gaussian_2d + noise
            self.set_dataset(
                "test_image", img, broadcast=True, persist=False, archive=False
            )
            sleep(0.5)

    def ones(self):
        img = np.array([[1, 0] * 100, [0, 1] * 100])
        self.set_dataset("ones", img, broadcast=True, persist=False, archive=False)
        sleep(0.5)
        img = np.array([[0, 1] * 100, [1, 0] * 100])
        self.set_dataset("ones", img, broadcast=True, persist=False, archive=False)
        sleep(0.5)
