import string
import time
import datetime
import re
import jinja2
import os
from base64 import b64encode
import hashlib
import json
from random import sample, choice
from parse_datetime import *
import calendar
from yastlib import *
from google.appengine.api import users
from google.appengine.api import mail
from google.appengine.ext import ndb
import webapp2

# contract information
#  description
#  identification number
#  start date
#  end date
#  allocated hours
#  billed client name
#  end client name
#  pay rates
#  pay rate schedule [flat, 8/day, 40/week, holiday-extra]

# password info
#  password
#  salt
#  hash function

# contractor information
#  name
#  contact info

# user information
#  name
#  contact info
#  billing id (points to contractor info for another user)

# yast information
#  user id
#  user password
#  parent project yast id

# approver information
#  name
#  contact info

# period info
#  start of period info
#   hours already billed (derived from yast)
#  hours billed
#   estimate total hours (specified prior to period)
#   detail (hours by day) (derived from yast)
#   actual total hours (derived from detail)
#   variance from estimate, hours
#   variance from estimate, percentage
#  end of period info
#   hours billed at end of period (derived)
# 

DEFAULT_USER_ID = 'guest'
DEFAULT_CONTRACTOR_ID = 'guest'

def create_password():
	chars = string.letters + string.digits
	length = 8
	return ''.join(choice(chars) for _ in range(length))

def enhash(text, salt, hash_func):
	password_hash = hashlib.sha256(salt + text).hexdigest()
	return password_hash

def user_password_key(user_id=DEFAULT_USER_ID):
	return ndb.Key('UserPassword', user_id)

class UserPassword(ndb.Model):
	password = ndb.StringProperty(indexed=False)
	salt = ndb.StringProperty(indexed=False)
	hash_func = ndb.StringProperty(indexed=False)
	
def get_user_password_info(user_id):
	user_password_query = UserPassword.query(ancestor=user_password_key(user_id))
	user_password_infos = user_password_query.fetch(1)
	if len(user_password_infos) > 0:
		return user_password_infos[0]
	else:
		return False

def user_info_key(user_id=DEFAULT_USER_ID):
	return ndb.Key('UserList', user_id)

class UserInfo(ndb.Model):
	name = ndb.StringProperty(indexed=False)
	billing_profile = ndb.StringProperty(indexed=False)
	
def exists_user(user_id):
	user_info_query = UserInfo.query(ancestor=user_info_key(user_id))
	user_infos = user_info_query.fetch(1)
	exists = False
	if len(user_infos) > 0:
		exists = True
	return exists
	
def verify_user(user_id, password):
	verify = False
	user_password_info = get_user_password_info(user_id)
	if user_password_info != False:
		stored_password_hash = user_password_info.password
		salt = user_password_info.salt
		hash_func = user_password_info.hash_func
		password_hash = enhash(password, salt, hash_func)
		if password_hash == stored_password_hash:
			verify = True
	return verify

def get_user_info(user_id):
	user_info_query = UserInfo.query(ancestor=user_info_key(user_id))
	user_infos = user_info_query.fetch(1)
	if len(user_infos) > 0:
		return user_infos[0]
	else:
		return False

def contractor_info_key(contractor_id=DEFAULT_CONTRACTOR_ID):
	return ndb.Key('ContractorList', contractor_id)

class BillingInfo(ndb.Model):
	approver_name = ndb.StringProperty(indexed=False)
	approver_contact = ndb.StringProperty(indexed=False)
	end_client_name = ndb.StringProperty(indexed=False)
	billed_client_name = ndb.StringProperty(indexed=False)
	yast_id = ndb.StringProperty(indexed=False)
	yast_password = ndb.StringProperty(indexed=False)
	yast_parent_project_id = ndb.IntegerProperty(indexed=False)

def get_billing_info(contractor_id):
	billing_info_query = BillingInfo.query(ancestor=contractor_info_key(contractor_id))
	billing_infos = billing_info_query.fetch(1)
	if len(billing_infos) > 0:
		return billing_infos[0]
	else:
		return False

jinja_environment = jinja2.Environment(loader=jinja2.FileSystemLoader(os.path.dirname(__file__)))

def parse_start_datetime(string_date):
	if string_date != "":
		date_s = parse_date(string_date)
		start_datetime = datetime.datetime(date_s.year, date_s.month, date_s.day)
	else:
		start_datetime = datetime.datetime(2012, 4, 1)
	return start_datetime
	
