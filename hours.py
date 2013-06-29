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

def get_projects_from_yast(yast, time_start, time_end, user_dict):
	projects = yast.getProjects()
	sorted_records = get_records_from_yast(yast, time_start, time_end, 2015302)
	yast_status = yast.getStatus()
		
	more_dict = { 'status': yast_status, 'projects': projects, 'records': sorted_records }
	template_values = dict(user_dict.items() + more_dict.items())
	return template_values
			
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
			template_values = get_projects_from_yast(yast, date_s2, date_e2, user_dict)

			# generate response
			if len(self.content_type) > 0:
				self.response.headers['Content-Type'] = self.content_type
			if self.response_template:
				self.response.out.write(self.response_template.render(template_values))
			else:
				projects = template_values['projects']
				records = template_values['records']
				t_list = []
				for k, r in records:
					t_dict = { 'project': projects[r.project].name, 'date': r.variables['startDate'], 'hours': r.variables['taskHours'], 'comment': r.variables['comment'] }
					t_list.append(t_dict)

				s = json.dumps( t_list )
				self.response.out.write(s)

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

		# connect to yast.com and retrieve data
		user_dict = { 'user': user, 'fala': fala, 'bala': bala, 'start': date_start, 'end': date_end }
		self.get_yast_data(date_s2, date_e2, user_dict)

class HoursReportHtml(HoursReport):
	def __init__(self, *args, **kwargs):
		super(HoursReportHtml, self).__init__(*args, **kwargs)
		self.response_template = jinja_environment.get_template('templates/report-hours.html.jinja')
		self.content_type = ''
		self.error_template = jinja_environment.get_template('templates/report-error-1.html.jinja')
		self.date_error_template = jinja_environment.get_template('templates/report-error.html.jinja')

class HoursReportDownload(HoursReport):
	def __init__(self, *args, **kwargs):
		super(HoursReportDownload, self).__init__(*args, **kwargs)
		format = self.request.get('format')
		if format == 'CSV':
			self.response_template = jinja_environment.get_template('templates/report-hours.csv.jinja')
			self.content_type = 'application/csv'
		if format == 'XML':
			self.response_template = jinja_environment.get_template('templates/report-hours.xml.jinja')
			self.content_type = 'text/xml'
		if format == 'JSON':
			self.response_template = ''
			self.content_type = 'application/json'
		self.error_template = jinja_environment.get_template('templates/report-error-1.html.jinja')
		self.date_error_template = jinja_environment.get_template('templates/report-error.html.jinja')

application = webapp.WSGIApplication(
	[
		('/', MainPage),
		('/hours-report', HoursReportHtml),
		('/hours-report-download', HoursReportDownload)
	],
	debug=False)

def main():
	run_wsgi_app(application)

if __name__ == "__main__":
	main()
