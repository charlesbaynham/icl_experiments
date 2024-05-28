"""
Relock the Toptica 689nm ECDL to the cavity

This is a test script which will be incorporated into a QButler Calibration
later.

The plan based on manual fiddling is:

1. Set 689nm ECDL to:
    FALC enabled Unlim disabled Piezo scan disabled

2. Use WAND to steer it back to 0 MHz offset (don't mess with the setpoint -
   SwitchIsotope should have made sure we're set correctly for the current EOM
   sidebands)

3. Set piezo scan enabled (10 Hz, 0.05V)

4. Set Unlim enabled

5. Set scan disabled

6 Check transmission

7. If high, done. If low, repeat from 2.
"""
