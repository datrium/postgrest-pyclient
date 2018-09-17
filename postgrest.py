#!/usr/bin/env python
#
# Copyright (c) 2017-2018 Datrium Inc.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#      http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
#

import json
import logging
import os
import re
import requests
import sys

logging.getLogger('requests.packages.urllib3.connectionpool').setLevel(logging.WARN)


class PostgrestException(requests.exceptions.HTTPError):
    pass


class Resource(object):
    '''
    Generic Resource class.

    Usage:
    class MyResource(Resource):
        POSTGREST_URL = 'http://my.server.com:3000/my_table'

    objs = MyResource.filter(id='lte.5')


    '''
    POSTGREST_URL = None  # must be defined by concrete subclass, else ValueError at runtime!
    session = requests.Session()

    def __init__(self, *args, **kwargs):
        if self.POSTGREST_URL is None:
            raise ValueError('%s must define a POSTGREST_URL!' % self.__class__.__name__)
        super(Resource, self).__init__(*args, **kwargs)

    @classmethod
    def common_headers(cls):
        return  {
            'Prefer': 'return=representation',
            'Content-type': 'application/json'
        }

    @classmethod
    def urlbase(cls):
        if cls.POSTGREST_URL is None:
            raise ValueError('%s must define a POSTGREST_URL!' % cls.__name__)
        return cls.POSTGREST_URL

    @classmethod
    def get(cls, **kwargs):
        '''
        get kwargs need to be properly formatted postgrest queries.
        '''
        if 'id' in kwargs:  # this is a specific filter, so reduce it
            value = str(kwargs['id'])
            if not value.startswith('eq.'):
                value = 'eq.%s' % value
            kwargs = {'id': value}
        objects = cls.filter(**kwargs)
        if objects:
            assert len(objects) == 1, objects
            return objects[0]
        return None

    @classmethod
    def post(cls, **kwargs):
        headers = cls.common_headers()
        data = kwargs or {}
        resp = cls.session.post(cls.urlbase(), data=json.dumps(data), headers=headers)
        try:
            resp.raise_for_status()
        except requests.exceptions.HTTPError as e:
            raise PostgrestException(str(e))
        return resp.json(), resp.headers

    @classmethod
    def filter(cls, **kwargs):
        headers = cls.common_headers()
        params = kwargs or {}
        # convert jsonb param from __jsonb__ to ->>
        # https://github.com/begriffs/postgrest/pull/183
        for key in params.keys():
            if '__jsonb__' in key:
                params[key.replace('__jsonb__', '->>')] = params[key]
                del params[key]
            if '__json__' in key:
                params[key.replace('__json__', '->>')] = params[key]
                del params[key]
        url = cls.urlbase()
        logging.debug('url: %s, params: %s' % (url, params))
        resp = cls.session.get(cls.urlbase(), params=params, headers=headers)
        try:
            resp.raise_for_status()
        except requests.exceptions.HTTPError as e:
            raise PostgrestException(str(e))
        objs, _ = resp.json(), resp.headers
        return [cls(attrs=x) for x in objs]

    def put(self, **kwargs):
        data = kwargs or {}
        headers = self.common_headers()
        json_data = json.dumps(data)
        json_data = re.sub(r'\\u0000', '', json_data)
        resp = self.session.patch(self.__url, data=json_data, headers=headers)
        try:
            resp.raise_for_status()
        except requests.exceptions.HTTPError as e:
            logging.exception(e)
            logging.error(json_data)
            raise PostgrestException(str(e))
        return resp.json(), resp.headers

    def __init__(self, attrs=None):
        attrs = attrs or {}
        self.attrs = attrs.copy()

    def __eq__(self, other):
        return self.__class__ == other.__class__ and self.attrs.get('id') == other.attrs.get('id')

    def __str__(self):
        return '<%s: %s>' % (self.__class__.__name__, self.__dict__)

    def __hash__(self):
        return hash(self._postgrest_url)

    def refresh(self):
        obj = self.__class__.get(id=self.attrs.get('id'))
        self.attrs = obj.attrs.copy()

    def update(self, **kwargs):
        # filter our keys with None values, because right now these cause data to be deleted
        # but, this means there is no way to intentionally delete/null values right now
        # we can add in a null_keys that contains the column names to
        # allow null values for.
        kwargs = {k:v for k, v in kwargs.items() if v is not None}
        self.put(**kwargs)
        self.refresh()

    @property
    def url(self):
        return self.urlbase() + '?id=eq.%d' % self.attrs.get('id')

    @classmethod
    def create(cls, **kwargs):
        obj, _ = cls.post(**kwargs)
        assert len(obj) == 1, obj
        return cls(attrs=obj[0])

    def rpc(self, name, **kwargs):
        url = self.urlbase().rstrip('/') + '/rpc/' + name
        headers = self.common_headers()
        data = kwargs or {}
        resp = self.session.post(url, data=json.dumps(data), headers=headers)
        try:
            resp.raise_for_status()
        except requests.exceptions.HTTPError as e:
            raise PostgrestException(str(e))
        return resp.json()[0], resp.headers

