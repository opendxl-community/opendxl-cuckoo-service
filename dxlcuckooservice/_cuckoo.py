# Shout out to Chris Smith, whose epo-service/epo-client libraries created an
# excellent framework for Sofware Wrappers.
# By Jesse Netz

import json
import logging
import requests
import warnings
from requests.auth import HTTPBasicAuth

# Configure local logger
logger = logging.getLogger(__name__)


class _Cuckoo(object):
    """
    A Cuckoo server that is being wrapped and exposed to the DXL fabric
    """

    # UTF-8 encoding (used for encoding/decoding payloads)
    UTF_8 = "utf-8"

    def __init__(self, name, host, port):
        """
        Constructs the cuckoo server wrapper

        :param name: The name of the cuckoo server
        :param host: The host for the cuckoo server
        :param port: The port for the cuckoo server
        """
        self._name = name
        self._client = _CuckooRemote(host, port)

    def execute(self, command):
        """
        Invokes a remote command on the cuckoo server (via HTTP)

        :param command: The command to invoke
        :return: The result of the command execution
        """
        return self._client.invoke_command(command)


class _CuckooRemote(object):
    """
    Handles REST invocation of cuckoo remote commands
    """

    def __init__(self, host, port):
        """

        Initializes the cuckooRemote with the information for the target cuckoo instance

        :param host: the hostname of the cuckoo to run remote commands on
        :param port: the port of the desired cuckoo
        """

        logger.info('Initializing cuckooRemote for cuckoo {} on port {}'.format(host, port))

        self._baseurl = 'http://{}:{}'.format(host, port)
        self._session = requests.Session()


    def invoke_command(self, command_name):
        """
        Invokes the given remote command by name with the supplied parameters

        :param command_name: The name of the cuckoo command to invoke
        :return: the response for the cuckoo command
        """


        params = {}

        return self._parse_response(self._send_request(command_name, params))
        #return self._send_request(command_name, params)

    def _send_request(self, command_name, params=None):
        """
        Sends a request to the cuckoo server with the supplied command name

        :param command_name: The command name to invoke
        :param params: The parameters to provide for the command. This is for
                        future implementations with POST methods
        :return: the response object from cuckoo
        """
        logger.info('Invoking command {} with the following parameters:'.format(command_name))
        logger.info(params)
        with warnings.catch_warnings():
            warnings.filterwarnings("ignore", ".*subjectAltName.*")
            geturl=self._baseurl + "/" + command_name
            return self._session.get(geturl,params=params)

    @staticmethod
    def _parse_response(response):
        """
        Parses the response object from cuckoo. Removes the return status and code from the response body and returns
        just the remote command response. Throws an exception if an error response is returned.

        :param response: the cuckoo command response object to parse
        :return: the cuckoo command results as a string
        """
        try:
            response_body = response.text

            logger.info('Response from cuckoo: ' + response_body)
            status = response_body[:response_body.index(':')]
            result = response_body[response_body.index(':')+1:].strip()

            if 'Error' in status:
                code = int(status[status.index(' '):].strip())
                raise Exception('Response failed with error code ' + str(code) + '. Message: ' + result)

            return result
        except:
            logger.error('Exception while parsing response.')
            raise
