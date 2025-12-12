The script in this directory are for running a minimal dashboard on Windows. Set
it up by running "windows_support\init_environment.bat" from the root
directory of this repository. Then, run
"windows_support\run_dashboard.bat" or
"windows_support\run_wand.bat".

If requirements.txt needs to be updated, manually install the packages that you
need to get it working and then use `pip freeze > requirements.txt` to record
the set that worked. This might get out of sync with the Nix setup. Blame
Microsoft and lobby for free-and-open-source software.