def parse_end_datetime(string_date):
	if string_date != "":
		date_s = parse_date(string_date)
		end_datetime = datetime.datetime(date_s.year, date_s.month, date_s.day, 23, 59, 59)
	else:
		end_datetime = datetime.today()
	return end_datetime
	
def get_records_from_yast(yast, start_datetime, end_datetime, parent_id):
	start_time = time.mktime([start_datetime.year, start_datetime.month, start_datetime.day, start_datetime.hour, start_datetime.minute, start_datetime.second, 0, 0, -1])
	end_datetime2 = end_datetime + datetime.timedelta(1)
	end_time = time.mktime([end_datetime2.year, end_datetime2.month, end_datetime2.day, end_datetime2.hour, end_datetime2.minute, end_datetime2.second, 0, 0, -1])
	records = yast.getRecords({'timeFrom': start_time, 'timeTo': end_time, 'parentId': parent_id})
	for k, r in records.iteritems():
		start_time = r.variables['startTime']
		r.variables['startDate'] = datetime.datetime.fromtimestamp(start_time)
		r.variables['taskHours'] = str(round((r.variables['endTime'] - start_time)/3600.0, 2))
	sorted_records = sorted(records.iteritems())
	return sorted_records

def daterange(start_date, end_date):
	for n in range(int((end_date - start_date).days) + 1):
		my_datetime = start_date + datetime.timedelta(n) 
		my_date = datetime.date(my_datetime.year, my_datetime.month, my_datetime.day)
		yield my_date

def get_summary_info(records):
	summary_records = []
	for k, r in records:
		current_time = time.localtime(r.variables['startTime'])
		current_date = datetime.date(current_time.tm_year, current_time.tm_mon, current_time.tm_mday)
		summary_records.append( { 'date': current_date, 'hours': float(r.variables['taskHours']) } )
	return summary_records
	
def summarize_records(records, start_date, end_date):
	summary_records = []
	old_date = False
	total_hours = 0.0
	for r in records:
		current_datetime = r['date']
		current_date = datetime.date(current_datetime.year, current_datetime.month, current_datetime.day) 
		if current_date != old_date:
			if old_date != False:
				summary_records.append( { 'date': old_date, 'hours': total_hours } )
			old_date = current_date
			total_hours = 0.0
		total_hours += r['hours']
	if old_date != False:
		summary_records.append( { 'date': old_date, 'hours': total_hours } )
	return summary_records

def weeklyize_records(summary_records):
	day_names = [ 'monday', 'tuesday', 'wednesday', 'thursday', 'friday', 'saturday', 'sunday' ]
	weekly_summary = []
	week_summary = {
	 'sunday': '',
	 'monday': '',
	 'tuesday': '',
	 'wednesday': '',
	 'thursday': '',
	 'friday': '',
	 'saturday': '',
	 'hours': 0.0,
	 'date': '2013-01-02' }
	hours = 0.0
	week_has_data = False
	for r in summary_records:
		current_date = r['date']
		day_of_week_name = day_names[current_date.weekday()]
		week_summary[day_of_week_name] = r['hours']
		hours += r['hours']
		week_summary['hours'] = hours
		if day_of_week_name == 'sunday':
			week_summary['date'] = current_date
		else:
			days_to_sunday = datetime.timedelta(current_date.weekday() + 1)
			sunday_date = current_date - days_to_sunday
			week_summary['date'] = sunday_date
		week_has_data = True
		if day_of_week_name == 'saturday':
			weekly_summary.append(week_summary)
			week_summary = { 'sunday': '', 'monday': '', 'tuesday': '', 'wednesday': '', 'thursday': '', 'friday': '', 'saturday': '', 'hours': 0.0, 'date': '2013-01-02' }
			hours = 0.0
			week_has_data = False
	if week_has_data:
		weekly_summary.append(week_summary)
	return weekly_summary

def monthlyize_records(summary_records, start_datetime, end_datetime):
	monthly_sums = {}
	for r in summary_records:
		d = r['date']
		key_date = datetime.datetime(d.year, d.month, 1)
		hours = r['hours']
		
		if key_date in monthly_sums:
			monthly_sums[key_date] += hours
		else:
			monthly_sums[key_date] = hours

	monthly_summary = []
	for k in sorted(monthly_sums.iterkeys()):
		(start_dow, end_day) = calendar.monthrange(k.year, k.month)
		ds = max( [ datetime.datetime(k.year, k.month, 1), start_datetime ] )
		de = min( [ datetime.datetime(k.year, k.month, end_day), end_datetime ] )
		start_date = str(ds.year) + '-' + '%02d' % ds.month + '-' + '%02d' % ds.day
		end_date = '%02d' % de.month + '-' + '%02d' % de.day
		monthly_summary.append( { 'date': k, 'start_date': start_date, 'end_date': end_date, 'hours': monthly_sums[k] } )
	return monthly_summary
	
