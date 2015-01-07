"""
Tasks to provision and configure PostgreSQL streaming replication.
"""

# Python imports
import os

# Other imports
import cuisine
from fabric.api import *
from fabtools import require

# Enviornment constants
PSQL_SUPERUSER = 'postgres' # PostgreSQL super user
ENV_USER = 'pmalm'
PSQL_DATA_DIRECTORY = '/var/lib/postgresql/9.3/main'
PSQL_CONF_DIRECTORY = '/etc/postgresql/9.3/main'
PSQL_MASTER = '10.1.0.156'
PSQL_SLAVES = ['10.1.0.174']

# Network configuration
env.use_ssh_config = True
env.roledefs = {
    'master': [PSQL_MASTER],
    'slave': PSQL_SLAVES
}
env.user = 'pmalm'

@task
def ensure_remote():
    print("Executing on %s as %s" % (env.host, env.user))
    cuisine.run("echo hello world")

@task
def ensure_system_packages():
    cuisine.sudo('apt-get update --quiet')
    cuisine.package_ensure('postgresql==9.3')

@task
def ensure_database():
    """ Database setup and running. """
    ensure_serverkey()
    cuisine.sudo('service postgresql restart')
    require.postgres.user('postgres', 'password')
    require.postgres.database('postgres')
    cuisine.run('psql -c "ALTER USER postgres PASSWORD \'password\';"')

def clean_data_directory(show_warning=True):
    user_response = 'n'
    if show_warning:
        print("*** WARNING! *** ")
        print("This command will delete the contents of {} on host {}".format(PSQL_DATA_DIRECTORY,env.host))
        user_response = raw_input("Do you wish to continue [Y/n]? ")
    else:
        user_response = 'Y'

    if user_response == 'Y':
        print("Deleting {}".format(PSQL_DATA_DIRECTORY))
        cuisine.run('sudo -u postgres rm -rf {}'.format(PSQL_DATA_DIRECTORY))
        print("Done.")
    else:
        print("Doing nothing.")

@hosts(PSQL_SLAVES)
def configure_slaves():
    # As per https://wiki.postgresql.org/wiki/Streaming_Replication
    ensure_database()
    cuisine.run('sudo -u {} service postgresql stop'.format(PSQL_SUPERUSER))
    clean_data_directory(show_warning=True)
    print("Backing up the database... this can take a while.")
    cuisine.run('/usr/bin/pg_basebackup -h {} -D {} -P -U replication --xlog-method=stream'
        .format(env.roledefs['master'][0],PSQL_DATA_DIRECTORY))
    cuisine.ensure_file('{}/pg_hba.conf'.format(PSQL_DATA_DIRECTORY))
    cuisine.ensure_file('{}/postgresql.conf'.format(PSQL_CONF_DIRECTORY))
    cuisine.ensure_file('{}/recovery.conf'.format(PSQL_DATA_DIRECTORY))
    cuisine.run('sudo -u {} service postgresql start'.format(PSQL_SUPERUSER))

@hosts(PSQL_MASTER)
def configure_master():
    cuisine.run('psql -c "CREATE ROLE replication WITH REPLICATION PASSWORD \'password\' LOGIN"')
    cuisine.ensure_file('{}/pg_hba.conf'.format(PSQL_DATA_DIRECTORY))
    cuisine.ensure_file('{}/postgresql.conf'.format(PSQL_CONF_DIRECTORY))
    print("Reloading PostgreSQL server...")
    cuisine.run('sudo -u {} pg_ctl reload'.format(PSQL_SUPERUSER))

def check_replication_status():
    cuisine.run('psql -c "SELECT pg_current_xlog_location()"')

@task
def ensure_replication():
    configure_slaves()
    configure_master()
    check_replication_status()
