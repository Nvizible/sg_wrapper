===============
Shotgun Wrapper
===============


Creating the Shotgun Wrapper object
::

 sgServer = "https://demo.shotgunstudio.com"
 sgScriptName = "demo_script"
 sgScriptKey = "abcdefghijklmnopqrstuvwxyz1234567890abcd"

 sg = sg_wrapper.Shotgun(sgServer, sgScriptName, sgScriptKey)

Requesting entities
-------------------

Requesting all entities
::

 projects = sg.Projects()
 for project in projects:
     print "%(name)s (%(code)s : %(id)d)" % project

Requesting an entity by code
::

 p = sg.Project("my_project")

Requesting an entity by another field::

 p = sg.Project(name = "My Project")


Modifying entities
::

 shots = sg.Shots(project = p)
 for shot in shots:
     if shot.sg_status_list == "ip":
         shot.sg_status_list = "cmpt"
         shot.commit() # Actually write any changes to Shotgun

Requesting entities using a more complex filter
::

 shots = sg.Shots(project = p, sg_status_list = "cmpt")

Structure of entity request calls
---------------------------------

The 'function' that is a part of the Shotgun Wrapper object can be a number of things. It can be singular of plural, and can reference the entity type or the entity name.

As an example, the 'HumanUser' entity type has the entity name of 'Person'. If the entity name has whitespace in it, then this is just removed (so "Mocap Routine", which is of type "Routine", would be referenced by "Routine" or "MocapRoutine")

The following two lines are equivalent
::

 me = sg.HumanUser("hughmacdonald")
 me = sg.Person("hughmacdonald")

They can also be requested using the plural form of the type or name. "Person" is the one non-standard plural (being "People"), but all others are covered by the following rules:

* If singular is "Person", then plural is "People"
* If singular ends in "y", but does not end in "Day" : Replace the "y" with "ies". e.g. Company -> Companies, Delivery -> Deliveries, but ShootDay -> ShootDays
* If singular ends in "s" or "h" : Add "es". e.g. Launch -> Launches, MocapPass -> MocapPasses
* Otherwise, add "s". e.g. Project -> Projects, Scene -> Scenes

If the name or type ends in a number (e.g. CustomEntity01), the it will just add an "s" to the end, giving "CustomEntity01s". Beacuse you can reference by name as well as type, it is envisaged that you would never reference "CustomEntity01", but would instead reference it by the name you gave it.

Only the plural form can be called without any arguments, meaning that you wish to request all of that type of entity. Calling the singular form without any arguments is the way of creating a new entity, which will be covered below.

To find all of the HumanUser (People) entities:
::

 people = sg.People()

Arguments that can be passed to the requesting function

fields (optional)
    A list of fields to request. If this is omitted, it will query the schema for the full list of fields.
exclude_fields (optional)
    A list of fields to exclude. This overrides fields passed into 'fields'. It is useful for avoiding slow fields (like image downloads)
order
    The order that you want the entities to be returned in. This is the same as the order argument in the shotgun API, with the exception that if it is just one field to sort on, it doesn't need to be a single-length list. e.g. {'field_name': "foo", 'direction': "asc"} or [{'field_name': "foo", 'direction': "asc"}, {'field_name': "bar", 'direction': "desc"}]
limit
    The maximum number of entities to return. This defaults to 0, which results in all entities being returned.

Any other keyword argument that is passed in is considered part of the filter. All filters are combined with AND.

If a non keyword argument is passed in, then it is either considered to be the ID (if it is an integer) or the primary key (if it is a string). The primary key is either "code" or "login", depending on which of these exist in the entity's schema. Most entities have "code", but HumanUser has "login".

The following lines will find the same person. The first will find by the "name" field, the second by the "login" field, and the third by the ID
::

 me = sg.Person(name = "Hugh Macdonald")
 me = sg.Person("hughmacdonald")
 me = sg.Person(8)

Creating new entities
---------------------

To create a new entity, call the singular version of the requesting function with no arguments
::

 s = sg.Shot()

And then continue setting values and committing as with requested entities (see below).

Note: The 'id' field won't be valid until the data has been committed to Shotgun. You will also not be able to assign it to fields in other entities until this point either.

Setting entity fields
---------------------

