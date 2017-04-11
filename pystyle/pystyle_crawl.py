#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import re
import sys
import shutil
import logging
import argparse
import subprocess
from urllib.parse import urlparse

import feedparser
import requests

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
        '--repository',
        help='Crawl a specific repository',
        metavar='https://github.com/julienpalard/pystyle/',
        type=str)
    parser.add_argument(
        '--pypi-project',
        help='Fetch a single PyPI project')
    parser.add_argument(
        'git_store',
        metavar='./git-clones/',
        help='Directory to store git clones.')
    return parser.parse_args(args)


def setup_logging(loglevel):
    """Setup basic logging

    Args:
      loglevel (int): minimum loglevel for emitting messages
    """
    logformat = "[%(asctime)s] %(levelname)s:%(name)s:%(message)s"
    logging.basicConfig(level=loglevel, stream=sys.stdout,
                        format=logformat, datefmt="%Y-%m-%d %H:%M:%S")


def is_github_project_url(url):
    """Returns True if the URL looks like a github project URL. False
    otherwise.
    """
    return re.match('https://github.com/[^/]*/[^/]*/?', url) is not None


def git_clone_or_update(clone_url, clone_path):
    if os.path.isdir(clone_path):
        _logger.debug("Git pull on: %s", clone_path)
        try:
            subprocess.run(['git', '-C', clone_path, 'pull', '--ff-only'],
                           check=True)
            return
        except subprocess.CalledProcessError:
            shutil.rmtree(clone_path)
    os.makedirs(clone_path)
    _logger.debug("Git clone: %s", clone_url)
    try:
        subprocess.run(['git', 'clone', '--depth', '1', clone_url, clone_path],
                       stdin=subprocess.DEVNULL, check=True)
    except subprocess.CalledProcessError:
        _logger.error("Clone failed for repo %s", clone_url)
        shutil.rmtree(clone_path, ignore_errors=True)


def clone_repository(clone_path, github_project_url):
    """Clone or update the given github project by URL.
    """
    github_project_url = github_project_url.rstrip('/')
    clone_url = github_project_url + '.git'
    git_clone_or_update(clone_url, clone_path)


def pypi_url_to_github_url(pypi_package_url):
    """By querying the PyPI API, try to find the github page of a pypi project.
    """
    project_response = requests.get(pypi_package_url + '/json')
    project_json = project_response.json()
    try:
        if is_github_project_url(project_json['home_page']):
            return project_json['home_page']
    except KeyError:
        project_text = project_response.text
        found_github = re.findall(
            'https://github.com/[a-zA-Z0-9_-]+/[a-zA-Z0-9_-]+/?',
            project_text)
        if found_github:
            return sorted(found_github, key=len)[0]


def crawl_pypi_project(git_store, pypi_package_url):
    """Crawl a PyPI package by trying to find it upstream git and cloning
    it.
    """
    _logger.info("Crawling %s", pypi_package_url)
    github_project_url = pypi_url_to_github_url(pypi_package_url)
    if github_project_url:
        clone_path = os.path.join(
            git_store,
            urlparse(github_project_url).path[1:])
        clone_repository(clone_path, github_project_url)



def crawl_pypi():
    """Crawl PyPI via RSS, return a list of pypi projects.
    """
    updates = feedparser.parse(
        'https://pypi.python.org/pypi?%3Aaction=rss')
    packages = feedparser.parse(
        'https://pypi.python.org/pypi?%3Aaction=packages_rss')
    return set(package['link'] for package in
               updates['items'] + packages['items'])


def main(args):
    """Main entry point allowing external calls

    Args:
      args ([str]): command line parameter list
    """
    args = parse_args(args)
    os.environ['GIT_ASKPASS'] = '/bin/true'
    setup_logging(args.loglevel)
    _logger.debug("Starting...")
    if args.repository:
        clone_repository(args.git_store, args.repository)
    elif args.pypi_project:
        crawl_pypi_project(args.git_store, args.pypi_project)
    else:
        pypi_projects = crawl_pypi()
        for pypi_project in pypi_projects:
            crawl_pypi_project(args.git_store, pypi_project)
    _logger.debug("Script ends here")


def run():
    """Entry point for console_scripts
    """
    main(sys.argv[1:])


if __name__ == "__main__":
    run()
