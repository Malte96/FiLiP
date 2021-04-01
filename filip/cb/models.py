from aenum import Enum
from typing import Any, List, Dict, Union, Optional, Pattern
from pydantic import BaseModel, \
    Field, \
    validator,  \
    root_validator, \
    create_model, \
    AnyHttpUrl, \
    Json
from datetime import datetime
from filip.core.models import DataType
from filip.core.simple_query_language import SimpleQuery


# Options for queries
class GetEntitiesOptions(str, Enum):
    _init_ = 'value __doc__'

    KEYVALUES = 'keyValues', ''
    VALUES = 'values', ''
    UNIQUE = 'unique', ''


class ContextMetadata(BaseModel):
    """
    Context metadata is used in FIWARE NGSI in several places, one of them being
    an optional part of the attribute value as described above. Similar to
    attributes, each piece of metadata has:

    Note that in NGSI it is not foreseen that metadata may contain nested
    metadata.
    """
    type: Optional[DataType] = Field(
        title="metadata type",
        description="a metadata type, describing the NGSI value type of the "
                    "metadata value Allowed characters "
                    "are the ones in the plain ASCII set, except the following "
                    "ones: control characters, whitespace, &, ?, / and #.",
        max_length=256,
        min_length=1,
        regex="^((?![?&#/\*])[\x00-\x7F])*$" # Make it FIWARE-Safe
    )
    value: Optional[DataType] = Field(
        title="metadata value",
        description="a metadata value containing the actual metadata"
    )

class NamedContextMetadata(ContextMetadata):
    name: str = Field(
        titel="metadata name",
        description="a metadata name, describing the role of the metadata in the "
                    "place where it occurs; for example, the metadata name "
                    "accuracy indicates that the metadata value describes how "
                    "accurate a given attribute value is. Allowed characters "
                    "are the ones in the plain ASCII set, except the following "
                    "ones: control characters, whitespace, &, ?, / and #.",
        max_length=256,
        min_length=1,
        regex="^((?![?&#/*])[\x00-\x7F])*$" # Make it FIWARE-Safe
    )


class ContextAttribute(BaseModel):
    type: DataType = Field(
        default=DataType.TEXT,
        description="The attribute type represents the NGSI value type of the "
                    "attribute value. Note that FIWARE NGSI has its own type "
                    "system for attribute values, so NGSI value types are not "
                    "the same as JSON types. Allowed characters "
                    "are the ones in the plain ASCII set, except the following "
                    "ones: control characters, whitespace, &, ?, / and #.",
        max_length = 256,
        min_length = 1,
        regex = "^((?![?&#/])[\x00-\x7F])*$", # Make it FIWARE-Safe
    )
    value: Union[float, int, bool, str] = Field(
        title="Attribute value",
        description="the actual data"
    )
    metadata: Optional[Union[Dict, ContextMetadata]] = Field(
        default={},
        title="Metadata",
        description="optional metadata describing properties of the attribute "
                    "value like e.g. accuracy, provider, or a timestamp")

    @validator('value')
    def validate_value_type(cls, v, values):
        type_ = values['type']
        if type_ == DataType.BOOLEAN:
            return bool(v)
        elif type_ == DataType.NUMBER:
            return float(v)
        else:
            return str(v)

    @validator('metadata')
    def validate_metadata_type(cls, v):
        if isinstance(v, Dict):
            if not v:
                return v
        else:
            return ContextMetadata(**v)

class NamedContextAttribute(ContextAttribute):
    """
    Context attributes are properties of context entities. For example, the
    current speed of a car could be modeled as attribute current_speed of entity
    car-104.

    In the NGSI data model, attributes have an attribute name, an attribute type
    an attribute value and metadata.
    """
    name: str = Field(
        titel="Attribute name",
        description="The attribute name describes what kind of property the "
                    "attribute value represents of the entity, for example "
                    "current_speed. Allowed characters "
                    "are the ones in the plain ASCII set, except the following "
                    "ones: control characters, whitespace, &, ?, / and #.",
        max_length = 256,
        min_length = 1,
        regex = "(^((?![?&#/])[\x00-\x7F])*$)(?!(id|type|geo:distance|\*))",
        # Make it FIWARE-Safe
    )
