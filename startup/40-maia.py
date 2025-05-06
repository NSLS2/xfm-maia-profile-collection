#from ophyd.log import config_ophyd_logging
#config_ophyd_logging(level='DEBUG')
from nslsii.detectors.maia import MAIA


maia = MAIA('XFM:MAIA', name='maia')

import numpy as np

import bluesky.plans as bp
import bluesky.plan_stubs as bps
import bluesky.preprocessors as bpp
import socket
import time

#HOST = '192.168.2.196'    # The remote host
#PORT = 9001              # The same port as used by the server
#s_maia=socket.socket(socket.AF_INET, socket.SOCK_STREAM)
#s_maia.connect((HOST, PORT))
#def maia_set(var, val):
#    putstr = "x set "+var+" "+str(val)+"\n"
#    s_maia.sendall(putstr.encode())
#    time.sleep(0.01)
#    r = s_maia.recv(1024)
    #print(r)
#    r1=r.decode()
#    r2=r1.rsplit(" ")
#    if (r2[1] == "error"):
#      print("Return string : ", r)

#def maia_get(var):
#    putstr = "x get "+var+"\n"
#    s_maia.sendall(putstr.encode())
#    time.sleep(0.01)
#    r = s_maia.recv(1024)
#    r1=r.decode()
#    r2=r1.rsplit(" ")
#    if (r2[1] == "error"):
#      print("Return string : ", r)     
#    val = r2[2]
    #print(val)
#    return(val)

def xscan(start, stop, step, dwell):
    mres=0.0002
    nxpitch=int(step/mres)
    if(nxpitch<3): # Force minimum pitch to 3 motor steps
        nxpitch=3
    step=nxpitch*mres
    print("Warning: I am forcing step to be an integer multiple of motor resolution: ", step);
    speed=step/dwell
    print("Speed=",speed)
    if start > stop:
        stop, start = start, stop
    xnum = int((stop - start)/step)
    if(start+xnum*step < stop):
      xnum+=1
    print("xnum=",xnum)
    xsize = xnum*step
    stop=start+xsize
    print("Warning: I am forcing xsize to be an integer multiple of step: ", xsize);
    #fout=open('/home/xf04bm/xpos.dat','w')
    # set the motors to the right speed
    yield from bps.mv(M.x.velocity, speed)
    print("set speed")
    print("Start=",start,"  Stop=",stop,"Step=",step,"   Speed=",speed)
    input("Press any key if it's OK to continue")
    # Move to beginning of scan
    yield from bps.mv(M.x, start)
    for i in range(0,xnum):
        pos=start+i*step
        yield from bps.mv(M.x, pos)
        yield from bps.sleep(0.2)
    #    a_x=str(maia_get("encoder.axis[0].position\n"))
    #    fout.write(str(i)+"  "+str(M.x.position)+"   "+a_x[0:len(a_x)-1]+"\n")
    #fout.close()
    yield from bps.mv(M.x, start)

def yscan(start, stop, step, dwell):
    mres=0.0002
    nxpitch=int(step/mres)
    if(nxpitch<3): # Force minimum pitch to 3 motor steps
        nxpitch=3
    step=nxpitch*mres
    print("Warning: I am forcing step to be an integer multiple of motor resolution: ", step);
    speed=abs(step/dwell)
    print("Speed=",speed)
    sign=1
    if start > stop:
        sign=-1
    #    stop, start = start, stop
    xnum = int((stop - start)/(sign*step))
    if(start+xnum*step < stop):
      xnum+=1
    print("xnum=",xnum)
    xsize = xnum*step
    stop=start+sign*xsize
    print("Warning: I am forcing size to be an integer multiple of step: ", xsize);
    #fout=open('/home/xf04bm/ypos.dat','w')
    # set the motors to the right speed
    yield from bps.mv(M.y.velocity, speed)
    print("set speed")
    print("Start=",start,"  Stop=",stop,"Step=",step,"   Speed=",speed)
    input("Press any key if it's OK to continue")
    # Move to beginning of scan
    yield from bps.mv(M.y, start)
    for i in range(0,xnum):
        pos=start+i*sign*step
        yield from bps.mv(M.y, pos)
        yield from bps.sleep(0.2)
    #    a_x=str(maia_get("encoder.axis[1].position\n"))
    #    fout.write(str(i)+"  "+str(M.y.position)+"   "+a_x[0:len(a_x)-1]+"\n")
    #fout.close()
    yield from bps.mv(M.y, start)

sample_md = {"sample": {"name": "Ni mesh", "owner": "stolen"}}


