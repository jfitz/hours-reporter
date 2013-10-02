from google.appengine.api import users
from google.appengine.ext import webapp
from google.appengine.ext.webapp.util import run_wsgi_app
import time, re, datetime
from yastlib import *
from parse_datetime import *
import jinja2
import os
import json

jinja_environment = jinja2.Environment(loader=jinja2.FileSystemLoader(os.path.dirname(__file__)))

def parse_start_date(string_date):
	if string_date != "":
		date_s = parse_date(string_date)
		date_s2 = time.mktime([date_s.year, date_s.month, date_s.day, 0, 0, 0, 0, 1, -1])
	else:
		date_s2 = time.mktime([2012, 4, 1, 0, 0, 0, 0, 1, -1])
	return date_s2
	
def parse_end_date(string_date):
	if string_date != "":
		date_s = parse_date(string_date)
		date_s2 = time.mktime([date_s.year, date_s.month, date_s.day, 23, 59, 59, 0, 1, -1])
	else:
		date_s2 = time.mktime(time.localtime())
	return date_s2
	
def get_records_from_yast(yast, time_start, time_end, parent_id):
	records = yast.getRecords({'timeFrom': time_start, 'timeTo': time_end, 'parentId': parent_id})
	for k, r in records.iteritems():
		time_start = r.variables['startTime']
		r.variables['startDate'] = time.strftime('%Y-%m-%d', time.localtime(time_start))
		r.variables['taskHours'] = str(round((r.variables['endTime'] - r.variables['startTime'])/3600.0, 2))
	sorted_records = sorted(records.iteritems())
	return sorted_records

def summarize_records(records):
	summary_records = []
	old_date = False
	total_hours = 0.0
	for k, r in records:
		if r.variables['startDate'] != old_date:
			if old_date != False:
				summary_records.append( { 'date': old_date, 'hours': total_hours } )
			old_date = r.variables['startDate']
			total_hours = 0.0
		total_hours += float(r.variables['taskHours'])
	if old_date != False:
		summary_records.append( { 'date': old_date, 'hours': str(total_hours) } )
	return summary_records
	
def get_projects_from_yast(yast, time_start, time_end, project_code):
	projects = yast.getProjects()
	sorted_records = get_records_from_yast(yast, time_start, time_end, project_code)
	yast_status = yast.getStatus()
	summary_records = summarize_records(sorted_records)
	values = { 'status': yast_status, 'projects': projects, 'records': sorted_records, 'summary': summary_records }
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

class HoursReport(webapp.RequestHandler):
	def __init__(self, *args, **kwargs):
		super(HoursReport, self).__init__(*args, **kwargs)
	
	def get_yast_data(self, date_s2, date_e2, user_dict):
		user = user_dict['user']
		falabala = user_dict['fala'] + str(len(user_dict['fala'])) + user_dict['bala']
		yast = Yast()
		hash = yast.login(user, falabala)
		if hash != False:
			yast_dict = get_projects_from_yast(yast, date_s2, date_e2, 2015302)
			values = dict(user_dict.items() + yast_dict.items())
			self.write_detail_response(values)
		else:
			self.response.out.write(yast_error(yast, self.error_template))

	def get(self):
		date_start = self.request.get('start_date')
		date_end = self.request.get('end_date')
		user = self.request.get('contractor_id')
		fala = self.request.get('fala')
		bala = self.request.get('bala')

		try:
			date_s2 = parse_start_date(self.request.get('start_date'))
			date_e2 = parse_end_date(self.request.get('end_date'))
		except ValueError:
			template_values = { }
			self.response.out.write(self.date_error_template.render(template_values))
			return

		user_dict = { 'user': user, 'fala': fala, 'bala': bala, 'start': date_start, 'end': date_end }
		# connect to yast.com and retrieve data
		self.get_yast_data(date_s2, date_e2, user_dict)

class Timesheet(HoursReport):
	def __init__(self, *args, **kwargs):
		super(Timesheet, self).__init__(*args, **kwargs)
	
	def write_detail_response(self, values):	
		self.response_template = jinja_environment.get_template('templates/timesheet.html.jinja')
		self.content_type = ''
		self.error_template = jinja_environment.get_template('templates/timesheet-error-1.html.jinja')
		self.date_error_template = jinja_environment.get_template('templates/timesheet-error.html.jinja')
		if len(self.content_type) > 0:
			self.response.headers['Content-Type'] = self.content_type
		if self.response_template:
			self.response.out.write(self.response_template.render(values))
		else:
			projects = values['projects']
			records = values['records']
			t_list = []
			for k, r in records:
				t_dict = { 'project': projects[r.project].name, 'date': r.variables['startDate'], 'hours': r.variables['taskHours'], 'comment': r.variables['comment'] }
				t_list.append(t_dict)
			s = json.dumps( t_list )
			self.response.out.write(s)
	
	
class HoursDetail(HoursReport):
	def __init__(self, *args, **kwargs):
		super(HoursDetail, self).__init__(*args, **kwargs)
	
	def write_detail_response(self, values):	
		if len(self.content_type) > 0:
			self.response.headers['Content-Type'] = self.content_type
		if self.response_template:
			self.response.out.write(self.response_template.render(values))
		else:
			projects = values['projects']
			records = values['records']
			t_list = []
			for k, r in records:
				t_dict = { 'project': projects[r.project].name, 'date': r.variables['startDate'], 'hours': r.variables['taskHours'], 'comment': r.variables['comment'] }
				t_list.append(t_dict)
			s = json.dumps( t_list )
			self.response.out.write(s)
	
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
		('/hours-detail', HoursDetailHtml),
		('/hours-detail-download', HoursDetailDownload),
		('/timesheet', Timesheet)
	],
	debug=False)

def main():
	run_wsgi_app(application)

if __name__ == "__main__":
	main()
