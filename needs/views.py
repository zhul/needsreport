from django.http import HttpResponse
from django.template.defaultfilters import slugify

from needs.mongodb import db, get_types_map, get_types
from needs.loc_query import geocode

from twilio import twiml

import time
import json
import math
import random
import uuid

def _find_type(request):
    slug = slugify(request.REQUEST.get('Body', ''))
    m = get_types_map()
    for _type in m.keys():
        if slug.find(_type.lower())>=0:
            return m[_type]

def _uid(request):
    return request.REQUEST['From']

def _new(request):

    r = twiml.Response()

    _type = _find_type(request)
    if not type:
        r.sms('We only support %s needs. Please try again.' % ', '.join(get_types()))
        return HttpResponse(str(r))

    data = dict()

    data['body'] = request.REQUEST.get('Body', '')

    data['from_num'] = request.REQUEST.get('From', None)
    data['type'] = _type

    data['full'] = str(request.REQUEST)
    data['_id'] = _uid(request)
    data['created'] = time.time()

    data['country'] = request.REQUEST.get('FromCountry', None)

    uid = db.needs.save(data)

    if uid:
        if data['country']=='US':
            r.sms('Thanks for sending in your needs for %s. Where are you located? Please only enter city, state E.g. new york, ny' % type)
        else:
            r.sms('Thanks for sending in your needs for %s. Where are you located? Please only enter city, provience, country E.g. istanbul, turkey' % type)

    return HttpResponse(str(r))

def _confirm(request, data):
    location = request.REQUEST.get('Body', '')

    address = location
    res = geocode(address)

    r = twiml.Response()

    if res:
        place, loc = res[0]
        db.needs.update({'_id':_uid(request)}, {'$set': {'loc':loc, 'loc_place':place, 'loc_input':location}})

        count = db.needs.find({'loc_place':place}).count()

        if count>1:
            r.sms('There are %s requests for %s in your area.  Hopefully someone will take action.' % (count, data['type'].lower()))
        else:
            r.sms('You are the first person to request for %s in your area.  Thank you!' % data['type'].lower())
    else:
        r.sms('We do not understand where %s is.  Please try again.' % location)

    return HttpResponse(str(r))

def _too_old(data):
    t = data.get('created', 0)
    return not t or time.time()-t > 3600

def sms(request):
    uid = _uid(request)
    data = db.needs.find_one(dict(_id=uid))

    if not data or _too_old(data) or data.get('loc', None):
        return _new(request)
    else:
        return _confirm(request, data)

def _loc_defined(points):
    for point in points:
        if point==(None, None):
            return False

    return True

def loc_data(request):
    req = json.loads(request.raw_post_data)
    loc_place = req['loc_place']
    start = int(req.get('start', 0))
    end = int(req.get('end', time.time()))
    condition = {'loc_place':loc_place, 'created':{'$lte': end, '$gte': start}}    
    locs = db.needs.group(key={'type':True}, condition=condition, reduce='function(a,c) {c.sum+=1}', initial={'sum':0})
    locs.sort(lambda a,b: int(b['sum']-a['sum']))

    return HttpResponse(json.dumps(locs), content_type='application/json')

def init_data(request):
    types = get_types()
    min_time_res = db.needs.find({'created':{'$exists': True}}).sort('created', 1).limit(1)
    if min_time_res.count()>0:
        min_time = min_time_res[0]['created']
    else:
        min_time = 1325376000

    return HttpResponse(json.dumps(dict(types=types, min_time=min_time)), content_type='application/json')    

def map_data(request):
    req = json.loads(request.raw_post_data)
    start = int(req.get('start', 0))
    end = int(req.get('end', time.time()))
    condition = {'loc':{'$exists': True}, 'created':{'$lte': end, '$gte': start}}
    locs = db.needs.group(key={'type':True, 'loc':True, 'loc_place':True}, condition=condition, reduce='function(a,c) {c.sum+=1}', initial={'sum':0})
    locs.sort(lambda a,b: int(b['sum']-a['sum']))

    data = []    
    for loc in locs:
        value = int(math.log(loc['sum'], 10))+1
        if value>5:
            value=5
        loc['value'] = value
        loc['type'] = loc['type'].title()
        data.append(loc)

    return HttpResponse(json.dumps(dict(types=get_types(), data=data)), content_type='application/json')