class ContextEntityKeyValues(BaseModel):
    id: str = Field(
        ...,
        title="Entity Id",
        description="Id of an entity in an NGSI context broker. "
                    "Allowed characters are the ones in the plain ASCII set, "
                    "except the following ones: control characters, "
                    "whitespace, &, ?, / and #.",
        example='Bcn-Welt',
        max_length=256,
        min_length=1,
        regex="^((?![?&#/])[\x00-\x7F])*$", # Make it FIWARE-Safe
        allow_mutation=False
    )
    type: str = Field(
        ...,
        title="Enity Type",
        description="Id of an entity in an NGSI context broker. "
                    "Allowed characters are the ones in the plain ASCII set, "
                    "except the following ones: control characters, "
                    "whitespace, &, ?, / and #.",
        example="Room",
        max_length=256,
        min_length=1,
        regex="^((?![?&#/])[\x00-\x7F])*$", # Make it FIWARE-Safe
        allow_mutation=False
    )

    class Config():
        extra = 'allow'
        validate_all = True
        validate_assignment = True


class ContextEntity(ContextEntityKeyValues):
    """
    Context entities, or simply entities, are the center of gravity in the
    FIWARE NGSI information model. An entity represents a thing, i.e., any
    physical or logical object (e.g., a sensor, a person, a room, an issue in
    a ticketing system, etc.). Each entity has an entity id.
    Furthermore, the type system of FIWARE NGSI enables entities to have an
    entity type. Entity types are semantic types; they are intended to describe
    the type of thing represented by the entity. For example, a context
    entity #with id sensor-365 could have the type temperatureSensor.

    Each entity is uniquely identified by the combination of its id and type.
    """
    def __init__(self,
                 id: str,
                 type: str,
                 **data):
        # There is currently no validation for extra fields
        data.update(self._validate_properties(data))
        super().__init__(id=id, type=type, **data)

    class Config():
        extra = 'allow'
        validate_all = True
        validate_assignment = True

    def _validate_properties(cls, data: Dict):
        attrs = {key: ContextAttribute.parse_obj(attr) for key, attr in \
                 data.items() if key not in ContextEntity.__fields__}
        return attrs

    def get_properties(self, format: str = 'list') -> Union[List[
        NamedContextAttribute], Dict[str, ContextAttribute]]:
        """
        Args:
            format:

        Returns:

        """
        if format == 'dict':
            return {key: ContextAttribute(**value) for key, value in
                    self.dict().items() if key not in ContextEntity.__fields__
                    and value.get('type') is not DataType.RELATIONSHIP}
        else:
            return [NamedContextAttribute(name=key, **value) for key, value in
                    self.dict().items() if key not in
                    ContextEntity.__fields__ and
                    value.get('type') is not DataType.RELATIONSHIP]

    def add_properties(self, attrs: Union[Dict[str, ContextAttribute],
                                         List[NamedContextAttribute]]):
        """

        Args:
            attrs:

        Returns:

        """
        if isinstance(attrs, List):
            attrs = {attr.name: ContextAttribute(**attr) for attr in attrs}
        for key, attr in attrs.items():
            self.__setattr__(name=key, value=attr)

    def get_relationships(self, format: str = 'list') -> Union[List[
                                           NamedContextAttribute], Dict[
                                           str, ContextAttribute]]:
        """

        Args:
            format:

        Returns:

        """
        if format == 'dict':
            return {key: ContextAttribute(**value) for key, value in
                    self.dict().items() if key not in ContextEntity.__fields__
                    and value.get('type') is DataType.RELATIONSHIP}
        else:
            return [NamedContextAttribute(name=key, **value) for key, value in
                    self.dict().items() if key not in
                    ContextEntity.__fields__ and
                    value.get('type') is DataType.RELATIONSHIP]

def username_alphanumeric(cls, v):
    #assert v.value.isalnum(), 'must be numeric'
    return v


