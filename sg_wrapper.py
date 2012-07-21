import shotgun_api3

# The Primary Text Keys are the field names to check when not defined.
# For example, calling sg.Project("my_project") will be the same as sg.Project(code = "my_project")
primaryTextKeys = ["code", "login"]

# For most entity types, the pluralise() function will define what the plural version of the entity name is.
# This dictionary defines any custom plural forms that we might want to have.
customPlural = {'Person': "People"}

# This is the base Shotgun class. Everything is created from here, and it deals with talking to the
# standard Shotgun API.
class Shotgun():
	def __init__(self, sgServer, sgScriptName, sgScriptKey):
		self._sg = shotgun_api3.Shotgun(sgServer, sgScriptName, sgScriptKey)
		self._entity_types = self.get_entity_list()
		self._entity_fields = {}
		self._entities = {}
		self._entity_searches = []
	
	def pluralise(self, name):
		if name in customPlural:
			return customPlural[name]
		if name[-1] == "y" and name[-3:] != "Day":
			return name[:-1] + "ies"
		if name[-1] in ["s", "h"]:
			return name + "es"
		
		return name + "s"
	
	def get_entity_list(self):
		entitySchema = self._sg.schema_entity_read()
		entities = []
		for e in entitySchema:
			newEntity = {'type': e, 'name': entitySchema[e]['name']['value'].replace(" ", ""), 'fields': []}
			newEntity['type_plural'] = self.pluralise(newEntity['type'])
			newEntity['name_plural'] = self.pluralise(newEntity['name'])
			entities.append(newEntity)
			
		return entities
	
	def get_entity_field_list(self, entityType):
		fields = self.get_entity_fields(entityType)
		return fields.keys()
	
	def get_entity_fields(self, entityType):
		if entityType not in self._entity_fields:
			self._entity_fields[entityType] = self._sg.schema_field_read(entityType)
		return self._entity_fields[entityType]
	
	def is_entity(self, entityType):
		for e in self._entity_types:
			if entityType in [e['type'], e['name']]:
				return True
		return False
	
	def is_entity_plural(self, entityType):
		for e in self._entity_types:
			if entityType in [e['type_plural'], e['name_plural']]:
				return True
		return False
	
	def find_entity(self, entityType, key = None, find_one = True, fields = None, exclude_fields = None, **kwargs):
		filters = {}
		
		thisEntityType = None
		thisEntityFields = None
		
		for e in self._entity_types:
			if entityType in [e['type'], e['name'], e['type_plural'], e['name_plural']]:
				thisEntityType = e['type']
				if not e['fields']:
					e['fields'] = self.get_entity_field_list(thisEntityType)
				thisEntityFields = e['fields']
		
		if key:
			if type(key) == int:
				filters['id'] = key
			elif type(key) == str:
				foundPrimaryKey = False
				for fieldName in primaryTextKeys:
					if fieldName in thisEntityFields:
						filters[fieldName] = key
						foundPrimaryKey = True
						break
				if not foundPrimaryKey:
					raise ShotgunWrapperError("Entity type '%s' does not have one of the defined primary keys(%s)." % (entityType, ", ".join(primaryTextKeys)))
		
		for arg in kwargs:
			if isinstance(kwargs[arg], Entity):
				filters[arg] = {'type': kwargs[arg].entity_type(), 'id': kwargs[arg].entity_id()}
			else:
				filters[arg] = kwargs[arg]
		
		if 'id' in filters:
			if thisEntityType in self._entities and filters['id'] in self._entities[thisEntityType]:
				return self._entities[thisEntityType][filters['id']]

		if not fields:
			fields = self.get_entity_field_list(thisEntityType)
		
		if exclude_fields:
			for f in exclude_fields:
				if f in fields:
					fields.remove(f)

		for search in self._entity_searches:
			if search['find_one'] == find_one \
			  and search['entity_type'] == thisEntityType \
			  and search['filters'] == filters \
			  and set(fields).issubset(set(search['fields'])):
				return search['result']
		
		sgFilters = []
		for f in filters:
			sgFilters.append([f, 'is', filters[f]])
		
		result = None

		if find_one:
			sg_result = self.sg_find_one(thisEntityType, sgFilters, fields)

			if sg_result:
				result = Entity(self, thisEntityType, sg_result)
		else:
			sg_results = self.sg_find(thisEntityType, sgFilters, fields)
			result = []
			for sg_result in sg_results:
				result.append(Entity(self, thisEntityType, sg_result))

		thisSearch = {}
		thisSearch['find_one'] = find_one
		thisSearch['entity_type'] = thisEntityType
		thisSearch['filters'] = filters
		thisSearch['fields'] = fields
		thisSearch['result'] = result
		self._entity_searches.append(thisSearch)
		
		return result

	def sg_find_one(self, entityType, filters, fields):
		return self._sg.find_one(entityType, filters, fields)

	def sg_find(self, entityType, filters, fields):
		return self._sg.find(entityType, filters, fields)
	
	def update(self, entity, updateFields):
		updateData = {}
		for f in updateFields:
			updateData[f] = entity.field(f)
		self._sg.update(entity._entity_type, entity._entity_id, updateData)
	
	def register_entity(self, entity):
		if entity._entity_type not in self._entities:
			self._entities[entity._entity_type] = {}
		
		if entity._entity_id not in self._entities[entity._entity_type]:
			self._entities[entity._entity_type][entity._entity_id] = entity
	
	def clear_cache(self):
		self._entities = {}
		self._entity_searches = []
	
	def __getattr__(self, attrName):
		def find_entity_wrapper(*args, **kwargs):
			return self.find_entity(attrName, find_one = True, *args, **kwargs)

		def find_multi_entity_wrapper(*args, **kwargs):
			return self.find_entity(attrName, find_one = False, *args, **kwargs)
		
		if self.is_entity(attrName):
			return find_entity_wrapper
		elif self.is_entity_plural(attrName):
			return find_multi_entity_wrapper
	
	def commit_all(self):
		for entityType in self._entities:
			for entityId in self._entities[entityType]:
				for entity in self._entities[entityType][entityId]:
					if entity.modified_fields():
						entity.commit()
		
