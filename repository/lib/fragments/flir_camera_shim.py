from aravis import Camera as _Camera


class Camera(_Camera):
    def __init__(self, device_mgr, name, loglevel):
        super().__init__(name, loglevel)