def totalize_hours(records):
	total_hours = 0.0
	for r in records:
		total_hours += r['hours']
	return total_hours

def get_projects_from_yast(yast, start_date, end_date, start_datetime, end_datetime, project_code):
	projects = yast.getProjects()
	sorted_records = get_records_from_yast(yast, start_datetime, end_datetime, project_code)
	yast_status = yast.getStatus()
	summary_records = []
	weekly_summary = []
	if yast_status == 0:
		complete_records = get_summary_info(sorted_records)
		for single_date in daterange(start_date, end_date):
			complete_records.append( { 'date': single_date, 'hours': 0 } )
		complete_sorted_records = sorted(complete_records, key=lambda k: k['date'])
		summary_records = summarize_records(complete_sorted_records, start_date, end_date)
		weekly_summary = weeklyize_records(summary_records)
		monthly_summary = monthlyize_records(summary_records, start_datetime, end_datetime)
		total_hours = totalize_hours(complete_sorted_records)
	values = { 'status': yast_status, 'projects': projects, 'records': sorted_records, 'summary': summary_records, 'weekly_summary': weekly_summary, 'monthly_summary': monthly_summary, 'total_hours': total_hours }
	return values
			
def yast_error(yast, template):
	if yast.getStatus() == YastStatus.LOGIN_FAILURE:
		error = "Wrong password or missing user"
	else:
		error = "Other error"
        		
	template_values = { 'message': error }
	return template.render(template_values)

class LoginRegisterPage(webapp2.RequestHandler):
	def get(self):
		template_values = { }
		template = jinja_environment.get_template('templates/index.html.jinja')
		self.response.out.write(template.render(template_values))

class LogoutPage(webapp2.RequestHandler):
	def get(self):
		template_values = { }
		template = jinja_environment.get_template('templates/index.html.jinja')
		self.response.set_cookie('user_id', '')
		self.response.out.write(template.render(template_values))

class LoginPage(webapp2.RequestHandler):
	def get(self):
		user_id = self.request.get('user_id')
		password = self.request.get('falabala')
		if verify_user(user_id, password):
			template_values = {
			 'user_id': user_id
			 }
			template = jinja_environment.get_template('templates/select.html.jinja')
			self.response.set_cookie('user_id', user_id)
		else:
			template_values = {
			 'message': 'Unknown user name and password'
			 }
			template = jinja_environment.get_template('templates/index.html.jinja')
			self.response.set_cookie('user_id', '')
		self.response.out.write(template.render(template_values))

class RegisterFormPage(webapp2.RequestHandler):
	def get(self):
		template_values = { }
		template = jinja_environment.get_template('templates/register-form.html.jinja')
		self.response.out.write(template.render(template_values))

class RegisterPage(webapp2.RequestHandler):
	def get(self):
		user_id = self.request.get('user_id')
		password1 = self.request.get('fala')
		password2 = self.request.get('bala')
		if len(user_id) > 0:
			if len(password1) > 0:
				if password1 == password2:
					if not exists_user(user_id):
						message = ''
					else:
						message = 'User ID "' + user_id + '" already exists'
				else:
					message = 'Passwords do not match'
			else:
				message = 'Password is required'
		else:
			message = 'User ID is required'
				
		if len(message) == 0:
			user_password_info = UserPassword(parent=user_password_key(user_id))
			salt = os.urandom(16)
			salt_token = b64encode(salt).decode('utf-8')
			hash_func = 'sha256'
			password_hash = enhash(password1, salt_token, hash_func)
			user_password_info.password = password_hash
			user_password_info.salt = salt_token
			user_password_info.hash_func = hash_func
			user_password_info.put()
			template_values = {
			 'user_id': user_id
			 }
			template = jinja_environment.get_template('templates/select.html.jinja')
			self.response.set_cookie('user_id', user_id)
		else:
			template_values = {
			 'message': message
			 }
			template = jinja_environment.get_template('templates/register-form.html.jinja')
			self.response.set_cookie('user_id', '')
		self.response.out.write(template.render(template_values))

