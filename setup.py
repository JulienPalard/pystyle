#!/usr/bin/env python
"""setup.py for pystyle.
"""

from setuptools import setup

with open('README.rst') as readme_file:
    readme = readme_file.read()

setup(
    name='pystyle',
    version='0.0.1',
    description="Extract style informations about Python projects.",
    long_description=readme,
    author="Julien Palard",
    author_email='julien@palard.fr',
    url='https://github.com/JulienPalard/pystyle/',
    packages=[
        'pystyle',
    ],
    package_dir = {'': 'src'},
    entry_points={
        'console_scripts': [
            'pystyle-crawl=pystyle.pystyle_crawl:main',
            'pystyle-update=pystyle.pystyle_update:main',
        ]
    },
    install_requires=[
        'feedparser==5.2.1',
        'licensename==0.4.2',
        'requests==2.18.4',
        'requirements-detector==0.5.2',
        'beautifulsoup4==4.6.0',
        'html5lib==1.0.1',
    ],
    extras_require={
        'dev': [
            'flake8==3.5.0',
            'mypy==0.600',
            'pylint==1.8.4',
        ]
    },
    license="MIT license",
    classifiers=[
        'Development Status :: 2 - Pre-Alpha',
        'Intended Audience :: Developers',
        'License :: OSI Approved :: MIT License',
        'Natural Language :: English',
        'Programming Language :: Python :: 3',
        'Programming Language :: Python :: 3.5',
        'Programming Language :: Python :: 3.6',
        'Programming Language :: Python :: 3.7',
    ]
)
