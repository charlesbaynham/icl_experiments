from pathlib import Path


def test_pydantic():
    # There's something broken about pydantic - try running an artiq stack to
    # see it. Not sure what yet, but this test should test it so that we can
    # then fix it. Until then, it serves as a reminded that this repo does not
    # yet work!
    raise NotImplementedError


def test_import_double_examine(device_mgr, dataset_mgr, mocker):
    mocker.patch("artiq.master.worker_impl.ipc")
    from artiq.master.worker_impl import examine

    test_file_a = Path("repository/lib/constants.py").resolve()
    test_file_b = Path("repository/lib/fragments/flir_camera.py").resolve()

    a = examine(device_mgr, dataset_mgr, str(test_file_a))
    b = examine(device_mgr, dataset_mgr, str(test_file_b))

    pass