def fly_maia(
    ystart,
    ystop,
    ypitch,
    xstart,
    xstop,
    xpitch,
    dwell,
    *,
    group=None,
    md=None,
    shutter = shutter,
    hf_stage,
    maia,
    print_params=False
):
    """Run a flyscan with the maia


    Parametersprint("open run")
    ----------
    ystart, ystop, ypitch : float
        The start position, end position and pixel pitch of the scan along the slow direction in absolute mm.

    xstart, xwidth, xpitch : float
        The limits of the scan along the fast direction in absolute mm.

    dwell : float
        The dwelll time in s.  This is used to set the motor velocity.

    group : str, optional
        The file group.  This goes into the file path that maia writes to.

    md : dict, optional
        Metadata to put into the start document.
print("open run")
        If there is a 'sample' key, then it must be a dictionary and the
        keys

           ['info', 'name', 'owner', 'serial', 'type']

        are passed through to the maia metadata.

        If there is a 'scan' key, then it must be a dictionary and the
        keys

             ['region', 'info', 'seq_num', 'seq_total']

        are passed through to maia metadata.
    """
    if print_params:
        print(f"ystart={ystart}, ystop={ystop}, ypitch={ypitch}, xstart={xstart}, xstop={xstop}, xpitch={xpitch}, dwell={dwell}")
    x_mres=0.0002
    y_mres=0.0002
    nxpitch=int(xpitch/x_mres)
    if(nxpitch<2): # Force minimum pitch to 2 motor steps
        nxpitch=2
    nypitch=int(ypitch/y_mres)
    if(nypitch<2): # Force minimum pitch to 2 motor steps
        nypitch=2
    xpitch=nxpitch*x_mres
    print("Warning: I am forcing xpitch to be an integer multiple of motor resolution: ", xpitch);
    ypitch=nypitch*y_mres
    print("Warning: I am forcing ypitch to be an integer multiple of motor resolution: ", ypitch);
    if xstart > xstop:
        xstop, xstart = xstart, xstop

    if ystart > ystop:
        ystop, ystart = ystart, ystop
    
    xnum = int((xstop -xstart)/xpitch)    # Should force to integer and enforce size = N * pitch
    ynum = int((ystop-ystart)/ypitch)

    print("xnum=",xnum)
    print("ynum=",ynum)

    if(xstart+xnum*xpitch < xstop):
      xnum+=1

    xsize = xnum*xpitch
    xstop=xstart+xsize
    ysize=ystart*xpitch
    ystop=ystart+ysize

    print("Warning: I am forcing xsize to be an integer multiple of xpitch: ", xsize);

    #if(ystart+ynum*ypitch < ystop):       #        yield from bps.sleep(0.5)
        #        a_x=str(maia_get("encoder.axis[0].position\n"))
        #       a_y=str(maia_get("encoder.axis[1].position\n"))
        #        fout.write(str(i)+"  "+str(hf_stage.x.position)+"   "+a_x[0:len(a_x)-1]+"   "+str(hf_stage.y.position)+"   "+a_y[0:len(a_y)-1]+"\n")
                #fout.write(str(i)+"  "+str(hf_stage.x.position)+"   "+str(maia.enc_axis_0_pos_mon.value.get())+"   "+str(hf_stage.y.position)+"   "+str(maia.enc_axis_1_pos_mon.value.get())+"\n")
        #fout.close()

    md = md or {}
    _md = {
        "detectors": ["maia"],
        "shape": [ynum, xnum],
        "motors": [m.name for m in [hf_stage.y, hf_stage.x]],
        "num_steps": xnum * ynum,
        "plan_args": dict(
            ystart=ystart,
            ystop=ystop,
            ynum=ynum,
            xstart=xstart,
            xstop=xstart+xsize,
            xnum=xnum,
            dwell=dwell,
            group=repr(group),
            md=md,
        ),
        "extents": [[ystart, ystop], [xstart, xstop]],
        "snaking": [False, True],
        "plan_name": "fly_maia",
    }
    _md.update(md)

    md = _md

    sample_md = md.get("sample", {})
    for k in ["info", "name", "owner", "serial", "type"]:
        v = sample_md.get(k, "")
        sig = getattr(maia, "meta_val_sample_{}_sp.value".format(k))
        yield from bps.mv(sig, str(v))

    scan_md = md.get("scan", {})
    for k in ["region", "info", "seq_num", "seq_total"]:
        v = scan_md.get(k, "")
        sig = getattr(maia, "meta_val_scan_{}_sp.value".format(k))
        yield from bps.mv(sig, str(v))

    if group is not None:
        yield from bps.mv(maia.blog_group_next_sp.value, group)

    #if xstart > xstop:
    #    xstop, xstart = xstart, xstop

    #if ystart > ystop:
    #    ystop, ystart = ystart, ystop

    # Pitch must match what raster driver uses for pitch ...
    #x_pitch = abs(xstop - xstart) / (xnum - 1)
    #y_pitch = abs(ystop - ystart) / (ynum - 1)

    # TODO compute this based on someting
    spd_x = xpitch / dwell
    print("speed_x=",spd_x)

    # Move to bottom LH corner of scan
    yield from bps.mv(hf_stage.x, xstart, hf_stage.y, ystart)

    x_val = yield from bps.rd(hf_stage.x)
    y_val = yield from bps.rd(hf_stage.y)
    # TODO, depends on actual device
    # Tell Hymod what we're doing
    yield from bps.mv(maia.enc_axis_0_pos_sp.value, x_val)
    yield from bps.mv(maia.enc_axis_1_pos_sp.value, y_val)

    yield from bps.mv(maia.x_pixel_dim_origin_sp.value, xstart)
    yield from bps.mv(maia.y_pixel_dim_origin_sp.value, ystart)

    yield from bps.mv(maia.x_pixel_dim_pitch_sp.value, xpitch)
    yield from bps.mv(maia.y_pixel_dim_pitch_sp.value, ypitch)

    yield from bps.mv(maia.x_pixel_dim_coord_extent_sp.value, xnum)
    yield from bps.mv(maia.y_pixel_dim_coord_extent_sp.value, ynum)
    yield from bps.mv(maia.scan_order_sp.value, "01")
    yield from bps.mv(maia.meta_val_scan_order_sp.value, "01")
    yield from bps.mv(maia.pixel_dwell.value, dwell)
    yield from bps.mv(maia.meta_val_scan_dwell.value, str(dwell))

    yield from bps.mv(maia.meta_val_beam_particle_sp.value, "photon")
    yield from bps.mv(
        maia.meta_val_beam_energy_sp.value, "{:.2f}".format(20_000)
        )
    #    yield from bps.mv(maia.maia_scan_info
    # need something to generate a filename here.
    #    yield from bps.mv(maia.blog_group_next_sp,datafile))
    # start blog in kickoff?

    @bpp.reset_positions_decorator([hf_stage.x.velocity])
    def _raster_plan():
        print("mark scan outline")
        yield from bps.mv(hf_stage.x, xstart)
        yield from bps.mv(hf_stage.y, ystart)
        yield from bps.sleep(1.0)
        yield from bps.mv(hf_stage.x, xstop)
        yield from bps.sleep(1.0)
        yield from bps.mv(hf_stage.y, ystop)
        yield from bps.sleep(1.0)
        yield from bps.mv(hf_stage.x, xstart)
        #yield from bps.sleep(1.0)
        yield from bps.mv(hf_stage.y, ystart)
        #input("Press enter if it's OK to continue")
        print("done outline")
        # open file to save positions
        #fout=open('/home/xf04bm/positions.dat','w')
	    # set the motors to the right speed
        yield from bps.mv(hf_stage.x.velocity, spd_x)
        print("set speed")
        yield from bps.mv(shutter, "Open")
