# postgrest-pyclient

A Python client for [Postgrest](http://postgrest.org).


## Install
```
pip install --process-dependency-links https://github.com/datrium/postgrest-pyclient/archive/master.zip#egg=postgrest
```

## Example Usage
```python
    import postgrest

    class MyTable(postgrest.Resource):
        _meta_table_name = 'my_table'

        @property
        def _get_or_create_keys(self):
            return ('col1',)

        @property
        def _pk_dict(self):
            return {'id': 'eq.%s' % self.id}

    class MyPostgrestAPI(postgrest.PostgrestAPI):
        resources = [MyTable]



    api = MyPostgrestAPI('http://my.server.com:3000')

    obj = api.MyTable.get({'id': 'eq.1'})

    objs = api.MyTable.filter({'id': 'lte.10', 'col1': 'eq.foo'})

    # filter accepts any syntax that is in postgrest http GET spec
    objs = api.MyTable.filter({
        'id': 'lte.10',
        'col1->obj->>property': 'like.*example*',
        'select': 'id,col1,col2',
        'order': 'id.asc'
    })

    # get_or_create, inspired by django's orm
    obj, created = api.MyTable.get_or_create({
        'col1': 'foo'
    })
```
