.. highlight:: shell

=========
Workflows
=========

This guide demonstrates common usage patterns and workflows for the pyf.aggregator package. Each workflow shows step-by-step commands to accomplish typical tasks.

Full Fetch Workflow
===================

The full fetch workflow is used when setting up a new collection or when you want to completely refresh the package data from PyPI.

Using Profiles (Recommended)
-----------------------------

Profiles provide a simplified way to aggregate packages by automatically loading pre-configured classifier sets.

Basic Full Fetch
~~~~~~~~~~~~~~~~

Fetch all packages for a specific framework:

.. code-block:: console

    $ pyfaggregator -f -p plone

This command:

- Fetches all packages matching the Plone profile classifiers
- Creates a Typesense collection named ``plone``
- Indexes all package metadata

Other Framework Examples
~~~~~~~~~~~~~~~~~~~~~~~~

Fetch Django packages:

.. code-block:: console

    $ pyfaggregator -f -p django

Fetch Flask packages:

.. code-block:: console

    $ pyfaggregator -f -p flask

Full Fetch with Limit (Testing)
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

When testing or developing, limit the number of packages to process:

.. code-block:: console

    $ pyfaggregator -f -p plone -l 100

This processes only the first 100 packages, useful for:

- Testing configuration changes
- Developing new features
- Quick validation

Using Manual Classifiers
-------------------------

For more control, custom classifier combinations, or when profiles aren't available:

.. code-block:: console

    $ pyfaggregator -f -ft "Framework :: Plone" -ft "Framework :: Plone :: 6.0" -t packages1

This approach:

- Requires explicit classifier specification
- Requires manual collection naming
- Provides maximum flexibility


Incremental Update Workflow
============================

The incremental update workflow fetches only packages that have been updated since the last run, making it ideal for regular maintenance and keeping data current.

Basic Incremental Update
-------------------------

Update packages using a profile:

.. code-block:: console

    $ pyfaggregator -i -p plone

This command:

- Reads the last run timestamp from ``.pyaggregator.since``
- Fetches only packages updated since that timestamp
- Updates the timestamp file after completion

.. note::
   The first time you run with ``-i``, if no timestamp file exists, it will create one and fetch all packages (equivalent to a full fetch).

Scheduled Updates
-----------------

Set up a cron job for regular updates:

.. code-block:: console

    # Update Plone packages daily at 2 AM
    0 2 * * * cd /path/to/project && pyfaggregator -i -p plone

    # Update Django packages every 6 hours
    0 */6 * * * cd /path/to/project && pyfaggregator -i -p django

Custom Timestamp File
---------------------

Use a different timestamp file for each profile:

.. code-block:: console

    $ pyfaggregator -i -p django -s .django.since
    $ pyfaggregator -i -p flask -s .flask.since

This allows:

- Independent update schedules per profile
- Different retention policies
- Easier troubleshooting

Incremental with Manual Classifiers
------------------------------------

.. code-block:: console

    $ pyfaggregator -i -ft "Framework :: Plone" -t packages1 -s .plone.since


GitHub Enrichment Workflow
===========================

GitHub enrichment adds valuable repository metadata to your indexed packages, including stars, watchers, issues, and update timestamps.

Basic Enrichment
----------------

Enrich packages using a profile:

.. code-block:: console

    $ pyfgithub -p plone

This command:

- Reads all packages from the ``plone`` collection
- Looks up GitHub repository URLs from package metadata
- Fetches repository data from the GitHub API
- Updates packages with GitHub fields
- Caches GitHub data to minimize API calls

GitHub Fields Added
-------------------

The enrichment process adds these fields to each package (when a GitHub repository is found):

- ``github_stars`` - Number of stargazers (repository popularity)
- ``github_watchers`` - Number of watchers (active followers)
- ``github_updated`` - Last repository update timestamp
- ``github_open_issues`` - Number of open issues (activity indicator)
- ``github_url`` - Canonical GitHub repository URL

Enrichment Best Practices
--------------------------

Rate Limiting
~~~~~~~~~~~~~

GitHub API has rate limits. To avoid hitting them:

.. code-block:: console

    # Set cooldown time in .env file
    GITHUB_COOLOFFTIME=2

This adds a 2-second delay between API calls.

.. note::
   GitHub enrichment cache is shared across all profiles, so enriching multiple profiles benefits from cached data.

Re-enrichment
~~~~~~~~~~~~~

Re-run enrichment periodically to update repository metrics:

.. code-block:: console

    # Update GitHub data weekly
    0 0 * * 0 cd /path/to/project && pyfgithub -p plone

Enrich Specific Collection
---------------------------

For manual collection names:

.. code-block:: console

    $ pyfgithub -t packages1


Multi-Profile Management Workflow
==================================

The aggregator supports managing multiple Python framework ecosystems simultaneously, with each profile maintaining its own Typesense collection while sharing the GitHub enrichment cache.

Setting Up Multiple Profiles
-----------------------------

Complete Setup Example
~~~~~~~~~~~~~~~~~~~~~~

