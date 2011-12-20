from google.appengine.dist import use_library
use_library('django', '1.2')
from google.appengine.ext import webapp
from google.appengine.ext.webapp import util
from google.appengine.api import urlfetch
from google.appengine.ext.webapp import template
from google.appengine.api import memcache
from django.utils import simplejson
import logging
import Cookie
import config
import os
import uuid
import cgi
import datetime
import time
import calendar
from models import *

class Index(webapp.RequestHandler):
    def get(self):
        cookie = None
        try:
            cookie = self.request.cookies['VenueOwner']
        except KeyError:
            logging.info('no cookie')
        if cookie:
            self.redirect("/settings")
        else:
            path = os.path.join(os.path.dirname(__file__), 'templates/homepage.html')
            self.response.out.write(template.render(path, {}))

class FourSquareOAuthRequest(webapp.RequestHandler):
    
    def get(self):
        self.redirect("https://foursquare.com/oauth2/authenticate?client_id=%s&response_type=code&redirect_uri=%s" % (config.fs_key, config.fs_return_url))

class FourSquareOAuthRequestValid(webapp.RequestHandler):
    def get(self):
        code = self.request.get('code')
        url = "https://foursquare.com/oauth2/access_token?client_id=%s&client_secret=%s&grant_type=authorization_code&redirect_uri=%s&code=%s" % (config.fs_key, config.fs_secret, config.fs_return_url, code)
        logging.info(url)
        auth_json = urlfetch.fetch(url, validate_certificate=False)
        access_token = simplejson.loads(auth_json.content)
        
        self_response_url = "https://api.foursquare.com/v2/venues/managed?oauth_token=%s" % (access_token['access_token'])
        self_response_json = urlfetch.fetch(self_response_url, validate_certificate=False)
        self_response = simplejson.loads(self_response_json.content)
        
        if not self_response['response']['venues']:
            self.redirect("/error/1")
        else:
            query = db.Query(VenueOwner)
            query.filter('token =', access_token['access_token'])
            results = query.fetch(limit=1)
            if len(results) > 0:
                logging.info('user exists')
                user = results[0]
            else:     
                self_response_url = "https://api.foursquare.com/v2/users/self?oauth_token=%s" % (access_token['access_token'])
                self_response_json = urlfetch.fetch(self_response_url, validate_certificate=False)
                self_response = simplejson.loads(self_response_json.content)
                u = uuid.uuid4()        
                user = VenueOwner(key_name=str(u))
                user.token = access_token['access_token']
                user.fs_user_id = str(self_response['response']['user']['id'])
                user.phone_number = self_response['response']['user']['contact']['phone']
                user.fs_firstName = self_response['response']['user']['firstName']
                user.fs_lastName = self_response['response']['user']['lastName']
                self_response_url = "https://api.foursquare.com/v2/venues/managed?oauth_token=%s" % (access_token['access_token'])
                self_response_json = urlfetch.fetch(self_response_url, validate_certificate=False)
                self_response = simplejson.loads(self_response_json.content)
                for venue in self_response['response']['venues']:
                    key = venue['id'] + "-" + user.fs_user_id
                    managedVenue = ManagedVenue(key_name=key)
                    managedVenue.fs_venue_id = venue['id']
                    managedVenue.fs_manager = user.fs_user_id
                    managedVenue.fs_name = venue['name']
                    managedVenue.fs_address = venue['location']['address']
                    managedVenue.fs_city = venue['location']['city']
                    managedVenue.fs_state = venue['location']['state']
                    managedVenue.put()
                    user.venues_managed.append(key)
                user.put()

            # set the cookie
            expires = datetime.datetime.now() + datetime.timedelta(weeks=2)
            expiresString = expires.strftime('%a, %d %b %Y %H:%M:%S') # Wdy, DD-Mon-YY HH:MM:SS GMT
            self.response.headers.add_header(
                  'Set-Cookie', 'VenueOwner=%s; expires=%s' % (user.key().name(), expiresString))
            self.redirect("/settings")

