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
        POSTGREST_URL = 'http://my.server.com:3000/my_table'

        @property
        def oid(self):
            return int(self.attrs.get('id'))


    obj = MyTable.get(id=1)
    print obj.url
    print obj.attrs
    print obj.oid

    # filter() can accept ->> with {1}__jsonb__{2}
    for obj in MyTable.filter(column1__jsonb__attribute1='eq.false'):
        print obj.url
        print obj.attrs
        print obj.oid

```