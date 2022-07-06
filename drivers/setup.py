import io
import os
import re

import setuptools


def read(filename):
    filename = os.path.join(os.path.dirname(__file__), filename)
    text_type = type("")
    with io.open(filename, mode="r", encoding="utf-8") as fd:
        return re.sub(text_type(r":[a-z]+:`~?(.*?)`"), text_type(r"``\1``"), fd.read())


setuptools.setup(
    version="0.0.0",
    name="icldrivers",
    license="None",
    author="Charles Baynham",
    author_email="c.baynham@imperial.ac.uk",
    description="Provides a package of drivers for ARTIQ at ICL.",
    packages=setuptools.find_packages(exclude=("tests",)),
    install_requires=[],
    # classifiers=[
    #     "Development Status :: 2 - Pre-Alpha",
    #     "Programming Language :: Python",
    #     "Programming Language :: Python :: 3.7",
    #     "Programming Language :: Python :: 3.8",
    #     "Programming Language :: Python :: 3.9",
    # ],
)
