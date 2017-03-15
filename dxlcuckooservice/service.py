# Shout out to Chris Smith, whose epo-service/epo-client libraries created an
# excellent framework for Sofware Wrappers.
# By Jesse Netz

import logging
import os
import json
from threading import Lock

from ConfigParser import ConfigParser, NoOptionError

from dxlclient.client import DxlClient
from dxlclient.client_config import DxlClientConfig
from dxlclient.service import ServiceRegistrationInfo
from dxlclient.callbacks import RequestCallback
from dxlclient.message import ErrorResponse, Response

from _cuckoo import _Cuckoo

# Configure local logger
logger = logging.getLogger(__name__)


class CuckooService(object):
    """
    A DXL service that exposes the remote commands of the cuckoo server to
    the DXL fabric. When a DXL request message is received, the remote command is invoked
    on the cuckoo server and its response is packaged and returned to the invoking
    client via a DXL response message.
    """

    # The name of the DXL client configuration file
    DXL_CLIENT_CONFIG_FILE = "dxlclient.config"
    # The name of the cuckoo service configuration file
    DXL_CUCKOO_SERVICE_CONFIG_FILE = "dxlcuckooservice.config"

    # The type of the cuckoo DXL service that is registered with the fabric
    DXL_SERVICE_TYPE = "/mcafee/service/cuckoo/remote"

    # The timeout used when registering/unregistering the service
    DXL_SERVICE_REGISTRATION_TIMEOUT = 60

    # The name of the "General" section within the cuckoo service configuration file
    GENERAL_CONFIG_SECTION = "General"
    # The property used to specify the cuckoo name within the "General" section of the
    # Cuckoo service configuration file
    GENERAL_CUCKOO_NAME_CONFIG_PROP = "cuckooName"

    # The default port used to communicate with a cuckoo server
    DEFAULT_CUCKOOAPI_PORT = 8090

    # configuration file
    CUCKOO_HOST_CONFIG_PROP = "host"
    # The property used to specify the port of a cuckoo server within the cuckoo service
    # configuration file (this property is optional)
    CUCKOO_PORT_CONFIG_PROP = "port"

    # The name of the "IncomingMessagePool" section within the cuckoo service
    # configuration file
    INCOMING_MESSAGE_POOL_CONFIG_SECTION = "IncomingMessagePool"
    # The property used to specify the queue size for the incoming message pool
    INCOMING_MESSAGE_POOL_QUEUE_SIZE_CONFIG_PROP = "queueSize"
    # The property used to specify the thread count for the incoming message pool
    INCOMING_MESSAGE_POOL_THREAD_COUNT_CONFIG_PROP = "threadCount"

    # The default thread count for the incoming message pool
    DEFAULT_THREAD_COUNT = 10
    # The default queue size for the incoming message pool
    DEFAULT_QUEUE_SIZE = 1000


    def __init__(self, config_dir):
        """
        Constructor parameters:

        :param config_dir: The location of the configuration files for the cuckoo service
        """
        self._config_dir = config_dir
        self._dxlclient_config_path = os.path.join(config_dir, self.DXL_CLIENT_CONFIG_FILE)
        self._dxlcuckooservice_config_path = os.path.join(config_dir, self.DXL_CUCKOO_SERVICE_CONFIG_FILE)
        self._cuckoo_by_topic = {}
        self._dxl_client = None
        self._dxl_service = None
        self._running = False
        self._destroyed = False

        self._incoming_thread_count = self.DEFAULT_THREAD_COUNT
        self._incoming_queue_size = self.DEFAULT_QUEUE_SIZE

        self._lock = Lock()

    def __del__(self):
        """destructor"""
        self.destroy()

    def __enter__(self):
        """Enter with"""
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        """Exit with"""
        self.destroy()

    def _validate_config_files(self):
        """
        Validates the configuration files necessary for the cuckoo service. An exception is thrown
        if any of the required files are inaccessible.
        """
        if not os.access(self._dxlclient_config_path, os.R_OK):
            raise Exception(
                "Unable to access client configuration file: {0}".format(
                    self._dxlclient_config_path))
        if not os.access(self._dxlcuckooservice_config_path, os.R_OK):
            raise Exception(
                "Unable to access service configuration file: {0}".format(
                    self._dxlcuckooservice_config_path))

    def _load_configuration(self):
        """
        Loads the configuration settings from the cuckoo service configuration file
        """
        config = ConfigParser()
        read_files = config.read(self._dxlcuckooservice_config_path)
        if len(read_files) is not 1:
            raise Exception(
                "Error attempting to read service configuration file: {0}".format(
                    self._dxlcuckooservice_config_path))

        # Determine the cuckoo servers in the configuration file
        cuckoo_name_str = config.get(self.GENERAL_CONFIG_SECTION, self.GENERAL_CUCKOO_NAME_CONFIG_PROP)
        if len(cuckoo_name_str.strip()) is 0:
            raise Exception("A Cuckoo server must be defined in the service configuration file")

        # Create an instance of the cuckoo object (used to communicate with
        # the cuckoo server via HTTP)
        cuckoo_name = cuckoo_name_str.strip()
        host = config.get(cuckoo_name, self.CUCKOO_HOST_CONFIG_PROP)
        # Port (optional)
        port = self.DEFAULT_CUCKOOAPI_PORT

        try:
            port = config.get(cuckoo_name, self.CUCKOO_PORT_CONFIG_PROP)
        except NoOptionError:
            pass

        # Create cuckoo wrapper
        cuckoo = _Cuckoo(name=cuckoo_name, host=host, port=port)

        # Create the request topic
        request_topic = self.DXL_SERVICE_TYPE
        
        # Associate cuckoo wrapper instance with the request topic
        self._cuckoo_by_topic[request_topic] = cuckoo

        #
        # Load message pool settings
        #

        try:
            self._incoming_queue_size = config.getint(self.INCOMING_MESSAGE_POOL_CONFIG_SECTION,
                                                      self.INCOMING_MESSAGE_POOL_QUEUE_SIZE_CONFIG_PROP)
        except NoOptionError:
            pass

        try:
            self._incoming_thread_count = config.getint(self.INCOMING_MESSAGE_POOL_CONFIG_SECTION,
                                                        self.INCOMING_MESSAGE_POOL_THREAD_COUNT_CONFIG_PROP)
        except NoOptionError:
            pass

    def _dxl_connect(self):
        """
        Attempts to connect to the DXL fabric and register the cuckoo DXL service
        """

        # Connect to fabric
        config = DxlClientConfig.create_dxl_config_from_file(self._dxlclient_config_path)
        config.incoming_message_thread_pool_size = self._incoming_thread_count
        config.incoming_message_queue_size = self._incoming_queue_size
        logger.info("Incoming message configuration: queueSize={0}, threadCount={1}".format(
            config.incoming_message_queue_size, config.incoming_message_thread_pool_size))

        client = DxlClient(config)
        logger.info("Attempting to connect to DXL fabric ...")
        client.connect()
        logger.info("Connected to DXL fabric.")

        try:
            # Register service
            service = ServiceRegistrationInfo(client, self.DXL_SERVICE_TYPE)
            for request_topic in self._cuckoo_by_topic:
                service.add_topic(str(request_topic), _CuckooRequestCallback(client, self._cuckoo_by_topic))

            logger.info("Registering service ...")
            client.register_service_sync(service, self.DXL_SERVICE_REGISTRATION_TIMEOUT)
            logger.info("Service registration succeeded.")
        except:
            client.destroy()
            raise

        self._dxl_client = client
        self._dxl_service = service

    def run(self):
        """
        Starts the cuckoo service. This will load the configuration files associated with the service,
        connect the DXL client to the fabric, and register the cuckoo DXL service with the fabric.
        """
        with self._lock:
            if self._running:
                raise Exception("The cuckoo service is already running")

            logger.info("Running service ...")
            self._validate_config_files()
            self._load_configuration()
            self._dxl_connect()
            self._running = True

    def destroy(self):
        """
        Destroys the cuckoo service. This will cause the cuckoo DXL service to be unregistered with the fabric
        and the DXL client to be disconnected.
        """
        with self._lock:
            if self._running and not self._destroyed:

                logger.info("Destroying service ...")
                if self._dxl_client is not None:

                    if self._dxl_service is not None:
                        logger.info("Unregistering service ...")
                        self._dxl_client.unregister_service_sync(
                            self._dxl_service, self.DXL_SERVICE_REGISTRATION_TIMEOUT)
                        logger.info("Service unregistration succeeded.")
                        self._dxl_service = None

                    self._dxl_client.destroy()
                    self._dxl_client = None
                self._destroyed = True

    def _get_path(self, in_path):
        """
        Returns an absolute path for a file specified in the configuration file (supports
        files relative to the configuration file).
        :param in_path: The specified path
        :return: An absolute path for a file specified in the configuration file
        """
        if not os.path.isfile(in_path) and not os.path.isabs(in_path):
            config_rel_path = os.path.join(self._config_dir, in_path)
            if os.path.isfile(config_rel_path):
                in_path = config_rel_path
        return in_path