class ReceiveHereNow(webapp.RequestHandler):
    """Received a pushed checkin and store it in the datastore."""
    def post(self):
        checkin_json = simplejson.loads(self.request.get('checkin'))
        user_id = checkin_json['user']['id']
        venue_id = checkin_json['venue']['id']
        
        # query to get the owner
        query = db.Query(ManagedVenue)
        query.filter('fs_venue_id =', venue_id)
        results = query.fetch(limit=1)
        managedVenue = None
        venueOwner = None
        if len(results) > 0:
            logging.info('yea,right?')
            managedVenue = results[0]
            query = db.Query(VenueOwner)
            query.filter('fs_user_id =', managedVenue.fs_manager)
            results = query.fetch(limit=1)
            venueOwner = results[0]
        else:
            logging.info('wwooops')
        
        key = user_id + "-" + venue_id
        customer = Customer.get_or_insert(key)
        customer.fs_user_id = user_id
        customer.fs_venue_id = venue_id
        customer.fs_venue_name = checkin_json['venue']['name']
        customer.fs_createdAt.append(checkin_json['createdAt'])
        customer.fs_timeZone = checkin_json['timeZone']
        if 'photo' in checkin_json['user']:
            customer.fs_photo = checkin_json['user']['photo'] #.replace('_thumbs','')
        customer.fs_firstName = checkin_json['user']['firstName']
        if 'lastName' in checkin_json['user']:
            customer.fs_lastName = checkin_json['user']['lastName']
        if 'gender' in checkin_json['user']:
            customer.fs_gender = checkin_json['user']['gender']
        if 'homeCity' in checkin_json['user']:
            customer.fs_homeCity = checkin_json['user']['homeCity']
            
        # can we just get the check-in count from foursquare?
        customer.expires = datetime.datetime.now() + datetime.timedelta(days=1)
        sixtyDaysAgo = datetime.datetime.now() - datetime.timedelta(days=60)
        checkinCount = 0
        for date in customer.fs_createdAt:
            if datetime.datetime.fromtimestamp(float(date)) > sixtyDaysAgo:
                checkinCount += 1
        customer.checkinCount = checkinCount
        
        # check if they're mayor
        self_response_url = "https://api.foursquare.com/v2/venues/%s?oauth_token=%s" % (venue_id, venueOwner.token)
        self_response_json = urlfetch.fetch(self_response_url, validate_certificate=False)
        self_response = simplejson.loads(self_response_json.content)
        if self_response['response']['venue']['mayor']['count'] > 0:
            if self_response['response']['venue']['mayor']['user']['id'] == user_id:
                customer.isMayor = True
            else:
                customer.isMayor = False
        
        # get twitter username
        self_response_url = "https://api.foursquare.com/v2/users/%s?oauth_token=%s" % (customer.fs_user_id, venueOwner.token)
        self_response_json = urlfetch.fetch(self_response_url, validate_certificate=False)
        self_response = simplejson.loads(self_response_json.content)
        if 'twitter' in self_response['response']['user']['contact']:
            customer.fs_twitter = self_response['response']['user']['contact']['twitter']
            self_response_url = "http://api.twitter.com/1/users/show.json?screen_name=" + customer.fs_twitter
            self_response_json = urlfetch.fetch(self_response_url, validate_certificate=False)
            self_response = simplejson.loads(self_response_json.content)
            if 'description' in self_response:
                customer.twitter_bio = self_response['description']
        
        # get tips        
        self_response_url = "https://api.foursquare.com/v2/users/%s/tips?sort=recent&oauth_token=%s" % (customer.fs_user_id, venueOwner.token)
        self_response_json = urlfetch.fetch(self_response_url, validate_certificate=False)
        self_response = simplejson.loads(self_response_json.content)
        
        if self_response['response']['tips']['items']:
            for tip in self_response['response']['tips']['items']:
                if venue_id == tip['venue']['id']:
                    tip_id = tip['id']
                    tipHere = Tip(key_name=tip_id)
                    tipHere.fs_tip_id = tip_id
                    tipHere.fs_createdAt = tip['createdAt']
                    tipHere.fs_tip_text = tip['text']
                    tipHere.fs_todo_count = tip['todo']['count']
                    tipHere.fs_done_count = tip['done']['count']
                    if 'photo' in tip:
                        for size in tip['photo']['sizes']['items']:
                            if size['width'] == 300:
                                tipHere.fs_photo = size['url']
                    tipHere.put()
                    if tip_id not in customer.tipsHere:
                        customer.tipsHere.append(tip_id)
        
        # get photos here
        
        
        customer.put()


