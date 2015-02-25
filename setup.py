#
# Copyright (c) 2015 Juniper Networks, Inc. All rights reserved.
#

import setuptools, re

def requirements(filename):
    with open(filename) as f:
        lines = f.read().splitlines()
    c = re.compile(r'\s*#.*')
    return filter(bool, map(lambda y: c.sub('', y).strip(), lines))

setuptools.setup(
    name='ceilometer-plugin-contrail',
    version='0.1dev',
    packages=setuptools.find_packages(),
    package_data={'': ['*.html', '*.css', '*.xml']},

    # metadata
    author="OpenContrail",
    author_email="dev@lists.opencontrail.org",
    license="Apache Software License",
    url="http://www.opencontrail.org/",

    long_description="OpenContrail Ceilometer Plugin",

    install_requires=requirements('requirements.txt'),

    entry_points = {
        'ceilometer.poll.central' : [
            'ip.floating.receive.packets = ceilometer_plugin_contrail.network.statistics.floatingip:FloatingIPPollsterReceivePackets',
            'ip.floating.transmit.packets = ceilometer_plugin_contrail.network.statistics.floatingip:FloatingIPPollsterTransmitPackets',
            'ip.floating.receive.bytes = ceilometer_plugin_contrail.network.statistics.floatingip:FloatingIPPollsterReceiveBytes',
            'ip.floating.transmit.bytes = ceilometer_plugin_contrail.network.statistics.floatingip:FloatingIPPollsterTransmitBytes',
        ],
        'network.statistics.drivers' : [
            'contrail = ceilometer_plugin_contrail.network.statistics.contrail.driver:ContrailDriver'
        ],
    },
)