To set fields on entities, treat the fields as member variables on the entity objects
::

 me.email = "some.other@email.com"
 me.commit()

Calling *commit()* on the entity will push the data back up to Shotgun. Only changed data will be sent back.

If you want to revert a change to what was most recently pulled from Shotgun, you can use the *revert()* method. This can either take a field name, a list of field names, or no arguments, in which case it will revert all changed fields.
::

 me.revert("email")
 me.revert(["email", "name"])
 me.revert()

You can also call *commit_all()* on the Shotgun Wrapper object, which will call *commit()* on all entities with changed values.
::

 sg.commit_all()

If you believe that the data on the Shotgun server end might have changed, you can request that it be re-loaded from the server
::

 me.reload()

Caching of entities
-------------------
Any entity requests are cached, as are the results and it will use the cached version if you search for an entity by ID, or the entity is linked from another entity (which is the equivalent). All searches are also cached, and will return the same result if searched for again. To clear the cache, and force any requests to update from the server, call *clear_cache()* on the Shotgun Wrapper object.
::

 sg.clear_cache()



=====================
Custom Entity Classes
=====================

Custom entity classes can be written, to allow extra functionality alongside the data that is kept
in Shotgun, and in the Entity class.

These are standard Python modules, but are not kept in a path defined by PYTHONPATH - they have their
own environment variable, which can be defined in the configuration section at the top of sg_wrapper.py
This is defined in the config variable ENTITY_CLASS_ENV, and defaults to SG_WRAPPER_ENTITY_PATH.

In all of the examples below, <entity_type> can either refer to the actual internal entity type, or
the entity name (for example, "HumanUser" vs "Person", or "CustomEntity01" vs whatever you called it)
In cases where the entity name has whitespace in it, this is stripped out, and not replaced with anything.

Modules are always lowercase, and classes use the same capitalisation as the entity type/name or
discriminator.

Creating custom entity classes
------------------------------

Inside any of these paths, the following structure is expected:
::

 ./<entity_type>/__init__.py
                 base.py
                 <entity_class>.py

base.py is a special case, as this stores the class for the base entity type, whereas any
<entity_class>.py files will store subclasses of this. __init__.py should 

The following code is an example for the Version entity, where there is a subclass called ClientVersion.

**__init__.py**
::

 from base import Version

**base.py**
::

 from sg_wrapper import Entity

 class Version(Entity):
     def __init__(self, shotgun, entity_type, fields):
         Entity.__init__(self, shotgun, entity_type, fields)
        
**clientversion.py**
::

 from version import Version
    
 class ClientVersion(Version):
     def __init__(self, shotgun, entity_type, fields):
         Version.__init__(self, shotgun, entity_type, fields)

Loading entities as the custom class
------------------------------------

Creating new custom entity classes is not done by directly calling their constructors. It is still done
through the Shotgun Wrapper object.

Create a new Version object
::

 sg.Version()
    
Creates an Entity object, linked to the Shot, as there is no Shot custom entity class
::

 sg.Shot()
    
Creates a new ClientVersion object, and sets the discriminator to "ClientVersion"
::

 sg.ClientVersion()
    
Returns a list of Version and ClientVersion objects. Any with the discriminator "ClientVersion" will be ClientVersion objects, and others will be Version objects. Arguments are as they would be for any other entity request.
::

 sg.Versions(<arguments>)
    
Creates a list of Version objects, as per sg.Versions(<filters>) and then filters this down again by which ones can be case to ClientVersion This is not the same as sg.Versions(<filters>, sg_discriminator = "ClientVersion") as this will also return objects where the custom entity class (and discriminator) are subclasses of ClientVersion.
::

 sg.ClientVersions(<arguments>)

In cases where a factory function is required, this should always expect the Shotgun object as its
first parameter, and can be called with:
::

 sg.ClientVersion.createNew(<parameters>)

This would call the following custom function:
::

 class ClientVersion(Version):
     @classmethod
     def createNew(cls, sg, <parameters>):
         ver = sg.ClientVersion()
         ver.code = "something custom"
         # Set any other default values here
         return ver

Note that cls() should not be called directly, as this requires queries to be performed on the Shotgun
database before being called.

Note also that custom entity classes of different base entities cannot be called the same thing. So,
for example, there could not be a subclass of Version called Client as well as a subclass of Delivery
called Client.
