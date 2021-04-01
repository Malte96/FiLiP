import re
import requests
from math import inf
from typing import Dict, List, Any, Union
from pydantic import \
    parse_obj_as, \
    PositiveInt, \
    PositiveFloat, \
    AnyHttpUrl
from urllib.parse import urljoin
from filip.core.base_client import BaseClient
from filip.core.settings import settings
from filip.core.models import FiwareHeader, PaginationMethod
from filip.core.simple_query_language import SimpleQuery
from filip.cb.models import \
    ContextEntity, \
    ContextEntityKeyValues, \
    ContextAttribute, \
    NamedContextAttribute, \
    GetEntitiesOptions, \
    Subscription,\
    Registration,\
    Update, \
    Query


class ContextBrokerClient(BaseClient):
    """
    Implementation of NGSI Context Broker functionalities, such as creating
    entities and subscriptions; retrieving, updating and deleting data.
    Further documentation:
    https://fiware-orion.readthedocs.io/en/master/

    Api specifications for v2 are located here:
    http://telefonicaid.github.io/fiware-orion/api/v2/stable/
    """

    def __init__(self,
                 *,
                 url: str = None,
                 session: requests.Session = None,
                 fiware_header: FiwareHeader = None):
        url = url or settings.CB_URL
        super().__init__(url=url,
                         session=session,
                         fiware_header=fiware_header)

    def __pagination__(self,
                       *,
                       method: PaginationMethod = PaginationMethod.GET,
                       url: str,
                       headers: Dict,
                       limit: Union[PositiveInt, PositiveFloat] = None,
                       params: Dict = None,
                       data: str = None) -> Union[List[Dict],
                                                  requests.Response]:
        """
        NGSIv2 implements a pagination mechanism in order to help clients to
        retrieve large sets of resources. This mechanism works for all listing
        operations in the API (e.g. GET /v2/entities, GET /v2/subscriptions,
        POST /v2/op/query, etc.). This function helps getting datasets that are
        larger than the limit for the different GET operations.

        https://fiware-orion.readthedocs.io/en/master/user/pagination/index.html

        Args:
            url: Information about the url, obtained from the original function
            headers: The headers from the original function
            params:
            limit:

        Returns:
            object:

        """
        if limit is None:
            limit = inf
        if limit > 1000:
            params['limit'] = 1000  # maximum items per request
        else:
            params['limit'] = limit

        res = self.session.request(method=method,
                                   url=url,
                                   params=params,
                                   headers=headers,
                                   data=data)
        if res.ok:
            items = res.json()
            # do pagination
            count = int(res.headers['Fiware-Total-Count'])

            while len(items) < limit and len(items) < count:
                # Establishing the offset from where entities are retrieved
                params['offset'] = len(items)
                params['limit'] = min(1000, (limit - len(items)))
                res = self.session.request(method=method,
                                           url=url,
                                           params=params,
                                           headers=headers,
                                           data=data)
                if res.ok:
                    items.extend(res.json())
                else:
                    res.raise_for_status()
            self.logger.debug(f'Received: {items}')
            return items
        else:
            res.raise_for_status()

    # MANAGEMENT API
    def get_version(self) -> Dict:
        """
        Gets version of IoT Agent
        Returns:
            Dictionary with response
        """
        url = urljoin(self.base_url, '/version')
        try:
            res = self.session.get(url=url, headers=self.headers)
            if res.ok:
                return res.json()
            else:
                res.raise_for_status()
        except requests.RequestException as err:
            self.logger.error(err)
            raise

    def get_resources(self) -> Dict:
        """
        Re
        Returns:

        """
        url = urljoin(self.base_url, '/v2')
        try:
            res = self.session.get(url=url, headers=self.headers)
            if res.ok:
                return res.json()
            else:
                res.raise_for_status()
        except requests.RequestException as err:
            self.logger.error(err)
            raise

    # STATISTICS API
    def get_statistics(self):
        """
        Gets statistics of context broker
        Returns:
            Dictionary with response
        """
        url = urljoin(self.base_url, 'statistics')
        try:
            res = self.session.get(url=url, headers=self.headers)
            if res.ok:
                return res.json()
            else:
                res.raise_for_status()
        except requests.RequestException as err:
            self.logger.error(err)
            raise

    # CONTEXT MANAGEMENT API ENDPOINTS
    # Entity Operations
    def post_entity(self, entity: ContextEntity, update: bool = False):
        """
        Function registers an Object with the NGSI Context Broker,
        if it already exists it can be automatically updated
        if the overwrite bool is True
        First a post request with the entity is tried, if the response code
        is 422 the entity is uncrossable, as it already exists there are two
        options, either overwrite it, if the attribute have changed
        (e.g. at least one new/new values) (update = True) or leave
        it the way it is (update=False)
        Args:
            update (bool): If the response.status_code is 422, whether the old
            entity should be updated or not
            entity (ContextEntity): Context Entity Object
        """
        url = urljoin(self.base_url, 'v2/entities')
        headers = self.headers.copy()
        try:
            res = self.session.post(
                url=url,
                headers=headers,
                json=entity.dict(exclude_unset=True,
                                 exclude_defaults=True,
                                 exclude_none=True))
            if res.ok:
                self.logger.info(f"Entity successfully posted!")
                return res.headers.get('Location')
            else:
                res.raise_for_status()
        except requests.RequestException as err:
            if update and err.response.status_code == 422:
                return self.update_entity(entity=entity, add=False)
            msg = "Could not post entity {entity.id}"
            self.log_error(err=err, msg=msg)
            raise

    def get_entity_list(self,
                        *,
                        entity_ids: List[str] = None,
                        entity_types: List[str] = None,
                        id_pattern: str = None,
                        type_pattern: str = None,
                        q: Union[str, SimpleQuery] = None,
                        mq: Union[str, SimpleQuery] = None,
                        georel: str = None,
                        geometry: str = None,
                        coords: str = None,
                        limit: int = inf,
                        attrs: List[str] = None,
                        metadata: str = None,
                        order_by: str = None,
                        options: List[GetEntitiesOptions] = None
                        ) -> Union[List[ContextEntity], List[Dict[str, Any]]]:
        """
        Retrieves a list of context entities that match different criteria by
        id, type, pattern matching (either id or type) and/or those which
        match a query or geographical query (see Simple Query Language and
        Geographical Queries). A given entity has to match all the criteria
        to be retrieved (i.e., the criteria is combined in a logical AND
        way). Note that pattern matching query parameters are incompatible
        (i.e. mutually exclusive) with their corresponding exact matching
        parameters, i.e. idPattern with id and typePattern with type.

        Args:
            entity_ids: A comma-separated list of elements. Retrieve entities
                whose ID matches one of the elements in the list.
                Incompatible with idPattern Example: Boe_Idarium
            entity_types: comma-separated list of elements. Retrieve entities
                whose type matches one of the elements in the list.
                Incompatible with typePattern. Example: Room.
            id_pattern: A correctly formated regular expression. Retrieve
                entities whose ID matches the regular expression. Incompatible
                with id. Example: Bode_.*.
            type_pattern: A correctly formated regular expression. Retrieve
                entities whose type matches the regular expression.
                Incompatible with type. Example: Room_.*.
            q (SimpleQuery): A query expression, composed of a list of
                statements separated by ;, i.e.,
                q=statement1;statement2;statement3. See Simple Query
                Language specification. Example: temperature>40.
            mq (SimpleQuery): A  query expression for attribute metadata,
                composed of a list of statements separated by ;, i.e.,
                mq=statement1;statement2;statement3. See Simple Query
                Language specification. Example: temperature.accuracy<0.9.
            georel: Spatial relationship between matching entities and a
                reference shape. See Geographical Queries. Example: near.
            geometry: Geografical area to which the query is restricted.
                See Geographical Queries. Example: point.
            coords: List of latitude-longitude pairs of coordinates separated
                by ';'. See Geographical Queries. Example: 41.390205,
                2.154007;48.8566,2.3522.
            limit: Limits the number of entities to be retrieved Example: 20
            attrs: Comma-separated list of attribute names whose data are to
                be included in the response. The attributes are retrieved in
                the order specified by this parameter. If this parameter is
                not included, the attributes are retrieved in arbitrary
                order. See "Filtering out attributes and metadata" section
                for more detail. Example: seatNumber.
            metadata: A list of metadata names to include in the response.
                See "Filtering out attributes and metadata" section for more
                detail. Example: accuracy.
            order_by: Criteria for ordering results. See "Ordering Results"
                section for details. Example: temperature,!speed.
            options (GetEntitiesOptions): Response Format. Note: That if
                'keyValues' or 'values' are used the response model will
                change to List[Dict[str, Any]]
        Returns:

        """
        url = urljoin(self.base_url, 'v2/entities/')
        headers = self.headers.copy()
        params = {}

        if entity_ids and id_pattern:
            raise ValueError
        if entity_types and type_pattern:
            raise ValueError
        if entity_ids:
            if not isinstance(entity_ids, list):
                entity_ids = [entity_ids]
            params.update({'id': ','.join(entity_ids)})
        if id_pattern:
            try:
                re.compile(id_pattern)
            except re.error:
                raise
            params.update({'idPattern': id_pattern})
        if entity_types:
            if not isinstance(entity_types, list):
                entity_types = [entity_types]
            params.update({'type': ','.join(entity_types)})
        if type_pattern:
            try:
                re.compile(type_pattern)
            except re.error:
                raise
            params.update({'typePattern': type_pattern})
        if attrs:
            params.update({'attrs': ','.join(attrs)})
        if metadata:
            params.update({'metadata': ','.join(metadata)})
        if q:
            params.update({'q': str(q)})
        if mq:
            params.update({'mq': str(mq)})
        if geometry:
            params.update({'geometry': geometry})
        if georel:
            params.update({'georel': georel})
        if coords:
            params.update({'coords': coords})
        if order_by:
            params.update({'orderBy': order_by})
        if options:
            if not isinstance(options, list):
                options = [options]
            options = options + ['count']
            options = ','.join(options)
        else:
            options = 'count'
        params.update({'options': options})

        try:
            items = self.__pagination__(method=PaginationMethod.GET,
                                        limit=limit,
                                        url=url,
                                        params=params,
                                        headers=headers)
            if options == 'count':
                return parse_obj_as(List[ContextEntity], items)
            elif 'keyValues' in options:
                return parse_obj_as(List[ContextEntityKeyValues], items)
            else:
                return items

        except requests.RequestException as err:
            msg = "Could not load entities"
            self.log_error(err=err, msg=msg)
            raise

    def get_entity(self,
                   entity_id: str,
                   entity_type: str = None,
                   attrs: List[str] = None,
                   metadata: List[str] = None,
                   options: str = None) -> ContextEntity:
        """
        This operation must return one entity element only, but there may be
        more than one entity with the same ID (e.g. entities with same ID but
        different types). In such case, an error message is returned, with
        the HTTP status code set to 409 Conflict.

        Args:
            entity_id (String): Id of the entity to be retrieved
            entity_type (String): Entity type, to avoid ambiguity in case
            there are several entities with the same entity id.
            attrs (List of Strings): List of attribute names whose data must be 
            included in the response. The attributes are retrieved in the order
            specified by this parameter.
            See "Filtering out attributes and metadata" section for more
            detail. If this parameter is not included, the attributes are
            retrieved in arbitrary order, and all the attributes of the entity
            are included in the response. Example: temperature,humidity.
            metadata (List of Strings): A list of metadata names to include in
            the response. See "Filtering out attributes and metadata" section
            for more detail. Example: accuracy.
            options (Dict):
        Returns:
            ContextEntity
        """
        url = urljoin(self.base_url, f'v2/entities/{entity_id}')
        headers = self.headers.copy()
        params = {}
        if entity_type:
            params.update({'type': entity_type})
        if attrs:
            params.update({'attrs': ','.join(attrs)})
        if metadata:
            params.update({'metadata': ','.join(metadata)})
        if options:
            params.update({'options': ','.join(options)})
        try:
            res = self.session.get(url=url, params=params, headers=headers)
            if res.ok:
                self.logger.debug(f'Received: {res.json()}')
                return ContextEntity(**res.json())
            else:
                res.raise_for_status()
        except requests.RequestException as err:
            msg = f"Could not load entity {entity_id}"
            self.log_error(err=err, msg=msg)
            raise

    def get_entity_attributes(self,
                              entity_id: str,
                              entity_type: str = None,
                              attrs: List[str] = None,
                              metadata: List[str] = None,
                              options: str = None) -> Dict[str, ContextEntity]:
        """
        This request is similar to retrieving the whole entity, however this
        one omits the id and type fields. Just like the general request of
        getting an entire entity, this operation must return only one entity
        element. If more than one entity with the same ID is found (e.g.
        entities with same ID but different type), an error message is
        returned, with the HTTP status code set to 409 Conflict.

        Args:
            entity_id (String): Id of the entity to be retrieved
            entity_type (String): Entity type, to avoid ambiguity in case
            there are several entities with the same entity id.
            attrs (List of Strings): List of attribute names whose data must be
            included in the response. The attributes are retrieved in the order
            specified by this parameter.
            See "Filtering out attributes and metadata" section for more
            detail. If this parameter is not included, the attributes are
            retrieved in arbitrary order, and all the attributes of the entity
            are included in the response. Example: temperature,humidity.
            metadata (List of Strings): A list of metadata names to include in
            the response. See "Filtering out attributes and metadata" section
            for more detail. Example: accuracy.
            options (Dict):
        Returns:
            Dict
        """
        url = urljoin(self.base_url, f'v2/entities/{entity_id}/attrs')
        headers = self.headers.copy()
        params = {}
        if entity_type:
            params.update({'type': entity_type})
        if attrs:
            params.update({'attrs': ','.join(attrs)})
        if metadata:
            params.update({'metadata': ','.join(metadata)})
        if options:
            params.update({'options': ','.join(options)})
        try:
            res = self.session.get(url=url, params=params, headers=headers)
            if res.ok:
                return {key: ContextAttribute(**values)
                        for key, values in res.json().items()}
            else:
                res.raise_for_status()
        except requests.RequestException as err:
            msg = f"Could not load attributes from entity {entity_id}!"
            self.log_error(err=err, msg=msg)
            raise

    def update_entity(self,
                      entity: ContextEntity,
                      options: str = None,
                      add=False):
        """
        The request payload is an object representing the attributes to
        append or update.
        Args:
            entity (ContextEntity):
            add (bool):
            options:
        Returns:

        """
        url = urljoin(self.base_url, f'v2/entities/{entity.id}/attrs')
        headers = self.headers.copy()
        params = {}
        if options:
            params.update({'options': options})
        try:
            res = self.session.post(url=url,
                                    headers=headers,
                                    json=entity.dict(exclude={'id', 'type'},
                                                     exclude_unset=True,
                                                     exclude_none=True))
            if res.ok:
                self.logger.info(f"Entity '{entity.id}' successfully updated!")
            else:
                res.raise_for_status()
        except requests.RequestException as err:
            msg = f"Could not update entity {entity.id}!"
            self.log_error(err=err, msg=msg)
            raise

    def delete_entity(self, entity_id: str, entity_type: str = None) -> None:

        """
        Remove a entity from the context broker. No payload is required
        or received.

        Args:
            entity_id: Id of the entity to be deleted
            entity_type: several entities with the same entity id.
        Returns:
            None
        """
        url = urljoin(self.base_url, f'v2/entities/{entity_id}')
        headers = self.headers.copy()
        if entity_type:
            params = {'type': entity_type}
        else:
            params = {}
        try:
            res = self.session.delete(url=url, params=params, headers=headers)
            if res.ok:
                self.logger.info(f"Entity '{entity_id}' successfully deleted!")
            else:
                res.raise_for_status()
        except requests.RequestException as err:
            msg = f"Could not delete entity {entity_id}!"
            self.log_error(err=err, msg=msg)
            raise

    def replace_entity_attributes(self,
                                  entity: ContextEntity,
                                  options: str = None,
                                  append: bool = True):
        """
        The attributes previously existing in the entity are removed and
        replaced by the ones in the request.

        Args:
            entity (ContextEntity):
            append (bool):
            options:
        Returns:

        """
        url = urljoin(self.base_url, f'v2/entities/{entity.id}/attrs')
        headers = self.headers.copy()
        params = {}
        if options:
            params.update({'options': options})
        try:
            res = self.session.put(url=url,
                                   headers=headers,
                                   json=entity.dict(exclude={'id', 'type'},
                                                    exclude_unset=True,
                                                    exclude_none=True))
            if res.ok:
                self.logger.info(f"Entity '{entity.id}' successfully updated!")
            else:
                res.raise_for_status()
        except requests.RequestException as err:
            msg = f"Could not replace attribute of entity {entity.id}!"
            self.log_error(err=err, msg=msg)
            raise

    # Attribute operations
    def get_attribute(self,
                      entity_id: str,
                      attr_name: str,
                      entity_type: str = None,
                      metadata: str = None) -> ContextAttribute:
        """
        Retrieves a specified attribute from an entity.
        Args:
            entity_id: Id of the entity. Example: Bcn_Welt
            attr_name: Name of the attribute to be retrieved.
                Example: temperature.
            entity_type:
            metadata: A list of metadata names to include in the response.
                See "Filtering out attributes and metadata" section for
                more detail.

        Returns:
            The content of the retrieved attribute as ContextAttribute
        Raises:
            Error

        """
        url = urljoin(self.base_url,
                      f'v2/entities/{entity_id}/attrs/{attr_name}')
        headers = self.headers.copy()
        params = {}
        if entity_type:
            params.update({'type': entity_type})
        if metadata:
            params.update({'metadata': ','.join(metadata)})
        try:
            res = self.session.get(url=url, params=params, headers=headers)
            if res.ok:
                self.logger.debug(f'Received: {res.json()}')
                return ContextAttribute(**res.json())
            else:
                res.raise_for_status()
        except requests.RequestException as err:
            msg = f"Could not load attribute '{attr_name}' from entity" \
                  f"'{entity_id}' "
            self.log_error(err=err, msg=msg)
            raise

    def update_entity_attribute(self,
                                entity_id: str,
                                attr: NamedContextAttribute,
                                entity_type: str = None):
        """
        Updates a specified attribute from an entity.
        Args:
            attr:
            entity_id: Id of the entity. Example: Bcn_Welt
            entity_type: Entity type, to avoid ambiguity in case there are
                several entities with the same entity id.
        """
        url = urljoin(self.base_url,
                      f'v2/entities/{entity_id}/attrs/{attr.name}')
        headers = self.headers.copy()
        params = {}
        if entity_type:
            params.update({'type': entity_type})
        try:
            res = self.session.put(url=url,
                                   headers=headers,
                                   json=attr.dict(exclude={'name'},
                                                  exclude_unset=True,
                                                  exclude_none=True))
            if res.ok:
                self.logger.info(f"Attribute '{attr.name}' of '{entity_id}' "
                                 f"successfully updated!")
            else:
                res.raise_for_status()
        except requests.RequestException as err:
            msg = f"Could not update attribute '{attr.name}' of entity" \
                  f"'{entity_id}' "
            self.log_error(err=err, msg=msg)
            raise

    def delete_entity_attribute(self,
                                entity_id: str,
                                attr_name: str,
                                entity_type: str = None) -> None:
        """
        Removes a specified attribute from an entity.
        Args:
            entity_id: Id of the entity. Example: Bcn_Welt
            attr_name: Name of the attribute to be retrieved.
                Example: temperature.
            entity_type: Entity type, to avoid ambiguity in case there are
                several entities with the same entity id.
        Raises:
            Error

        """
        url = urljoin(self.base_url,
                      f'v2/entities/{entity_id}/attrs/{attr_name}')
        headers = self.headers.copy()
        params = {}
        if entity_type:
            params.update({'type': entity_type})
        try:
            res = self.session.delete(url=url, headers=headers)
            if res.ok:
                self.logger.info(f"Attribute '{attr_name}' of '{entity_id}' "
                                 f"successfully deleted!")
            else:
                res.raise_for_status()
        except requests.RequestException as err:
            msg = f"Could not delete attribute '{attr_name}' of entity" \
                  f"'{entity_id}' "
            self.log_error(err=err, msg=msg)
            raise

    # Attribute value operations
    def get_attribute_value(self,
                            entity_id: str,
                            attr_name: str,
                            entity_type: str = None) -> Any:
        """
        This operation returns the value property with the value of the
        attribute.

        Args:
            entity_id: Id of the entity. Example: Bcn_Welt
            attr_name: Name of the attribute to be retrieved.
                Example: temperature.
            entity_type: Entity type, to avoid ambiguity in case there are
                several entities with the same entity id.

        Returns:

        """
        url = urljoin(self.base_url,
                      f'v2/entities/{entity_id}/attrs/{attr_name}/value')
        headers = self.headers.copy()
        params = {}
        if entity_type:
            params.update({'type': entity_type})
        try:
            res = self.session.get(url=url, params=params, headers=headers)
            if res.ok:
                self.logger.debug(f'Received: {res.json()}')
                return res.json()
            else:
                res.raise_for_status()
        except requests.RequestException as err:
            msg = f"Could not load value of attribute '{attr_name}' from " \
                  f"entity'{entity_id}' "
            self.log_error(err=err, msg=msg)
            raise

    def update_attribute_value(self, *,
                               entity_id: str,
                               attr_name: str,
                               value: Any,
                               entity_type: str = None):
        """
        Updates the value of a specified attribute of an entity

        Args:
            value: update value
            entity_id: Id of the entity. Example: Bcn_Welt
            attr_name: Name of the attribute to be retrieved.
                Example: temperature.
            entity_type: Entity type, to avoid ambiguity in case there are
                several entities with the same entity id.
        Returns:

        """
        url = urljoin(self.base_url,
                      f'v2/entities/{entity_id}/attrs/{attr_name}/value')
        headers = self.headers.copy()
        params = {}
        if entity_type:
            params.update({'type': entity_type})
        try:
            if not isinstance(value, Dict):
                headers.update({'Content-Type': 'text/plain'})
                if isinstance(value, str):
                    value = f'"{value}"'
                res = self.session.put(url=url,
                                       headers=headers,
                                       data=str(value))
            else:
                res = self.session.put(url=url,
                                       headers=headers,
                                       json=value)
            if res.ok:
                self.logger.info(f"Attribute '{attr_name}' of '{entity_id}' "
                                 f"successfully updated!")
            else:
                res.raise_for_status()
        except requests.RequestException as err:
            msg = f"Could not update value of attribute '{attr_name}' from " \
                  f"entity '{entity_id}' "
            self.log_error(err=err, msg=msg)
            raise

    # Types Operations
    def get_entity_types(self,
                         *,
                         limit: int = None,
                         offset: int = None,
                         options: str = None) -> List[Dict[str, Any]]:
        """

        Args:
            limit: Limit the number of types to be retrieved.
            offset: Skip a number of records.
            options: Options dictionary. Allowed: count, values

        Returns:

        """
        url = urljoin(self.base_url, 'v2/types')
        headers = self.headers.copy()
        params = {}
        if limit:
            params.update({'limit': limit})
        if offset:
            params.update({'offset': offset})
        if options:
            params.update({'options': options})
        try:
            res = self.session.get(url=url, params=params, headers=headers)
            if res.ok:
                self.logger.debug(f'Received: {res.json()}')
                return res.json()
            else:
                res.raise_for_status()
        except requests.RequestException as err:
            msg = f"Could not load entity types!"
            self.log_error(err=err, msg=msg)
            raise

    def get_entity_type(self, entity_type: str) -> Dict[str, Any]:
        """

        Args:
            entity_type: Entity Type. Example: Room

        Returns:

        """
        url = urljoin(self.base_url, f'v2/types/{entity_type}')
        headers = self.headers.copy()
        params = {}
        try:
            res = self.session.get(url=url, params=params, headers=headers)
            if res.ok:
                self.logger.debug(f'Received: {res.json()}')
                return res.json()
            else:
                res.raise_for_status()
        except requests.RequestException as err:
            msg = f"Could not load entities of type" \
                  f"'{entity_type}' "
            self.log_error(err=err, msg=msg)
            raise

    # SUBSCRIPTION API ENDPOINTS
    def get_subscription_list(self,
                              limit: PositiveInt = inf) -> List[Subscription]:
        """
        Returns a list of all the subscriptions present in the system.
        Args:
            limit: Limit the number of subscriptions to be retrieved
        Returns:
            list of subscriptions
        """
        url = urljoin(self.base_url, 'v2/subscriptions/')
        headers = self.headers.copy()
        params = {}

        # We always use the 'count' option to check weather pagination is
        # required
        params.update({'options': 'count'})
        try:
            items = self.__pagination__(limit=limit,
                                        url=url,
                                        params=params,
                                        headers=headers)
            return parse_obj_as(List[Subscription], items)
        except requests.RequestException as err:
            msg = f"Could not load subscriptions!"
            self.log_error(err=err, msg=msg)
            raise

    def post_subscription(self, subscription: Subscription) -> str:
        """
        Creates a new subscription. The subscription is represented by a
        Subscription object defined in filip.cb.models.

        Args:
            subscription:

        Returns:

        """
        url = urljoin(self.base_url, 'v2/subscriptions')
        headers = self.headers.copy()
        headers.update({'Content-Type': 'application/json'})
        try:
            res = self.session.post(
                url=url,
                headers=headers,
                data=subscription.json(exclude={'id'},
                                       exclude_unset=True,
                                       exclude_defaults=True,
                                       exclude_none=True))
            if res.ok:
                self.logger.info(f"Subscription successfully created!")
                return res.headers['Location'].split('/')[-1]
            else:
                res.raise_for_status()
        except requests.RequestException as err:
            msg = f"Could not send subscription!"
            self.log_error(err=err, msg=msg)
            raise

    def get_subscription(self, subscription_id: str) -> Subscription:
        """
        Retrieves a subscription from
        Args:
            subscription_id: id of the subscription

        Returns:

        """
        url = urljoin(self.base_url, f'v2/subscriptions/{subscription_id}')
        headers = self.headers.copy()
        try:
            res = self.session.get(url=url, headers=headers)
            if res.ok:
                self.logger.debug(f'Received: {res.json()}')
                return Subscription(**res.json())
            else:
                res.raise_for_status()
        except requests.RequestException as err:
            msg = f"Could not load subscription {subscription_id}!"
            self.log_error(err=err, msg=msg)
            raise

    def update_subscription(self, subscription: Subscription):
        """
        Only the fields included in the request are updated in the subscription.
        Args:
            subscription: Subscription to update
        Returns:

        """
        url = urljoin(self.base_url, f'v2/subscriptions/{subscription.id}')
        headers = self.headers.copy()
        headers.update({'Content-Type': 'application/json'})
        try:
            res = self.session.patch(
                url=url,
                headers=headers,
                data=subscription.json(exclude={'id'},
                                       exclude_unset=True,
                                       exclude_defaults=True,
                                       exclude_none=True))
            if res.ok:
                self.logger.info(f"Subscription successfully updated!")
            else:
                res.raise_for_status()
        except requests.RequestException as err:
            msg = f"Could not update subscription {subscription.id}!"
            self.log_error(err=err, msg=msg)
            raise

    def delete_subscription(self, subscription_id: str) -> None:
        """
        Deletes a subscription from a Context Broker
        Args:
            subscription_id: id of the subscription
        """
        url = urljoin(self.base_url,
                      f'v2/subscriptions/{subscription_id}')
        headers = self.headers.copy()
        try:
            res = self.session.delete(url=url, headers=headers)
            if res.ok:
                self.logger.info(f"Subscription '{subscription_id}' "
                                 f"successfully deleted!")
            else:
                res.raise_for_status()
        except requests.RequestException as err:
            msg = f"Could not delete subscription {subscription_id}!"
            self.log_error(err=err, msg=msg)
            raise

    # Registration API
    def get_registration_list(self,
                              *,
                              limit: PositiveInt = None) -> List[Registration]:
        """
        Lists all the context provider registrations present in the system.

        Args:
            limit: Limit the number of registrations to be retrieved
        Returns:

        """
        url = urljoin(self.base_url, 'v2/registrations/')
        headers = self.headers.copy()
        params = {}

        # We always use the 'count' option to check weather pagination is
        # required
        params.update({'options': 'count'})
        try:
            items = self.__pagination__(limit=limit,
                                        url=url,
                                        params=params,
                                        headers=headers)

            return parse_obj_as(List[Registration], items)
        except requests.RequestException as err:
            msg = f"Could not load registrations!"
            self.log_error(err=err, msg=msg)
            raise

    def post_registration(self, registration: Registration):
        """
        Creates a new context provider registration. This is typically used
        for binding context sources as providers of certain data. The
        registration is represented by cb.models.Registration

        Args:
            registration (Registration):

        Returns:

        """
        url = urljoin(self.base_url, 'v2/registrations')
        headers = self.headers.copy()
        headers.update({'Content-Type': 'application/json'})
        try:
            res = self.session.post(
                url=url,
                headers=headers,
                data=registration.json(exclude={'id'},
                                       exclude_unset=True,
                                       exclude_defaults=True,
                                       exclude_none=True))
            if res.ok:
                self.logger.info(f"Registration successfully created!")
                return res.headers['Location'].split('/')[-1]
            else:
                res.raise_for_status()
        except requests.RequestException as err:
            msg = f"Could not send registration {registration.id}!"
            self.log_error(err=err, msg=msg)
            raise

    def get_registration(self, registration_id: str) -> Registration:
        """
        Retrieves a registration from context broker by id
        Args:
            registration_id: id of the registration
        Returns:
            Registration
        """
        url = urljoin(self.base_url, f'v2/registrations/{registration_id}')
        headers = self.headers.copy()
        try:
            res = self.session.get(url=url, headers=headers)
            if res.ok:
                self.logger.debug(f'Received: {res.json()}')
                return Registration(**res.json())
            else:
                res.raise_for_status()
        except requests.RequestException as err:
            msg = f"Could not load registration {registration_id}!"
            self.log_error(err=err, msg=msg)
            raise

    def update_registration(self, registration: Registration):
        """
        Only the fields included in the request are updated in the registration.
        Args:
            registration: Registration to update
        Returns:

        """
        url = urljoin(self.base_url, f'v2/registrations/{registration.id}')
        headers = self.headers.copy()
        headers.update({'Content-Type': 'application/json'})
        try:
            res = self.session.patch(
                url=url,
                headers=headers,
                data=registration.json(exclude={'id'},
                                       exclude_unset=True,
                                       exclude_defaults=True,
                                       exclude_none=True))
            if res.ok:
                self.logger.info(f"Registration successfully updated!")
            else:
                res.raise_for_status()
        except requests.RequestException as err:
            msg = f"Could not update registration {registration.id}!"
            self.log_error(err=err, msg=msg)
            raise

    def delete_registration(self, registration_id: str) -> None:
        """
        Deletes a subscription from a Context Broker
        Args:
            registration_id: id of the subscription
        """
        url = urljoin(self.base_url,
                      f'v2/registrations/{registration_id}')
        headers = self.headers.copy()
        try:
            res = self.session.delete(url=url, headers=headers)
            if res.ok:
                self.logger.info(f"Registration '{registration_id}' "
                                 f"successfully deleted!")
            else:
                res.raise_for_status()
        except requests.RequestException as err:
            msg = f"Could not delete registration {registration_id}!"
            self.log_error(err=err, msg=msg)
            raise

    # Batch operation API
    def update(self,
               *,
               update: Update,
               options: str = None) -> None:
        """
        This operation allows to create, update and/or delete several entities
        in a single batch operation.
        Args:
            update (Update): Payload to update
            options (str): Optional 'keyValues'

        Returns:

        """

        url = urljoin(self.base_url, 'v2/op/update')
        headers = self.headers.copy()
        params = {}
        if options:
            assert options == 'keyValues', \
                "Only 'keyValues' is allowed as option"
            params.update({'options': 'keyValues'})
        try:
            res = self.session.post(
                url=url,
                headers=headers,
                params=params,
                json=update.dict())
            if res.ok:
                self.logger.info(f"Update operation '"
                                 f"{update.actionType.value}' succeeded!")
            else:
                res.raise_for_status()
        except requests.RequestException as err:
            msg = f"Update operation '{update.actionType.value}' failed!"
            self.log_error(err=err, msg=msg)
            raise

    def query(self,
              *,
              query: Query,
              limit: PositiveInt = None,
              order_by: str = None,
              options: GetEntitiesOptions = None):
        """

        Args:
            query (Query):
            limit (PositiveInt):
            order_by (str):
            options ():
        Returns:

        """
        url = urljoin(self.base_url, 'v2/op/query')
        headers = self.headers.copy()
        headers.update({'Content-Type': 'application/json'})
        params = {'options': 'count'}
        if options:
            params['options'] = ','.join([options, 'count'])
        try:
            items = self.__pagination__(method=PaginationMethod.POST,
                                        url=url,
                                        headers=headers,
                                        params=params,
                                        data=query.json(exclude_unset=True,
                                                        exclude_none=True),
                                        limit=limit)
            if params['options'] == 'count':
                return parse_obj_as(List[ContextEntity], items)
            else:
                return parse_obj_as(List[ContextEntityKeyValues], items)
        except requests.RequestException as err:
            msg = f"Query operation failed!"
            self.log_error(err=err, msg=msg)
            raise