def create_context_entity_model(name: str = None, data: Dict = None):
    properties = {key: (ContextAttribute, ...) for key in data.keys() if
                  key not in ContextEntity.__fields__}
    validators = {f'validate_test': validator('temperature')(
        username_alphanumeric)}
    return create_model(
        __model_name=name or 'GeneratedContextEntity',
        __base__=ContextEntity,
        __validators__=validators,
        **properties
    )


# Models for Subscriptions start here
class HttpMethods(str, Enum):
    _init_ = 'value __doc__'

    POST = "POST", "Post Method"
    PUT = "PUT", "Put Method"
    PATCH = "PATCH", "Patch Method"


class Http(BaseModel):
    url: AnyHttpUrl = Field(
        description="URL referencing the service to be invoked when a "
                    "notification is generated. An NGSIv2 compliant server "
                    "must support the http URL schema. Other schemas could "
                    "also be supported."
    )


class HttpCustom(Http):
    headers: Optional[Dict[str, Union[str, Json]]] = Field(
        description="a key-map of HTTP headers that are included in "
                    "notification messages."
    )
    qs: Optional[Dict[str, Union[str, Json]]] = Field(
        description="a key-map of URL query parameters that are included in "
                    "notification messages."
    )
    method: str = Field(
        default=HttpMethods.POST,
        description="the method to use when sending the notification "
                    "(default is POST). Only valid HTTP methods are allowed. "
                    "On specifying an invalid HTTP method, a 400 Bad Request "
                    "error is returned."
    )
    payload: Optional[str] = Field(
        description='the payload to be used in notifications. If omitted, the '
                    'default payload (see "Notification Messages" sections) '
                    'is used.'
    )


class AttrsFormat(str, Enum):
    _init_ = 'value __doc__'

    NORMALIZED = "normalized", "Normalized message representation"
    KEYVALUE = "keyValues", "Key value message representation"
    VALUES = "values", "Key value message representation"


class NotificationMessage(BaseModel):
    subscriptionId: Optional[str] = Field(
        description="Id of the subscription the notification comes from",
    )
    data: ContextEntity = Field(
        description="is an array with the notification data itself which "
                    "includes the entity and all concerned attributes. Each "
                    "element in the array corresponds to a different entity. "
                    "By default, the entities are represented in normalized "
                    "mode. However, using the attrsFormat modifier, a "
                    "simplified representation mode can be requested."
    )


class Notification(BaseModel):
    """
    If the notification attributes are left empty, all attributes will be
    included in the notifications. Otherwise, only the specified ones will
    be included.
    :param attribute_type: either 'attrs' or 'exceptAttrs'
    :param _list: list of either 'attrs' or 'exceptAttrs' attributes
    """
    attrs: Optional[List[str]] = Field(
        description='List of attributes to be included in notification '
                    'messages. It also defines the order in which attributes '
                    'must appear in notifications when attrsFormat value is '
                    'used (see "Notification Messages" section). An empty list '
                    'means that all attributes are to be included in '
                    'notifications. See "Filtering out attributes and '
                    'metadata" section for more detail.'
    )
    exceptAttrs: Optional[List[str]] = Field(
        description='List of attributes to be excluded from the notification '
                    'message, i.e. a notification message includes all entity '
                    'attributes except the ones listed in this field.'
    )
    http: Optional[Http] = Field(
        description='It is used to convey parameters for notifications '
                    'delivered through the HTTP protocol. Cannot be used '
                    'together with "httpCustom"'
    )
    httpCustom: Optional[HttpCustom] = Field(
        description='It is used to convey parameters for notifications '
                    'delivered through the HTTP protocol. Cannot be used '
                    'together with "http"'
    )
    attrsFormat: Optional[AttrsFormat] = Field(
        default= AttrsFormat.NORMALIZED,
        description='specifies how the entities are represented in '
                    'notifications. Accepted values are normalized (default), '
                    'keyValues or values. If attrsFormat takes any value '
                    'different than those, an error is raised. See detail in '
                    '"Notification Messages" section.'
    )
    metadata: Optional[Any] = Field(
        description='List of metadata to be included in notification messages. '
                    'See "Filtering out attributes and metadata" section for '
                    'more detail.'
    )

    @validator('httpCustom')
    def validate_http(cls, v, values, field):
        if v is not None:
            assert values['http'] == None
        return v

    @validator('exceptAttrs')
    def validate_attr(cls, v, values):
        if v is not None:
            assert values['attrs'] == None
        return v

