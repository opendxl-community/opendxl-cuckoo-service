# Shout out to Chris Smith, whose epo-service/epo-client libraries created an
# excellent framework for Sofware Wrappers.
# By Jesse Netz
# -*- coding: utf-8 -*-
################################################################################
################################################################################

from __future__ import absolute_import

from .service import CuckooService

__version__ = "1.2.3"


def get_version():
    """
    Returns the version of the Cuckoo service

    :return: The version of the Cuckoo service
    """
    return __version__

