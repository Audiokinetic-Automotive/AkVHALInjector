from distutils.core import setup

setup(
    name='AkVHALInjector',
    version='0.0.1',
    description='A Python interface to inject VHAL properties using adb.',
    packages=['AkVHALInjector', 'AkVHALInjector.adb'],
)