class Entity():
	def __init__(self, shotgun, entity_type, fields):
		self._entity_type = entity_type
		self._shotgun = shotgun
		self._fields = fields
		self._fields_changed = {}
		self._sg_filters = []

		self._entity_id = self._fields['id']
		self._shotgun.register_entity(self)
	
	def reload(self):
		self._field_names = self._shotgun.get_entity_field_list(self._entity_type)
		self._fields = self._shotgun.sg_find_one(self._entity_type, [["id", "is", self._entity_id]], fields = self._field_names)
	
	def fields(self):
		return self._fields.keys()
	
	def entity_type(self):
		return self._entity_type
	
	def entity_id(self):
		return self._entity_id
	
	def field(self, fieldName):
		if fieldName in self._fields:
			attribute = self._fields[fieldName]
			if type(attribute) == dict and 'id' in attribute and 'type' in attribute:
				if 'entity' not in attribute:
					attribute['entity'] = self._shotgun.find_entity(attribute['type'], id = attribute['id'])
					#attribute['entity'] = Entity(self._shotgun, attribute['type'], {'id': attribute['id']})
				return attribute['entity']
			elif type(attribute) == list:
				iterator = self.list_iterator(self._fields[fieldName])
				attrResult = []
				for item in iterator:
					attrResult.append(item)
				return attrResult
			else:
				return self._fields[fieldName]
			
		raise AttributeError("Entity '%s' has no field '%s'" % (self._entity_type, fieldName))

	def list_iterator(self, entities):
		for entity in entities:
			if 'entity' not in entity:
				entity['entity'] = self._shotgun.find_entity(entity['type'], id = entity['id'])
				#entity['entity'] = Entity(self._shotgun, entity['type'], {'id': entity['id']})
			
			yield entity['entity']
		
	def modified_fields(self):
		return self._fields_changed.keys()
	
	def commit(self):
		if not self.modified_fields():
			return False

		self._shotgun.update(self, self._fields_changed.keys())
		self._fields_changed = {}
		return True
	
	def revert(self, revert_fields = None):
		if revert_fields == None:
			revert_fields = self.modified_fields()
		elif type(revert_fields) == "str":
			revert_fields = [revert_fields]
		
		for field in self.modified_fields():
			if field in revert_fields:
				self._fields[field] = self._fields_changed[field]
				del self._fields_changed[field]
		
	def set_field(self, fieldName, value):
		entityFields = self._shotgun.get_entity_fields(self._entity_type)
		if fieldName in entityFields:
			if entityFields[fieldName]['editable']['value'] == True:
				oldValue = self._fields[fieldName]
				self._fields[fieldName] = value
				if fieldName not in self._fields_changed:
					self._fields_changed[fieldName] = oldValue
			else:
				raise AttributeError("Field '%s' in Entity '%s' is not editable" % (fieldName, self._entity_type))
		else:
			raise AttributeError("Entity '%s' has no field '%s'" % (self._entity_type, fieldName))
		
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