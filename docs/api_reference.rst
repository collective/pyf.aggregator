.. highlight:: shell

=============
API Reference
=============

REST API
--------

.. note::
   The REST API is planned for a future release and is not yet implemented.
   This section will be updated when the REST API functionality is available.

Planned Features
~~~~~~~~~~~~~~~~

The upcoming REST API will provide HTTP endpoints for:

* Fetching aggregated feeds
* Managing feed subscriptions
* Configuring aggregation settings
* Retrieving feed metadata

Python API
----------

For programmatic access to pyf.aggregator functionality, please refer to the
:doc:`cli_reference` documentation which covers the command-line interface and Python
module usage.

Core Classes
~~~~~~~~~~~~

The main classes and their methods are documented in the module docstrings.
You can access them by importing the package:

.. code-block:: python

    from pyf.aggregator import Aggregator

For detailed API documentation of the Python classes, use Python's built-in help:

.. code-block:: python

    import pyf.aggregator
    help(pyf.aggregator)

Future Updates
--------------

This documentation will be expanded when the REST API feature (feature-3) is
implemented. Stay tuned for updates in future releases.
