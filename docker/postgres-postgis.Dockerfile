# PostgreSQL 16 with PostGIS, built on the image production already runs.
#
# The obvious move — swapping `postgres:16` for `postgis/postgis:16-3.5` — is
# wrong here, and quietly so. That image is Debian 11 (glibc 2.31) carrying
# PostgreSQL 16.9. This database runs Debian 13 (glibc 2.41) on 16.13, and
# `pg_database.datcollversion` records **2.41** against an `en_US.utf8` libc
# collation. Starting the older image on this data directory downgrades the
# server minor version and, worse, reads every existing text index under a
# different glibc collation than the one that built it. Collation changes
# reorder strings; an index sorted under one version and searched under another
# returns wrong rows without erroring. That is not a risk worth taking to avoid
# writing four lines.
#
# Deriving from `postgres:16` instead keeps the distribution, the glibc, and the
# locale data identical, and takes PostGIS from the same PGDG repository the
# base image already trusts. Nothing about the data directory changes.
FROM postgres:16

# postgresql-16-postgis-3 provides the shared library; -scripts provides the
# extension SQL that CREATE EXTENSION reads. Pulling both explicitly means a
# packaging change to the dependency chain cannot leave us with a half install.
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        postgresql-16-postgis-3 \
        postgresql-16-postgis-3-scripts \
    && rm -rf /var/lib/apt/lists/*