class SelectPage(webapp2.RequestHandler):
	def get(self):
		user_id = self.request.cookies.get('user_id')
		if len(user_id) > 0:
			template_values = {
			 'user_id': user_id
			 }
			template = jinja_environment.get_template('templates/select.html.jinja')
		else:
			template_values = { }
			template = jinja_environment.get_template('templates/index.html.jinja')
		self.response.out.write(template.render(template_values))

class UserPasswordEditPage(webapp2.RequestHandler):
	def get(self):
		user_id = self.request.cookies.get('user_id')
		if len(user_id) > 0:
			template_values = {
			 'user_id': user_id
			 }
			template = jinja_environment.get_template('templates/user-password-edit.html.jinja')
		else:
			template_values = { }
			template = jinja_environment.get_template('templates/index.html.jinja')
		self.response.out.write(template.render(template_values))

class UserPasswordSavePage(webapp2.RequestHandler):
 def get(self):
		user_id = self.request.cookies.get('user_id')
		if len(user_id) > 0:
			password1 = self.request.get('password1')
			password2 = self.request.get('password2')
			if password2 == password1:
				user_password_info = get_user_password_info(user_id)
				if user_password_info == False:
					user_password_info = UserPassword(parent=user_password_key(user_id))
				salt = os.urandom(16)
				salt_token = b64encode(salt).decode('utf-8')
				hash_func = 'sha256'
				password_hash = enhash(password1, salt_token, hash_func)
				user_password_info.password = password_hash
				user_password_info.salt = salt_token
				user_password_info.hash_func = hash_func
				user_password_info.put()
				template_values = {
				 'user_id': user_id,
				 'message': 'Password changed'
				 }
				template = jinja_environment.get_template('templates/select.html.jinja')
			else:
				template_values = {
				 'user_id': user_id,
				 'message': 'Passwords do not match'
				 }
				template = jinja_environment.get_template('templates/select.html.jinja')
		else:
			template_values = { }
			template = jinja_environment.get_template('templates/index.html.jinja')
		self.response.out.write(template.render(template_values))

class UserProfileDisplayPage(webapp2.RequestHandler):
	def get(self):
		user_id = self.request.cookies.get('user_id')
		if len(user_id) > 0:
			user_info = get_user_info(user_id)
			if user_info != False:
				user_name = user_info.name
				billing_profile = user_info.billing_profile
			else:
				user_name = ''
				billing_profile = ''
			template_values = {
			 'user_id': user_id,
			 'user_name': user_name,
			 'billing_profile': billing_profile
			 }
			template = jinja_environment.get_template('templates/user-profile-display.html.jinja')
		else:
			template_values = { }
			template = jinja_environment.get_template('templates/index.html.jinja')
		self.response.out.write(template.render(template_values))
 	
class UserProfileEditPage(webapp2.RequestHandler):
	def get(self):
		user_id = self.request.cookies.get('user_id')
		if len(user_id) > 0:
			user_info = get_user_info(user_id)
			if user_info != False:
				user_name = user_info.name
				billing_profile = user_info.billing_profile
			else:
				user_name = ''
				billing_profile = ''
			template_values = {
			 'user_id': user_id,
			 'user_name': user_name,
			 'billing_profile': billing_profile
			 }
			template = jinja_environment.get_template('templates/user-profile-edit.html.jinja')
		else:
			template_values = { }
			template = jinja_environment.get_template('templates/index.html.jinja')
		self.response.out.write(template.render(template_values))

class UserProfileSavePage(webapp2.RequestHandler):
 def get(self):
		user_id = self.request.cookies.get('user_id')
		if len(user_id) > 0:
			user_name = self.request.get('user_name')
			billing_profile = self.request.get('billing_profile')
			user_info = get_user_info(user_id)
			if user_info == False:
				user_info = UserInfo(parent=user_info_key(user_id))
			user_info.name = user_name
			user_info.billing_profile = billing_profile
			user_info.put()
			template_values = {
			 'user_id': user_id,
			 'user_name': user_name,
			 'billiing_profile': billing_profile
			 }
			template = jinja_environment.get_template('templates/user-profile-display.html.jinja')
		else:
			template_values = { }
			template = jinja_environment.get_template('templates/index.html.jinja')
		self.response.out.write(template.render(template_values))

