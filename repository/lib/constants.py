"""Constants

This module is simply used to store static constants that can be referred to
by other parts of the code. This is the only file where magic numbers should
be stored, so you should never e.g. store an AOM's optimal attenuation as a
default setting in a build() method somewhere: it should be here.
"""


BLUE_INJECTION_AOM_ATTENUATION = 20.0
BLUE_INJECTION_AOM_DEFAULT_FREQUENCY = 200e6
