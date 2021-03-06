# Copyright (c) 2020 Seagate Technology LLC and/or its Affiliates
#
# This program is free software: you can redistribute it and/or modify it under the
# terms of the GNU Affero General Public License as published by the Free Software
# Foundation, either version 3 of the License, or (at your option) any later version.
#
# This program is distributed in the hope that it will be useful, but WITHOUT ANY
# WARRANTY; without even the implied warranty of MERCHANTABILITY or FITNESS FOR A
# PARTICULAR PURPOSE. See the GNU Affero General Public License for more details.
#
# You should have received a copy of the GNU Affero General Public License along
# with this program. If not, see <https://www.gnu.org/licenses/>. For any questions
# about this software or licensing, please email opensource@seagate.com or
# cortx-questions@seagate.com.

"""
This script will be installed in SSU and will do the necessary bundling for
that node. The details of files/logs to collect will be given to this script
as the input.
"""


import subprocess
import os
import shutil
import sys
import json
import socket

# NOTE:- Since this script will be triggered by mco we will not be
# showing detailed output/Errors on the screens, instead return codes.
#
# Return codes of the script:-
#
# 0 : SUCCESS
# 1 : UNKNOWN ERROR
# 2 : Invalid argument
# 3 : Command lines arguments not supplied
# 4 : Could not create tmp/bundle directory
# 5 : Some commands could not be executed
# 6 : Files cannot be copied to /tmp/bundle
# 7 : Tar bundle could not be created
# 8 : Tar Bundle could not be send to SSU
# 9 : Clean up Failed
# Note: Detailed input params for debugging purposes as follows:
# '{"action": ["m0reportbug", "mv -f m0reportbug-data.tar.gz /tmp/bundle/"],
#  "files": [], "host": {"": "xxxxxxxx", "bucket":
# "/var/lib/support_bundles/2016-08-29_12-42-28/nodes/",
# "name": "vmc-rekvm-hvt-cc1.xy01.xyratex.com"}}' TRACE


TRACE = True
LOGGER = None


