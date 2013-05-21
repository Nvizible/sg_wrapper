"""
A module for providing an easier interface with Shotgun
"""
########################################
######## Configuration settings ########
########################################

# The environment variable to look for custom entities in
# Will try, on each path in ENTITY_CLASS_ENV to
# import <entity>.<discriminator>.<Discriminator>()
#     or <entity>.<Entity>()
ENTITY_CLASS_ENV = "SG_WRAPPER_ENTITY_PATH"

# The field (that must exist on every entity) to use as a discriminator
# If this value is None, then only try to load base level entity classes.
ENTITY_DISCRIMINATOR_FIELD_NAME = "Discriminator"
ENTITY_DISCRIMINATOR_FIELD = "sg_" + ENTITY_DISCRIMINATOR_FIELD_NAME.lower().replace(" ", "_") if ENTITY_DISCRIMINATOR_FIELD_NAME else None

# Which schema cache to use.
# Options are:
#   None  : Do not cache the schema
#   redis : Use redis
SCHEMA_CACHE = "redis"

# The hostname of the redis schema cache
SCHEMA_CACHE_REDIS_HOST = "redis"

# The port to connect to the redis schema cache
SCHEMA_CACHE_REDIS_PORT = 6000

# The database id of the redis schema cache
SCHEMA_CACHE_REDIS_DB = 1

# Turn on debug mode by setting this to True
# This will print any function call being made to the core
# Shotgun API
DEBUG = False

########################################
###### End configuration settings ######
########################################

import shotgun_api3
import pickle
import sys
import os
import glob

if SCHEMA_CACHE == "redis":
    import redis

class ShotgunError(StandardError):
    """
    An error class for errors relating to shotgun
    """
    pass