class BillingProfileDisplayPage(webapp2.RequestHandler):
	def get(self):
		user_id = self.request.cookies.get('user_id')
		if len(user_id) > 0:
			contractor_id = user_id
			billing_info = get_billing_info(contractor_id)
			if billing_info != False:
				approver_name = billing_info.approver_name
				approver_contact = billing_info.approver_contact
				end_client_name = billing_info.end_client_name
				billed_client_name = billing_info.billed_client_name
				yast_id = billing_info.yast_id
				yast_password = billing_info.yast_password
				if len(yast_password) > 0:
					yast_password = 'xxxxxxxxx'
				else:
					yast_password = ''
				yast_parent_project_id = str(billing_info.yast_parent_project_id)
			else:
				approver_name = ''
				approver_contact = ''
				end_client_name = ''
				billed_client_name = ''
				yast_id = ''
				yast_password = ''
				yast_parent_project_id = '0'
			template_values = {
			 'user_id': user_id,
			 'contractor_id': contractor_id,
			 'approver_name': approver_name,
			 'approver_contact': approver_contact,
			 'end_client_name': end_client_name,
			 'billed_client_name': billed_client_name,
			 'yast_id': yast_id,
			 'yast_password': yast_password,
			 'yast_parent_project_id': yast_parent_project_id
			 }
			template = jinja_environment.get_template('templates/billing-profile-display.html.jinja')
		else:
			template_values = { }
			template = jinja_environment.get_template('templates/index.html.jinja')
		self.response.out.write(template.render(template_values))
 	
class BillingProfileEditPage(webapp2.RequestHandler):
	def get(self):
		user_id = self.request.cookies.get('user_id')
		if len(user_id) > 0:
			contractor_id = user_id
			billing_info = get_billing_info(contractor_id)
			if billing_info != False:
				approver_name = billing_info.approver_name
				approver_contact = billing_info.approver_contact
				end_client_name = billing_info.end_client_name
				billed_client_name = billing_info.billed_client_name
				yast_id = billing_info.yast_id
				yast_password = billing_info.yast_password
				yast_parent_project_id = str(billing_info.yast_parent_project_id)
			else:
				approver_name = ''
				approver_contact = ''
				end_client_name = ''
				billed_client_name = ''
				yast_id = ''
				yast_password = ''
				yast_parent_project_id = '0'
			template_values = {
			 'user_id': user_id,
			 'contractor_id': contractor_id,
			 'approver_name': approver_name,
			 'approver_contact': approver_contact,
			 'end_client_name': end_client_name,
			 'billed_client_name': billed_client_name,
			 'yast_id': yast_id,
			 'yast_password': yast_password,
			 'yast_parent_project_id': yast_parent_project_id
			 }
			template = jinja_environment.get_template('templates/billing-profile-edit.html.jinja')
		else:
			template_values = { }
			template = jinja_environment.get_template('templates/index.html.jinja')
		self.response.out.write(template.render(template_values))

class BillingProfileSavePage(webapp2.RequestHandler):
	def get(self):
		user_id = self.request.cookies.get('user_id')
		if len(user_id) > 0:
			contractor_id = user_id
			approver_name = self.request.get('approver_name')
			approver_contact = self.request.get('approver_contact')
			end_client_name = self.request.get('end_client_name')
			billed_client_name = self.request.get('billed_client_name')
			yast_id = self.request.get('yast_id')
			yast_password = self.request.get('yast_password')
			yast_parent_project_id = self.request.get('yast_parent_project_id')

			billing_info = get_billing_info(contractor_id)
			if billing_info == False:
				billing_info = BillingInfo(parent=contractor_info_key(contractor_id))
			billing_info.approver_name = approver_name
			billing_info.approver_contact = approver_contact
			billing_info.end_client_name = end_client_name
			billing_info.billed_client_name = billed_client_name
			billing_info.yast_id = yast_id
			billing_info.yast_password = yast_password
			billing_info.yast_parent_project_id = int(yast_parent_project_id)
			billing_info.put()
			if len(yast_password) > 0:
				yast_password = 'xxxxxxxxx'
			else:
				yast_password = ''
			template_values = {
			 'user_id': user_id,
			 'contractor_id': contractor_id,
			 'approver_name': approver_name,
			 'approver_contact': approver_contact,
			 'end_client_name': end_client_name,
			 'billed_client_name': billed_client_name,
			 'yast_id': yast_id,
			 'yast_password': yast_password,
			 'yast_parent_project_id': yast_parent_project_id
			 }
			template = jinja_environment.get_template('templates/billing-profile-display.html.jinja')
		else:
			template_values = { }
			template = jinja_environment.get_template('templates/index.html.jinja')
		self.response.out.write(template.render(template_values))

