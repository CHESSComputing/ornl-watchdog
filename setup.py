#!/usr/bin/env python
"""
Standard python setup.py file
to build     : python setup.py build
to install   : python setup.py install --prefix=<some dir>
to clean     : python setup.py clean
to build doc : python setup.py doc
to run tests : python setup.py test
"""

import os
import setuptools

# [set version]
version = 'PACKAGE_VERSION'
# [version set]

with open("README.md", "r") as fh:
    long_description = fh.read()

setuptools.setup(
    name="ornl-watchdog",
    version=version,
    author="Keara Soloway",
    author_email="",
    description="Watchdog application for 2026-2 ORNL beamtime",
    long_description=long_description,
    long_description_content_type="text/markdown",
    url="https://github.com/CHESSComputing/ornl-watchdog",
    packages=[
        'app',
    ],
    package_dir={
        'app': 'app',
    },
    entry_points={
        'console_scripts': ['edd-watchdog = app.main:run']
    },
    classifiers=[
        "Programming Language :: Python :: 3",
        "License :: OSI Approved :: MIT License",
        "Operating System :: OS Independent",
    ],
    python_requires='>=3.10',
    install_requires=[
        'chess-pyspec',
        'watchdog',
        'pyyaml',
    ],
)
