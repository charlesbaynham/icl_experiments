from artiq.experiment import EnvExperiment
import numpy as np
from scipy.stats import multivariate_normal
from time import sleep
import random
from artiq.language import NumberValue


class MakeImages(EnvExperiment):

    def build(self):
        self.setattr_device("ccb")

        import numpy as np

        # Parameters for the 2D Gaussian

        size = 100  # Size of the array (100x100)

        # Create a 2D grid of coordinates (x, y)
        x = np.linspace(-3, 3, size)
        y = np.linspace(-3, 3, size)
        self.X, self.Y = np.meshgrid(x, y)

        self.setattr_argument(
            "n_images",
            NumberValue(default=10, precision=0, scale=1, step=1, type="int"),
        )
        self.n_images: int

        # # Create the 2D Gaussian array
        # self.gaussian_2d = (1 / (2 * np.pi * sigma**2)) * np.exp(
        #     -((x - mean) ** 2 + (y - mean) ** 2) / (2 * sigma**2)
        # )

    def run(self):
        cmd_1 = "${python} 'repository/lib/applets/simple_img_applet.py' test_image"
        cmd_2 = "${python} 'repository/lib/applets/img_applet_slices.py' test_image"
        self.ccb.issue("create_applet", "simple", cmd_1)
        self.ccb.issue("create_applet", "slices", cmd_2)
        noise_mean = 0  # Mean of the noise
        noise_std = 0.01  # Standard deviation of the noise
        for i in range(self.n_images):

            mu_x = 1 - 2 * random.random()
            mu_y = 1 - 2 * random.random()
            sigma_x = random.random()
            sigma_y = random.random()
            rv = multivariate_normal([mu_x, mu_y], [[sigma_x, 0], [0, sigma_y]])
            pos = np.empty(self.X.shape + (2,))
            pos[:, :, 0] = self.X
            pos[:, :, 1] = self.Y
            gaussian_2d = rv.pdf(pos)
            noise = np.random.normal(noise_mean, noise_std, gaussian_2d.shape)
            img = gaussian_2d + noise
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
