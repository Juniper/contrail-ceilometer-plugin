#
# Copyright (c) 2015 Juniper Networks, Inc. All rights reserved.
#

env = DefaultEnvironment().Clone()

sources = [
    'ceilometer_plugin_contrail/__init__.py',
    'ceilometer_plugin_contrail/neutron_client.py',
    'ceilometer_plugin_contrail/network/__init__.py',
    'ceilometer_plugin_contrail/network/statistics/__init__.py',
    'ceilometer_plugin_contrail/network/statistics/floatingip.py',
    'ceilometer_plugin_contrail/network/statistics/contrail/__init__.py',
    'ceilometer_plugin_contrail/network/statistics/contrail/client.py',
    'ceilometer_plugin_contrail/network/statistics/contrail/driver.py',
    'requirements.txt',
    'setup.py',
]

cd_cmd = 'cd ' + Dir('.').path + ' && '
sdist_gen = env.Command('dist/ceilometer_plugin_contrail-0.1dev.tar.gz', sources, cd_cmd + 'python setup.py sdist')
env.Alias('ceilometer_plugin_contrail:sdist', sdist_gen)

if 'install' in BUILD_TARGETS:
    install_cmd = env.Command(None, sources,
                              cd_cmd + 'python setup.py install %s' %
                              env['PYTHON_INSTALL_OPT'])
    env.Alias('install', install_cmd)

# Local Variables:
# mode: python
# End:
