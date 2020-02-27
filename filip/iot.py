import requests
from requests import Response

import json
import string
import random
from filip import orion
from filip import request_utils as requtils
from filip import test


PROTOCOLS = ['IoTA-JSON','IoTA-UL']


class Attribute: # DeviceAttribute
    def __init__(self, name: str, attr_type: str, value_type: str,
                 object_id: str=None, attr_value: str=None):
        self.name = name
        self.value_type = value_type
        self.attr_type = attr_type
        self.object_id = object_id
        self.attr_value = attr_value
        if attr_value != None and attr_type != "static":
            print("[WARN]: Setting attribute value only allowed for "
                      "static attributes! Value will be ignored!")
            self.attr_value = None

    def get_json(self):
        if self.attr_value != None:
            return {'value': self.attr_value, 'type': '{}'.format(
                self.attr_type)}
        else:
            return {'type': '{}'.format(self.attr_type)}


class Device:
    """
    Represents all necessary information for device registration with an Fiware IoT Agent.
    :ivar device_id: Device ID that will be used to identify the device (mandatory).
    :ivar service: Name of the service the device belongs to (will be used in the fiware-service header).
    :ivar service_path: Name of the subservice the device belongs to (used in the fiware-servicepath header).
    :ivar entity_name: Name of the entity representing the device in the Context Broker.
    :ivar timezone: Time zone of the sensor if it has any.
    :ivar endpoint: Endpoint where the device is going to receive commands, if any.
    :ivar protocol: Name of the device protocol, for its use with an IoT Manager.
    :ivar transport: Name of the device transport protocol, for the IoT Agents with multiple transport protocols.
    :ivar attributes: List of active attributes of the device.
    :ivar lazy: List of lazy attributes of the device.
    :ivar commands: List of commands of the device
    :ivar static_attributes: List of static attributes to append to the entity. All the updateContext requests to the CB will have this set of attributes appended.
        """
    def __init__(self, device_id: str, entity_name: str, entity_type: str, **kwargs):
        self.device_id = device_id
        self.entity_name = entity_name
        self.entity_type = entity_type
        self.service = None
        self.service_path = "/"
        self.timezone = kwargs.get("timezone")
        self.endpoint = kwargs.get("endpoint") # necessary for HTTP
        self.protocol = kwargs.get("protocol")
        self.transport = kwargs.get("transport")
        self.attributes = kwargs.get("attributes", [])
        self.lazy = kwargs.get("lazy", [])
        self.commands = kwargs.get("commands", [])
        self.static_attributes = kwargs.get("static_attributes", [])

    def get_json(self):
        dict = {}
        dict['device_id']= self.device_id
        dict['entity_name']= self.entity_name
        dict['entity_type']= self.entity_type
        dict['timezone'] = self.timezone
        if self.endpoint:
            dict['endpoint'] = self.endpoint
        dict['protocol'] = self.protocol
        dict['transport'] = self.transport
        dict['attributes'] = self.attributes
        dict['lazy'] = self.lazy
        dict['commands'] = self.commands
        dict['static_attributes'] = self.static_attributes
        return json.dumps(dict, indent=4)

    def add_attribute(self, attr_name: str, attr_type: str, value_type: str,
                 object_id: str=None, attr_value: str=None):
        """
        :param name: The name of the attribute as submitted to the context broker.
        :param type: The type of the attribute as submitted to the context broker.
        :param object_id: The id of the attribute used from the southbound API.
        :param attr_type: One of \"active\" (default), \"lazy\" or \"static\"
        """
        attribute=Attribute(attr_name, attr_type, value_type,
                 object_id, attr_value)
        
        attr = {}
        if attribute.object_id:
            attr["object_id"] = attribute.object_id
        if attribute.attr_value != None and\
                attribute.attr_type == "static":
            attr["value"] = attribute.attr_value
        attr["name"] = attribute.name
        attr["type"] = attribute.value_type


        # attr["value"] = Attribute.value NOT Supported by agent-lib
        #TODO: implement as switch
        if attribute.attr_type == "active":
            self.attributes.append(attr)
        elif attribute.attr_type == "lazy":
            self.lazy.append(attr)
        elif attribute.attr_type == "static":
            self.static_attributes.append(attr)
        elif attribute.attr_type == "command":
            self.commands.append(attr)
        else:
            print("[WARN]: Attribute type unknown: \"{}\"".format(
                attr['type']))


    def delete_attribute(self, attr_name, attr_type):
        '''
        Removing attribute by name and from the list of attributes in the
        local device. You need to execute update device in iot agent in
        order to update the configuration to remote!
        :param attr_name: Name of the attribute to delete
        :param attr_type: Type of the attribute to delete
        :return:
        '''
        # TODO: check whether the list comprehensions below can be written in a different way
        try:
            if attr_type == "active":
                self.attributes = [i for i in self.attributes if not (i[
                                                        'name']==attr_name)]
            elif attr_type == "lazy":
                self.lazy = [i for i in self.lazy if not (i['name'] ==
                                                                   attr_name)]
            elif attr_type == "static":
                self.static_attributes = [i for i in self.static_attributes if
                                          not (
                        i['name'] == attr_name)]
            elif attr_type == "command":
                self.commands = [i for i in self.commands if not (i['name'] ==
                                                                   attr_name)]
            else:
                print("[WARN]: Attribute type unknown: \"{}\"".format(attr_type))
            print("[INFO]: Attribute succesfully deleted: \"{}\"".format(
                attr_name))
        except:
            print("[WARN]: Attribute could not be deleted: \"{}\"".format(
                attr_name))



