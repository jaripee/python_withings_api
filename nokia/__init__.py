# -*- coding: utf-8 -*-
#
"""
Python library for the Nokia Health API
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Nokia Health API
<https://developer.health.nokia.com/api>

Uses Oauth 2.0 to authentify. You need to obtain a consumer key
and consumer secret from Nokia by creating an application
here: <https://account.health.nokia.com/partner/add_oauth2>

Usage:

auth = NokiaAuth(CONSUMER_KEY, CONSUMER_SECRET, CALLBACK_URL)
authorize_url = auth.get_authorize_url()
print("Go to %s allow the app and copy the url you are redirected to." % authorize_url)
authorization_response = raw_input('Please enter your full authorization response url: ')
creds = auth.get_credentials(authorization_response)

client = NokiaApi(creds)
measures = client.get_measures(limit=1)
print("Your last measured weight: %skg" % measures[0].weight)

creds = client.get_credentials()

"""

from __future__ import unicode_literals

__title__ = 'nokia'
__version__ = '0.4.0'
__author__ = 'Maxime Bouroumeau-Fuseau, and ORCAS'
__license__ = 'MIT'
__copyright__ = 'Copyright 2012-2017 Maxime Bouroumeau-Fuseau, and ORCAS'

__all__ = [str('NokiaCredentials'), str('NokiaAuth'), str('NokiaApi'),
           str('NokiaMeasures'), str('NokiaMeasureGroup')]

import arrow
import datetime
import json

from arrow.parser import ParserError
from requests_oauthlib import OAuth2Session

class NokiaCredentials(object):
    def __init__(self, access_token=None, token_expiry=None, token_type=None,
                 refresh_token=None, user_id=None, 
                 client_id=None, consumer_secret=None):
        self.access_token = access_token
        self.token_expiry = token_expiry
        self.token_type = token_type
        self.refresh_token = refresh_token
        self.user_id = user_id
        self.client_id = client_id
        self.consumer_secret = consumer_secret


class NokiaAuth(object):
    URL = 'https://account.health.nokia.com'

    def __init__(self, client_id, consumer_secret, callback_uri):
        self.client_id = client_id
        self.consumer_secret = consumer_secret
        self.callback_uri = callback_uri

    def get_authorize_url(self, scope='user.metrics'):
        oauth = OAuth2Session(self.client_id,
                              redirect_uri=self.callback_uri, 
                              scope=scope)

        return oauth.authorization_url('%s/oauth2_user/authorize2'%self.URL)[0]

    def get_credentials(self, code):
        
        oauth = OAuth2Session(self.client_id,
                              redirect_uri=self.callback_uri, 
                              scope='user.metrics')
        
        tokens = oauth.fetch_token(
            '%s/oauth2/token' % self.URL,
            code=code,
            client_secret=self.consumer_secret)
        
        return NokiaCredentials(
            access_token=tokens['access_token'],
            token_expiry=str(ts()+int(tokens['expires_in'])),
            token_type=tokens['token_type'],
            refresh_token=tokens['refresh_token'],
            user_id=tokens['userid'],
            client_id=self.client_id,
            consumer_secret=self.consumer_secret,
        )


def is_date(key):
    return 'date' in key


def is_date_class(val):
    return isinstance(val, (datetime.date, datetime.datetime, arrow.Arrow, ))

def ts():
    return int(datetime.datetime.now(tz=datetime.timezone.utc).timestamp())