class DetailForm(webapp2.RequestHandler):
	def get(self):
		user_id = self.request.cookies.get('user_id')
		if len(user_id) > 0:
			user_info = get_user_info(user_id)
			if user_info != False:
				user_name = user_info.name
				billing_profile_id = user_info.billing_profile
				if billing_profile_id == '':
					billing_profile_id = user_id
				billing_info = get_billing_info(billing_profile_id)
				if billing_info != False:
					template_values = { 
					 'user_id': user_id,
					 'start_date': datetime.date.today().isoformat(),
					 'end_date': datetime.date.today().isoformat()
					 }
					template = jinja_environment.get_template('templates/detail-form.html.jinja')
				else:
					template_values = { 
					 'message': 'No billing information found for ' + billing_profile_id
					 }
					template = jinja_environment.get_template('templates/select.html.jinja')
			else:
				template_values = { 
				 'message': 'No user information found for ' + user_id
				 }
				template = jinja_environment.get_template('templates/select.html.jinja')
		else:
			template_values = { }
			template = jinja_environment.get_template('templates/index.html.jinja')
		self.response.out.write(template.render(template_values))
	
class HoursReport(webapp2.RequestHandler):
	def __init__(self, *args, **kwargs):
		super(HoursReport, self).__init__(*args, **kwargs)
	
	def response_json(self, values):
		projects = values['projects']
		records = values['records']
		t_list = []
		for k, r in records:
			t_dict = {
			 'project': projects[r.project].name,
			 'date': str(r.variables['startDate']),
			 'hours': r.variables['taskHours'],
			 'comment': r.variables['comment']
			 }
			t_list.append(t_dict)
		return json.dumps( t_list )
	
	def get(self):
		user_id = self.request.cookies.get('user_id')
		
		if len(user_id) > 0:
			approver_name = self.request.get('approver_name')
			approver_contact = self.request.get('approver_contact')
			end_client_name = self.request.get('end_client_name')
			billed_client_name = self.request.get('billed_client_name')
			format = self.request.get('format')
			
			user_info = get_user_info(user_id)
			if user_info != False:
				user_name = user_info.name
				billing_info_id = user_info.billing_profile
				contractor_name = user_name
				if billing_info_id == '':
					billing_info_id = user_id
				else:
					contractor_user_info = get_user_info(billing_info_id)
					if contractor_user_info != False:
						contractor_id = billing_info_id
						contractor_name = contractor_user_info.name
			else:
				user_name = ''
				contractor_name = ''
				billing_info_id = ''

			billing_info = get_billing_info(billing_info_id)
			if billing_info != False:
				yast_id = billing_info.yast_id
				yast_password = billing_info.yast_password
				yast_parent_project_id = billing_info.yast_parent_project_id
			else:
				yast_id = ''
				yast_password = ''
				yast_parent_project_id = 0 

			try:
				start_datetime = datetime.datetime.strptime(self.request.get('start_date'), "%m/%d/%Y")
				end_datetime = datetime.datetime.strptime(self.request.get('end_date'), "%m/%d/%Y")
			except ValueError:
				try:
					start_datetime = datetime.datetime.strptime(self.request.get('start_date'), "%Y-%m-%d")
					end_datetime = datetime.datetime.strptime(self.request.get('end_date'), "%Y-%m-%d")
				except ValueError:
					template_values = { }
					self.response.out.write(self.date_error_template.render(template_values))
					return

			contractor_id = billing_info_id
			start_date = datetime.date(start_datetime.year, start_datetime.month, start_datetime.day)
			end_date = datetime.date(end_datetime.year, end_datetime.month, end_datetime.day)

			user_dict = {
			 'user_id': user_id,
			 'user_name': user_name,
			 'contractor_id': contractor_id,
			 'contractor_name': contractor_name,
			 'approver_name': approver_name,
			 'approver_contact': approver_contact,
			 'end_client_name': end_client_name,
			 'billed_client_name': billed_client_name,
			 'start': start_date,
			 'end': end_date,
			 'format': format
			 }

			yast = Yast()
			hash = yast.login(yast_id, yast_password)
			if hash != False:
				yast_dict = get_projects_from_yast(yast, start_date, end_date, start_datetime, end_datetime, yast_parent_project_id)
				values = dict(user_dict.items() + yast_dict.items())
				self.write_response(values)
			else:
				self.response.out.write(yast_error(yast, self.error_template))
		else:
			template_values = { }
			template = jinja_environment.get_template('templates/index.html.jinja')
			self.response.out.write(response_template.render(user_dict))

