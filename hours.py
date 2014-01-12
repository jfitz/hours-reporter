import time
import datetime
import re
import jinja2
import os
import json
from parse_datetime import *
from yastlib import *
from google.appengine.api import users
from google.appengine.ext import ndb
import webapp2

DEFAULT_CONTRACTOR_ID = 'jfitz@computer.org'

def contractor_info_key(contractor_id=DEFAULT_CONTRACTOR_ID):
	return ndb.Key('ContractorList', contractor_id)

class ContractorInfo(ndb.Model):
	contractor_name = ndb.StringProperty(indexed=False)
	approver_name = ndb.StringProperty(indexed=False)
	approver_contact = ndb.StringProperty(indexed=False)
	yast_id = ndb.StringProperty(indexed=False)
	yast_password = ndb.StringProperty(indexed=False)

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
	week_summary = { 'sunday': '', 'monday': '', 'tuesday': '', 'wednesday': '', 'thursday': '', 'friday': '', 'saturday': '', 'hours': 0.0, 'date': '2013-01-02' }
	hours = 0.0
	week_has_data = False
	for r in summary_records:
		current_date = r['date']
		day_of_week_name = day_names[current_date.weekday()]
		# put time in dictionary
		week_summary[day_of_week_name] = r['hours']
		hours += r['hours']
		week_summary['hours'] = hours
		# calc sunday date, put in dictionary
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
		total_hours = totalize_hours(complete_sorted_records)
	values = { 'status': yast_status, 'projects': projects, 'records': sorted_records, 'summary': summary_records, 'weekly_summary': weekly_summary, 'total_hours': total_hours }
	return values
			
def yast_error(yast, template):
	if yast.getStatus() == YastStatus.LOGIN_FAILURE:
		error = "Wrong password or missing user"
	else:
		error = "Other error"
        		
	template_values = { 'message': error }
	return template.render(template_values)

class MainPage(webapp2.RequestHandler):
	def get(self):
		template_values = { }
		template = jinja_environment.get_template('templates/index.html.jinja')
		self.response.out.write(template.render(template_values))

class SelectPage(webapp2.RequestHandler):
	def get(self):
		contractor_id = self.request.get('contractor_id')
		template_values = { }
		template = jinja_environment.get_template('templates/select.html.jinja')
		self.response.set_cookie('contractor_id', contractor_id)
		self.response.out.write(template.render(template_values))

class EditProfilePage(webapp2.RequestHandler):
	def get(self):
		contractor_id = self.request.cookies.get('contractor_id')
		contractor_info_query = ContractorInfo.query(ancestor=contractor_info_key(contractor_id))
		contractor_infos = contractor_info_query.fetch(10)
		if len(contractor_infos) > 0:
			print 'number of profiles: ' + str(len(contractor_infos))
			contractor_info = contractor_infos[0]
			contractor_name = contractor_info.contractor_name
			approver_name = contractor_info.approver_name
			approver_contact = contractor_info.approver_contact
			yast_id = contractor_info.yast_id
			yast_password = contractor_info.yast_password
		else:
			contractor_name = ''
			approver_name = ''
			approver_contact = ''
			yast_id = ''
			yast_password = ''
		user_dict = { 'contractor_id': contractor_id, 'contractor_name': contractor_name, 'approver_name': approver_name, 'approver_contact': approver_contact, 'yast_id': yast_id, 'yast_password': yast_password }
		response_template = jinja_environment.get_template('templates/edit-profile.html.jinja')
		self.response.out.write(response_template.render(user_dict))

class EditProfileDonePage(webapp2.RequestHandler):
 def get(self):
		contractor_id = self.request.cookies.get('contractor_id')
		# get the existing item from the datastore
		contractor_info_query = ContractorInfo.query(ancestor=contractor_info_key(contractor_id))
		contractor_infos = contractor_info_query.fetch(1)
		if len(contractor_infos) > 0:
			# update the existing item
			contractor_info = contractor_infos[0]
			contractor_name = self.request.get('contractor_name')
			approver_name = self.request.get('approver_name')
			approver_contact = self.request.get('approver_contact')
			yast_id = self.request.get('yast_id')
			yast_password = self.request.get('yast_password')
		else:
			# create an item
			contractor_name = self.request.get('contractor_name')
			approver_name = self.request.get('approver_name')
			approver_contact = self.request.get('approver_contact')
			yast_id = self.request.get('yast_id')
			yast_password = self.request.get('yast_password')
			contractor_info = ContractorInfo(parent=contractor_info_key(contractor_id))
		contractor_info.contractor_name = contractor_name
		contractor_info.approver_name = approver_name
		contractor_info.approver_contact = approver_contact
		contractor_info.yast_id = yast_id
		contractor_info.yast_password = yast_password
		contractor_info.put()
		user_dict = { 'contractor_id': contractor_id, 'contractor_name': contractor_name, 'approver_name': approver_name, 'approver_contact': approver_contact, 'yast_id': yast_id, 'yast_password': yast_password }
		response_template = jinja_environment.get_template('templates/edit-profile-done.html.jinja')
		self.response.out.write(response_template.render(user_dict))

