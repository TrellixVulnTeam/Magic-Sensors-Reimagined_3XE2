"""
	File: redeploy_backend.py
	
	Function: This file acts as a means to automatically update the backend server
	to the lastest version on git, while also relaunching the application. This 
	function is invoked by server_daemon.py. This function is also responsible for
	invoking generate_pydocs.py after the code is updated.
"""

import os
import psutil
import time
import logger

__author__ = "Ryan Lanciloti"
__credits__ = ["Ryan Lanciloti"]
__version__ = "1.5.0"
__maintainer__ = "Ryan Lanciloti"
__email__ = ["ryanjl9@iastate.edu", "rlanciloti@outlook.com"]
__status__ = "Development"

def check_main_pid() -> None:
	""" This function will find attempt to take the current server process and
	kill it. It will then pull the most up-to-date version of code from git if
	it's there, and then it will launch the server.
	"""
	pidfile = "/tmp/server_daemon.pid"
	file_path = "/home/sd2021/gitRepo/Magic-Sensors-Reimagined/Backend Server"
	file_name = "main.py"
	if os.path.isfile(pidfile):
		with open(pidfile, "r") as f:
			pid = int(f.readline())
			if psutil.pid_exists(pid):
				p = psutil.Process(pid)
				logger.info(f"Killing server proc {pid}")
				p.kill()
	os.chdir(file_path)
	logger.info("Pulling newest version of code from git")
	os.system("git pull origin master")
	logger.info("Relaunching Backend Server")
	os.system(f"python3 {file_name} &")
	os.system("python3 generate_pydocs.py")


if __name__ == "__main__":
    check_main_pid()