class RemoteFileCollector(object):
    # pylint: disable=too-few-public-methods
    """
    MCO interface for the remote file collection.
    """

    BUNDLE_TMP_DIR = '/tmp/bundle'
    BUNDLE_TAR = '{}.tar'.format(BUNDLE_TMP_DIR)

    def __init__(self, collection_rules):
        self._rule = json.loads(collection_rules)
        self._actions = self._rule.get('action', [])
        self._files = self._rule.get('files', [])
        host_info = self._rule.get('host', {})
        self._bucket = os.path.join(
            host_info.get('bucket'),
            socket.gethostname()
        )
        self._node_name = host_info.get('name')
        self._pwd = host_info.get('viel')
        self.cleanup = self._rule.get('cleanup')

        log('Action      : {}'.format(self._actions))
        log('Files       : {}'.format(self._files))
        log('Host Bucket : {}'.format(self._bucket))
        log('Host Name   : {}'.format(self._node_name))
        log('Cleanup     : {}'.format(self.cleanup))

    def collect(self):
        """Collect files from remote nodes"""
        if self._execute_actions():
            if self._collect_files():
                self._send_tar_bundle()
        self.clean_up()

    def _execute_actions(self):
        """
        Execute the commands in remote nodes using mco
        """
        if RemoteFileCollector._create_tmp_bundle_directory():
            for action in self._actions:
                if not self._execute_command(action):
                    log('Action: {} Failed.'.format(action), 2)
                    print 5
                else:
                    log('Action Execution Successful: [{}].for'.format(action))
            return True
        else:
            return False

    @staticmethod
    def _create_tmp_bundle_directory():
        """
        Create the tmp bundle directory on SSUs
        """
        try:
            if os.path.exists(RemoteFileCollector.BUNDLE_TMP_DIR):
                shutil.rmtree(RemoteFileCollector.BUNDLE_TMP_DIR)
                log('Older bundle directory is removed!')
            if os.path.exists(RemoteFileCollector.BUNDLE_TAR):
                os.remove(RemoteFileCollector.BUNDLE_TAR)
                log('Older bundle.tar is removed!')
            os.mkdir(RemoteFileCollector.BUNDLE_TMP_DIR)
            log('Tmp bundle, {} dir Successfully Created'.format(
                RemoteFileCollector.BUNDLE_TMP_DIR))
            return True
        except (subprocess.CalledProcessError, IOError, OSError) as err:
            log(
                'Unable to create bundle base: {}, Details: {}. '
                'Bundling could not be completed.'.format(
                    RemoteFileCollector.BUNDLE_TMP_DIR, err
                ), 3
            )
            print 4
            return False

    def _collect_files(self):
        """
        Collect files into local bucket and create a tar ball
        """
        self._copy_files_to_local_bucket()

        tar_cmd = 'tar -cf {} -C /tmp bundle'.format(
            RemoteFileCollector.BUNDLE_TAR
        )
        if self._execute_command(tar_cmd):
            log('Bundle package created. bundle.tar')
            return True
        else:
            log('Bundle package Failed to tarred. Command: {}'.format(
                tar_cmd), 3)
            print 7
            return False

    def _copy_files_to_local_bucket(self):
        """
        Copy each file mentioned in the list to remote bundle package
        """
        copy_count = 0
        for _file in self._files:
            try:
                shutil.copy(_file, RemoteFileCollector.BUNDLE_TMP_DIR)
                log('File collected successfully: [{}]'.format(_file))
                copy_count += 1
            except (OSError, IOError) as err:
                log('Failed to collect bundle directory: {}. Details: {}'
                    .format(_file, str(err)))
        if copy_count < 1 and len(self._files) > 0:
            print 6
            return False
        else:
            return True

    @staticmethod
    def _execute_command(command):
        """
        Execute the command on remote node using mco
        """
        try:
            result = subprocess.check_output(command, shell=True) or 'success'
        except (subprocess.CalledProcessError, OSError, IOError) as err:
            err_msg = 'Command: {}, failed to execute. Details: {}'. \
                format(command, str(err))
            log(err_msg, 2)
            return None
        return result

    def _send_tar_bundle(self):
        """
        Get the file from remote node
        """
        cmd = 'scp {}.* root@{}:{}/ '.format(
            RemoteFileCollector.BUNDLE_TMP_DIR,
            self._node_name,
            self._bucket
        )
        log('Sending the tar file to CMU')
        if self._execute_command(cmd):
            log('Tar ball Successfully Sent.')
        else:
            log('Tar bundle CANNOT be sent to CMU', 3)
            print 8

    def clean_up(self):
        """
        Clean the tar bundle
        """
        for _file in self.cleanup:
            try:
                if os.path.isdir(_file):
                    shutil.rmtree(_file)
                elif os.path.isfile(_file):
                    os.remove(_file)
            except OSError as err:
                log('Cleanup Error. Details: {}'.format(str(err)))
                print 9


# pylint: disable=W0603
def main():
    """
        Initialize the logging if debug mode
    """
    global TRACE
    start_log()
    if len(sys.argv) > 1:
        bundling_info = sys.argv[1]
        if len(sys.argv) == 3:
            TRACE = True
        try:
            log('Remote Bundling is triggered. Params: {}'.format(
                bundling_info))
            remote_bundling_obj = RemoteFileCollector(bundling_info)
            remote_bundling_obj.collect()
        except (ValueError, TypeError) as err:
            log('Invalid bundling Params. Details: {}'.format(err), 3)
            print 2
    else:
        log('Incomplete Arguments to run the script.', 3)
        print 3  # Incomplete arguments to run the script
    stop_log()


# pylint: disable=W0603, W0602
def start_log():
    """Open the looger object and close"""
    global LOGGER
    global TRACE
    if TRACE and not LOGGER:
        try:
            LOGGER = open('/tmp/bundle.log', 'w')
        except OSError as err:
            print 'Could not open logger object. Details: {}'.format(str(err))
            TRACE = False
            LOGGER = None


# pylint: disable=W0603, W0602
def stop_log():
    """
    CLose the logger object
    """
    global LOGGER
    if LOGGER:
        LOGGER.close()


# pylint: disable=W0603
def log(msg, level=1):
    """
    Log the msg with the type;
    NOTE: These will be logged only if the debug=True
    """
    if TRACE and LOGGER:
        if level == 1:
            msg = 'INFO : {} \n'.format(msg)
        elif level == 2:
            msg = 'WARNING : {} \n'.format(msg)
        elif level == 3:
            msg = 'ERROR : {} \n'.format(msg)
        else:
            msg = 'WARNING : {} \n'.format(msg)
        LOGGER.write(msg)

main()