class NokiaApi(object):
    URL = 'https://api.health.nokia.com'

    def __init__(self, credentials):
        self.credentials = credentials        
        self.token = {
            'access_token': credentials.access_token,
            'refresh_token': credentials.refresh_token,
            'token_type': credentials.token_type,
            'expires_in': str(int(credentials.token_expiry) - ts()),
        }
        extra = {
            'client_id': credentials.client_id,
            'client_secret': credentials.consumer_secret,
        }
        refresh_url = 'https://account.health.nokia.com/oauth2/token'
        self.client = OAuth2Session(credentials.client_id, 
                                    token=self.token, 
                                    auto_refresh_url=refresh_url, 
                                    auto_refresh_kwargs=extra, 
                                    token_updater=self.set_token)
        
    def get_credentials(self):
        return self.credentials
    
    def set_token(self, token):
        self.token = token
        self.credentials.token_expiry = str(ts()+int(self.token['expires_in']))
        self.credentials.access_token = self.token['access_token']
        self.credentials.refresh_token = self.token['refresh_token']

    def request(self, service, action, params=None, method='GET',
                version=None):
        params = params or {}
        params['access_token'] = self.token['access_token']
        params['userid'] = self.credentials.user_id
        params['action'] = action
        for key, val in params.items():
            if is_date(key) and is_date_class(val):
                params[key] = arrow.get(val).timestamp
        url_parts = filter(None, [self.URL, version, service])
        r = self.client.request(method, '/'.join(url_parts), params=params)
        response = json.loads(r.content.decode())
        if response['status'] != 0:
            raise Exception("Error code %s" % response['status'])
        return response.get('body', None)

    def get_user(self):
        return self.request('user', 'getbyuserid')

    def get_activities(self, **kwargs):
        r = self.request('measure', 'getactivity', params=kwargs, version='v2')
        activities = r['activities'] if 'activities' in r else [r]
        return [NokiaActivity(act) for act in activities]

    def get_measures(self, **kwargs):
        r = self.request('measure', 'getmeas', kwargs)
        return NokiaMeasures(r)

    def get_sleep(self, **kwargs):
        r = self.request('sleep', 'get', params=kwargs, version='v2')
        return NokiaSleep(r)

    def subscribe(self, callback_url, comment, **kwargs):
        params = {'callbackurl': callback_url, 'comment': comment}
        params.update(kwargs)
        self.request('notify', 'subscribe', params)

    def unsubscribe(self, callback_url, **kwargs):
        params = {'callbackurl': callback_url}
        params.update(kwargs)
        self.request('notify', 'revoke', params)

    def is_subscribed(self, callback_url, appli=1):
        params = {'callbackurl': callback_url, 'appli': appli}
        try:
            self.request('notify', 'get', params)
            return True
        except:
            return False

    def list_subscriptions(self, appli=1):
        r = self.request('notify', 'list', {'appli': appli})
        return r['profiles']


class NokiaObject(object):
    def __init__(self, data):
        self.set_attributes(data)

    def set_attributes(self, data):
        self.data = data
        for key, val in data.items():
            try:
                setattr(self, key, arrow.get(val) if is_date(key) else val)
            except ParserError:
                setattr(self, key, val)


class NokiaActivity(NokiaObject):
    pass


class NokiaMeasures(list, NokiaObject):
    def __init__(self, data):
        super(NokiaMeasures, self).__init__(
            [NokiaMeasureGroup(g) for g in data['measuregrps']])
        self.set_attributes(data)


class NokiaMeasureGroup(NokiaObject):
    MEASURE_TYPES = (
        ('weight', 1),
        ('height', 4),
        ('fat_free_mass', 5),
        ('fat_ratio', 6),
        ('fat_mass_weight', 8),
        ('diastolic_blood_pressure', 9),
        ('systolic_blood_pressure', 10),
        ('heart_pulse', 11),
        ('temperature', 12),
        ('spo2', 54),
        ('body_temperature', 71),
        ('skin_temperature', 72),
        ('muscle_mass', 76),
        ('hydration', 77),
        ('bone_mass', 88),
        ('pulse_wave_velocity', 91)
    )

    def __init__(self, data):
        super(NokiaMeasureGroup, self).__init__(data)
        for n, t in self.MEASURE_TYPES:
            self.__setattr__(n, self.get_measure(t))

    def is_ambiguous(self):
        return self.attrib == 1 or self.attrib == 4

    def is_measure(self):
        return self.category == 1

    def is_target(self):
        return self.category == 2

    def get_measure(self, measure_type):
        for m in self.measures:
            if m['type'] == measure_type:
                return m['value'] * pow(10, m['unit'])
        return None


class NokiaSleepSeries(NokiaObject):
    def __init__(self, data):
        super(NokiaSleepSeries, self).__init__(data)
        self.timedelta = self.enddate - self.startdate


class NokiaSleep(NokiaObject):
    def __init__(self, data):
        super(NokiaSleep, self).__init__(data)
        self.series = [NokiaSleepSeries(series) for series in self.series]
