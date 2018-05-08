=======
pystyle
=======

Extract style informations about Python projects.


Description
===========

- ``pystyle-crawl`` crawls pypi (via RSS) and github.
- ``pystyle-update`` updates json files to be commited in https://github.com/JulienPalard/pystyle-data.

So a typical run is::

    $ pystyle-crawl ./git-clones/
    $ pystyle-update ./git-clones/ ../pystyle-data/github.com/
