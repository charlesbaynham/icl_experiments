"""Prove the vendored qbutler (repo root) shadows the installed 0.2.

The AION artiq fork puts the repository checkout root at sys.path[0] for
worker build/examine, so `import qbutler` must resolve to the vendored
package, not site-packages. This experiment fails loudly if it doesn't.
"""

import qbutler
from artiq.experiment import EnvExperiment


class QbutlerVendorSmoke(EnvExperiment):
    def run(self):
        print("qbutler loaded from:", qbutler.__file__)
        assert "site-packages" not in qbutler.__file__, (
            "vendored qbutler did NOT shadow the installed copy: "
            + qbutler.__file__
        )
        print("VENDOR SMOKE OK")
