"""
Windows Service Wrapper for Knowledge-Base Application
This module allows running the knowledge-base application as a Windows service.
"""

import os
import sys
import time
import subprocess
from pathlib import Path

try:
    import servicemanager
    import win32serviceutil
    import win32service
    import win32event
    import winerror
    from win32api import GetLastError
except ImportError:
    print("Error: pywin32 is not installed")
    print("Please install it with: pip install pywin32")
    sys.exit(1)


class KnowledgeBaseService(win32serviceutil.ServiceFramework):
    """Windows service for Knowledge-Base application"""
    
    _svc_name_ = "KnowledgeBase"
    _svc_display_name_ = "Knowledge-Base Service"
    _svc_description_ = "Local-first knowledge base service with vector search and conversational QA"
    
    def __init__(self, args):
        win32serviceutil.ServiceFramework.__init__(self, args)
        self.hWaitStop = win32event.CreateEvent(None, 0, 0, None)
        self.is_alive = True
        self.process = None
        
    def SvcStop(self):
        """Handle service stop event"""
        self.ReportServiceStatus(win32service.SERVICE_STOP_PENDING)
        win32event.SetEvent(self.hWaitStop)
        self.is_alive = False
        
        # Terminate the process
        if self.process:
            try:
                self.process.terminate()
                self.process.wait(timeout=10)
            except Exception as e:
                servicemanager.LogErrorMsg(f"Error stopping process: {str(e)}")
                if self.process:
                    self.process.kill()
    
    def SvcDoRun(self):
        """Main service run method"""
        servicemanager.LogMsg(
            servicemanager.EVENTLOG_INFORMATION_TYPE,
            servicemanager.PYS_SERVICE_STARTED,
            (self._svc_name_, "")
        )
        
        try:
            self.main()
        except Exception as e:
            servicemanager.LogErrorMsg(f"Service error: {str(e)}")
            self.SvcStop()
    
    def main(self):
        """Main application logic"""
        # Get the project root directory
        service_dir = Path(__file__).parent.absolute()
        project_root = service_dir
        
        # Check for virtual environment
        venv_activate = project_root / ".venv" / "Scripts" / "activate.bat"
        
        if not venv_activate.exists():
            servicemanager.LogErrorMsg(
                f"Virtual environment not found at {venv_activate}"
            )
            return
        
        # Prepare the command
        if sys.platform == "win32":
            # Use activate.bat for Windows
            cmd = f'cmd /c "{venv_activate}" && python -m src.main'
        else:
            cmd = f'source "{venv_activate.parent.parent}/activate" && python -m src.main'
        
        try:
            # Start the application process
            self.process = subprocess.Popen(
                cmd,
                cwd=str(project_root),
                shell=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True
            )
            
            servicemanager.LogMsg(
                servicemanager.EVENTLOG_INFORMATION_TYPE,
                servicemanager.PYS_SERVICE_STARTED,
                (f"Knowledge-Base process started (PID: {self.process.pid})", "")
            )
            
            # Wait for service stop event
            while self.is_alive:
                rc = win32event.WaitForSingleObject(self.hWaitStop, 5000)
                
                if rc == winerror.WAIT_OBJECT_0:
                    servicemanager.LogMsg(
                        servicemanager.EVENTLOG_INFORMATION_TYPE,
                        servicemanager.PYS_SERVICE_STOPPED,
                        (self._svc_name_, "")
                    )
                    break
                
                # Check if process is still alive
                if self.process and self.process.poll() is not None:
                    # Process has terminated
                    servicemanager.LogErrorMsg("Application process terminated unexpectedly")
                    break
        
        except Exception as e:
            servicemanager.LogErrorMsg(f"Failed to start service: {str(e)}")


def handle_commandline(argv):
    """Handle command line arguments"""
    win32serviceutil.HandleCommandLine(KnowledgeBaseService, argv)


if __name__ == '__main__':
    handle_commandline(sys.argv)