Set up tracking for Django, Flask, and Plone:

.. code-block:: console

    # Initial full fetch for each framework
    $ pyfaggregator -f -p django
    $ pyfaggregator -f -p flask
    $ pyfaggregator -f -p plone

    # Enrich all with GitHub data (shared cache!)
    $ pyfgithub -p django
    $ pyfgithub -p flask
    $ pyfgithub -p plone

    # Create search-only API keys for each
    $ pyfupdater --add-search-only-apikey -p django
    $ pyfupdater --add-search-only-apikey -p flask
    $ pyfupdater --add-search-only-apikey -p plone

Benefits of This Approach
~~~~~~~~~~~~~~~~~~~~~~~~~~

- **Ecosystem Independence**: Each framework has its own collection
- **Shared GitHub Cache**: GitHub data is cached and reused across profiles, saving API calls
- **Simplified Management**: Each profile can be updated independently
- **Collection Auto-Naming**: Collections automatically named after profiles (``django``, ``flask``, ``plone``)

Maintaining Multiple Profiles
------------------------------

Regular Updates
~~~~~~~~~~~~~~~

Update all profiles with incremental fetches:

.. code-block:: console

    $ pyfaggregator -i -p django
    $ pyfaggregator -i -p flask
    $ pyfaggregator -i -p plone

Automated Multi-Profile Updates
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Create a shell script for regular maintenance:

.. code-block:: bash

    #!/bin/bash
    # update_all_profiles.sh

    PROFILES=("django" "flask" "plone")

    for profile in "${PROFILES[@]}"; do
        echo "Updating $profile packages..."
        pyfaggregator -i -p "$profile"

        echo "Enriching $profile with GitHub data..."
        pyfgithub -p "$profile"
    done

    echo "All profiles updated!"

Run via cron:

.. code-block:: console

    # Update all profiles daily at 3 AM
    0 3 * * * /path/to/update_all_profiles.sh

Listing Profile Collections
----------------------------

View all profile collections:

.. code-block:: console

    $ pyfupdater -lsn

Example output:

.. code-block:: text

    django
    flask
    plone

View detailed collection information:

.. code-block:: console

    $ pyfupdater -ls

Migration Between Profiles
---------------------------

You can migrate data between collections or create versioned collections:

.. code-block:: console

    # Create a versioned snapshot of Django collection
    $ pyfupdater --migrate -s django -t django-v1

    # Create an alias pointing to the current version
    $ pyfupdater --add-alias -s django-current -t django


Complete Workflow Examples
===========================

Initial Setup from Scratch
---------------------------

Starting with a fresh installation:

.. code-block:: console

    # 1. Start services
    $ docker-compose up -d

    # 2. Configure environment (create .env file with credentials)

    # 3. Perform full fetch
    $ pyfaggregator -f -p plone

    # 4. Enrich with GitHub data
    $ pyfgithub -p plone

    # 5. Create API key for client applications
    $ pyfupdater --add-search-only-apikey -p plone

Daily Maintenance Workflow
---------------------------

Typical daily operations:

.. code-block:: console

    # 1. Incremental update of packages
    $ pyfaggregator -i -p plone

    # 2. Refresh GitHub data (optional, can be done weekly)
    $ pyfgithub -p plone

    # 3. Verify collections
    $ pyfupdater -lsn

Testing and Development Workflow
---------------------------------

When developing or testing changes:

.. code-block:: console

    # 1. Fetch limited dataset
    $ pyfaggregator -f -p plone -l 50 -t plone-test

    # 2. Enrich test collection
    $ pyfgithub -t plone-test

    # 3. Verify results
    $ pyfupdater -ls

    # 4. Clean up test collection when done
    # (delete via Typesense API or UI)

Migration and Versioning Workflow
----------------------------------

Creating versioned collections for safe updates:

.. code-block:: console

    # 1. Create new version collection
    $ pyfaggregator -f -p plone -t plone-v2

    # 2. Enrich new collection
    $ pyfgithub -t plone-v2

    # 3. Verify new collection is complete
    $ pyfupdater -ls

    # 4. Update alias to point to new version
    $ pyfupdater --add-alias -s plone -t plone-v2

    # 5. Old collection (plone-v1) can be kept as backup or deleted


Troubleshooting Common Workflows
=================================

Workflow Failures and Recovery
-------------------------------

If a full fetch fails partway through:

.. code-block:: console

    # Resume using incremental mode
    $ pyfaggregator -i -p plone

This will pick up where it left off based on the timestamp file.

GitHub Rate Limit Exceeded
---------------------------

If you hit GitHub API rate limits:

.. code-block:: console

    # Increase cooldown time in .env
    GITHUB_COOLOFFTIME=5

    # Re-run enrichment (will skip cached entries)
    $ pyfgithub -p plone

Verifying Collection Status
----------------------------

Check if collections are properly populated:

.. code-block:: console

    # List all collections with document counts
    $ pyfupdater -ls

    # Check specific collection in Typesense UI
    # Navigate to http://localhost:8108 (if using local setup)
