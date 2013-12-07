from google.appengine.api import users
from google.appengine.ext import webapp
from google.appengine.ext.webapp.util import run_wsgi_app
import time, re
import datetime
from yastlib import *
from parse_datetime import *
import jinja2
import os
import json

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
	if yast_status == 0:
		complete_records = get_summary_info(sorted_records)
		for single_date in daterange(start_date, end_date):
			complete_records.append( { 'date': single_date, 'hours': 0 } )
		complete_sorted_records = sorted(complete_records, key=lambda k: k['date'])
		summary_records = summarize_records(complete_sorted_records, start_date, end_date)
		total_hours = totalize_hours(complete_sorted_records)
	values = { 'status': yast_status, 'projects': projects, 'records': sorted_records, 'summary': summary_records, 'total_hours': total_hours }
	return values
			
def yast_error(yast, template):
	if yast.getStatus() == YastStatus.LOGIN_FAILURE:
		error = "Wrong password or missing user"
	else:
		error = "Other error"
        		
	template_values = { 'message': error }
	return template.render(template_values)

class MainPage(webapp.RequestHandler):
	def get(self):
		template_values = { }
		template = jinja_environment.get_template('templates/index.html.jinja')
		self.response.out.write(template.render(template_values))

class SelectReport(webapp.RequestHandler):
	def get(self):
		contractor_id = self.request.get('contractor_id')
		fala = self.request.get('fala')
		bala = self.request.get('bala')
		template_values = { 'contractor_id': contractor_id, 'fala': fala, 'bala': bala }
		template = jinja_environment.get_template('templates/select.html.jinja')
		self.response.out.write(template.render(template_values))

class HoursReport(webapp.RequestHandler):
	def __init__(self, *args, **kwargs):
		super(HoursReport, self).__init__(*args, **kwargs)
	
	def get_yast_data(self, start_date, end_date, start_datetime, end_datetime, user_dict):
		contractor_id = user_dict['contractor_id']
		falabala = user_dict['fala'] + str(len(user_dict['fala'])) + user_dict['bala']
		yast = Yast()
		hash = yast.login(contractor_id, falabala)
		if hash != False:
			yast_dict = get_projects_from_yast(yast, start_date, end_date, start_datetime, end_datetime, 2015302)
			values = dict(user_dict.items() + yast_dict.items())
			self.write_detail_response(values)
		else:
			self.response.out.write(yast_error(yast, self.error_template))

	def write_detail_response(self, values):	
		if len(self.content_type) > 0:
			self.response.headers['Content-Type'] = self.content_type
		if self.response_template:
			self.response.out.write(self.response_template.render(values))
		else:
			self.response.out.write(self.response_json(values))
	
	def get(self):
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
		contractor_id = self.request.get('contractor_id')
		fala = self.request.get('fala')
		bala = self.request.get('bala')
		contractor_name = self.request.get('contractor_name')
		approver_name = self.request.get('approver_name')
		approver_contact = self.request.get('approver_contact') 

		user_dict = { 'contractor_id': contractor_id, 'contractor_name': contractor_name, 'approver_name': approver_name, 'approver_contact': approver_contact, 'fala': fala, 'bala': bala, 'start': start_date, 'end': end_date }
		# connect to yast.com and retrieve data
		self.get_yast_data(start_date, end_date, start_datetime, end_datetime, user_dict)

class Timesheet(HoursReport):
	def __init__(self, *args, **kwargs):
		super(Timesheet, self).__init__(*args, **kwargs)
		self.response_template = jinja_environment.get_template('templates/timesheet.html.jinja')
		self.content_type = ''
		self.error_template = jinja_environment.get_template('templates/timesheet-error-1.html.jinja')
		self.date_error_template = jinja_environment.get_template('templates/timesheet-error.html.jinja')
	
	def response_json(self, values):
		projects = values['projects']
		records = values['records']
		t_list = []
		for k, r in records:
			t_dict = { 'project': projects[r.project].name, 'date': r.variables['startDate'], 'hours': r.variables['taskHours'], 'comment': r.variables['comment'] }
			t_list.append(t_dict)
		return json.dumps( t_list )
		
class HoursDetail(HoursReport):
	def __init__(self, *args, **kwargs):
		super(HoursDetail, self).__init__(*args, **kwargs)
	
	def response_json(self, values):
		projects = values['projects']
		records = values['records']
		t_list = []
		for k, r in records:
			t_dict = { 'project': projects[r.project].name, 'date': r.variables['startDate'], 'hours': r.variables['taskHours'], 'comment': r.variables['comment'] }
			t_list.append(t_dict)
		return json.dumps( t_list )
	
class HoursDetailHtml(HoursDetail):
	def __init__(self, *args, **kwargs):
		super(HoursDetailHtml, self).__init__(*args, **kwargs)
		self.response_template = jinja_environment.get_template('templates/detail-hours.html.jinja')
		self.content_type = ''
		self.error_template = jinja_environment.get_template('templates/detail-error-1.html.jinja')
		self.date_error_template = jinja_environment.get_template('templates/detail-error.html.jinja')

class HoursDetailDownload(HoursDetail):
	def __init__(self, *args, **kwargs):
		super(HoursDetailDownload, self).__init__(*args, **kwargs)
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

application = webapp.WSGIApplication(
	[
		('/', MainPage),
		('/select', SelectReport),
		('/hours-detail', HoursDetailHtml),
		('/hours-detail-download', HoursDetailDownload),
		('/timesheet', Timesheet)
	],
	debug=False)

def main():
	run_wsgi_app(application)

if __name__ == "__main__":
	main()