#    def post_relationship(self, json_data=None):
#        """
#        Function can be used to post a one to many or one to one relationship.
#        :param json_data: Relationship Data obtained from the Relationship
#        class. e.g. :
#                {"id": "urn:ngsi-ld:Shelf:unit001", "type": "Shelf",
#                "refStore": {"type": "Relationship", "value":
#                "urn:ngsi-ld:Store:001"}}
#                Can be a one to one or a one to many relationship
#        """
#        url = self.url + '/v2/op/update'
#        headers = self.get_header(requtils.HEADER_CONTENT_JSON)
#        # Action type append required,
#        # Will overwrite existing entities if they exist whereas
#        # the entities attribute holds an array of entities we wish to update.
#        payload = {"actionType": "APPEND",
#                   "entities": [json.loads(json_data)]}
#        data = json.dumps(payload)
#        response = self.session.post(url=url, data=data, headers=headers)
#        ok, retstr = requtils.response_ok(response)
#        if not ok:
#            level, retstr = requtils.logging_switch(response)
#            self.log_switch(level, retstr)
#
#    def get_subjects(self, object_entity_name: str, object_entity_type: str, subject_type=None):
#        """
#        Function gets the JSON for child / subject entities for a parent /
#        object entity.
#        :param object_entity_name: The parent / object entity name
#        :param object_entity_type: The type of the parent / object entity
#        :param subject_type: optional parameter, if added only those child /
#        subject entities are returned that match the type
#        :return: JSON containing the child / subject information
#        """
#        url = self.url + '/v2/entities/?q=ref' + object_entity_type + '==' + object_entity_name + '&options=count'
#        if subject_type is not None:
#            url = url + '&attrs=type&type=' + subject_type
#        headers = self.get_header()
#        response = self.session.get(url=url, headers=headers, )
#        ok, retstr = requtils.response_ok(response)
#        if not ok:
#            level, retstr = requtils.logging_switch(response)
#            self.log_switch(level, retstr)
#        else:
#            return response.text
#
#    def get_objects(self, subject_entity_name: str, subject_entity_type:
#    str, object_type=None):
#        """
#        Function returns a List of all objects associated to a subject. If
#        object type is not None,
#        only those are returned, that match the object type.
#        :param subject_entity_name: The child / subject entity name
#        :param subject_entity_type: The type of the child / subject entity
#        :param object_type:
#        :return: List containing all associated objects
#        """
#        url = self.url + '/v2/entities/' + subject_entity_name + '/?type=' + subject_entity_type + '&options=keyValues'
#        if object_type is not None:
#            url = url + '&attrs=ref' + object_type
#        headers = self.get_header()
#        response = self.session.get(url=url, headers=headers)
#        ok, retstr = requtils.response_ok(response)
#        if not ok:
#            level, retstr = requtils.logging_switch(response)
#            self.log_switch(level, retstr)
#        else:
#            return response.text
#
#    def get_associated(self, name: str, entity_type: str,
#    associated_type=None):
#        """
#        Function returns all associated data for a given entity name and type
#        :param name: name of the entity
#        :param entity_type: type of the entity
#        :param associated_type: if only associated data of one type should
#        be returned, this parameter has to be the type
#        :return: A dictionary, containing the data of the entity,
#        a key "subjects" and "objects" that contain each a list
#                with the reflective data
#        """
#        data_dict = {}
#        associated_objects = self.get_objects(subject_entity_name=name,
#        subject_entity_type=entity_type,
#                                              object_type=associated_type)
#        associated_subjects = self.get_subjects(object_entity_name=name,
#        object_entity_type=entity_type,
#                                                subject_type=associated_type)
#        if associated_subjects is not None:
#            data_dict["subjects"] = json.loads(associated_subjects)
#        if associated_objects is not None:
#            object_json = json.loads(associated_objects)
#            data_dict["objects"] = []
#            if isinstance(object_json, list):
#                for associated_object in object_json:
#                    entity_name = associated_object["id"]
#                    object_data = json.loads(self.get_entity(
#                    entity_name=entity_name))
#                    data_dict["objects"].append(object_data)
#            else:
#                entity_name = object_json["id"]
#                object_data = json.loads(self.get_entity(
#                entity_name=entity_name))
#                data_dict["objects"].append(object_data)
#
#        entity_dict = json.loads(self.get_entity(entity_name=name))
#
#        whole_dict = {**entity_dict, **data_dict}
#
#        return whole_dict
#