class DeviceGroup:
    """
    For every Device Group, the pair (resource, apikey) must be unique
    (as it is used to identify which group to assign to which device).
    Those operations of the API targeting specific resources will need
    the use of the resource and apikey parameters to select the
    apropriate instance.

    :param name:    Service of the devices of this type
    :param path:    Subservice of the devices of this type.
    :param cbHost: Context Broker connection information. This options
    can be used to override the global ones for specific types of devices.
    :param kwargs:
    :ivar entity_type: Name of the type to assign to the group.
    :ivar trust: Trust token to use for secured access to the Context Broker
    for this type of devices (optional; only needed for secured scenarios).
    :ivar lazy: List of lazy attributes of the device.
    :ivar commands: List of commands of the device
    :ivar attributes: List of active attributes of the device.
    :ivar static_attributes: List of static attributes to append to the entity. All the updateContext requests to the CB will have this set of attributes appended.
    :ivar internal_attributes: Optional section with free format, to allow
    specific IoT Agents to store information along with the devices in the Device Registry.
    """
    def __init__(self, fiware_service , cb_host: str,
                           **kwargs):

        self.__service = fiware_service.name
        self.__subservice = fiware_service.path
        self.__resource = kwargs.get("resource", "/iot/d") #for iot-ul 1.7.0
        # the default must be empty string
        self.__apikey = kwargs.get("apikey", "12345")

        self.__entity_type = kwargs.get("entity_type", "Thing")
        #self.trust
        self.__cbHost = cb_host
        self.__lazy = kwargs.get("lazy", [])
        self.__commands = kwargs.get("commands", [])
        self.__attributes = kwargs.get("attributes", [])
        self.__static_attributes = kwargs.get("static_attributes", [])
        self.__internal_attributes = kwargs.get("internal_attributes", [])

        self.devices = []
        self.__agent = kwargs.get("iot-agent", "iota-json")


        #For using the update functionality, the former configuration needs
        # to be stored
        self.__service_last = fiware_service.name
        self.__subservice_last = fiware_service.path
        self.__resource_last = kwargs.get("resource", "/iot/d")
        self.__apikey_last = kwargs.get("apikey", "12345")

    def update(self,**kwargs):
        #For using the update functionality, the former configuration needs
        # to be stored
        # TODO: NOTE: It is not recommenend to change the combination fiware
        #  service structure and apikey --> Delete old and register a new one
        self.__service_last = self.__service
        self.__subservice_last = self.__subservice
        self.__resource_last = self.__resource
        self.__apikey_last = self.__apikey

        # From here on the variables are updated
        self.__service = kwargs.get("fiware_service", self.__service)
        self.__subservice = kwargs.get("fiware_service_path",
                                       self.__subservice)
        self.__resource = kwargs.get("resource", self.__resource)  # for iot-ul 1.7.0
        # the default must be empty string
        self.__apikey = kwargs.get("apikey", self.__apikey)
        self.__entity_type = kwargs.get("entity_type", self.__entity_type)
        # self.trust
        self.__cbHost = kwargs.get("cb_host", self.__cbHost)
        self.__lazy = kwargs.get("lazy", self.__lazy)
        self.__commands = kwargs.get("commands", self.__commands)
        self.__attributes = kwargs.get("attributes", self.__attributes)
        self.__static_attributes = kwargs.get("static_attributes",
                                              self.__static_attributes)
        self.__internal_attributes = kwargs.get("internal_attributes",
                                                self.__internal_attributes)

        self.__devices = []
        self.__agent = kwargs.get("iot-agent", self.__agent)

    def add_default_attribute(self, Attribute):
        """
        :param name: The name of the attribute as submitted to the context broker.
        :param type: The type of the attribute as submitted to the context broker.
        :param object_id: The id of the attribute used from the southbound API.
        :param attr_type: One of \"active\" (default), \"lazy\" or \"static\"
        """
        attr = {}
        if Attribute.object_id:
            attr["object_id"] = Attribute.object_id
        if Attribute.attr_value != None\
                and Attribute.attr_type == "static":
            attr["value"]  = Attribute.attr_value
        attr["name"] = Attribute.name
        attr["type"] = Attribute.value_type

        if Attribute.attr_type == "active":
            self.__attributes.append(attr)
        elif Attribute.attr_type == "lazy":
            self.__lazy.append(attr)
        elif Attribute.attr_type == "static":
            self.__static_attributes.append(attr)
        elif Attribute.attr_type == "internal":
            self.__internal_attributes.append(attr)
        elif Attribute.attr_type == "command":
            self.__commands.append(attr)
        else:
            print("[WARN]: Attribute type unknown: \"{}\"".format(
                attr['type']))

    def delete_default_attribute(self, attr_name, attr_type):
        '''
        Removing attribute by name and from the list of attributes in the
        local device group. You need to execute update device in iot agent in
        order to update the configuration to remote!
        :param attr_name: Name of the attribute to delete
        :param attr_type: Type of the attribute to delte
        :return:
        '''
        try:
            if attr_type == "active":
                self.__attributes = [i for i in self.__attributes if not (i[
                                                        'name']==attr_name)]
            elif attr_type == "lazy":
                self.__lazy = [i for i in self.__lazy if not (i['name'] ==
                                                                   attr_name)]
            elif attr_type == "static":
                self.__static_attributes = [i for i in
                                            self.__static_attributes
                                            if not (
                            i['name'] == attr_name)]
            elif attr_type == "internal":
                self.__internal_attributes = [i for i in
                                              self.__internal_attributes
                                              if not
                                              (i['name'] ==  attr_name)]
            elif attr_type == "command":
                self.__commands = [i for i in self.__commands if not
                (i['name'] == attr_name)]
            else:
                print("[WARN]: Attribute type unknown: \"{}\"".format(
                    attr_type))
            print("[INFO]: Attribute succesfully deleted: \"{}\"".format(
                attr_name))
        except:
            print("[WARN]: Attribute could not be deleted: \"{}\"".format(
                attr_name))

    def get_apikey(self):
        return self.__apikey

    def get_resource(self):
        return self.__resource

    def get_apikey_last(self):
        return self.__apikey_last

    def get_resource_last(self):
        return self.__resource_last

    def get_header(self) -> dict:
        return {
            "fiware-service": self.__service,
            "fiware-servicepath": self.__subservice
        }

    def get_header_last(self) -> dict:
        return {
            "fiware-service": self.__service_last,
            "fiware-servicepath": self.__subservice_last
        }

    def get_json(self):
        dict = {}
        dict['apikey']= self.__apikey
        dict['cbroker'] = self.__cbHost
        dict['entity_type'] = self.__entity_type
        dict['resource'] = self.__resource
        dict['lazy'] = self.__lazy
        dict['attributes'] = self.__attributes
        dict['commands'] = self.__commands
        dict['static_attributes'] = self.__static_attributes
        dict['internal_attributes'] = self.__internal_attributes
        return json.dumps(dict, indent=4)

    def generate_apikey(self, length: int = 10):
        """
        This function generates a random key from lowercase letter and
        digit characters
        :ivar length: Number of characters in the key string
        """
        return ''.join(random.choice(
            string.ascii_lowercase + string.digits) for _ in range(
            length))

    def test_apikey(self):
        """
        This function tests if an apikey is defined in the configfile.
        Otherwise it will ask the user to generate one and saves it to the
        configfile in the given sections.
        """
        try:
            if self.__apikey == "":
                res = input("[INFO]: No API-Key defined. Do you want to "
                            "generate one? "
                            "y/Y ")
                if res == "y" or res == "Y":
                    res = input("Please specify number of key (default is "
                                "10)? ")
                    if res != 10:
                        self.__apikey = self.generate_apikey(int(res))
                    else:
                        self.__apikey = self.generate_apikey()
                    #with open(self.path, 'w') as configfile:
                    #    self.config.write(configfile)
                    print("[INFO]: Random Key generated: '" + self.__apikey +
                          "'")
                else:
                    print("[INFO]: Default Key will be used: '1234'!")
            print("[INFO]: API-Key check success! " + self.__apikey)
        except Exception:
            print("[ERROR]: API-Key check failed. Please check configuration!")



