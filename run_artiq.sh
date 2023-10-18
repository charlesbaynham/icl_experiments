# You can use this file to save your artiq launch command, to save wear-and-tear
# on your keyboard. Alternatively, just run the command below to launch an ARTIQ
# session.
#
# You can also do "nix run .#full_stack --help" to see more options than just the
# default.

# FIXME: Hack to get around the full_stack app not having the right environment
nix develop -c nix run .#full_stack
