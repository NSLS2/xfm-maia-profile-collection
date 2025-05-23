from ophyd import EpicsSignal
from bluesky.suspenders import SuspendFloor
import sys
import nslsii
import builtins

nslsii.configure_base(
  get_ipython().user_ns, 
  'xfm',
  publish_documents_with_kafka=True

  )
import redis
from redis_json_dict import RedisJSONDict

uri = "info.xfm.nsls2.bnl.gov"
# Provide an endstation prefix, if needed, with a trailing "-"
new_md = RedisJSONDict(redis.Redis(uri), prefix="maia")
#BEAMLINE_ID = 'xfm'

nslsii.configure_olog(get_ipython().user_ns)

#Optional: set any metadata that rarely changes.
#RE.md['beamline_id'] = 'XFM'
RE.md = new_md

#beam_current = EpicsSignal('XF:04BM-ES:2{Sclr:1}scaler1.s4')
beam_current = EpicsSignal('SR:OPS-BI{DCCT:1}I:Real-I')

#sus = SuspendFloor(beam_current,395,resume_thresh=400)
#RE.install_suspender(sus)
get_ipython().run_line_magic("matplotlib", "qt")


def flush_print(*args, **kwargs):
    kwargs.setdefault('flush', True)
    builtins.print(*args, **kwargs)

print = flush_print
#print = xfm_print