class ShotgunSchemaCache(object):
    """
    This class is used to access the schema cache that is stored in redis
    """
    def __init__(self, sg):
        """
        Initialise the schema cache
        """
        self.sg = sg
        self.sgServer = sg.base_url
        if SCHEMA_CACHE == "redis":
            self.cache = redis.Redis(SCHEMA_CACHE_REDIS_HOST, port=SCHEMA_CACHE_REDIS_PORT, db=SCHEMA_CACHE_REDIS_DB)
        self.entities = {}
    
    def delete_all(self):
        """
        Delete all of the cache in redis
        """
        if self.cache.keys():
            return self.cache.delete(*self.cache.keys())
        else:
            return True
    
    def delete(self, key):
        """
        Delete a specific key from redis
        """
        return self.cache.delete(key)
    
    def get_cache_list(self, key):
        """
        Get a list of items from a cache set
        """
        return list(self.cache.smembers(key))

    def append_cache_list(self, key, value):
        """
        Add an item to a list in the cache
        """
        self.cache.sadd(key, value)
        self.cache.persist(key)
    
    def get_cache_dict(self, key, defaults = None):
        """
        Get a dictionary from the redis cache
        There is an optional defaults argument, which would be a dictionary
        with default values that might not be set in redis
        """
        result = str(self.cache.get(key))
        if result:
            try:
                resultDict = pickle.loads(result)
            except Exception:
                print "ERROR UNPICKLING"
                print "Key: %s" % key
                print "Result: %s" % result
                resultDict = {}
        else:
            resultDict = {}

        if defaults:
            for k in defaults:
                if k not in resultDict:
                    resultDict[k] = defaults[k]
        return resultDict
    
    def set_cache_dict(self, key, data):
        """
        Assign a dictionary to a key in the cache
        """
        self.cache.set(key, pickle.dumps(data))
        self.cache.persist(key)

    def get_entities(self):
        """
        Get a list of all of the entities referred to in the cache
        """
        if not self.entities:
            if SCHEMA_CACHE:
                entities = self.get_cache_list("%s:entities" % self.sgServer)
                for e in entities:
                    self.entities[e] = None
            else:
                entities = self.sg.schema_entity_read()
                for e in entities:
                    details = {'type': e,
                               'name': entities[e]['name']['value'].replace(" ", "")}
                    details['type_plural'] = self.pluralise(details['type'])
                    details['name_plural'] = self.pluralise(details['name'])
                    self.entities[e] = details
        
        return self.entities.keys()
    
    def get_entity_details(self, entity):
        """
        Get the details for a specified entity
        """
        try:
            assert(self.entities[entity])
        except:
            self.get_entities()

        if not self.entities[entity]:
            if SCHEMA_CACHE:
                self.entities[entity] = self.get_cache_dict("%s:%s:details" % (self.sgServer, entity))
            # Should never get to an else stage here, as if SCHEMA_CACHE is false, self.entities[entity]
            # should have been filled in in self.get_entities()

        return self.entities[entity]
    
    def get_entity_fields(self, entity):
        """
        Get a list of the fields that an entity has
        """
        try:
            assert(self.entities[entity]['name'])
        except:
            self.get_entity_details(entity)
            
        if 'fields' not in self.entities[entity] or not self.entities[entity]['fields']:
            self.entities[entity]['fields'] = {}
            if SCHEMA_CACHE:
                fields = self.get_cache_list("%s:%s:fields" % (self.sgServer, entity))
                for f in fields:
                    self.entities[entity]['fields'][f] = None
            else:
                fields = self.sg.schema_field_read(entity)
                for f in fields:
                    details = {}
                    details['name'] = fields[f]['name']['value']
                    details['mandatory'] = fields[f]['mandatory']['value']
                    details['editable'] = fields[f]['editable']['value']
                    details['data_type'] = fields[f]['data_type']['value']
                    if 'valid_types' in fields[f]['properties']:
                        details['valid_types'] = fields[f]['properties']['valid_types']['value']
                    else:
                        details['valid_types'] = None
                    if 'valid_values' in fields[f]['properties']:
                        details['valid_values'] = fields[f]['properties']['valid_values']['value']
                    else:
                        details['valid_values'] = None
                    self.entities[entity]['fields'][f] = details

        return self.entities[entity]['fields'].keys()
    
    def get_entity_field_details(self, entity, field):
        """
        Get the details for a field in a specific entity
        """
        try:
            assert(self.entities[entity]['fields'][field])
        except:
            self.get_entity_fields(entity)

        if not self.entities[entity]['fields'][field]:
            if SCHEMA_CACHE:
                self.entities[entity]['fields'][field] = self.get_cache_dict("%s:%s:%s:details" % (self.sgServer, entity, field))
            # Should never get to an else stage here, as if SCHEMA_CACHE is false, self.entities[entity]['fields'][field]
            # should have been filled in in self.get_entity_fields()
        
        return self.entities[entity]['fields'][field]

    def add_entity(self, entity):
        """
        Add an entity to the cache
        """
        return self.append_cache_list("%s:entities" % self.sgServer, entity)

    def set_entity_details(self, entity, details):
        """
        Set an entity's details
        """
        return self.set_cache_dict("%s:%s:details" % (self.sgServer, entity), details)
    
    def add_entity_field(self, entity, field):
        """
        Add a field to an entity
        """
        return self.append_cache_list("%s:%s:fields" % (self.sgServer, entity), field)
    
    def set_entity_field_details(self, entity, field, details):
        """
        Set the details for a field on an entity
        """
        return self.set_cache_dict("%s:%s:%s:details" % (self.sgServer, entity, field), details)

    def update_schema_entity_cache(self, entity, schema_entities = None, createDiscriminator = False):
        """
        Update the schema cache for a specific entity.
        Optionally, pass through the entity schema, to save this being requested
        multiple times
        """
        
        if not SCHEMA_CACHE:
            # Don't do anything, as we aren't caching the schema
            return
            
        if not schema_entities:
            schema_entities = self.sg.schema_entity_read()
        
        if entity not in schema_entities:
            raise ShotgunError("Entity %s not found in schema" % entity)
        
        print "Updating schema cache for '%s'" % entity
                
        details = {'type': entity,
                   'name': schema_entities[entity]['name']['value'].replace(" ", "")}
        details['type_plural'] = self.pluralise(details['type'])
        details['name_plural'] = self.pluralise(details['name'])

        self.add_entity(entity)
        self.set_entity_details(entity, details)
    
        fields = self.sg.schema_field_read(entity)
        modifiedFields = False
        if ENTITY_DISCRIMINATOR_FIELD and ENTITY_DISCRIMINATOR_FIELD not in fields and createDiscriminator:
            print "Discriminator field does not exist. Creating"
            self.sg.schema_field_create(entity, "text", ENTITY_DISCRIMINATOR_FIELD_NAME)
            modifiedFields = True
        
        if modifiedFields:
            fields = self.sg.schema_field_read(entity)

        print "Fields:"
        for f in fields:
            print "    %s (%s)" % (fields[f]['name']['value'], fields[f]['data_type']['value'])
            details = {}
            details['name'] = fields[f]['name']['value']
            details['mandatory'] = fields[f]['mandatory']['value']
            details['editable'] = fields[f]['editable']['value']
            details['data_type'] = fields[f]['data_type']['value']
            if 'valid_types' in fields[f]['properties']:
                details['valid_types'] = fields[f]['properties']['valid_types']['value']
            else:
                details['valid_types'] = None
            if 'valid_values' in fields[f]['properties']:
                details['valid_values'] = fields[f]['properties']['valid_values']['value']
            else:
                details['valid_values'] = None
                    
            self.add_entity_field(entity, f)
            self.set_entity_field_details(entity, f, details)


    def update_schema_cache(self):
        """
        Update the entire schema cache
        """
        if not SCHEMA_CACHE:
            # Don't do anything, as we aren't caching the schema
            return
            
        self.delete_all()
        print "Getting entity schema"
        entities = self.sg.schema_entity_read()
        for e in entities:
            self.update_schema_entity_cache(e, entities)

    def pluralise(self, name):
        """
        Get the plural version of 'name'
        """
        if name in Shotgun._customPlural:
            return Shotgun._customPlural[name]
        if name[-1] == "y" and name[-3:] != "Day":
            return name[:-1] + "ies"
        if name[-1] in ["s", "h"]:
            return name + "es"
        
        return name + "s"
        