class TimesheetForm(webapp2.RequestHandler):
	def get(self):
		user_id = self.request.cookies.get('user_id')
		if len(user_id) > 0:
			user_info = get_user_info(user_id)
			if user_info != False:
				user_name = user_info.name
				billing_profile_id = user_info.billing_profile
				if billing_profile_id == '':
					billing_profile_id = user_id
				billing_info = get_billing_info(billing_profile_id)
				if billing_info != False:
					contractor_id = billing_profile_id
					approver_name = billing_info.approver_name
					approver_contact = billing_info.approver_contact
					end_client_name = billing_info.end_client_name
					billed_client_name = billing_info.billed_client_name
					template_values = {
					 'user_id': user_id,
					 'contractor_id': contractor_id,
					 'user_name': user_name,
					 'approver_name': approver_name,
					 'approver_contact': approver_contact,
					 'end_client_name': end_client_name,
					 'billed_client_name': billed_client_name,
					 'start_date': datetime.date.today().isoformat(),
					 'end_date': datetime.date.today().isoformat()
					 }
					template = jinja_environment.get_template('templates/timesheet-form.html.jinja')
				else:
					template_values = { 
					 'message': 'No billing information found for ' + billing_profile_id
					 }
					template = jinja_environment.get_template('templates/select.html.jinja')
			else:
				template_values = { 
				 'message': 'No user information found for ' + user_id
				 }
				template = jinja_environment.get_template('templates/select.html.jinja')
		else:
			template_values = { }
			template = jinja_environment.get_template('templates/index.html.jinja')
		self.response.out.write(template.render(template_values))
	
class TimesheetReport(HoursReport):
	def __init__(self, *args, **kwargs):
		super(TimesheetReport, self).__init__(*args, **kwargs)
		self.error_template = jinja_environment.get_template('templates/timesheet-error-1.html.jinja')
		self.date_error_template = jinja_environment.get_template('templates/timesheet-error.html.jinja')

	def write_response(self, values):
		start_date = values['start']
		end_date = values['end']
		format = values['format']
		threshold = datetime.timedelta(15)
		if format == 'vertical' or (format == 'auto' and end_date - start_date < threshold):
			template = jinja_environment.get_template('templates/timesheet.html.jinja')
		else:
			template = jinja_environment.get_template('templates/timesheet-month.html.jinja')
		self.response.out.write(template.render(values))
	
class HoursReportHtml(HoursReport):
	def __init__(self, *args, **kwargs):
		super(HoursReportHtml, self).__init__(*args, **kwargs)
		self.error_template = jinja_environment.get_template('templates/detail-error-1.html.jinja')
		self.date_error_template = jinja_environment.get_template('templates/detail-error.html.jinja')

	def write_response(self, values):
		template = jinja_environment.get_template('templates/detail-hours.html.jinja')
		self.response.out.write(template.render(values))

class HoursReportDownload(HoursReport):
	def __init__(self, *args, **kwargs):
		super(HoursReportDownload, self).__init__(*args, **kwargs)
		format = self.request.get('format')
		if format == 'CSV':
			self.response_template = jinja_environment.get_template('templates/detail-hours.csv.jinja')
			self.content_type = 'application/csv'
		if format == 'XML':
			self.response_template = jinja_environment.get_template('templates/detail-hours.xml.jinja')
			self.content_type = 'text/xml'
		if format == 'JSON':
			self.response_template = ''
			self.content_type = 'application/json'
		self.error_template = jinja_environment.get_template('templates/detail-error-1.html.jinja')
		self.date_error_template = jinja_environment.get_template('templates/detail-error.html.jinja')

	def write_response(self, values):
		self.response.headers['Content-Type'] = self.content_type
		if self.response_template:
			self.response.out.write(self.response_template.render(values))
		else:
			self.response.out.write(self.response_json(values))

class DisplayResetPasswordForm(webapp2.RequestHandler):
	def get(self):
		template_values = { }
		template = jinja_environment.get_template('templates/reset-password-form.html.jinja')
		self.response.out.write(template.render(template_values))

