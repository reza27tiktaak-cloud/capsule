import sys
import os

# مسیر پروژه
path = '/home/rezamahdavi'
if path not in sys.path:
    sys.path.insert(0, path)

# اجرای برنامه Flask
from app import app as application