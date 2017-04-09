#!/usr/bin/env python
# -*- coding: utf-8 -*-

import pytest
from python_style_stats.skeleton import fib

__author__ = "Julien Palard"
__copyright__ = "Julien Palard"
__license__ = "mit"


def test_fib():
    assert fib(1) == 1
    assert fib(2) == 1
    assert fib(7) == 13
    with pytest.raises(AssertionError):
        fib(-10)