class ConfirmResetPasswordPage(webapp2.RequestHandler):
	def build_message(self, user_name, new_password):
		template_values = {
		 'user_name': user_name,
		 'new_password': new_password
		}
		template = jinja_environment.get_template('templates/password-reset.email.jinja')
		return template.render(template_values)
		
	def get(self):
		user_id = self.request.get('user_id')
		user_info = get_user_info(user_id)
		if user_info != False:
			user_name = user_info.name
			user_password_info = get_user_password_info(user_id)
			if user_password_info != False:
				new_password = create_password()
				salt = os.urandom(16)
				salt_token = b64encode(salt).decode('utf-8')
				hash_func = 'sha256'
				if user_password_info == False:
					user_password_info = UserPassword(parent=user_password_key(user_id))
				user_password_info.password = enhash(new_password, salt_token, hash_func)
				user_password_info.salt = salt_token
				user_password_info.hash_func = hash_func
				user_password_info.put()
				message_body = self.build_message(user_name, new_password)
				mail.send_mail(sender="Hours Reporter Support <jfitzpatrick.h89@gmail.com>",
					to="<" + user_id + ">",
					subject="Hours Reporter password reset",
					body=message_body)
		template_values = {
		 'message': 'Password has been reset. Check your e-mail for new password.'
		 }
		template = jinja_environment.get_template('templates/index.html.jinja')
		self.response.out.write(template.render(template_values))

class SummaryForm(webapp2.RequestHandler):
	def get(self):
		user_id = self.request.cookies.get('user_id')
		if len(user_id) > 0:
			user_info = get_user_info(user_id)
			if user_info != False:
				user_name = user_info.name
				billing_profile_id = user_info.billing_profile
				if billing_profile_id == '':
					billing_profile_id = user_id
				billing_info = get_billing_info(billing_profile_id)
				if billing_info != False:
					contractor_id = billing_profile_id
					end_client_name = billing_info.end_client_name
					billed_client_name = billing_info.billed_client_name
					template_values = {
					 'user_id': user_id,
					 'contractor_id': contractor_id,
					 'user_name': user_name,
					 'end_client_name': end_client_name,
					 'billed_client_name': billed_client_name,
					 'start_date': datetime.date.today().isoformat(),
					 'end_date': datetime.date.today().isoformat()
					 }
					template = jinja_environment.get_template('templates/summary-form.html.jinja')
				else:
					template_values = { 
					 'message': 'No billing information found for ' + billing_profile_id
					 }
					template = jinja_environment.get_template('templates/select.html.jinja')
			else:
				template_values = { 
				 'message': 'No user information found for ' + user_id
				 }
				template = jinja_environment.get_template('templates/select.html.jinja')
		else:
			template_values = { }
			template = jinja_environment.get_template('templates/index.html.jinja')
		self.response.out.write(template.render(template_values))
	
class SummaryReportHtml(HoursReport):
	def __init__(self, *args, **kwargs):
		super(SummaryReportHtml, self).__init__(*args, **kwargs)
		self.error_template = jinja_environment.get_template('templates/detail-error-1.html.jinja')
		self.date_error_template = jinja_environment.get_template('templates/detail-error.html.jinja')

	def write_response(self, values):
		response_template = jinja_environment.get_template('templates/summary-report.html.jinja')
		self.response.out.write(response_template.render(values))

class NotFoundPage(webapp2.RequestHandler):
	def get(self):
		self.error(404)
		template_values = { }
		template = jinja_environment.get_template('templates/not-found.html.jinja')
		self.response.out.write(template.render(template_values))

application = webapp2.WSGIApplication(
	[
		('/', LoginRegisterPage),
		('/billing-profile-display', BillingProfileDisplayPage),
		('/billing-profile-edit', BillingProfileEditPage),
		('/billing-profile-save', BillingProfileSavePage),
		('/detail-form', DetailForm),
		('/details-download', HoursReportDownload),
		('/details-report', HoursReportHtml),
		('/login', LoginPage),
		('/logout', LogoutPage),
		('/register', RegisterPage),
		('/register-form', RegisterFormPage),
		('/reset-password-confirm', ConfirmResetPasswordPage),
		('/reset_password_request', DisplayResetPasswordForm),
		('/select', SelectPage),
		('/summary-form', SummaryForm),
		('/summary-report', SummaryReportHtml),
		('/timesheet-form', TimesheetForm),
		('/timesheet-report', TimesheetReport),
		('/user-password-edit', UserPasswordEditPage),
		('/user-password-save', UserPasswordSavePage),
		('/user-profile-display', UserProfileDisplayPage),
		('/user-profile-edit', UserProfileEditPage),
		('/user-profile-save', UserProfileSavePage),
		('/.*', NotFoundPage)
	],
	debug=False)

def main():
	run_wsgi_app(application)

if __name__ == "__main__":
	main()
