# Offer to route gitlab.com git traffic over SSH — with the user's consent.
#
# Why this exists: the lab's HTTPS git credential helper (oauth device-flow /
# gopass) is unreliable, so fetching gitlab dependencies over HTTPS frequently
# fails. SSH access to gitlab.com is reliable. The fix is an http(s) -> ssh
# `url.insteadOf` rewrite. It has to live in the user's *global* git config to
# take effect for nix/poetry dependency fetches (those read global config, not a
# repo-local one) — so we must not write it without asking.
#
# Behaviour, on entering an INTERACTIVE dev shell, only if an SSH key is present
# AND authenticates to GitLab:
#   - already configured globally, or previously declined/suggested -> silent.
#   - global git config is a symlink (managed by home-manager/nix) -> we can't
#     write it, so just print a one-off suggestion to add it declaratively.
#   - otherwise -> offer a [Y/n] prompt (default yes) to add it to ~/.gitconfig. "no" is
#     remembered so we don't nag.
#
# CI safety: CI has no SSH key (only an HTTPS token) and runs non-interactively,
# so it never prompts and never changes anything — HTTPS keeps working.
#
# Sourced from the devShell shellHook (flake.nix). Safe to source: runs in a
# function, never calls `exit` or `set -e`, and only prompts interactively.

_icl_gitlab_ssh_rewrite() {
	local ssh_base="ssh://git@gitlab.com/"
	local gc="$HOME/.gitconfig"
	local xdg="${XDG_CONFIG_HOME:-$HOME/.config}/git/config"
	local state_dir="${XDG_STATE_HOME:-$HOME/.local/state}/icl_experiments"
	local declined="$state_dir/gitlab-ssh-rewrite.declined"
	local suggested="$state_dir/gitlab-ssh-rewrite.nix-suggested"

	_icl_has_rewrite() {
		git config --file "$1" --get-all "url.${ssh_base}.insteadOf" \
			2>/dev/null | grep -q .
	}

	# Already configured in either global config file? -> nothing to do.
	if _icl_has_rewrite "$gc" || _icl_has_rewrite "$xdg"; then
		unset -f _icl_has_rewrite
		return 0
	fi
	unset -f _icl_has_rewrite

	# Previously declined, or already suggested to a nix user? -> don't nag.
	[ -f "$declined" ] && return 0
	[ -f "$suggested" ] && return 0

	# Only act in an interactive shell. `nix develop -c ...`, CI, and the
	# tmux-launched ARTIQ stack all run non-interactively and must never block.
	case "$-" in
		*i*) ;;
		*) return 0 ;;
	esac

	# Check 1: is an SSH key available at all? (agent identity, or a key file
	# ssh would offer for gitlab.com). Cheap; lets keyless setups bail early.
	local have_key=1 _k idfile
	if ssh-add -l >/dev/null 2>&1; then
		have_key=0
	else
		while read -r _k idfile; do
			[ "$_k" = "identityfile" ] || continue
			idfile="${idfile/#\~/$HOME}"
			[ -e "$idfile" ] && { have_key=0; break; }
		done < <(ssh -G git@gitlab.com 2>/dev/null)
	fi
	[ "$have_key" -eq 0 ] || return 0

	# Check 2: does that key actually authenticate to GitLab?
	ssh -T -o BatchMode=yes -o ConnectTimeout=5 \
		-o StrictHostKeyChecking=accept-new git@gitlab.com 2>&1 \
		| grep -qi 'Welcome to GitLab' || return 0

	# If the global git config is a symlink it's almost certainly managed by
	# home-manager/nix and read-only — don't write it. Suggest the declarative
	# change instead, just once.
	if [ -L "$gc" ] || [ -L "$xdg" ]; then
		echo
		echo "icl_experiments: your SSH key works with GitLab, and the lab's HTTPS"
		echo "git credential helper is flaky (it breaks nix/poetry fetches). Your"
		echo "global git config looks managed (symlinked), so I won't touch it."
		echo "If you use home-manager, consider adding to programs.git:"
		echo
		echo '    programs.git.extraConfig.url."ssh://git@gitlab.com/".insteadOf ='
		echo '      [ "https://gitlab.com/" "http://git@gitlab.com/" "http://gitlab.com/" ];'
		echo
		mkdir -p "$state_dir" && : > "$suggested"
		echo "(Routes gitlab.com over SSH. I won't mention this again — reset: rm $suggested)"
		return 0
	fi

	# Writable global config -> ask for consent, then install to ~/.gitconfig.
	echo
	echo "icl_experiments: your SSH key works with GitLab, but the lab's HTTPS git"
	echo "credential helper is flaky, which breaks nix/poetry dependency fetches."
	echo "I can fix that by routing gitlab.com over SSH (an 'insteadOf' rewrite added"
	echo "to your ~/.gitconfig). CI is unaffected — it has no SSH key."
	# Default to yes (Enter installs) to nudge people onto the working setup.
	local ans
	if ! read -r -p "Add the gitlab.com -> SSH rewrite to ~/.gitconfig? [Y/n] " ans; then
		return 0 # EOF / no real input -> do nothing this session
	fi
	case "$ans" in
		n | N | no | No | NO)
			mkdir -p "$state_dir" && : > "$declined"
			echo "OK, I won't ask again. (Change your mind: rm $declined)"
			;;
		*)
			# Default (empty) and any affirmative -> install.
			local from
			for from in "http://git@gitlab.com/" "https://gitlab.com/" "http://gitlab.com/"; do
				git config --file "$gc" --add "url.${ssh_base}.insteadOf" "$from"
			done
			echo "Done — gitlab.com now routes over SSH. (Undo: edit $gc)"
			;;
	esac
}

_icl_gitlab_ssh_rewrite
unset -f _icl_gitlab_ssh_rewrite