#        yield from bps.sleep(1)
        start_uid = yield from bps.open_run(md)
        yield from bps.sleep(2)
        print("open run")
        yield from bps.mv(maia.meta_val_scan_crossref_sp.value, start_uid)
        # long int here.  consequneces of changing?
        #    yield from bps.mv(maia.scan_number_sp,start_uid)
        yield from bps.stage(maia)  # currently a no-op
        print("Stage maia")
        xstartnew=xstart-xpitch/2
        xstopnew=xstop+xpitch/2
        ystartnew=ystart #-ypitch/2
        ystopnew=ystop #+ypitch/2
        ynumnew=ynum+1
        #take up backlash
        yield from bps.mv(hf_stage.x, xstartnew-1.0)
        yield from bps.mv(hf_stage.x, xstartnew)
        yield from bps.mv(hf_stage.y, ystartnew-1.0)
        yield from bps.mv(hf_stage.y, ystartnew)
        print("Backlash removed")
        #yield from bps.sleep(1)
        yield from bps.kickoff(maia, wait=True)
        print("kickoff")
        yield from bps.checkpoint()
        print("checkpoint")
        #yield from bps.mv(hf_stage.x, xstart)
        #yield from bps.mv(hf_stage.y, ystart)
        yield from bps.sleep(2)
        # by row
        for i in range(0,ynumnew):
            y_pos=ystartnew+i*ypitch
            
            #yield from bps.checkpoint()
            # move to the row we want
            yield from bps.mv(hf_stage.y, y_pos)
            if i % 2:
                # for odd-rows move from stop to start
                yield from bps.mv(hf_stage.x, xstartnew)
            else:
                # for even-rows move from start to stop
                yield from bps.mv(hf_stage.x, xstopnew)
 
    def _cleanup_plan():
        # stop the maia ("I'll wait until you're done")
        yield from bps.complete(maia, wait=True)
        
        # return stage to scan origin
        yield from bps.mv(hf_stage.x, xstart-1.0)
        yield from bps.mv(hf_stage.x, xstart)
        yield from bps.mv(hf_stage.y, ystart-1.0)
        yield from bps.mv(hf_stage.y, ystart)
        # shut the shutter
        yield from bps.mv(shutter, "Close")
        yield from bps.sleep(2)
        # collect data from maia
        yield from bps.collect(maia)
        yield from bps.close_run()
        yield from bps.unstage(maia)
        #yield from bps.close_run()
        yield from bps.mv(maia.meta_val_scan_crossref_sp.value, "")
        for k in ["info", "name", "owner", "serial", "type"]:
            sig = getattr(maia, "meta_val_sample_{}_sp.value".format(k))
            yield from bps.mv(sig, "")

        for k in ["region", "info", "seq_num", "seq_total"]:
            sig = getattr(maia, "meta_val_scan_{}_sp.value".format(k))
            yield from bps.mv(sig, "")
        yield from bps.mv(maia.meta_val_beam_energy_sp.value, "")
        yield from bps.mv(maia.meta_val_scan_dwell.value, "")
        yield from bps.mv(maia.meta_val_scan_order_sp.value, "")
        yield from bps.sleep(2)

    return (yield from bpp.finalize_wrapper(_raster_plan(), _cleanup_plan()))