class Shotgun(object):
    """
    This is the base Shotgun class. Everything is created from
    here, and it deals with talking to the standard Shotgun API.
    """
    # The Primary Text Keys are the field names to check when not defined.
    # For example, calling sg.Project("my_project") will be the same as sg.Project(code = "my_project")
    _primaryTextKeys = ["code", "login"]

    # For most entity types, the pluralise() function will define what the plural version of the entity name is.
    # This dictionary defines any custom plural forms that we might want to have.
    _customPlural = {'Person': "People"}

    _shotgunObjects = {}
    
    @classmethod
    def shotgun_object(cls, sgServer, sgScriptName, sgScriptKey):
        """
        Get a Shotgun object for a specific script/key pair
        """
        
        objectHash = "%s.%s.%s" % (sgScriptName, sgScriptKey)
        if objectHash not in Shotgun._shotgunObjects:
            cls._shotgunObjects[objectHash] = cls(sgServer,
                                                  sgScriptName,
                                                  sgScriptKey)
        return Shotgun._shotgunObjects[objectHash]
    
    def __init__(self, sgServer, sgScriptName, sgScriptKey):
        """
        Initialise the shotgun object with the specified script name/key combo.
        Also, an optional config parameter is available to define which section
        of the config file to use
        """
        if DEBUG:
            print "shotgun_api3.Shotgun(%s, %s, %s)" % (`sgServer`, `sgScriptName`, `sgScriptKey`)
        self._sg = shotgun_api3.Shotgun(sgServer, sgScriptName, sgScriptKey)
        self._schema_cache = ShotgunSchemaCache(self._sg)
        self._entities = {}
        self._entity_searches = []
    
    def set_session_uuid(self, uuid):
        """
        Set the session UUID for Shotgun
        """
        self._sg.set_session_uuid(uuid)
    
    def get_entities(self):
        """
        Get a list of the entities in the cache
        """
        return self._schema_cache.get_entities()
    
    def get_entity_details(self, entityType):
        """
        Get the details for an entity
        """
        return self._schema_cache.get_entity_details(entityType)
    
    def get_entity_fields(self, entityType):
        """
        Get a list of the fields in the specified entity
        """
        return self._schema_cache.get_entity_fields(entityType)
    
    def get_entity_field_details(self, entityType, field):
        """
        Get the details of the fields in the specified entity
        """
        return self._schema_cache.get_entity_field_details(entityType, field)
    
    def is_entity(self, entityType):
        """
        Return true if the specified entity exists
        """
        entities = self.get_entities()
        if entityType in entities:
            return True
        
        for e in entities:
            if self.get_entity_details(e)['name'] == entityType:
                return True
        
        return False
    
    def is_entity_plural(self, entityType):
        """
        Return true if the specified type is the plural
        version of one of the entities
        """
        entities = self.get_entities()
        for e in entities:
            entityDetails = self.get_entity_details(e)
            if entityType in [entityDetails['type_plural'], entityDetails['name_plural']]:
                return True
        return False
    
    def find_custom_entity_class_base(self, entityClassName):
        """
        For a specific entity class name, find the base class
        """
        if "_" in entityClassName:
            entityClassBase, entityClassName = entityClassName.split("_")
        else:
            entityClassBase = None

        entityClass = Entity.find_custom_entity_class(self, entityClassName, entityClassBase)
        if entityClass != None:
            return entityClass.get_entity_base()
        
        return None

    def find_custom_entity_plural_class_base(self, entityClass):
        """
        For a plural class name, find the base class for the singular entity
        """
        return self.find_custom_entity_class_base(self.plural_to_single(entityClass))

    def plural_to_single(self, plural_name):
        """
        Converts a plural name to the singular equivalent
        """
        
        for single in self._customPlural:
            if self._customPlural[single] == plural_name:
                return single
        
        if plural_name[-3:] == "ies":
            return plural_name[:-3]+"y"
        if plural_name[-4:] == "shes" or plural_name[-3:] == "ses":
            return plural_name[:-2]
        if plural_name[-1] == "s":
            return plural_name[:-1]
        
        return plural_name

    def get_primary_key(self, entityType):
        """
        Get the primary key for the specified entity
        """
        
        fields = self.get_entity_fields(entityType)
        primaryKeys = list(set(fields).intersection(set(Shotgun._primaryTextKeys)))
        if primaryKeys:
            return primaryKeys[0]
        
        return None
    
    def get_entity_field(self, entityType, entityId, field):
        """
        Get a single field for an entity from Shotgun
        """
        result = self.sg_find_one(entityType,
                                  [["id", "is", entityId]],
                                  [field])
        if result:
            return result[field]
        return None
    
    def get_entity_type(self, entityName):
        """
        Get the actual entity type for an entity name, which
        could be any of the type, name or plural of either
        of those
        """
        entities = self.get_entities()
        if entityName in entities:
            return entityName
            
        for e in entities:
            entityDetails = self.get_entity_details(e)
            if entityName in (entityDetails['name'],
                              entityDetails['type_plural'],
                              entityDetails['name_plural']):
                return entityDetails['type']

        return None
    
    def get_entity_name(self, entityType):
        """
        Get the name for an entity type
        """
        if entityType in self.get_entities():
            return self.get_entity_details(entityType)['name']

        return None
    
    def find_entity(self,
                    entityType,
                    key = None,
                    find_one = True,
                    fields = None,
                    exclude_fields = None,
                    **kwargs):
        """
        Find an entity from the Shotgun database
        """

        if find_one and not key and not kwargs:
            return self.new(entityType)
            
        filters = {}

        filters['logical_operator'] = "and"
        filters['conditions'] = []
        
        order = None
        limit = 0
        
        entityType = self.get_entity_type(entityType)
        entityFields = self.get_entity_fields(entityType)
        
        if not entityType or not entityFields:
            return None
        
        if key:
            if isinstance(key, int):
                filters['conditions'].append({'path': "id",
                                              'relation': "is",
                                              'values': [key]})
            elif isinstance(key, str):
                foundPrimaryKey = False
                for fieldName in Shotgun._primaryTextKeys:
                    if fieldName in entityFields:
                        filters['conditions'].append({'path': fieldName,
                                                      'relation': "is",
                                                      'values': [key]})
                        foundPrimaryKey = True
                        break
                if not foundPrimaryKey:
                    raise ShotgunError("Entity type '%s' does not have one of the defined primary keys(%s)." % \
                                            (entityType,
                                             ", ".join(Shotgun._primaryTextKeys)))
        
        for arg in kwargs:
            if arg == "order":
                order = kwargs[arg]
                if isinstance(order, dict):
                    order = [order]
            elif arg == "limit":
                limit = kwargs[arg]
            else:
                fieldName = arg
                altFieldName = "sg_%s" % fieldName
                if fieldName not in entityFields:
                    if altFieldName in entityFields:
                        fieldName = altFieldName
                    else:
                        raise ShotgunError("Unknown field in entity %s : %s" % (entityType,
                                                                                fieldName))
                
                if isinstance(kwargs[arg], Entity):
                    filters['conditions'].append({'path': fieldName,
                                                  'relation': "is",
                                                  'values': [{'type': kwargs[arg].entity_type(),
                                                              'id': kwargs[arg].entity_id()}]})
                elif isinstance(kwargs[arg], dict) and 'type' in kwargs[arg] and 'id' in kwargs[arg]:
                    filters['conditions'].append({'path': fieldName,
                                                  'relation': "is",
                                                  'values': [{'type': kwargs[arg]['type'],
                                                              'id': kwargs[arg]['id']}]})
                else:
                    fieldDetails = self.get_entity_field_details(entityType, fieldName)
                    fieldType = fieldDetails['data_type']
                    values = kwargs[arg]
                    relation = "is"
                    if not isinstance(values, list):
                        values = [values]
                    if len(values) > 1:
                        relation = "in"
                        
                    if fieldType in ["entity", "multi_entity"] and kwargs[arg] != None:
                        argFilters = {}
                        argFilters['logical_operator'] = "or"
                        argFilters['conditions'] = []
                        for validType in fieldDetails['valid_types']:
                            if validType in self.get_entities():
                                primaryKey = self.get_primary_key(validType)
                                if primaryKey:
                                    argFilters['conditions'].append({'path': "%s.%s.%s" % \
                                                                                (fieldName,
                                                                                 validType,
                                                                                 primaryKey),
                                                                     'relation': relation,
                                                                     'values': values})
                        filters['conditions'].append(argFilters)
                    else:
                        filters['conditions'].append({'path': fieldName,
                                                      'relation': relation,
                                                      'values': values})
        
        for query in filters['conditions']:
            if 'path' in query \
            and query['path'] == 'id':
                if entityType in self._entities \
                and query['values'][0] in self._entities[entityType]:
                    return self._entities[entityType][query['values'][0]]

        if not fields:
            fields = self.get_entity_fields(entityType)
        
        if exclude_fields:
            for f in exclude_fields:
                if f in fields:
                    fields.remove(f)

        for search in self._entity_searches:
            if search['find_one'] == find_one \
              and search['entity_type'] == entityType \
              and search['filters'] == filters \
              and search['limit'] == limit \
              and search['order'] == order \
              and set(fields).issubset(set(search['fields'])) \
              and search['result']:
                return search['result']
        
        result = None
        
        if find_one:
            sg_result = self.sg_find_one(entityType,
                                         filters,
                                         fields,
                                         order)
            if sg_result:
                result = Entity.create_entity(self,
                                             entityType,
                                             sg_result)
        else:
            sg_results = self.sg_find(entityType,
                                      filters,
                                      fields,
                                      order,
                                      limit)
            result = []
            for sg_result in sg_results:
                result.append(Entity.create_entity(self,
                                                  entityType,
                                                  sg_result))

        thisSearch = {}
        thisSearch['find_one'] = find_one
        thisSearch['entity_type'] = entityType
        thisSearch['filters'] = filters
        thisSearch['fields'] = fields
        thisSearch['limit'] = limit
        thisSearch['result'] = result
        thisSearch['order'] = order
        self._entity_searches.append(thisSearch)
        
        return result

    def sg_find_one(self, entityType, filters, fields, order = None):
        """
        A wrapper around the Shotgun API's find_one() function
        """
        if DEBUG:
            print "sg.find_one(%s, %s, %s, order =  %s)" % (`entityType`, `filters`, `fields`, `order`)
        result = self._sg.find_one(entityType, filters, fields, order = order)
        
        return result

    def sg_find(self, entityType, filters, fields, order = None, limit = 0):
        """
        A wrapper around the Shotgun API's find() function
        """
        if DEBUG:
            print "sg.find(%s, %s, %s, order =  %s, limit = %s)" % (`entityType`, `filters`, `fields`, `order`, `limit`)
        result = self._sg.find(entityType, filters, fields, order = order, limit = limit)
        
        return result
    
    def convert_entities(self, data):
        """
        Convert data to a format that the Shotgun API understands.
        This mainly involves converting Entity objects to dictionaries
        """
        listTypes = [list, tuple, set, frozenset]
        dictTypes = [dict]
        
        if isinstance(data, Entity):
            return {'type': data.entity_type(),
                    'id': data.entity_id()}
        elif isinstance(data, MultiEntity):
            entityList = []
            for e in data:
                entityList.append(self.convert_entities(e))
            return entityList
        elif type(data) in listTypes:
            newList = []
            for i in data:
                newList.append(self.convert_entities(i))
            return type(data)(newList)
        elif type(data) in dictTypes:
            newDict = {}
            for k in data:
                newDict[self.convert_entities(k)] = self.convert_entities(data[k])
            return newDict
        else:
            return data
    
    def update(self, entity, updateFields):
        """
        Update the entity in the Shotgun database with the specified fields 
        """
        updateData = {}
        for f in updateFields:
            updateData[f] = self.convert_entities(entity.field(f))
        
        if DEBUG:
            print "sg.update(%s, %s, %s)" % (`entity.entity_type()`, `entity.entity_id()`, `updateData`)
        self._sg.update(entity.entity_type(), entity.entity_id(), updateData)
        
    
    def create(self, entity):
        """
        Create a new instance of the specified entity in the Shotgun database
        """
        createData = {}
        for f in entity._fields:
            createData[f] = self.convert_entities(entity.field(f))
            print "%s : %s" % (f, createData[f])
        
        if DEBUG:
            print "sg.create(%s, %s)" % (`entity.entity_type()`, `createData`)
        newEntity = self._sg.create(entity.entity_type(), createData)

        return newEntity['id']
    
    def delete(self, entity):
        """
        Delete the specified entity
        """
        if DEBUG:
            print "sg.delete(%s, %s)" % (`entity.entity_type()`, `entity.entity_id()`)
        self._sg.delete(entity.entity_type(), entity.entity_id())

    def register_entity(self, entity):
        """
        Register an entity with the master Shotgun object so that it can
        be retrieved from the cache at a later date
        """
        if entity.entity_type() not in self._entities:
            self._entities[entity.entity_type()] = {}
        
        if entity.entity_id() not in self._entities[entity.entity_type()]:
            self._entities[entity.entity_type()][entity.entity_id()] = entity
    
    def filter_entity_custom_class_results(self, results, entity_class, limit = 0):
        """
        Filter a list of results based on whether they are acceptable to the specified
        entity_class
        """
        newResults = []
        entityClass = Entity.find_custom_entity_class(self, entity_class)
        for r in results:
            if ENTITY_DISCRIMINATOR_FIELD and ENTITY_DISCRIMINATOR_FIELD in r.fields():
                resultClass = Entity.find_custom_entity_class(self, r.field(ENTITY_DISCRIMINATOR_FIELD))
                if resultClass and issubclass(resultClass, entityClass):
                    newResults.append(r)
                    if limit and len(newResults) >= limit:
                        return newResults
        return newResults
    
    def __getattr__(self, attrName):
        """
        Get an attribute from the Shotgun object. This will either be a find() or a new()
        """
        originalAttrName = attrName
        singleAttrName = self.plural_to_single(attrName)
        entityType = attrName.split("_")[0]
        
        def find_entity_wrapper(*args, **kwargs):
            """
            A wrapper function for finding a single entity
            """
            return self.find_entity(attrName,
                                    find_one = True,
                                    *args,
                                    **kwargs)

        def find_multi_entity_wrapper(*args, **kwargs):
            """
            A wrapper string for finding multiple entities
            """
            return self.find_entity(attrName,
                                    find_one = False,
                                    *args,
                                    **kwargs)
        
        def find_custom_entity_class_wrapper(*args, **kwargs):
            if kwargs:
                results = self.find_entity(entityType,
                                           find_one = False,
                                           *args,
                                           **kwargs)
                return self.filter_entity_custom_class_results(results, originalAttrName, 1)
            else:
                return self.new(originalAttrName)
        
        def find_custom_entity_plural_class_wrapper(*args, **kwargs):
            results = self.find_entity(entityType,
                                       find_one = False,
                                       *args,
                                       **kwargs)
            return self.filter_entity_custom_class_results(results, singleAttrName)
        
        if attrName[0] == "_":
            return object.__getattr__(self, attrName)
        if self.is_entity(attrName):
            return find_entity_wrapper
        if self.is_entity_plural(attrName):
            return find_multi_entity_wrapper
        entityType = self.find_custom_entity_class_base(attrName)
        if entityType:
            return find_custom_entity_class_wrapper
        entityType = self.find_custom_entity_plural_class_base(attrName)
        if entityType:
            return find_custom_entity_plural_class_wrapper
        
        return None
        
    def commit_all(self):
        """
        Commit all changes in all registered entities
        """
        for entityType in self._entities:
            for entityId in self._entities[entityType]:
                entity = self._entities[entityType][entityId]
                if entity.modified_fields():
                    entity.commit()
    
    def new(self, entity_type):
        """
        Create a new entity object
        """
        
        if "_" in entity_type:
            entity_base, entity_subclass = entity_type.split("_")
            return Entity.create_new_entity(self, entity_subclass, entity_base)
        else:
            return Entity.create_new_entity(self, entity_type)

    def get_all_entity_classes(self):
        """
        Get a list of all possible Entity subclasses
        """

        oldSysPath = sys.path
        entityPaths = os.environ[ENTITY_CLASS_ENV].split(":")
        sys.path[:0] = entityPaths
        foundModules = []
        classes = []
        for entityPath in entityPaths:
            entities = glob.glob(os.path.join(entityPath, "*/*.py"))
            for e in entities:
                entityBase = os.path.basename(os.path.dirname(e))
                entityClass = os.path.splitext(e)[0]
                if entityClass[0] == "_":
                    continue
                
                if entityClass == "base":
                    moduleName = entityBase
                    entityClass = entityBase
                else:
                    moduleName = "%s.%s" % (entityBase, entityClass)    

                if moduleName in foundModules:
                    continue
                foundModules.append(moduleName)
                try:
                    if "." in moduleName:
                        moduleRoot = ".".join(moduleName.split(".")[:-1])
                        moduleName = moduleName.split(".")[-1]
                        moduleBase = __import__(moduleRoot, globals(), locals(), [moduleName])
                        module = getattr(moduleBase, moduleName)
                    else:
                        module = __import__(moduleName, globals(), locals())

                    for item in dir(module):
                        if item.lower() == entityClass:
                            c = getattr(module, item)
                            if issubclass(c, Entity):
                                classes.append(getattr(module, item))
                except ImportError, e:
                    pass
        
        sys.path = oldSysPath
        return classes
    
    def add_to_class_tree(self, classTree, thisClass):
        """
        Find where in classTree thisClass fits, and insert it
        """
        if classTree['class'] in thisClass.__bases__:
            classTree['subclasses'].append({'class': thisClass,
                                            'name': thisClass.__name__,
                                            'subclasses': []})
            return True
        else:
            for c in classTree['subclasses']:
                if self.add_to_class_tree(c, thisClass):
                    return True
        return False
    
    def get_entity_class_tree(self, base = None):
        """
        Get a tree of entity classes, from a specified base.
        If the base is not specified, use Entity as the base
        """
        classes = self.get_all_entity_classes()
        remainingClasses = classes[:]
        if not base:
            base = Entity
        classTree = {'class': base, 'name': base.__name__, 'subclasses': []}
        foundClass = True
        while remainingClasses and foundClass:
            foundClass = None
            for c in remainingClasses:
                if self.add_to_class_tree(classTree, c):
                    foundClass = c
                    break
            if foundClass:
                remainingClasses.remove(foundClass)
        
        return classTree
    
    def print_entity_class_tree(self, classTree, indent = 0):
        """
        Print out the entity class tree
        """
        print ("  "*indent) + classTree['name']
        for c in classTree['subclasses']:
            self.print_entity_class_tree(c, indent+1)
    
    def clear_entity_cache(self):
        """
        Clear the cache of entities, and, if the schema has changed, also
        clear the entity definitions
        """
        self._entities = {}
        self._entity_searches = []
        

