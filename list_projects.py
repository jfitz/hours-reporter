from yastlib import *

yast_id = 'id'
yast_password = 'password'
yast = Yast()
yast_hash = yast.login(yast_id, yast_password)
if yast_hash != False:
	print 'Connected to yast.com'
	projects = yast.getProjects()
	nodes = projects.items()
	for k, n in nodes:
		print 'project ' + str(k) + ': ' + 'name: "' + n.name + '" parent: ' + str(n.parentId)
	folders = yast.getFolders()
	nodes = folders.items()
	for k, n in nodes:
		print 'folder: ' + str(k) + ': ' + 'name: "' + n.name + '" parent: ' + str(n.parentId)
else:
	print 'Could not connect to yast.com'
