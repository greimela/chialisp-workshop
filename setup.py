#!/usr/bin/env python

from __future__ import annotations

from setuptools import find_packages, setup

with open("README.md", "rt") as fh:
    long_description = fh.read()

dependencies = [
    "chia-dev-tools",
    "packaging",
    "pytest",
    "pytest-asyncio",
    "pytimeparse",
    "anyio",
    "chia-blockchain==2.1.1",
]

dev_dependencies = [
    "black==23.7.0",
    "types-aiofiles",
    "types-click",
    "types-cryptography",
    "types-pkg_resources",
    "types-pyyaml",
    "types-setuptools",
    "isort",
    "pre-commit",
    "pylint",
]

setup(
    name="chialisp_workshop",
    packages=find_packages(exclude=("tests",)),
    author="Andreas Greimel",
    entry_points={
        "console_scripts": ["chiwo = workshop.cli:main"],
    },
    package_data={
        "": ["*.clvm", "*.clvm.hex", "*.clib", "*.clsp", "*.clsp.hex"],
    },
    author_email="andreas@mintgarden.io",
    setup_requires=["setuptools_scm"],
    install_requires=dependencies,
    url="https://github.com/greimela",
    license="https://opensource.org/licenses/Apache-2.0",
    description="Chialisp Workshop",
    long_description=long_description,
    long_description_content_type="text/markdown",
    classifiers=[
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.8",
        "Programming Language :: Python :: 3.9",
        "License :: OSI Approved :: Apache Software License",
        "Topic :: Security :: Cryptography",
    ],
    extras_require=dict(
        dev=dev_dependencies,
    ),
    project_urls={
        "Bug Reports": "https://github.com/greimela/chialisp-workshop",
        "Source": "https://github.com/greimela/chialisp-workshop",
    },
)
