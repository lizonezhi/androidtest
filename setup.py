#!/usr/bin/env python

from distutils.core import setup

setup(
    name='androidtest',
    version='0.0.5',
    packages=['androidtest'],
    url='https://github.com/lizongzi/androidtest',
    license='1.0',
    author='lizongzhi',
    author_email='136313283@qq.com',
    description='基于adb的安卓自动化操作',
    install_requires=[
        'uiautomator2',
        'requests>=2.7.0',
        'six',
        'humanize',
        'opencv-contrib-python==3.3.0.10',
        'docopt',
        'progress>=1.3',
        'retry>=0.9.2',
        'whichcraft',
        'pillow',
        'numpy',
    ]
)
