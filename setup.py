import os
from setuptools import setup, find_packages

requires = []

with open(os.path.join(os.path.dirname(__file__), 'requirements.txt'), 'r') as f:
    for resource in f.readlines():
        if not resource.startswith('git+'):
            requires.append(resource.strip())
        else:
            res = resource.strip()
            egg = res.split("#egg=")[1]
            requires.append("@".join([egg, res]))

setup(
    name='prozorro_chronograph',
    version='1.0.2',
    description='',
    packages=find_packages('src'),
    package_dir={"": "src"},
    install_requires=requires,
)
