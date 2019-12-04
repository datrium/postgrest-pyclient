#
# Copyright (c) 2017-2019 Datrium Inc.
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

import datetime
import json
import logging
import os
import re
import requests
import sys

try:
    # try python3 import
    import urllib.parse as urlparse
except ImportError:
    # fallback to python2 import
    import urlparse

logging.getLogger('requests.packages.urllib3.connectionpool').setLevel(logging.WARN)


class PostgrestException(requests.exceptions.HTTPError):
    pass


class PostgrestResource(object):
    _meta_table_name = ''

    def __init__(self, api, attrs=None):
        self.api = api
        attrs = attrs or {}
        self.attrs = attrs.copy()

    @property
    def connection_url(self):
        return self.api.connection_url + '/%s' % self._meta_table_name

    @property
    def _get_or_create_keys(self):
        raise NotImplementedError()  # must be implemented by concrete Resource

    @property
    def _pk_dict(self):
        raise NotImplementedError()  # must be implemented by concrete Resource

    @property
    def _pk_url(self):
        query_string = '&'.join(['%s=%s' % (k,v) for k,v in self._pk_dict.items()])
        return self.connection_url + '?' + query_string

    def __getattr__(self, name):
        if name in self.attrs:
            return self.attrs[name]
        raise AttributeError("'%s' object has no attribute '%s'" % (self.__class__.__name__, name))

    def __hash__(self):
        return hash(tuple(sorted(self._pk_dict.items())))

    def __eq__(self, other):
        return hash(self) == hash(other)

    @property
    def as_json(self):
        attrs = self.attrs.copy()
        attrs['_class'] = '.'.join([self.__class__.__module__, self.__class__.__name__])
        return json.dumps(attrs, sort_keys=True)

    def as_datetime(self, d):
        formats = ['%Y-%m-%dT%H:%M:%S+00:00', '%Y-%m-%dT%H:%M:%S.%f+00:00', '%Y-%m-%dT%H:%M:%S.%f']
        for fmt in formats:
            try:
                return datetime.datetime.strptime(d, fmt)
            except ValueError:
                continue
        raise ValueError('%s does not match any of %s' % (d, formats))

    def filter(self, params=None):
        headers = self.api.common_headers()
        params = params or {}
        #logging.info('url: %s, params: %s' % (self.connection_url, params))
        try:
            resp = self.api.session.get(self.connection_url, params=params, headers=headers)
            resp.raise_for_status()
        except requests.exceptions.HTTPError as e:
            raise PostgrestException(str(e), response=resp)
        objs, _ = resp.json(), resp.headers
        return [self.__class__(self.api, attrs=x) for x in objs]

    def get(self, params):
        objects = self.filter(params)
        if objects:
            assert len(objects) == 1, objects
            return objects[0]
        return None

    def refresh(self):
        obj = self.get(self._pk_dict)
        self.attrs = obj.attrs.copy()

    def put(self, payload):
        headers = self.api.common_headers()
        json_data = json.dumps(payload)
        json_data = re.sub(r'\\u0000', '', json_data)
        try:
            resp = self.api.session.patch(self._pk_url, data=json_data, headers=headers)
            resp.raise_for_status()
        except requests.exceptions.HTTPError as e:
            logging.exception(e)
            logging.error(json_data)
            raise PostgrestException(str(e), response=resp)
        return resp.json(), resp.headers

    def update(self, payload=None):
        if payload:
            self.put(payload)
        self.refresh()

    def post(self, payload=None):
        headers = self.api.common_headers()
        # headers['Prefer'] = 'return=representation,resolution=merge-duplicates'  # cannot us resolution for pg < 9.5 (asupdb)
        headers['Prefer'] = 'return=representation'
        try:
            resp = self.api.session.post(self.connection_url, data=json.dumps(payload), headers=headers)
            resp.raise_for_status()
        except requests.exceptions.HTTPError as e:
            raise PostgrestException(str(e), response=resp)
        return resp.json(), resp.headers

    def create(self, payload):
        attrs, headers = self.post(payload)
        return self.__class__(self.api, attrs=attrs[0])

    def delete(self):
        headers = self.api.common_headers()
        try:
            resp = self.api.session.delete(self._pk_url, headers=headers)
            resp.raise_for_status()
        except requests.exceptions.HTTPError as e:
            logging.exception(e)
            raise PostgrestException(str(e), response=resp)
        return

    def get_or_create(self, params):
        def __get(params):
            d = {}
            for k, v in params.items():
                if k in self._get_or_create_keys:
                    d[k] = 'eq.%s' % v
                    if v is None:
                        d[k] = 'is.null'
            return self.get(d)

        for k in self._get_or_create_keys:
            if k not in params:
                raise ValueError('Must provide "%s" param for %s get_or_create!' % (k, self.__class__.__name__))

        found = __get(params)
        if found:
            return found, False
        try:
            return self.create(params), True
        except PostgrestException as e:
            if '409 Client Error: Conflict for' not in str(e):
                raise
        return __get(params), False


class PostgrestAPI(object):
    resources = [PostgrestResource]

    def __init__(self, connection_url=None, session=None):
        self.connection_url = connection_url
        if not re.match(r'https?://', self.connection_url):
            self.connection_url = 'http://' + self.connection_url
        parts = urllib.parse.urlparse(self.connection_url)
        self.connection_url = parts.scheme + '://' + parts.netloc
        self.session = session or requests.Session()
        for cls in self.resources:
            setattr(self, cls.__name__, cls(self))
        self.related_apis = {}

    def common_headers(self):
        return  {
            'Prefer': 'return=representation',
            'Content-type': 'application/json'
        }

    def add_related_api(self, name, api):
        self.related_apis[name] = api