class MultiEntity(list):
    """
    A class for storing a list of Entity objects
    """
    def __init__(self, shotgun, parent, entity_list = None):
        list.__init__(self)
        self._shotgun = shotgun
        self._parent = parent
        self._original = None
        if entity_list:
            for entity in entity_list:
                self.append(entity)
        self._modified = False
    
    def set_original(self):
        """
        Set the original contents of the list so that it
        can be reverted if needed
        """
        entities = []
        for entity in list.__iter__(self):
            entities.append(entity)
        self._original = MultiEntity(self._shotgun,
                                     self._parent,
                                     entities)
    
    def __iter__(self):
        """
        Iterate through the MultiEntity list
        """
        for entity in list.__iter__(self):
            if 'entity' not in entity:
                entity['entity'] = self._shotgun.find_entity(entity['type'],
                                                             id = entity['id'])
            yield entity['entity']
    
    def __cmp__(self, alt):
        """
        Compare two MultiEntity objects
        """
        if not isinstance(alt, MultiEntity):
            return 1
        if len(self) > len(alt):
            return 1
        elif len(self) < len(alt):
            return -1
        
        for i in self:
            if i not in alt:
                return 1
        
        return 0
    
    def append(self, item):
        """
        Append an object to the list
        """
        if isinstance(item, Entity):
            item = {'entity': item,
                    'type': item.entity_type(),
                    'id': item.entity_id()}
        list.append(self, item)
        self._modified = True
    
    def extend(self, items):
        """
        Extend the list with another list
        """
        for i in items:
            self.append(i)
    
    def remove(self, item):
        """
        Remove an item from the list
        """
        self._modified = True
        list.remove(self, item)
    
    def modified(self):
        """
        Return True if the list has been modified since creation
        """
        return self._modified
    
    def original(self):
        """
        Get the original list as it was when it was first created
        """
        return self._original
    
