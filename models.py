from google.appengine.ext import db

class VenueOwner(db.Model):
    fs_user_id = db.StringProperty()
    phone_number = db.PhoneNumberProperty()
    token = db.StringProperty()
    fs_firstName = db.StringProperty()
    fs_lastName = db.StringProperty()
    venues_managed = db.StringListProperty()

    @property
    def get_all_venues(self):
        listOfVenues = []
        for key in self.venues_managed:
            listOfVenues.append(ManagedVenue.get_by_key_name(key))
        return listOfVenues
        
class Customer(db.Model):
    fs_user_id = db.StringProperty()
    fs_venue_id = db.StringProperty()
    fs_venue_name = db.StringProperty()
    fs_firstName = db.StringProperty()
    fs_lastName = db.StringProperty()
    fs_createdAt = db.ListProperty(int)
    fs_photo = db.StringProperty()
    fs_timeZone = db.StringProperty()
    fs_gender = db.StringProperty()
    fs_homeCity = db.StringProperty()
    fs_twitter = db.StringProperty()
    isMayor = db.BooleanProperty()
    expires = db.DateTimeProperty()
    checkinCount = db.IntegerProperty()
    tipsHere = db.StringListProperty()
    twitter_bio = db.StringProperty()

    @property
    def get_tips(self):
        listOfTips = []
        for key in self.tipsHere:
            listOfTips.append(Tip.get_by_key_name(key))
        return listOfTips
        
class ManagedVenue(db.Model):
    fs_venue_id = db.StringProperty()
    fs_manager = db.StringProperty()
    fs_name = db.StringProperty()
    fs_address = db.StringProperty()
    fs_city = db.StringProperty()
    fs_state = db.StringProperty()
    mayorAlert = db.BooleanProperty(default=True)
    freqAlert = db.BooleanProperty(default=True)
    freqAlertVal = db.IntegerProperty(default=5)
    
class Tip(db.Model):
    fs_tip_id = db.StringProperty()
    fs_createdAt = db.IntegerProperty()
    fs_tip_text = db.StringProperty()
    fs_todo_count = db.IntegerProperty()
    fs_done_count = db.IntegerProperty()
    fs_photo = db.StringProperty()
    
class HereNow(db.Model):
    temp_user_id = db.StringProperty()
    temp_photo = db.StringProperty()
    temp_firstName = db.StringProperty()
    temp_lastName = db.StringProperty()