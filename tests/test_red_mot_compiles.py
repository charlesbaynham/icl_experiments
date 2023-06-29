from repository.measure_red_mot import MeasureRedMOTFrag


def test_red_mot(fragment_factory):
    def precompile(self):
        precompiled = self.core.precompile(self.run_once)
        print("Experiment was precompiled:")
        print(precompiled)

    setattr(MeasureRedMOTFrag, "precompile", precompile)

    exp = fragment_factory(MeasureRedMOTFrag)

    exp.precompile()
