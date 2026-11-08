"""Mide el tiempo de import de app.py (= arranque del worker con --preload) por fases."""
import sys, time, os
T0 = time.perf_counter()
sys.path.insert(0, os.path.dirname(__file__))
import fake_env
fake_env.install()
T1 = time.perf_counter()
ROOT = os.environ.get('APP_ROOT', os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))
os.chdir(ROOT)
sys.path.insert(0, ROOT)

import cProfile, pstats, io
pr = cProfile.Profile() if os.getenv('PROF') else None
if pr: pr.enable()
t = time.perf_counter()
import app  # noqa
t_app = time.perf_counter() - t
if pr:
    pr.disable()
    s = io.StringIO()
    pstats.Stats(pr, stream=s).sort_stats('cumulative').print_stats(35)
    print(s.getvalue())
print(f'fake data build: {T1-T0:.2f}s')
print(f'import app (startup): {t_app:.2f}s')
print(f'index_string: {len(app.app.index_string)/1024:.0f} KB')
print(f'geojson features: {len(app.geojson_data["features"])}, raw {len(fake_env.GEOJSON_BYTES)/1024:.0f} KB')
