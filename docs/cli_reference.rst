.. highlight:: shell

=============
CLI Reference
=============

The pyf.aggregator package provides three command-line tools for aggregating Python package metadata from PyPI and enriching it with GitHub data.

pyfaggregator
-------------

Fetches package information from PyPI and indexes it into Typesense.

Usage
~~~~~

.. code-block:: console

    $ pyfaggregator [options]

Options
~~~~~~~

``-f``, ``--first``
    First/full fetch from PyPI (fetches all packages)

``-i``, ``--incremental``
    Incremental fetch (only packages updated since last run)

``-s``, ``--sincefile``
    File to store timestamp of last run (default: ``.pyaggregator.since``)

``-l``, ``--limit``
    Limit the number of packages to process

``-fn``, ``--filter-name``
    Filter packages by name (substring match)

``-ft``, ``--filter-troove``
    Filter by trove classifier (can be used multiple times)

``-p``, ``--profile``
    Use a predefined profile (loads classifiers and sets collection name)

``-t``, ``--target``
    Target Typesense collection name (auto-set from profile if not specified)

Examples
~~~~~~~~

Full fetch of all Plone packages using manual classifiers:

.. code-block:: console

    $ pyfaggregator -f -ft "Framework :: Plone" -t packages1

Full fetch using the Plone profile (recommended):

.. code-block:: console

    $ pyfaggregator -f -p plone

Full fetch of Django packages using the Django profile:

.. code-block:: console

    $ pyfaggregator -f -p django

Full fetch of Flask packages using the Flask profile:

.. code-block:: console

    $ pyfaggregator -f -p flask

Incremental update for Django profile:

.. code-block:: console

    $ pyfaggregator -i -p django

Fetch with limit for testing:

.. code-block:: console

    $ pyfaggregator -f -p plone -l 100

Profile with custom collection name (overrides auto-naming):

.. code-block:: console

    $ pyfaggregator -f -p django -t django-test


pyfgithub
---------

Enriches indexed packages with data from GitHub (stars, watchers, issues, etc.).

Usage
~~~~~

.. code-block:: console

    $ pyfgithub -t <collection_name>

Options
~~~~~~~

``-p``, ``--profile``
    Use a profile (auto-sets target collection name)

``-t``, ``--target``
    Target Typesense collection name (auto-set from profile if not specified)

Examples
~~~~~~~~

Enrich using profile (recommended):

.. code-block:: console

    $ pyfgithub -p plone

Enrich Django packages:

.. code-block:: console

    $ pyfgithub -p django

Enrich Flask packages:

.. code-block:: console

    $ pyfgithub -p flask

Enrich a specific collection (manual):

.. code-block:: console

    $ pyfgithub -t packages1

GitHub Fields Added
~~~~~~~~~~~~~~~~~~~

This command adds the following fields to each package (if a GitHub repository is found):

- ``github_stars`` - Number of stargazers
- ``github_watchers`` - Number of watchers
- ``github_updated`` - Last update timestamp
- ``github_open_issues`` - Number of open issues
- ``github_url`` - URL to the GitHub repository

.. note::
   GitHub enrichment cache is shared across all profiles to minimize API calls.


pyfupdater
----------

Utility for managing Typesense collections, aliases, and API keys.

Usage
~~~~~

.. code-block:: console

    $ pyfupdater [options]

Options
~~~~~~~

``-ls``, ``--list-collections``
    List all collections with full details

``-lsn``, ``--list-collection-names``
    List collection names only

``-lsa``, ``--list-aliases``
    List all collection aliases

``-lssoa``, ``--list-search-only-apikeys``
    List all search-only API keys

``--migrate``
    Migrate data from source to target collection

``--add-alias``
    Add a collection alias

``--add-search-only-apikey``
    Create a search-only API key

``-p``, ``--profile``
    Use a profile (auto-sets target collection name)

``-s``, ``--source``
    Source collection name (for migrate/alias)

``-t``, ``--target``
    Target collection name (auto-set from profile if not specified)

``-key``, ``--key``
    Custom API key value (optional, auto-generated if not provided)

Examples
~~~~~~~~

List all collections:

.. code-block:: console

    $ pyfupdater -ls

List collection names only:

.. code-block:: console

    $ pyfupdater -lsn

List aliases:

.. code-block:: console

    $ pyfupdater -lsa

Add an alias (packages -> packages1):

.. code-block:: console

    $ pyfupdater --add-alias -s packages -t packages1

Migrate data between collections:

.. code-block:: console

    $ pyfupdater --migrate -s packages1 -t packages2

Create a search-only API key:

.. code-block:: console

    $ pyfupdater --add-search-only-apikey -t packages

Create a search-only API key with custom value:

.. code-block:: console

    $ pyfupdater --add-search-only-apikey -t packages -key your_custom_key

Profile-aware operations:

.. code-block:: console

    $ pyfupdater --add-search-only-apikey -p django
    $ pyfupdater --add-alias -s django -t django-v2
