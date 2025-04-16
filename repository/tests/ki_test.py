T_CYCLE = (2 * (8 + 64) + 2) * 8 * 10 ** (-9)  # Must match gateware Servo.t_cycle.
COEFF_SHIFT = 11
COEFF_WIDTH = 18


B_NORM = 1 << COEFF_SHIFT + 1
A_NORM = 1 << COEFF_SHIFT
COEFF_MAX = 1 << COEFF_WIDTH - 1

g = 0.0
kp = 0.0
ki = -300.0

kp *= B_NORM
if ki == 0.0:
    # pure P
    a1 = 0
    b1 = 0
    b0 = int(round(kp))
else:
    # I or PI
    ki *= B_NORM * T_CYCLE / 2.0
    if g == 0.0:
        c = 1.0
        a1 = A_NORM
    else:
        c = 1.0 / (1.0 + ki / (g * B_NORM))
        a1 = int(round((2.0 * c - 1.0) * A_NORM))
    b0 = int(round(kp + ki * c))
    b1 = int(round(kp + (ki - 2.0 * kp) * c))
    if b1 == -b0:
        print(ki)
        raise ValueError("low integrator gain and/or gain limit")
    else:
        print("ok")

if b0 >= COEFF_MAX or b0 < -COEFF_MAX or b1 >= COEFF_MAX or b1 < -COEFF_MAX:
    raise ValueError("high gains")
