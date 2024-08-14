from setuptools import setup, find_packages

setup(
    name="AkVHALInjector",
    url="https://github.com/Audiokinetic-Automotive/AkVHALInjector",
    version="0.0.1",
    packages=find_packages(),
    description="A Python interface to inject VHAL properties using adb.",
    license="Apache License 2.0",
)