class DetailForm(webapp2.RequestHandler):
	def get(self):
		user_dict = { }
		response_template = jinja_environment.get_template('templates/detail-form.html.jinja')
		self.response.out.write(response_template.render(user_dict))
	
class HoursReport(webapp2.RequestHandler):
	def __init__(self, *args, **kwargs):
		super(HoursReport, self).__init__(*args, **kwargs)
	
	def response_json(self, values):
		projects = values['projects']
		records = values['records']
		t_list = []
		for k, r in records:
			t_dict = { 'project': projects[r.project].name, 'date': r.variables['startDate'], 'hours': r.variables['taskHours'], 'comment': r.variables['comment'] }
			t_list.append(t_dict)
		return json.dumps( t_list )
	
	def get(self):
		contractor_name = self.request.get('contractor_name')
		approver_name = self.request.get('approver_name')
		approver_contact = self.request.get('approver_contact')

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

		start_date = datetime.date(start_datetime.year, start_datetime.month, start_datetime.day)
		end_date = datetime.date(end_datetime.year, end_datetime.month, end_datetime.day)

		contractor_id = self.request.cookies.get('contractor_id')
		contractor_info_query = ContractorInfo.query(ancestor=contractor_info_key(contractor_id))
		contractor_infos = contractor_info_query.fetch(1)
		if len(contractor_infos) > 0:
			contractor_info = contractor_infos[0]
			yast_id = contractor_info.yast_id
			yast_password = contractor_info.yast_password
		else:
			yast_id = ''
			yast_password = ''

		user_dict = { 'contractor_id': contractor_id, 'contractor_name': contractor_name, 'approver_name': approver_name, 'approver_contact': approver_contact, 'start': start_date, 'end': end_date }

		# connect to yast.com and retrieve data
		yast = Yast()
		hash = yast.login(yast_id, yast_password)
		if hash != False:
			yast_dict = get_projects_from_yast(yast, start_date, end_date, start_datetime, end_datetime, 2015302)
			values = dict(user_dict.items() + yast_dict.items())
			self.write_response(values)
		else:
			self.response.out.write(yast_error(yast, self.error_template))

class TimesheetForm(webapp2.RequestHandler):
	def get(self):
		contractor_id = self.request.cookies.get('contractor_id')
		contractor_info_query = ContractorInfo.query(ancestor=contractor_info_key(contractor_id))
		contractor_infos = contractor_info_query.fetch(1)
		if len(contractor_infos) > 0:
			contractor_info = contractor_infos[0]
			contractor_name = contractor_info.contractor_name
			approver_name = contractor_info.approver_name
			approver_contact = contractor_info.approver_contact
		else:
			contractor_name = ''
			approver_name = ''
			approver_contact = ''
		template_values = { 'contractor_id': contractor_id, 'contractor_name': contractor_name, 'approver_name': approver_name, 'approver_contact': approver_contact }
		template = jinja_environment.get_template('templates/timesheet-form.html.jinja')
		self.response.out.write(template.render(template_values))
	
class TimesheetReport(HoursReport):
	def __init__(self, *args, **kwargs):
		super(TimesheetReport, self).__init__(*args, **kwargs)
		self.error_template = jinja_environment.get_template('templates/timesheet-error-1.html.jinja')
		self.date_error_template = jinja_environment.get_template('templates/timesheet-error.html.jinja')

	def write_response(self, values):
		start_date = values['start']
		end_date = values['end']
		threshold = datetime.timedelta(15)
		if end_date - start_date < threshold:
			response_template = jinja_environment.get_template('templates/timesheet.html.jinja')
		else:
			response_template = jinja_environment.get_template('templates/timesheet-month.html.jinja')
		self.response.out.write(response_template.render(values))
	
class HoursReportHtml(HoursReport):
	def __init__(self, *args, **kwargs):
		super(HoursReportHtml, self).__init__(*args, **kwargs)
		self.error_template = jinja_environment.get_template('templates/detail-error-1.html.jinja')
		self.date_error_template = jinja_environment.get_template('templates/detail-error.html.jinja')

	def write_response(self, values):
		response_template = jinja_environment.get_template('templates/detail-hours.html.jinja')
		self.response.out.write(response_template.render(values))

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

application = webapp2.WSGIApplication(
	[
		('/', MainPage),
		('/select', SelectPage),
		('/edit-profile', EditProfilePage),
		('/edit-profile-done', EditProfileDonePage),
		('/detail-form', DetailForm),
		('/details-report', HoursReportHtml),
		('/details-download', HoursReportDownload),
		('/timesheet-form', TimesheetForm),
		('/timesheet-report', TimesheetReport)
	],
	debug=False)

def main():
	run_wsgi_app(application)

if __name__ == "__main__":
	main()
