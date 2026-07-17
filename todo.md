# branch roadmap

1. Calibrations need to show their output as they optimize

2. Calibrations code needs to be fully portable. I should be able to call fix_state() from a kernel in an ExpFragment and have it work. Note that it's fine to use RPCs where necessairy. But recompilations are banned.
