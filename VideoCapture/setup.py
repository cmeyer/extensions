# -*- coding: utf-8 -*-

"""
To upload to PyPI, PyPI test, or a local server:
python setup.py bdist_wheel upload -r <server_identifier>
"""

import setuptools
import os

setuptools.setup(
    name="nionswift-video-capture",
    version="0.1.0",
    author="Nion Software",
    author_email="swift@nion.com",
    description="Capture video from built-in camera using OpenCV.",
    packages=["nionswift_plugin.nionswift_video_capture"],
    install_requires=[],
    license='GPLv3',
    include_package_data=True,
    python_requires='~=3.5',
)
