# from ndscan.experiment import ExpFragment
# from artiq.experiment import EnvExperiment
# class MyExpFragment(ExpFragment):
#     def build_fragment(self):
#         # ...
#         self.setattr_result("foo")
#     def run_once(self):
#         # ...
# class MyEnvExperiment(EnvExperiment):
#     def run(self):
#         results = create_and_run_once(self, MyExpFragment)
#         print(results["foo"])
# MyExpFragmentScan = make_fragment_scan_exp(MyExpFragment)