class _CuckooRequestCallback(RequestCallback):
    """
    Request callback used to handle incoming service requests
    """

    # UTF-8 encoding (used for encoding/decoding payloads)
    UTF_8 = "utf-8"

    # The key in the request used to specify the cuckoo command to invoke
    CMD_NAME_KEY = "command"


    def __init__(self, client, cuckoo_by_topic):
        """
        Constructs the callback

        :param client: The DXL client associated with the service
        :param cuckoo_by_topic: The cuckoo server wrappers by associated request topics
        """
        super(_CuckooRequestCallback, self).__init__()
        self._dxl_client = client
        self._cuckoo_by_topic = cuckoo_by_topic

    def on_request(self, request):
        """
        Invoked when a request is received

        :param request: The request that was received
        """
        try:
            # Build dictionary from the request payload
            req_dict = json.loads(request.payload.decode(encoding=self.UTF_8))

            # Determine the cuckoo command
            if self.CMD_NAME_KEY not in req_dict:
                raise Exception("A command name was not specified ('{0}')".format(self.CMD_NAME_KEY))
            command = req_dict[self.CMD_NAME_KEY]

            # Get the cuckoo server to invoke the command on
            cuckoo = self._cuckoo_by_topic[request.destination_topic]

            # Execute the cuckoo Remote Command
            result = cuckoo.execute(command)

            # Create the response, set payload, and deliver
            response = Response(request)
            response.payload = result
            self._dxl_client.send_response(response)

        except Exception as ex:
            logger.exception("Error while processing request")
            # Send error response
            self._dxl_client.send_response(
                ErrorResponse(request,
                              error_message=str(ex).encode(encoding=self.UTF_8)))