class NotificationResponse(Notification):
    timesSent: int = Field(
        description='(not editable, only present in GET operations): '
                    'Number of notifications sent due to this subscription.'
    )
    lastNotification: datetime = Field(
        description='(not editable, only present in GET operations): '
                    'Last notification timestamp in ISO8601 format.'
    )
    lastFailure: Optional[datetime] = Field(
        description='(not editable, only present in GET operations): '
                    'Last failure timestamp in ISO8601 format. Not present if '
                    'subscription has never had a problem with notifications.'
    )
    lastSuccess: Optional[datetime] = Field(
        description='(not editable, only present in GET operations): '
                    'Timestamp in ISO8601 format for last successful '
                    'notification. Not present if subscription has never '
                    'had a successful notification.'
    )


class Status(str, Enum):
    _init_ = 'value __doc__'

    ACTIVE = "active", "for active subscriptions"
    INACTIVE = "inactive", "for inactive subscriptions"
    FAILED = "failed", "for failed subscription"
    EXPIRED = "expired", "for expired subscription"


class Expression(BaseModel):
    q: Optional[Union[str, SimpleQuery]] = Field(
        description=''
    )
    mq: Optional[Union[str, SimpleQuery]] = Field()
    # TODO: Adding additional query options
    # http://telefonicaid.github.io/fiware-orion/api/v2/stable/

    # TODO: This does not work yet
    #@validator('q', 'mq')
    #def validate_expressions(cls, v):
    #    if isinstance(v, str):
    #        return SimpleQuery.parse_str(v)

class Condition(BaseModel):
    attrs: List[str] = Field(
        description='array of attribute names'
    )
    expression: Optional[Union[str, Expression]] = Field(
        description='an expression composed of q, mq, georel, geometry and '
                    'coords (see "List entities" operation above about this '
                    'field).'
    )


class Entity(BaseModel):
    """
    Entity pattern
    """
    id: Optional[str] = Field(regex='\w')
    idPattern: Optional[Pattern]
    type: Optional[str] = Field(regex='\w')
    typePattern: Optional[Pattern]

    @root_validator()
    def validate_conditions(cls, values):
        assert ((values['id'] and not values['idPattern']) or
                (not values['id'] and values['idPattern'])), \
            "Both cannot be used at the same time, but one of them " \
            "must be present."
        if values['type'] or values.get('typePattern', None):
            assert ((values['type'] and not values['typePattern']) or
                    (not values['id'] and values['typePattern'])), \
                "Type or pattern of the affected entities. " \
                "Both cannot be used at the same time."
        return values


class Subject(BaseModel):
    entities: List[Entity] = Field(
        description="A list of objects, each one composed of by an Entity "
                    "Object:"
    )
    condition: Optional[Condition] = Field()


class Subscription(BaseModel):
    """
    Subscription payload validations
    https://fiware-orion.readthedocs.io/en/master/user/ngsiv2_implementation_notes/index.html#subscription-payload-validations
    """
    id: Optional[str] = Field(
        description="Subscription unique identifier. Automatically created at "
                    "creation time."
    )
    description: Optional[str] = Field(
        description="A free text used by the client to describe the "
                    "subscription."
    )
    status: Optional[Status] = Field(
        default=Status.ACTIVE,
        description="Either active (for active subscriptions) or inactive "
                    "(for inactive subscriptions). If this field is not "
                    "provided at subscription creation time, new subscriptions "
                    "are created with the active status, which can be changed"
                    " by clients afterwards. For expired subscriptions, this "
                    "attribute is set to expired (no matter if the client "
                    "updates it to active/inactive). Also, for subscriptions "
                    "experiencing problems with notifications, the status is "
                    "set to failed. As soon as the notifications start working "
                    "again, the status is changed back to active."
    )
    subject: Subject = Field(
        description="An object that describes the subject of the subscription.",
        example={
            'entities': [{'idPattern': '.*', 'type': 'Room'}],
            'condition': {
                'attrs': ['temperature'],
                'expression': {'q': 'temperature>40'},
            },
        },
    )
    notification: Notification = Field(
        description="An object that describes the notification to send when "
                    "the subscription is triggered.",
        example={
            'http': {'url': 'http://localhost:1234'},
            'attrs': ['temperature', 'humidity'],
        },
    )
    expires: Optional[datetime] = Field(
        description="Subscription expiration date in ISO8601 format. "
                    "Permanent subscriptions must omit this field."
    )

    throttling: Optional[int] = Field(
        description="Minimal period of time in seconds which "
                    "must elapse between two consecutive notifications. "
                    "It is optional."
    )

