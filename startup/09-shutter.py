from nslsii.devices import TwoButtonShutter


shutter = TwoButtonShutter("XF:04BMB-PPS{Sh:A}", name="shutter")
shutter.MAX_ATTEMPTS = 20
