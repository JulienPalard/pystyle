#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""Looks for git clones and compute stats about them.
"""

import os
import sys
import glob
import json
import logging
import argparse

from pystyle import __version__

__author__ = "Julien Palard"
__copyright__ = "Julien Palard"
__license__ = "mit"

_logger = logging.getLogger(__name__)


def parse_args(args):
    """Parse command line parameters

    Args:
      args ([str]): command line parameters as list of strings

    Returns:
      :obj:`argparse.Namespace`: command line parameters namespace
    """
    parser = argparse.ArgumentParser(
        description="Crawl github Python repositories and infer their style.")
    parser.add_argument(
        '--version',
        action='version',
        version='pystyle {ver}'.format(ver=__version__))
    parser.add_argument(
        '-v',
        '--verbose',
        dest="loglevel",
        help="set loglevel to INFO",
        action='store_const',
        const=logging.INFO)
    parser.add_argument(
        '-vv',
        '--very-verbose',
        dest="loglevel",
        help="set loglevel to DEBUG",
        action='store_const',
        const=logging.DEBUG)
    parser.add_argument(
        'json_store',
        help='Where to put the style files.')
    return parser.parse_args(args)


def setup_logging(loglevel):
    """Setup basic logging

    Args:
      loglevel (int): minimum loglevel for emitting messages
    """
    logformat = "[%(asctime)s] %(levelname)s:%(name)s:%(message)s"
    logging.basicConfig(level=loglevel, stream=sys.stdout,
                        format=logformat, datefmt="%Y-%m-%d %H:%M:%S")


def infer_style_of_repo(path):
    """Given a path to a git clone, compute some stats about the project.
    """
    typical_files = ('.gitignore',
                     'AUTHORS.md',
                     'AUTHORS.rst',
                     'docs/',
                     'CONTRIBUTING.md',
                     'CONTRIBUTING.rst',
                     'LICENSE',
                     'MANIFEST.in',
                     'README',
                     'README.md',
                     'README.rst',
                     'requirements.txt',
                     'setup.cfg',
                     'setup.py',
                     'tests/',
                     'test-requirements.txt',
                     'tox.ini',
                     'Makefile')
    style = {'has_file': {}, 'has_dir': {}}
    for typical_file in typical_files:
        if typical_file[-1] == '/':
            style['has_dir'][typical_file] = os.path.isdir(
                os.path.join(path, typical_file))
        else:
            style['has_file'][typical_file] = os.path.isfile(
                os.path.join(path, typical_file))
    return style


def infer_style(json_store):
    """Compute stats file from a bunch of clones.
    """
    for path in glob.glob('./git-clones/*/*/'):
        style = infer_style_of_repo(path)
        json_stat_file = os.path.join(json_store,
                                      *path.split('/')[-3:-1],
                                      'style.json')
        os.makedirs(os.path.dirname(json_stat_file), exist_ok=True)
        with open(json_stat_file, 'w') as json_stats:
            json.dump(style, json_stats, indent=4)


def main(args):
    """Main entry point allowing external calls

    Args:
      args ([str]): command line parameter list
    """
    args = parse_args(args)
    os.environ['GIT_ASKPASS'] = '/bin/true'
    setup_logging(args.loglevel)
    infer_style(args.json_store)


def run():
    """Entry point for console_scripts
    """
    main(sys.argv[1:])


if __name__ == "__main__":
    run()
