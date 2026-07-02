from RsInstrument import RsInstrument


class RSDevice:
    def __init__(self, *args, address: str, id_query: bool, reset: bool):
        self.device = RsInstrument(
            resource_name=address, id_query=id_query, reset=reset
        )

    def get_instrument(self):
        return self.device


# class MockRSDevice:
#     def __init__(
#         self,
#         address: str = "",
#         id_query: bool = True,
#         reset: bool = True,
#         options: str = "",
#     ):
#         self.device = RsInstrument(
#             address, options="Simulate=True" + options, id_query=id_query, reset=reset
#         )

#     def get_instrument(self):
#         return self.device