# Registration Models
class ForwardingMode(str, Enum):
    _init_ = 'value __doc__'

    NONE = "none", "This provider does not support request forwarding."
    QUERY = "query", "This provider only supports request forwarding to query " \
                     "data."
    UPDATE = "update", "This provider only supports request forwarding to " \
                       "update data."
    ALL = "all", "This provider supports both query and update forwarding " \
                 "requests. (Default value)"


class Provider(BaseModel):
    http: AnyHttpUrl = Field(
        description="It is used to convey parameters for providers that "
                    "deliver information through the HTTP protocol. (Only "
                    "protocol supported nowadays). It must contain a subfield "
                    "named url with the URL that serves as the endpoint that "
                    "offers the providing interface. The endpoint must not "
                    "include the protocol specific part (for instance "
                    "/v2/entities). "
    )
    supportedForwardingMode: ForwardingMode = Field(
        default=ForwardingMode.ALL,
        description="It is used to convey the forwarding mode supported by "
                    "this context provider. By default all."
    )

class ForwardingInformation(BaseModel):
    timesSent: int = Field(
        description="(not editable, only present in GET operations): "
                    "Number of request forwardings sent due to this "
                    "registration."
    )
    lastForwarding: datetime = Field(
        description="(not editable, only present in GET operations): "
                    "Last forwarding timestamp in ISO8601 format."
    )
    lastFailure: Optional[datetime] = Field(
        description="(not editable, only present in GET operations): "
                    "Last failure timestamp in ISO8601 format. Not present "
                    "if registration has never had a problem with forwarding."
    )
    lastSuccess: Optional[datetime] = Field(
        description="(not editable, only present in GET operations): "
                    "Timestamp in ISO8601 format for last successful "
                    "request forwarding. Not present if registration has "
                    "never had a successful notification."
    )

    class Config:
        allow_mutation = False

class DataProvided(BaseModel):
    entities: List[Entity] = Field(
        description="A list of objects, each one composed by an entity object"
    )
    attrs: Optional[List[str]] = Field(
        description="List of attributes to be provided "
                    "(if not specified, all attributes)"
    )
    expression: Optional[Union[str, Expression]] = Field(
        description="By means of a filtering expression, allows to express "
                    "what is the scope of the data provided. Currently only "
                    "geographical scopes are supported "
    )


class Registration(BaseModel):
    """
    A Context Registration allows to bind external context information
    sources so that they can play the role of providers of certain subsets
    (entities, attributes) of the context information space, including those
    located at specific geographical areas.
    """

    id: Optional[str] = Field(
        description="Unique identifier assigned to the registration. "
                    "Automatically generated at creation time."
    )
    description: Optional[str] = Field(
        description="A free text used by the client to describe the "
                    "registration.",
        example="Relative Humidity Context Source"
    )
    provider: Provider = Field(
        description="Object that describes the context source registered.",
        example='"http": {"url": "http://localhost:1234"}'
    )
    dataProvived: DataProvided = Field(
        description="Object that describes the data provided by this source",
        example='{'
                '   "entities": [{"id": "room2", "type": "Room"}],'
                '   "attrs": ["relativeHumidity"]'
                '},'
    )
    status: Optional[Status] = Field(
        default=Status.ACTIVE,
        description="Either active (for active registration) or inactive "
                    "(for inactive registration). If this field is not "
                    "provided at rtegistration creation time, new registration "
                    "are created with the active status, which can be changed"
                    " by clients afterwards. For expired registration, this "
                    "attribute is set to expired (no matter if the client "
                    "updates it to active/inactive). Also, for subscriptions "
                    "experiencing problems with notifications, the status is "
                    "set to failed. As soon as the notifications start working "
                    "again, the status is changed back to active."
    )
    expires: Optional[datetime] = Field(
        description="Registration expiration date in ISO8601 format. "
                    "Permanent registrations must omit this field."
    )
    forwardingInformation: Optional[ForwardingInformation] = Field(
        description="Information related to the forwarding operations made "
                    "against the provider. Automatically provided by the "
                    "implementation, in the case such implementation supports "
                    "forwarding capabilities."
    )