def fly_maia_finger_sync(
    ystart,
    ystop,
    ynum,
    xstart,
    xstop,
    xnum,
    dwell,
    *,
    group=None,
    md=None,
    shut_b,
    hf_stage,
):
#    shutter = shutter
    md = md or {}
    _md = {
        "detectors": ["maia"],
        "shape": [ynum, xnum],
        "motors": [m.name for m in [hf_stage.y, hf_stage.x]],
        "num_steps": xnum * ynum,
        "plan_args": dict(
            ystart=ystart,
            ystop=ystop,
            ynum=ynum,
            xstart=xstart,
            xstop=xstop,
            xnum=xnum,
            dwell=dwell,
            group=repr(group),
            md=md,
        ),
        "extents": [[ystart, ystop], [xstart, xstop]],
        "snaking": [False, True],
        "plan_name": "fly_maia",
    }
    _md.update(md)

    md = _md

    if xstart > xstop:
        xstop, xstart = xstart, xstop

    if ystart > ystop:
        ystop, ystart = ystart, ystop

    # Pitch must match what raster driver uses for pitch ...
    x_pitch = abs(xstop - xstart) / (xnum - 1)

    # TODO compute this based on someting
    spd_x = x_pitch / dwell

    yield from bps.mv(hf_stage.x, xstart, hf_stage.y, ystart)

    @bpp.reset_positions_decorator([hf_stage.x.velocity])
    def _raster_plan():

        # set the motors to the right speed
        yield from bps.mv(hf_stage.x.velocity, spd_x)

#        yield from bps.mv(shutter, "Open")
        yield from bps.open_run(md)

        yield from bps.checkpoint()
        # by row
        for i, y_pos in enumerate(np.linspace(ystart, ystop, ynum)):
            yield from bps.checkpoint()
            # move to the row we want
            yield from bps.mv(hf_stage.y, y_pos)
            if i % 2:
                # for odd-rows move from start to stop
                yield from bps.mv(hf_stage.x, xstop)
            else:
                # for even-rows move from stop to start
                yield from bps.mv(hf_stage.x, xstart)

    def _cleanup_plan():
        # shut the shutter
#        yield from bps.mv(shutter, "Close")
        yield from bps.mv(hf_stage.x, xstart)
        yield from bps.mv(hf_stage.y, ystart)
        yield from bps.close_run()

    return (yield from bpp.finalize_wrapper(_raster_plan(), _cleanup_plan()))