class LoyalCustomer(webapp.RequestHandler):
    def get(self, customer_id):
        customer = Customer.get_by_key_name(customer_id)
        
        if datetime.datetime.now() < customer.expires:
            path = os.path.join(os.path.dirname(__file__), 'templates/customer.html')
            self.response.out.write(template.render(path, {'customer' : customer}))
        else:
            self.redirect("/error/2")

class iPad(webapp.RequestHandler):
  def get(self):
    path = os.path.join(os.path.dirname(__file__), 'templates/ipad.html')
    self.response.out.write(template.render(path, {}))

class HereNow(webapp.RequestHandler):
  def get(self):
      cookie = None
      try:
          cookie = self.request.cookies['VenueOwner']
      except KeyError:
          logging.info('no cookie')
      if cookie:
          cookieUser = VenueOwner.get_by_key_name(cookie)
          thisVenue = ManagedVenue.get_by_key_name(cookieUser.venues_managed[0])

          self_response_url = "https://api.foursquare.com/v2/venues/%s/herenow?oauth_token=%s" % (thisVenue.fs_venue_id, cookieUser.token)
          self_response_json = urlfetch.fetch(self_response_url, validate_certificate=False)
          self_response = simplejson.loads(self_response_json.content)
          logging.info(self_response_url)
          
          logging.info(self_response)
          
          hereNow = []
          
          for visitor in self_response['response']['hereNow']['items']:
            
              key = visitor['user']['id'] + "-" + thisVenue.fs_venue_id
              customer = memcache.get(key)
              if customer is None:
                  customer = Customer.get_by_key_name(key)
                  memcache.add(key, customer, 3600)
              hereNow.append(customer)
              
          path = os.path.join(os.path.dirname(__file__), 'templates/hereNow.html')
          self.response.out.write(template.render(path, {'hereNow' : hereNow}))

class Logout(webapp.RequestHandler):
    def get(self):
        cookie = None
        try:
            cookie = self.request.cookies['VenueOwner']
        except KeyError:
            logging.info('no cookie')
        if cookie:
            self.response.headers.add_header(
                'Set-Cookie', 'VenueOwner=%s; expires=Thu, 01-Jan-1970 00:00:01 GMT' % cookie)
        self.redirect("/")

class Error(webapp.RequestHandler):
    def get(self, error_code):
        logging.info(error_code)
        path = os.path.join(os.path.dirname(__file__), 'templates/error.html')
        self.response.out.write(template.render(path, {'error': int(error_code)}))

def main():
    application = webapp.WSGIApplication([('/', Index),
                                          ('/auth', FourSquareOAuthRequest),
                                          ('/authreturn', FourSquareOAuthRequestValid),
                                          ('/customer/(.*)', LoyalCustomer),
                                          ('/logout', Logout),
                                          ('/error/(.*)', Error),
                                          ('/ipad', iPad),
                                          ('/checksin', ReceiveHereNow),
                                          ('/hereNow', HereNow)],
                                         debug=True)                                         
    util.run_wsgi_app(application)


if __name__ == '__main__':
    main()