class Agent:
# https://iotagent-node-lib.readthedocs.io/en/latest/
# https://fiware-iotagent-json.readthedocs.io/en/latest/usermanual/index.html
    def __init__(self, agent_name: str, config):
        self.name = agent_name
        self.test_config(config)
        self.host = config.data['iota']['host']
        self.port = config.data['iota']['port']
        self.url = self.host + ":" + self.port
        self.protocol = config.data['iota']['protocol']
        #TODO: Figuring our how to register the service and conncet with devices
        self.services = []

    def test_config(self, config):
        test.test_config(self.name, config.data)

    def test_connection(self, config):
        test.test_connection(self.name , config.data[self.name]['host']
                                 +":" +config.data[self.name]['port']+
                                 '/iot/about')

    def get_groups(self, device_group):
        url = self.url + '/iot/services'
        headers = DeviceGroup.get_header(device_group)
        response = requests.request("GET", url, headers=headers)
        print(response.text)

    def delete_group(self, device_group):
        url = self.url + '/iot/services'
        headers = DeviceGroup.get_header(device_group)
        querystring = {"resource": device_group.get_resource(),
                       "apikey": device_group.get_apikey()}
        response = requests.request("DELETE", url,
                                    headers=headers, params=querystring)
        if response.status_code==204:
            print("[INFO]: Device group successfully deleted!")
        else:
            print(response.text)

    def post_group(self, device_group:object, update:bool=True):
        url = self.url + '/iot/services'
        headers = {**requtils.HEADER_CONTENT_JSON, **device_group.get_header()}
        payload={}
        payload['services'] = [json.loads(device_group.get_json())]
        payload = json.dumps(payload, indent=4)
        print(payload)
        response = requests.request("POST", url, data=payload,
                                    headers=headers)
        if response.status_code not in [201, 200, 204]:
            print("[WARN] Unable to register default configuration for "
                  "service \"{}\", path \"{}\": \"{}\" {}".format(
                device_group.get_header()['fiware-service'],
                device_group.get_header()['fiware-servicepath'],
                "Code:" + str(response.status_code),
                response.text))
            return None
        #filip.orion.post(url, head, AUTH, json_dict)

    def update_group(self, device_group):
        url = self.url + '/iot/services'
        headers = {**requtils.HEADER_CONTENT_JSON, **device_group.get_header_last()}
        querystring ={"resource":device_group.get_resource_last(),
                      "apikey":device_group.get_apikey_last()}
        payload= json.loads(device_group.get_json())
        payload = json.dumps(payload, indent=4)
        print("[INFO]: Update group with:\n"+payload)
        response = requests.request("PUT", url,
                                    data=payload, headers=headers,
                                    params=querystring)
        print(url)
        if response.status_code not in [201, 200, 204]:
            print("[WARN]: Unable to update device group:\n")
            print(response.text)
            print("payload")
        else:
            print("[INFO]: Device group successfully updated!")
        # filip.orion.post(url, head, AUTH, json_dict)

    def post_device(self, device_group:object, device:object, update:bool=True):
        url = self.url + '/iot/devices'
        headers = {**requtils.HEADER_CONTENT_JSON, **device_group.get_header()}
        payload={}
        payload['devices'] = [json.loads(device.get_json())]
        payload = json.dumps(payload, indent=4)
        response = requests.request("POST", url, data=payload,
                                    headers=headers)

        print(url, payload, headers)
        if (response.status_code == 409) & (update== True):
            device_data = {}
            device_data["attributes"] = json.loads(device.get_json())["attributes"]
            device_data = json.dumps(device_data, indent=4)
            self.update_device(device_group, device, device_data)

        elif response.status_code != 201:
            print("[WARN]: Unable to post device:\n")
            print(response.text)
            print("payload")
        else:
            print("[INFO]: Device successfully posted!")

    def delete_device(self, device_group, device):
        # TODO: Check if
        url = self.url + '/iot/devices/'+ device.device_id
        headers = {**requtils.HEADER_CONTENT_JSON, **device_group.get_header()}
        response = requests.request("DELETE", url, headers=headers)
        if response.status_code == 204:
            print("[INFO]: Device successfully deleted!")
        else:
            print(response.text)


    def get_device(self, device_group, device):
        url = self.url + '/iot/devices/' + device.device_id
        headers = {**requtils.HEADER_CONTENT_JSON, **device_group.get_header()}
        payload = ""
        response = requests.request("GET", url, data=payload,
                                    headers=headers)
        print(response.text)

    def update_device(self, device_group, device, payload: json):
        url = self.url + '/iot/devices/' + device.device_id
        headers = {**requtils.HEADER_CONTENT_JSON, **device_group.get_header()}
        response = requests.request("PUT", url, data=payload,
                                    headers=headers)

        print(url, payload, headers)
        if response.status_code not in [201, 200, 204]:
            print("[WARN]: Unable to update device:\n")
            print(response.text)
            print("payload")
        else:
            print("[INFO]: Device successfully updated!")


### END of valid Code################

    def add_service(self, service_name: str, service_path: str,
                           **kwargs):
        device_group={'service': service_name,
                'service_path': service_path,
                'data':{
                    "entity_type": "Thing",
                    "protocol": kwargs.get("protocol", self.protocol),
                    "transport": kwargs.get("transport", "MQTT"),
                    "apikey": kwargs.get("apikey", "1234"),
                    "attributes": [],
                    "lazy": [],
                    "commands": [],
                    "static_attributes": []
                 }
             }



    def fetch_service(self, service: str, service_path: str) -> [dict]:
        resp = requests.get(self.url + "/iot/services",
                            headers=self._get_header(
            service, service_path))

        if resp.status_code == 200:
            return resp.json()["services"]
        else:
            print("[WARN] Unable to fetch configuration for service "
                  "\"{}\", path \"{}\": {}"
                  .format(service, service_path, resp.text))



