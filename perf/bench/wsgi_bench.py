import sys, os
sys.path.insert(0, os.path.dirname(__file__))
import fake_env; fake_env.install()
import os as _o; R=_o.environ.get('APP_ROOT', _o.path.abspath(_o.path.join(_o.path.dirname(__file__), '..', '..'))); os.chdir(R); sys.path.insert(0, R)
from app import server  # noqa