class Query(BaseModel):
    entities: List[Entity] = Field(
        description="a list of entities to search for. Each element is "
                    "represented by a JSON object"
    )
    attrs: Optional[List[str]] = Field(
        description="List of attributes to be provided "
                    "(if not specified, all attributes)."
    )
    expression: Optional[Expression] = Field(
        description="An expression composed of q, mq, georel, geometry and "
                    "coords "
    )
    metadata: Optional[List[str]] = Field(
        description='a list of metadata names to include in the response. '
                    'See "Filtering out attributes and metadata" section for '
                    'more detail.'
    )


class ActionType(str, Enum):
    _init_ = 'value __doc__'
    APPEND = "append", "maps to POST /v2/entities (if the entity does not " \
                       "already exist) or POST /v2/entities/<id>/attrs (if " \
                       "the entity already exists). "
    APPEND_STRICT = "appendStrict", "maps to POST /v2/entities (if the entity " \
                                    "does not already exist) or POST " \
                                    "/v2/entities/<id>/attrs?options=append " \
                                    "(if the entity already exists)."
    UPDATE = "update", "maps to PATCH /v2/entities/<id>/attrs."
    DELETE = "delete", "maps to DELETE /v2/entities/<id>/attrs/<attrName> on " \
                       "every attribute included in the entity or to DELETE " \
                       "/v2/entities/<id> if no attribute were included in " \
                       "the entity."
    REPLACE = "replace", "maps to PUT /v2/entities/<id>/attrs"


class Update(BaseModel):
    actionType: ActionType = Field(
        description="actionType, to specify the kind of update action to do: "
                    "either append, appendStrict, update, delete, or replace. "
    )
    entities: List[ContextEntity] = Field(
        description="an array of entities, each entity specified using the "
                    "JSON entity representation format "
    )


class Notify(BaseModel):
    subscriptionId: str = Field(
        description=""
    )

# TODO: Add Registrations and Relationships
#class Relationship:
#    """
#    Class implements the concept of FIWARE Entity Relationships.
#    """
#    def __init__(self, ref_object: Entity, subject: Entity, predicate: str =
        #    None):
#        """
#        :param ref_object:  The parent / object of the relationship
#        :param subject: The child / subject of the relationship
#        :param predicate: currently not supported -> describes the
        #        relationship between object and subject
#        """
#        self.object = ref_object
#        self.subject = subject
#        self.predicate = predicate
#        self.add_ref()
#
#    def add_ref(self):
#        """
#        Function updates the subject Attribute with the relationship attribute
#        :return:
#        """
#        ref_attr = json.loads(self.get_ref())
#        self.subject.add_attribute(ref_attr)
#
#    def get_ref(self):
#        """
#        Function creates the NGSI Ref schema in a ref_dict, needed for the
        #        subject
#        :return: ref_dict
#        """
#        ref_type = self.object.type
#        ref_key = "ref" + str(ref_type)
#        ref_dict = dict()
#        ref_dict[ref_key] = {"type": "Relationship",
#                             "value": self.object.id}
#
#        return json.dumps(ref_dict)
#
#    def get_json(self):
#        """
#        Function returns a JSON to describe the Relationship,
#        which then can be pushed to orion
#        :return: whole_dict
#        """
#        temp_dict = dict()
#        temp_dict["id"] = self.subject.id
#        temp_dict["type"] = self.subject.type
#        ref_dict = json.loads(self.get_ref())
#        whole_dict = {**temp_dict, **ref_dict}
#        return json.dumps(whole_dict)
#
#