class Entity(object):
    """
    Class for storing information about a specific entity
    """
    
    @classmethod
    def get_entity_base(cls):
        """
        Get the base parent (before Entity) class of the specified class
        """
        bases = cls.__bases__
        if Entity in bases:
            return cls.__name__
        
        for base in bases:
            if base is not object:
                baseEntity = base.get_entity_base()
                if baseEntity:
                    return baseEntity
        
        return None
    
    def __init__(self, shotgun, entity_type, fields):
        """
        Initialise an Entity object
        """
        self._entity_type = entity_type
        self._shotgun = shotgun
        self._fields = fields
        self._field_names = self._shotgun.get_entity_fields(self._entity_type)
        self._fields_changed_dict = {}
        self._sg_filters = []

        if 'id' in self._fields:
            self._entity_id = self._fields['id']
            self._shotgun.register_entity(self)
        else:
            self._entity_id = None
            for field in self._shotgun.get_entity_fields(entity_type):
                if field != "id" and field not in self.fields():
                    fieldDetails = self._shotgun.get_entity_field_details(entity_type, field)
                    if fieldDetails['editable']:
                        if fieldDetails['data_type'] in ["multi_entity", "tag_list"]:
                            self.set_field(field, [])
                        elif fieldDetails['data_type'] == "checkbox":
                            self.set_field(field, False)
                        elif fieldDetails['data_type'] == "color":
                            self.set_field(field, "1,1,1")
                        elif fieldDetails['data_type'] not in ["summary"]:
                            self.set_field(field, None)
    
    def get_shotgun_object(self):
        return self._shotgun
    
    @property
    def _fields_changed(self):
        """
        Return True if any of the fields in the entity have changed
        """
        changed = self._fields_changed_dict
        for f in self._fields:
            if isinstance(self._fields[f], MultiEntity):
                if self._fields[f].modified():
                    changed[f] = self._fields[f].original()
        return changed
    
    @classmethod
    def create_new_entity(cls, shotgun, entity_class, entity_base = None):
        """
        Create a new entity. If entity_class refers to a valid class, then
        create that class, otherwise create an Entity
        """
        if not entity_base:
            entity_base = cls.get_entity_base()
        
        customCls = cls.find_custom_entity_class(shotgun, entity_class, entity_base)
        
        entityType = None
        if customCls:
            entityType = shotgun.get_entity_type(customCls.get_entity_base())
            cls = customCls
        elif shotgun.is_entity(entity_class):
            entityType = shotgun.get_entity_type(entity_class)
        
        entity = None
        
        if entityType:
            entity = cls(shotgun, entityType, {})
            if ENTITY_DISCRIMINATOR_FIELD and ENTITY_DISCRIMINATOR_FIELD in entity.fields():
                entity.set_field(ENTITY_DISCRIMINATOR_FIELD, entity_class)
        
        return entity

    @classmethod
    def create_entity(cls, shotgun, entity_type, fields):
        """
        Create the appropriate Entity class
        """
        
        if ENTITY_DISCRIMINATOR_FIELD and ENTITY_DISCRIMINATOR_FIELD in fields:
            discriminator = fields[ENTITY_DISCRIMINATOR_FIELD]
        else:
            discriminator = None
        
        if discriminator and "_" in discriminator and shotgun.is_entity(discriminator.split("_")[0]):
            discriminator = "_".join(discriminator.split("_")[1:])
        
        # Will return only the first one to not return False or None
        return (discriminator and \
                cls.create_entity_object(shotgun,
                                         discriminator,
                                         entity_type,
                                         fields)) or \
                cls.create_entity_object(shotgun,
                                         entity_type,
                                         entity_type,
                                         fields) or \
                cls.create_entity_object(shotgun,
                                         shotgun.get_entity_name(entity_type),
                                         entity_type,
                                         fields) or \
                cls.create_entity_object(shotgun,
                                         None,
                                         entity_type,
                                         fields)
    
    @classmethod
    def create_entity_object(cls, shotgun, entity_class, entity_type, fields):
        """
        Try and create an entity using the specified fields of type entity_class
        """
        
        if entity_class:
            newClass = cls.find_custom_entity_class(shotgun, entity_class, entity_type)
            if not newClass:
                newClass = cls.find_custom_entity_class(shotgun,
                                                        entity_class,
                                                        shotgun.get_entity_name(entity_type))
            cls = newClass

        if cls:
            return cls(shotgun, entity_type, fields)

        return None
    
    @classmethod
    def find_custom_entity_class(cls, shotgun, entity_class, entity_type = None):
        """
        Try to load a specified custom entity_class. If it fails, returns None
        If entity_type is passed in, and is not the same as entity_class,
        then assume that it is looking for a subclass of an entity (as defined
        by a discriminator)
        
        Before doing any import statement, prepend the contents of the environment
        variable stored in ENTITY_CLASS_ENV onto sys.path. Also ensure that sys.path
        is reset before returning.
        
        If looking for a subclass, it will load:
            <entity_type.lower()>.<entity_class.lower()>.<entity_class>
        Otherwise:
            <entity_class.lower()>.<entity_class>
        
        For example, if looking for an entity_class of ClientVersion, with an
        entity_type of Version, will try to load:
            version.clientversion.ClientVersion
        
        Or if just looking for an entity_class of Version, and an entity_type of
        None, will try to load:
            version.Version
        """
        
        oldSysPath = sys.path
        if ENTITY_CLASS_ENV:
            entityPaths = os.environ[ENTITY_CLASS_ENV].split(":")
            sys.path[:0] = entityPaths

        try:
            if entity_type and entity_class != entity_type:
                importPath = "%s.%s" % (entity_type.lower(),
                                        entity_class.lower())
            else:
                importPath = "%s" % (entity_class.lower())
            mod = __import__(importPath, globals(), locals(), [entity_class])
            sys.path = oldSysPath
            return getattr(mod, entity_class)
        except ImportError:
            sys.path = oldSysPath
            return None
            
    @classmethod
    def get_entity_class_tree(cls, shotgun):
        """
        Get the subclass tree for the current class
        """
        return shotgun.get_entity_class_tree(cls)
    
    def reload(self):
        """
        Reload the entity field values from the Shotgun database
        """
        if self._entity_id:
            self._field_names = self._shotgun.get_entity_fields(self._entity_type)
            self._fields = self._shotgun.sg_find_one(self._entity_type,
                                                     [["id", "is", self._entity_id]],
                                                     fields = self._fields.keys())
        else:
            raise ShotgunError("Tried to reload an entity that has not been stored")
    
    def fields(self):
        """
        Return a list of the fields that currently exist
        """
        return self._fields.keys()

    def all_fields(self):
        """
        Return a list of all of the fields that this entity type supports
        """
        return self._field_names
    
    def entity_type(self):
        """
        Return this entity's type
        """
        return self._entity_type
    
    def entity_id(self):
        """
        Return this entity's ID
        """
        return self._entity_id
    
    def translate_attribute(self, attribute):
        """
        Translate an attribute into a form that is useful
        """
        if type(attribute) == dict \
        and 'id' in attribute \
        and 'type' in attribute:
            if 'entity' not in attribute:
                attribute['entity'] = self._shotgun.find_entity(attribute['type'],
                                                                id = attribute['id'])
            return attribute['entity']

        return attribute
    
    def field(self, fieldName):
        """
        Get the contents of a field in the appropriate format.
        If a field hasn't been requested from the Shotgun database,
        then request it first
        """
        
        altFieldName = "sg_%s" % fieldName
        if fieldName not in self.all_fields() and altFieldName in self.all_fields():
            fieldName = altFieldName
        
        if fieldName not in self._fields:
            if fieldName in self._field_names:
                if self._entity_id:
                    result = self._shotgun.get_entity_field(self._entity_type,
                                                            self._entity_id,
                                                            fieldName)
                    if result:
                        self._fields[fieldName] = result
                    else:
                        raise AttributeError("Entity '%s' (%d) not found when searching for '%s'" % \
                                                (self._entity_type,
                                                 self._entity_id,
                                                 fieldName))
                else:
                    raise ShotgunError("Tried to load an undefined field in an entity that has not been stored yet")
        
        if fieldName in self._fields:
            if type(self._fields[fieldName]) == list:
                self._fields[fieldName] = MultiEntity(self._shotgun,
                                                      self,
                                                      self._fields[fieldName])
                self._fields[fieldName].set_original()
            return self.translate_attribute(self._fields[fieldName])
            
        raise AttributeError("Entity '%s' has no field '%s'" % (self._entity_type,
                                                                fieldName))

    def modified_fields(self):
        """
        Returns a list of all of the fields in the entity that have changed
        """
        return self._fields_changed.keys()
    
    def commit(self):
        """
        Write any changed fields back to the Shotgun database
        """
        if self._entity_id:
            if not self.modified_fields():
                return False
            
            self._shotgun.update(self, self._fields_changed.keys())
            self._fields_changed = {}
        else:
            self._entity_id = self._shotgun.create(self)
            self._shotgun.register_entity(self)
        
        return True
    
    def delete(self):
        """
        Delete this entity from Shotgun
        """
        self._shotgun.delete(self)
    
    def revert(self, revert_fields = None):
        """
        Revert all changed fields (or just the specified ones) back
        to how they were in the Shotgun database originally
        """
        if revert_fields == None:
            revert_fields = self.modified_fields()
        elif type(revert_fields) == "str":
            revert_fields = [revert_fields]
        
        for field in self.modified_fields():
            if field in revert_fields:
                self._fields[field] = self._fields_changed[field]
                del self._fields_changed[field]
                if isinstance(self._fields[field], MultiEntity):
                    self._fields[field].set_original()
    
    @staticmethod
    def compare_field_values(valueA, valueB):
        """
        Compare two field values. This has a specific use
        """
        if isinstance(valueA, dict) and isinstance(valueB, dict):
            if 'local_path' in valueA \
            and 'local_path' in valueB \
            and valueA['local_path'] == valueB['local_path']:
                return True
            
        
        if valueA == valueB:
            return True
        else:
            return False
    
    def set_field(self, fieldName, value):
        """
        Set a field in the entity to a specified value
        """
        
        altFieldName = "sg_%s" % fieldName
        if fieldName not in self.all_fields() and altFieldName in self.all_fields():
            fieldName = altFieldName

        fieldDetails = self._shotgun.get_entity_field_details(self._entity_type, fieldName)
        if fieldDetails:
            # Disable editable check, as some fields that are marked as uneditable, actually
            # are, under certain circumstances (like created_by and updated_by) 
            if 1: # entityFields[fieldName]['editable']['value'] == True:
                fieldType = fieldDetails['data_type']
                if value is not None:
                    if fieldType == "entity" \
                    and not isinstance(value, Entity):
                        for validType in fieldDetails['valid_types']:
                            if validType in self._shotgun.get_entities():
                                entity = self._shotgun.find_entity(validType, value)
                                if entity:
                                    value = entity
                                    break
                        if not isinstance(value, Entity):
                            raise ShotgunError("Cannot find a valid entity for %s ('%s')" % \
                                                (fieldName,
                                                 value))
                    elif fieldType == "multi_entity":
                        if not isinstance(value, list):
                            value = [value]
                        
                        oldValue = value
                        value = []
                        for v in oldValue:
                            if not isinstance(v, Entity):
                                for validType in fieldDetails['valid_types']:
                                    if validType in self._shotgun.get_entities():
                                        entity = self._shotgun.find_entity(validType, v)
                                        if entity:
                                            v = entity
                                            break
                                if not isinstance(v, Entity):
                                    raise ShotgunError("Cannot find a valid entity for %s ('%s')" % \
                                                        (fieldName,
                                                        v))
                            value.append(v)
                    elif fieldType in ["url"]:
                        if isinstance(value, str):
                            value = {'local_path': value}

                if self._entity_id:
                    oldValue = self.field(fieldName)
                    if not self.compare_field_values(value, oldValue):
                        if fieldName in self._fields_changed \
                        and value == self._fields_changed[fieldName]:
                            del self._fields_changed[fieldName]
                        elif fieldName not in self._fields_changed:
                            self._fields_changed[fieldName] = oldValue
                else:
                    if value != None:
                        self._fields_changed[fieldName] = None
                    elif fieldName in self._fields_changed:
                        del self._fields_changed[fieldName]
                self._fields[fieldName] = value
            else:
                raise AttributeError("Field '%s' in Entity '%s' is not editable" % \
                                        (fieldName,
                                         self._entity_type))
        else:
            raise AttributeError("Entity '%s' has no field '%s'" % \
                                    (self._entity_type,
                                     fieldName))
        
    def __getattr__(self, attrName):
        return self.field(attrName)
    
    def __setattr__(self, attrName, value):
        if attrName[0] == "_":
            self.__dict__[attrName] = value
            return
            
        self.set_field(attrName, value)

    def __getitem__(self, itemName):
        return self.field(itemName)
        
    def __setitem__(self, itemName, value):
        self.set_field(itemName, value)
    
    def __cmp__(self, e):
        if not isinstance(e, Entity):
            return 1
        
        if self.entity_type() > e.entity_type():
            return 1
        elif self.entity_type() < e.entity_type():
            return -1
        elif self.entity_id() > e.entity_id():
            return 1
        elif self.entity_id() < e.entity_id():
            return -1
        
        return 0
