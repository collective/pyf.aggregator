Python Package Filter Aggregator
================================

The Python Package Filter Aggregator (``pyf.aggregator``) aggregates the meta
information of all Python packages in the PyPI.

Requirements
------------

We need a running `Typesense <https://typesense.org/docs/guide/install-typesense.html>`_ search engine.


Install
-------

Git clone the package somewhere and change into the pyf.aggregator repository directory.
Create a virtualenv and install the package

.. code-block:: shell

    $ python -m venv venv
    $ ./venv/bin/pip install -e .

For the connection to typesense we need to define some environment variables in a .env file.

.. code-block:: ini

    TYPESENSE_HOST=localhost
    TYPESENSE_PORT=8108
    TYPESENSE_PROTOCOL=http
    TYPESENSE_API_KEY=<your_secret_typesense_apikey>
    TYPESENSE_TIMEOUT=120
    GITHUB_COOLOFFTIME=2
    GITHUB_TOKEN=<your_secret_github_apikey>


Quickstart
----------

To aggregate Plone content from PyPi run the following command:

.. code-block:: shell

    $ ./venv/bin/pyfaggregator -ft "Framework :: Plone" -i -t packages1

The target Typesense collection is given here with ``-t``.

To enrich the data with data from GitHub, run the following command:

.. code-block:: shell

    $ ./venv/bin/pyfgithub -t packages1

.. note::

    We need a typesense alias called "packages" pointing to the most recent packages collection: 'packages1'.


Add a typesense alias
.....................

.. code-block:: shell

    $ ./venv/bin/pyfupdater --add-alias -s packages -t packages1

To list existing aliases, use the following command:

.. code-block:: shell

    $ ./venv/bin/pyfupdater -lsa
    {'aliases': [{'collection_name': 'packages1', 'name': 'packages'}]}


Create a search only api key
............................

A search only api key is used by the client to search for Plone add-on's.
It should be limited to a collection, in our case the collection alias "packages".

.. code-block:: shell

    $ ./venv/bin/pyfupdater --add-search-only-apikey -t packages
    res_key: {'actions': ['*'], 'collections': [''], 'description': 'Search-only key.', 'expires_at': 64723363199, 'id': 4, 'value': 'sHlV6xOtgsg0AaegA62eniyU5aALn1Os'}

or if you want to define the key your self, you can provide one:

.. code-block:: shell

    $ ./venv/bin/pyfupdater --add-search-only-apikey -t packages -key sHlV6xOtgsg0AaegA62eniyU5aAsn1Os

The pyfupdater command can also be used to migrate a Typesense collection to another, when you make bigger changes to the schema.


For detailed installation instructions, read the `docs
<https://pyfaggregator.readthedocs.io/en/latest/installation.html>`_.


License
-------

The code is open-source and licensed under the Apache License 2.0.

Credits
-------

* `@jensens <https://github.com/jensens>`_
* `@veit <https://github.com/veit>`_
* `@guziel <https://github.com/guziel>`_
* `@pgrunewald <https://github.com/pgrunewald>`_
* `@MrTango <https://github.com/MrTango>`_
* `@pypa <https://github.com/pypa>`_

