=====
Usage
=====

``pyf.aggregator`` is meant to be used with the following command-line tool

.. code:: bash

    $ pyfaggregator --filter some.package --limit 10

This command triggers the aggregation of up to ``10`` result items according to the given filter query ``some.package``.
These items will be added to ElasticSearch service (running on default configuration, i.e. ``localhost:9200``).

For more details on the pyfaggregator command, please refer to the ``--help`` option:

.. code:: bash

    $ pyfaggregator --help
    usage: pyfaggregator [-h] [-f] [-i] [-s [SINCEFILE]] [-t [TOKEN]] [--filter [FILTER]] [--limit [LIMIT]]

    Fetch information about pinned versions and its overrides in simple and complex/cascaded buildouts.

    optional arguments:
      -h, --help            show this help message and exit
      -f, --first           First fetch from PyPI
      -i, --incremental     Incremental fetch from PyPI
      -s [SINCEFILE], --sincefile [SINCEFILE]
                            File with timestamp of last run
      -t [TOKEN], --token [TOKEN]
                            Github OAuth token
      --filter [FILTER]
      --limit [LIMIT]

Using GitHub API
----------------

For every package with an associated repository on GitHub, there will be made the attempt to retrieve interesting
metadata (e.g. number of stars, number of watchers, last update etc.). Due to very strict rate limits for accessing the
GitHub API (at the time of writing: 60 requests / hour), there is the option to add your GitHub OAuth token to exploit
the  higher rate limit for registered users (at the time of writing: 5000 requests / hour).

To do so, `create your token <https://github.com/settings/tokens>`_ and pass it with the ``--token`` option.

When the rate limit is being hit, the aggregator will wait until the Github API can be accessed again.