#
#
#    def check_duplicate_subscription(self, subscription_body, limit: int = 20):
#        """
#        Function compares the subject of the subscription body, on whether a subscription
#        already exists for a device / entity.
#        :param subscription_body: the body of the new subscripton
#        :param limit: pagination parameter, to set the number of
#        subscriptions bodies the get request should grab
#        :return: exists, boolean -> True, if such a subscription allready
#        exists
#        """
#        exists = False
#        subscription_subject = json.loads(subscription_body)["subject"]
#        # Exact keys depend on subscription body
#        try:
#            subscription_url = json.loads(subscription_body)[
#            "notification"]["httpCustom"]["url"]
#        except KeyError:
#            subscription_url = json.loads(subscription_body)[
#            "notification"]["http"]["url"]
#
#        # If the number of subscriptions is larger then the limit,
#        paginations methods have to be used
#        url = self.url + '/v2/subscriptions?limit=' + str(limit) +
#        '&options=count'
#        response = self.session.get(url, headers=self.get_header())
#
#        sub_count = float(response.headers["Fiware-Total-Count"])
#        response = json.loads(response.text)
#        if sub_count >= limit:
#            response = self.get_pagination(url=url, headers=self.get_header(),
#                                           limit=limit, count=sub_count)
#            response = json.loads(response)
#
#        for existing_subscription in response:
#            # check whether the exact same subscriptions already exists
#            if existing_subscription["subject"] == subscription_subject:
#                exists = True
#                break
#            try:
#                existing_url = existing_subscription["notification"][
#                "http"]["url"]
#            except KeyError:
#                existing_url = existing_subscription["notification"][
#                "httpCustom"]["url"]
#            # check whether both subscriptions notify to the same path
#            if existing_url != subscription_url:
#                continue
#            else:
#                # iterate over all entities included in the subscription object
#                for entity in subscription_subject["entities"]:
#                    if 'type' in entity.keys():
#                        subscription_type = entity['type']
#                    else:
#                        subscription_type = entity['typePattern']
#                    if 'id' in entity.keys():
#                        subscription_id = entity['id']
#                    else:
#                        subscription_id = entity["idPattern"]
#                    # iterate over all entities included in the exisiting
#                    subscriptions
#                    for existing_entity in existing_subscription["subject"][
#                    "entities"]:
#                        if "type" in entity.keys():
#                            type_existing = entity["type"]
#                        else:
#                            type_existing = entity["typePattern"]
#                        if "id" in entity.keys():
#                            id_existing = entity["id"]
#                        else:
#                            id_existing = entity["idPattern"]
#                        # as the ID field is non optional, it has to match
#                        # check whether the type match
#                        # if the type field is empty, they match all types
#                        if (type_existing == subscription_type) or\
#                                ('*' in subscription_type) or \
#                                ('*' in type_existing)\
#                                or (type_existing == "") or (
#                                subscription_type == ""):
#                            # check if on of the subscriptions is a pattern,
#                            or if they both refer to the same id
#                            # Get the attrs first, to avoid code duplication
#                            # last thing to compare is the attributes
#                            # Assumption -> position is the same as the
#                            entities list
#                            # i == j
#                            i = subscription_subject["entities"].index(entity)
#                            j = existing_subscription["subject"][
#                            "entities"].index(existing_entity)
#                            try:
#                                subscription_attrs = subscription_subject[
#                                "condition"]["attrs"][i]
#                            except (KeyError, IndexError):
#                                subscription_attrs = []
#                            try:
#                                existing_attrs = existing_subscription[
#                                "subject"]["condition"]["attrs"][j]
#                            except (KeyError, IndexError):
#                                existing_attrs = []
#
#                            if (".*" in subscription_id) or ('.*' in
#                            id_existing) or (subscription_id == id_existing):
#                                # Attributes have to match, or the have to
#                                be an empty array
#                                if (subscription_attrs == existing_attrs) or
#                                (subscription_attrs == []) or (existing_attrs == []):
#                                        exists = True
#                            # if they do not match completely or subscribe
#                            to all ids they have to match up to a certain position
#                            elif ("*" in subscription_id) or ('*' in
#                            id_existing):
#                                    regex_existing = id_existing.find('*')
#                                    regex_subscription =
#                                    subscription_id.find('*')
#                                    # slice the strings to compare
#                                    if (id_existing[:regex_existing] in
#                                    subscription_id) or (subscription_id[:regex_subscription] in id_existing) or \
#                                            (id_existing[regex_existing:] in
#                                            subscription_id) or (subscription_id[regex_subscription:] in id_existing):
#                                            if (subscription_attrs ==
#                                            existing_attrs) or (subscription_attrs == []) or (existing_attrs == []):
#                                                exists = True
#                                            else:
#                                                continue
#                                    else:
#                                        continue
#                            else:
#                                continue
#                        else:
#                            continue
#                    else:
#                        continue
#        return exists
#

# def post_cmd_v1(self, entity_id: str, entity_type: str, cmd_name: str,
# cmd_value: str): url = self.url + '/v1/updateContext' payload = {
# "updateAction": "UPDATE", "contextElements": [ {"id": entity_id, "type":
# entity_type, "isPattern": "false", "attributes": [ {"name": cmd_name,
# "type": "command", "value": cmd_value }] }] } headers = self.get_header(
# requtils.HEADER_CONTENT_JSON) data = json.dumps(payload) response =
# self.session.post(url, headers=headers, data=data) ok, retstr =
# requtils.response_ok(response) if not ok: level, retstr =
# requtils.logging_switch(response) self.log_switch(level, retstr)
